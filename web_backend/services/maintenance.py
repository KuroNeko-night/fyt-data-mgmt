"""Web 服务的存储维护和后台周期清理。

维护服务通过依赖对象访问数据库、路径和业务回调，避免反向依赖启动入口。
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class MaintenanceDependencies:
    """存储维护所需的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    data_root: Path
    storage_lock: Any
    output_retention_count: int
    trash_retention_days: int
    workshop_draft_retention_hours: int
    tree_size: Callable[[Path], int]
    is_review_pending: Callable[[Any], bool]
    workshop_issue_dir: Callable[[int, str], Path]
    now_iso: Callable[[], str]
    merge_ready_batches: Callable[[int], dict[str, Any]]
    merge_environment: Callable[[], Any]


def move_job_to_trash(
    deps: MaintenanceDependencies,
    job_id: str,
    deleted_by: int | None = None,
    audit_action: str | None = None,
) -> str | None:
    """把任务记录、结果版本和所属输出目录一致地移入回收站。

    文件系统与 SQLite 无法共享真正的跨资源事务，因此采用可补偿顺序：先读取完整记录，
    再移动目录，随后删除任务并写入恢复元数据；数据库阶段失败时把目录移回原位。返回
    ``None`` 表示任务在操作前已不存在，调用方可据此保持删除接口的幂等语义。
    """
    with deps.storage_lock:  # 文件移动和数据库记录必须串行，防止维护线程与管理员删除同一任务。
        with deps.db_lock, deps.db() as connection:
            row = connection.execute("SELECT * FROM web_jobs WHERE id = ?", (job_id,)).fetchone()
            version_rows = connection.execute(
                "SELECT job_id, user_id, version, result, files, status, created_at "
                "FROM web_job_versions WHERE job_id = ? ORDER BY version",
                (job_id,),
            ).fetchall()
        if row is None:
            return None

        trash_id = uuid.uuid4().hex  # 回收站编号与原任务编号解耦，允许同一任务恢复后再次删除。
        original = deps.data_root / "users" / str(row["user_id"]) / "jobs" / job_id
        relative = original.relative_to(deps.data_root).as_posix()  # 只保存相对路径，部署目录变化后仍可恢复。
        payload = deps.data_root / "trash" / trash_id / "payload"
        size = deps.tree_size(original)  # 移动前统计大小，回收站目录本身不参与原始数据计量。
        if original.exists():
            payload.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(original), str(payload))  # 同卷移动通常为原子重命名，大输出无需复制两份。
        try:
            with deps.db_lock, deps.db() as connection:
                changed = connection.execute("DELETE FROM web_jobs WHERE id = ?", (job_id,)).rowcount  # 删除条件再次确认，捕获并发状态变化。
                if not changed:
                    raise RuntimeError("任务记录已发生变化")
                connection.execute(
                    "INSERT INTO trash_items(id, kind, label, record_json, original_path, size, deleted_by, deleted_at) "
                    "VALUES (?, 'job', ?, ?, ?, ?, ?, ?)",
                    (
                        trash_id,
                        row["title"],
                        json.dumps(
                            {
                                "job": dict(row),
                                "versions": [dict(version) for version in version_rows],
                            },
                            ensure_ascii=False,
                        ),
                        relative,
                        size,
                        deleted_by,
                        deps.now_iso(),
                    ),
                )
                if audit_action:
                    connection.execute(
                        "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                        (deleted_by, audit_action, deps.now_iso()),
                    )
        except Exception:  # 数据库写入失败时把已移动目录放回原位，维持文件与记录一致。
            if payload.exists() and not original.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(payload), str(original))
            raise
        return trash_id

def enforce_output_retention(
    deps: MaintenanceDependencies,
    limit: int | None = None,
    move_job: Callable[..., str | None] | None = None,
) -> int:
    """按账号归档超出保留数量的已完成输出任务。

    额度只计算实际含结果文件且不等待人工复核的任务；普通完成记录、失败记录和分析阶段
    结果不会错误占用或被提前归档。候选任务逐个进入统一回收站流程，单次统计返回成功
    移动数量，原始任务按更新时间和稳定存储顺序确定新旧。
    """
    keep_count = max(1, int(deps.output_retention_count if limit is None else limit))  # 即使配置错误也至少保留一个可下载结果。
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT rowid AS storage_order, * FROM web_jobs "
            "WHERE status = 'completed' "
            "ORDER BY user_id, updated_at DESC, created_at DESC, storage_order DESC"  # rowid 作为同秒记录的稳定兜底顺序。
        ).fetchall()

    seen_by_user: dict[int, int] = {}
    candidates: list[str] = []
    for row in rows:
        if deps.is_review_pending(row):  # 待人工确认任务不能自动归档，否则复核页面会失去依据。
            continue
        try:
            files = json.loads(row["files"] or "[]")
        except (TypeError, json.JSONDecodeError):
            files = []
        if not isinstance(files, list) or not files:  # 无输出文件的完成任务不占“最近 20 次输出”额度。
            continue
        user_id = int(row["user_id"])
        seen_by_user[user_id] = seen_by_user.get(user_id, 0) + 1
        if seen_by_user[user_id] > keep_count:
            candidates.append(str(row["id"]))

    moved = 0
    for job_id in candidates:
        if (move_job or (lambda job_id, **kwargs: move_job_to_trash(deps, job_id, **kwargs)))(job_id, audit_action=f"auto_retention_job:{job_id}"):
            moved += 1
    return moved

