"""报表中心与周期报表服务。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse

from web_backend.errors import ApiError
from web_backend.config import BUSINESS_TZ


# 报表时间范围参数与中文标题的映射；"week" 是 "7d" 的历史别名，统一显示为“近7天”。
REPORT_RANGE_LABELS = {
    "7d": "近7天",
    "30d": "近30天",
    "month": "本月",
    "all": "全部",
    "week": "近7天",
}


@dataclass(frozen=True)
class ReportDependencies:
    """报表生成、下载与周期任务所需的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    data_root: Path
    now_iso: Callable[[], str]
    json_value: Callable[..., Any]
    collect_result_files: Callable[[object], list[dict[str, object]]]
    feature_key_for_action: Callable[[object], str]
    path_is_within: Callable[[Path, Path], bool]
    report_core: Any


def build_web_report_file(
    deps: ReportDependencies,
    range_key: str,
    user_id: int | None,
    scope_all: bool,
) -> Path:
    """按时间范围与账号范围生成业务任务报表，并返回服务器文件路径。

    时间边界由 Core 统一计算；个人报表在 SQL 中绑定账号，全量报表仅由上层管理员入口
    调用。每条任务只投影功能、状态、开始时间和结果文件数量，不把错误堆栈或绝对路径
    写进报表。生成文件按个人和全量范围分目录保存，下载接口会再次校验目录边界。
    """
    if range_key not in REPORT_RANGE_LABELS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "报表范围参数无效")
    start = deps.report_core.range_start(range_key)  # 时间范围算法由 Core 统一，Web 不重复定义“本月”等边界。
    since = start.isoformat()  # 数据库 created_at 使用 ISO 文本，可在统一 UTC 格式下直接按字典序筛选。
    with deps.db_lock, deps.db() as connection:
        if scope_all:
            rows = connection.execute(
                "SELECT action, title, status, created_at, result FROM web_jobs "
                "WHERE created_at >= ? ORDER BY created_at",
                (since,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT action, title, status, created_at, result FROM web_jobs "
                "WHERE user_id = ? AND created_at >= ? ORDER BY created_at",
                (user_id, since),
            ).fetchall()

    items = []
    for row in rows:
        result = deps.json_value(row["result"], None)  # 历史损坏结果按空值处理，报表仍可统计任务本身。
        items.append({
            "feature": deps.feature_key_for_action(row["action"]),
            "title": str(row["title"]),
            "status": str(row["status"]),
            "started_at": str(row["created_at"]),
            "files": len(deps.collect_result_files(result)),  # 递归结果提取与任务下载共用规则，目录输出也会展开计数。
        })
    if not items:
        raise ApiError(HTTPStatus.NOT_FOUND, "所选时间范围内没有任务记录")

    scope = "all" if scope_all else "self"
    root = deps.data_root / "reports" / scope  # 全量与个人报表分目录，下载时仍统一限制在 reports 根内。
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    range_label = REPORT_RANGE_LABELS[range_key]
    target = root / f"业务报表_{range_label}_{stamp}.xlsx"
    deps.report_core.build_report(items, str(target), range_label)
    return target


def _read_report_state(path: Path, field: str) -> str:
    """读取周期报表状态；损坏或不存在时按尚未执行处理。"""
    try:
        if not path.is_file():
            return ""
        value = json.loads(path.read_text(encoding="utf-8"))  # 状态文件只作幂等提示，损坏时安全地重新执行。
    except (OSError, ValueError, TypeError):
        return ""
    return str(value.get(field) or "") if isinstance(value, dict) else ""


def _write_report_state(path: Path, field: str, value: str) -> None:
    """原子写入周期报表状态，避免中断留下半份 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")  # 先写同目录临时文件，确保 os.replace 保持同文件系统原子性。
    temporary.write_text(
        json.dumps({field: value}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)  # 进程中断时最多留下 .tmp，不会破坏上一份有效状态。


def _notify_report_ready(
    deps: ReportDependencies,
    title: str,
    content: str,
) -> int:
    """向所有已审核账号发送报表生成通知，返回接收账号数。"""
    with deps.db_lock, deps.db() as connection:
        recipients = connection.execute(  # 只通知已审核账号，暂停或待审核账号不会收到系统消息。
            "SELECT id FROM users WHERE status = 'approved'",
        ).fetchall()
        created_at = deps.now_iso()
        for row in recipients:
            connection.execute(
                "INSERT INTO messages(recipient_user_id, title, content, created_by, created_at) "
                "VALUES (?, ?, ?, NULL, ?)",
                (row["id"], title, content, created_at),
            )
    return len(recipients)


def _auto_report_if_due(
    deps: ReportDependencies,
    *,
    due: bool,
    state_name: str,
    state_field: str,
    state_value: str,
    range_key: str,
    notification_title: str,
    notification_content: str,
    result_label: str,
) -> str:
    """执行一次具备幂等状态记录的周期报表任务。

    调用方决定本周期是否到期以及状态键；只有报表生成和全员通知都成功后才原子记录
    本周期已完成。范围内没有任务时保持未执行状态，允许同一周期后续维护再次尝试。
    空字符串表示本次无需向维护日志输出内容。
    """
    if not due:
        return ""
    state_path = deps.data_root / state_name
    if _read_report_state(state_path, state_field) == state_value:  # 同一周/月已记录成功时直接返回，保证任务幂等。
        return ""
    try:
        target = build_web_report_file(deps, range_key, None, True)
    except ApiError:  # 没有任务数据不是维护故障，不记录状态，后续周期仍可重试。
        return ""
    recipient_count = _notify_report_ready(
        deps, notification_title, notification_content,
    )
    _write_report_state(state_path, state_field, state_value)  # 报表和通知均成功后才标记完成。
    return f"已生成{result_label} {target.name}，并通知 {recipient_count} 个账号"


def auto_weekly_report_if_due(deps: ReportDependencies) -> str:
    """每周一自动生成全量周报，同一周只执行一次。"""
    today = datetime.now(BUSINESS_TZ)  # 按业务时区判“今天”，避免服务器本地时区与业务时区不一致时错日触发。
    return _auto_report_if_due(
        deps,
        due=today.weekday() == 0,
        state_name="auto_weekly_report_state.json",
        state_field="last_weekly",
        state_value=today.strftime("%Y%m%d"),
        range_key="week",
        notification_title="本周业务报表已生成",
        notification_content="近 7 天业务报表已生成，可在侧栏「报表中心」下载查看。",
        result_label="周报",
    )


def auto_monthly_report_if_due(deps: ReportDependencies) -> str:
    """每月一号自动生成全量月报，同一月份只执行一次。"""
    today = datetime.now(BUSINESS_TZ)  # 按业务时区判“今天”，避免服务器本地时区与业务时区不一致时错日触发。
    return _auto_report_if_due(
        deps,
        due=today.day == 1,
        state_name="auto_monthly_report_state.json",
        state_field="last_monthly",
        state_value=today.strftime("%Y%m"),
        range_key="month",
        notification_title="上月业务报表已生成",
        notification_content="上月业务报表已生成，可在侧栏「报表中心」下载查看。",
        result_label="月报",
    )


def build_report_endpoint(handler: Any, deps: ReportDependencies) -> None:
    """按请求范围生成业务报表并返回受控下载地址。"""
    user = handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    range_key = str((query.get("range") or ["30d"])[0])
    scope_all = str((query.get("scope") or [""])[0]) == "all"
    if scope_all and user["role"] != "admin":
        raise ApiError(HTTPStatus.FORBIDDEN, "仅管理员可以查看全量报表")
    target = build_web_report_file(deps, range_key, int(user["id"]), scope_all)
    relative = target.relative_to(deps.data_root).as_posix()  # 返回相对路径而非服务器绝对路径，避免泄露部署结构。
    handler.send_json({
        "url": f"/api/reports/download?path={quote(relative)}",
        "name": target.name,
    })


def list_report_files(handler: Any, deps: ReportDependencies) -> None:
    """列出报表中心可下载的历史 Excel 文件。

    自动周报/月报和管理员手动生成的全量报表都保存在 ``reports/all``，当前账号范围的
    手动报表保存在 ``reports/self``。这里只返回文件名、大小、时间和受控下载地址，绝不
    暴露服务器绝对路径；每个候选文件再次经过真实路径边界检查，避免符号链接或异常目录
    逃逸报表根目录。最多返回最近 100 份，防止历史文件无限增长拖慢页面。
    """
    handler.require_user(admin=True)
    reports_root = (deps.data_root / "reports").resolve()
    if not reports_root.is_dir():
        handler.send_json({"reports": []})
        return

    entries: list[dict[str, object]] = []
    for candidate in reports_root.rglob("*.xlsx"):
        try:
            target = candidate.resolve()
            if not deps.path_is_within(reports_root, target) or not target.is_file():
                continue
            relative = target.relative_to(deps.data_root).as_posix()
            parts = target.relative_to(reports_root).parts
            scope = parts[0] if parts and parts[0] in {"all", "self"} else ""
            if not scope:
                continue
            stat = target.stat()
        except (OSError, ValueError):
            # 单个文件在扫描期间被清理或替换时跳过，不影响其他历史报表展示。
            continue
        generated_at = datetime.fromtimestamp(stat.st_mtime, BUSINESS_TZ).isoformat(timespec="seconds")
        entries.append({
            "name": target.name,
            "url": f"/api/reports/download?path={quote(relative)}",
            "size": stat.st_size,
            "generated_at": generated_at,
            "scope": scope,
            "scope_label": "全量统计" if scope == "all" else "当前账号",
        })

    entries.sort(key=lambda item: str(item["generated_at"]), reverse=True)
    handler.send_json({"reports": entries[:100]})


def download_report_file(handler: Any, deps: ReportDependencies) -> None:
    """下载报表目录内的文件，并阻止路径越界。"""
    handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    relative = str((query.get("path") or [""])[0])
    target = (deps.data_root / relative).resolve()  # 展开 .. 和符号链接后再检查真实位置。
    reports_root = (deps.data_root / "reports").resolve()
    if not deps.path_is_within(reports_root, target) or not target.is_file():  # 同时验证目录边界与文件存在性，统一返回 404。
        raise ApiError(HTTPStatus.NOT_FOUND, "报表不存在")
    handler.send_file(
        target,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
