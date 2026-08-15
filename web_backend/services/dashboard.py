"""工作台概览与个人任务看板聚合服务。

本模块为所有角色提供启动数据，但任务查询严格按当前 user_id 隔离；待审核账号数等
管理指标只作为聚合值下发，前端按角色决定是否展示，隐藏导航不能替代后端鉴权。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable


@dataclass(frozen=True)
class DashboardDependencies:
    """工作台聚合所需的运行时依赖。"""

    # 数据库与时间依赖由组合根注入；时间统一用业务时区口径。
    db_lock: Any
    db: Callable[[], Any]
    now_iso: Callable[[], str]
    business_today: Callable[[], Any]
    business_date: Callable[[str], str]
    is_review_pending: Callable[[Any], bool]
    feature_key_for_action: Callable[[object], str]
    # 功能目录来自配置；任务文件 JSON 使用兼容解析器，脏项不会阻断工作台。
    features: list[dict[str, object]]
    json_list: Callable[..., list[Any]]
    user_public: Callable[[Any], dict[str, object]]
    notification_public: Callable[[Any, str], dict[str, object]]


def overview(handler: Any, deps: DashboardDependencies) -> None:
    """返回工作台启动所需的账号、功能目录和轻量统计。"""
    user = handler.require_user()
    with deps.db_lock, deps.db() as connection:
        pending = connection.execute(
            "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'",  # 全局待审核数，所有角色都会收到但前端按角色展示。
        ).fetchone()["n"]
        total_users = connection.execute(
            "SELECT COUNT(*) AS n FROM users WHERE status = 'approved'",
        ).fetchone()["n"]
        output_jobs = connection.execute(
            "SELECT COUNT(*) AS n FROM web_jobs "
            "WHERE user_id = ? AND status = 'completed'",
            (user["id"],),
        ).fetchone()["n"]
    handler.send_json({
        "user": deps.user_public(user),
        "features": deps.features,
        "metrics": {
            "pending_users": pending,
            "approved_users": total_users,
            "output_jobs": output_jobs,
        },
    })


def _status_breakdown(job_rows: list[Any], status_rows: list[Any], deps: DashboardDependencies) -> dict[str, int]:
    """把等待人工复核的完成任务单独归入复核状态。"""
    breakdown = {str(row["status"]): int(row["n"]) for row in status_rows}  # 先保留数据库原始状态，再重分类复核任务。
    review_count = sum(1 for row in job_rows if deps.is_review_pending(row))
    if review_count:
        breakdown["completed"] = max(0, breakdown.get("completed", 0) - review_count)  # 分析完成不等于业务最终完成，需从 completed 中扣除。
        breakdown["review"] = review_count
    return breakdown


def _trend_and_features(
    job_rows: list[Any],
    deps: DashboardDependencies,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """汇总最近七个业务日的任务趋势和高频业务模块。

    趋势按业务时区转换创建时间，并把等待复核的分析完成任务排除在最终完成数之外；
    功能使用频率则统计全部任务动作，再把普通动作和 Web 复核动作归一到同一功能键。
    返回结果已按图表和排行榜需要的稳定顺序整理。
    """
    today = deps.business_today()
    trend = {
        (today - timedelta(days=offset)).isoformat(): {
            "total": 0,
            "completed": 0,
            "failed": 0,
        }
        for offset in range(6, -1, -1)
    }  # 预先创建连续七天，即使某天没有任务也能让图表显示零值而非断点。
    feature_counts: dict[str, int] = {}
    for row in job_rows:
        created = deps.business_date(row["created_at"])  # UTC 存储时间转业务日期，避免凌晨任务落入前一天。
        if created in trend:
            trend[created]["total"] += 1
            if row["status"] == "completed" and not deps.is_review_pending(row):
                trend[created]["completed"] += 1
            elif row["status"] == "failed":
                trend[created]["failed"] += 1
        feature_key = deps.feature_key_for_action(row["action"])  # 普通动作与 web.* 复核动作归并到同一业务模块。
        feature_counts[feature_key] = feature_counts.get(feature_key, 0) + 1

    feature_titles = {
        str(item["key"]): str(item["title"])
        for item in deps.features
    }
    feature_usage = [
        {"key": key, "title": feature_titles.get(key, key), "count": count}
        for key, count in sorted(
            feature_counts.items(),
            key=lambda pair: (-pair[1], pair[0]),
        )[:6]  # 只展示使用频率最高的六项，避免卡片被长尾功能挤满。
    ]
    return (
        [{"date": day, **values} for day, values in trend.items()],
        feature_usage,
    )


def _recent_content(
    job_rows: list[Any],
    deps: DashboardDependencies,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """从时间倒序任务中整理最近任务卡片和最近六个结果文件。

    任务卡片最多八条；结果文件只取已完成任务，每个任务最多贡献五项，最终全局最多
    六项。文件 JSON 通过兼容解析器读取，历史脏项被跳过而不会阻断工作台响应。
    """
    recent_jobs = [{
        "id": row["id"],
        "action": row["action"],
        "title": row["title"],
        "status": row["status"],
        "progress": row["progress"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "review_pending": deps.is_review_pending(row),
    } for row in job_rows[:8]]

    recent_files: list[dict[str, object]] = []
    for row in job_rows:  # job_rows 已按时间倒序，首次收集到的文件自然是最近结果。
        if row["status"] != "completed":
            continue
        for index, item in enumerate(deps.json_list(row["files"])[:5]):  # 单任务最多贡献五个文件，避免某个大任务垄断列表。
            if not isinstance(item, dict):
                continue
            recent_files.append({
                "name": item.get("name", "未命名文件"),
                "size": item.get("size", 0),
                "url": f"/api/jobs/{row['id']}/files/{index}",
                "job_id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
            })
            if len(recent_files) >= 6:  # 达到界面容量后立即结束双层循环，减少无意义 JSON 解析。
                return recent_jobs, recent_files
    return recent_jobs, recent_files


def dashboard(handler: Any, deps: DashboardDependencies) -> None:
    """返回当前账号的工作台指标、趋势、最近内容和通知快照。

    任务查询始终绑定当前账号；账号总数是管理概览指标，但前端按角色决定是否展示。
    公告和私信在同一 SQL 快照中对齐字段并合并，后续所有派生指标都使用同一批查询结果，
    避免一个响应内部的总数、趋势和最近任务口径互相漂移。
    """
    user = handler.require_user()
    generated_at = deps.now_iso()  # 查询公告有效期和响应时间戳共用同一时刻，保证快照自洽。
    with deps.db_lock, deps.db() as connection:
        job_rows = connection.execute(
            "SELECT * FROM web_jobs WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT 500",  # 趋势只需近期样本，限制上限避免历史任务无限拖慢工作台。
            (user["id"],),
        ).fetchall()
        status_rows = connection.execute(
            "SELECT status, COUNT(*) AS n FROM web_jobs "
            "WHERE user_id = ? GROUP BY status",
            (user["id"],),
        ).fetchall()
        pending_users = connection.execute(
            "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'",  # 全局待审核数，所有角色都会收到但前端按角色展示。
        ).fetchone()["n"]
        approved_users = connection.execute(
            "SELECT COUNT(*) AS n FROM users WHERE status = 'approved'",
        ).fetchone()["n"]
        notification_rows = connection.execute(
            "SELECT a.id, a.title, a.content, a.created_at, a.expires_at, "
            "a.active, 'announcement' AS kind, r.read_at "
            "FROM announcements a LEFT JOIN announcement_reads r "
            "ON r.announcement_id = a.id AND r.user_id = ? "
            "WHERE a.active = 1 AND "
            "(a.expires_at IS NULL OR a.expires_at = '' OR a.expires_at > ?) "
            "UNION ALL "  # 公告和私信字段对齐后一次查询返回，避免两次查询间出现时间竞态。
            "SELECT id, title, content, created_at, NULL AS expires_at, "
            "1 AS active, 'message' AS kind, read_at "
            "FROM messages WHERE recipient_user_id = ? "
            "ORDER BY created_at DESC LIMIT 12",
            (user["id"], generated_at, user["id"]),
        ).fetchall()

    status_breakdown = _status_breakdown(job_rows, status_rows, deps)
    trend, feature_usage = _trend_and_features(job_rows, deps)
    recent_jobs, recent_files = _recent_content(job_rows, deps)
    handler.send_json({
        "user": deps.user_public(user),
        "generated_at": generated_at,
        "metrics": {
            "pending_users": int(pending_users),
            "approved_users": int(approved_users),
            "total_jobs": sum(status_breakdown.values()),
            "completed_jobs": status_breakdown.get("completed", 0),
            "running_jobs": (
                status_breakdown.get("running", 0)
                + status_breakdown.get("queued", 0)
                + status_breakdown.get("review", 0)
            ),
            "failed_jobs": status_breakdown.get("failed", 0),
        },
        "status_breakdown": status_breakdown,
        "trend": trend,
        "feature_usage": feature_usage,
        "recent_jobs": recent_jobs,
        "recent_files": recent_files,
        "notifications": [
            deps.notification_public(row, str(row["kind"]))
            for row in notification_rows
        ],
        "unread_count": sum(1 for row in notification_rows if not row["read_at"]),
    })