def purge_expired_trash(
    deps: MaintenanceDependencies,
    retention_days: int | None = None,
    current_time: datetime | None = None,
) -> tuple[int, int]:
    """彻底删除超过保留期的回收站数据，失败项目留待下次重试。

    截止时间统一换算为 UTC ISO 文本，与数据库存储格式一致。每项先删除磁盘载荷，再按
    编号和截止时间双重条件移除索引；目录占用等文件错误只增加失败计数，不删除数据库
    记录，从而保留下次维护重试所需的定位信息。
    """
    now = current_time or datetime.now(timezone.utc)  # 测试可注入固定时间，生产使用 UTC 当前时间。
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)  # 无时区时间按 UTC 解释，避免与数据库 ISO 时间直接比较出错。
    cutoff = (now.astimezone(timezone.utc) - timedelta(days=max(1, int(deps.trash_retention_days if retention_days is None else retention_days)))).isoformat(
        timespec="seconds"
    )
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT id FROM trash_items WHERE deleted_at <= ? ORDER BY deleted_at",
            (cutoff,),
        ).fetchall()

    purged = 0
    failed = 0
    with deps.storage_lock:
        for row in rows:
            trash_id = str(row["id"])
            try:  # 先删除磁盘内容，成功后再删索引；失败项保留记录供下一周期重试。
                shutil.rmtree(deps.data_root / "trash" / trash_id, ignore_errors=False)
            except FileNotFoundError:  # 目录已被人工清理时仍允许移除陈旧数据库记录。
                pass
            except OSError:
                failed += 1
                continue
            with deps.db_lock, deps.db() as connection:
                purged += connection.execute(
                    "DELETE FROM trash_items WHERE id = ? AND deleted_at <= ?",
                    (trash_id, cutoff),
                ).rowcount
        if purged:
            with deps.db_lock, deps.db() as connection:
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (NULL, ?, ?)",
                    (f"auto_purge_trash:{purged}", deps.now_iso()),
                )
    return purged, failed

def cleanup_stale_workshop_drafts(
    deps: MaintenanceDependencies,
    retention_hours: int | None = None,
    current_time: datetime | None = None,
) -> int:
    """删除长期未发布的车间问题草稿及其临时图片。

    清理对象严格限制为过期草稿，已发布问题不参与。删除图片目录后，SQL 再次检查状态
    和更新时间，避免用户恰在清理期间发布或编辑草稿时记录被误删；文件删除失败则整条
    草稿留待下一周期处理。
    """
    now = current_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = (now.astimezone(timezone.utc) - timedelta(hours=max(1, int(deps.workshop_draft_retention_hours if retention_hours is None else retention_hours)))).isoformat(
        timespec="seconds"
    )
    with deps.storage_lock:  # 发布、图片上传和草稿清理不能同时操作同一问题目录。
        with deps.db_lock, deps.db() as connection:
            rows = connection.execute(
                "SELECT id, user_id FROM workshop_issues "
                "WHERE status = 'draft' AND updated_at <= ? ORDER BY updated_at",
                (cutoff,),
            ).fetchall()
        removed = 0
        for row in rows:
            folder = deps.workshop_issue_dir(int(row["user_id"]), str(row["id"]))
            try:
                shutil.rmtree(folder, ignore_errors=False)
            except FileNotFoundError:
                pass
            except OSError:
                continue
            with deps.db_lock, deps.db() as connection:
                removed += connection.execute(  # SQL 再次校验草稿状态和截止时间，发布中的记录不会被误删。
                    "DELETE FROM workshop_issues WHERE id = ? AND status = 'draft' AND updated_at <= ?",
                    (row["id"], cutoff),
                ).rowcount
        if removed:
            with deps.db_lock, deps.db() as connection:
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (NULL, ?, ?)",
                    (f"auto_purge_workshop_drafts:{removed}", deps.now_iso()),
                )
    return removed

def merge_confirmed_master_data(deps: MaintenanceDependencies, limit: int = 5) -> dict[str, int]:
    """定期合并管理员已确认的主数据批次，并记录系统审计。"""
    with deps.merge_environment():  # 主数据路径通过临时环境切到 Web 数据根，避免污染桌面端本地档案。
        report = deps.merge_ready_batches(limit=limit)
    merged_ids = [str(value) for value in report.get("merged", [])]
    if merged_ids:
        with deps.db_lock, deps.db() as connection:
            for batch_id in merged_ids:
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (NULL, ?, ?)",
                    (f"master_data_auto_merge:{batch_id}", deps.now_iso()),
                )
    return {
        "merged_master_data_batches": len(merged_ids),
        "master_data_review_required": len(report.get("review_required", [])),
        "master_data_merge_failures": len(report.get("failed", [])),
    }

def run_storage_maintenance(
    deps: MaintenanceDependencies,
    output_limit: int | None = None,
    trash_retention_days: int | None = None,
    current_time: datetime | None = None,
) -> dict[str, int]:
    """按固定顺序执行一次完整存储维护并汇总各子任务结果。

    先清理过期回收站释放空间，再把超额输出移入回收站；随后清理未发布草稿并尝试合并
    已确认主数据。各子步骤保持独立统计，调度器可在日志中区分成功数量、重试数量和需
    人工复核的主数据批次。
    """
    purged, failed = purge_expired_trash(deps, trash_retention_days, current_time)  # 先清理旧回收站，为后续新归档释放空间。
    moved = enforce_output_retention(deps, output_limit)
    drafts = cleanup_stale_workshop_drafts(deps, current_time=current_time)
    master_data = merge_confirmed_master_data(deps)
    return {
        "moved_outputs": moved,
        "purged_trash": purged,
        "trash_cleanup_failures": failed,
        "purged_workshop_drafts": drafts,
        **master_data,
    }
