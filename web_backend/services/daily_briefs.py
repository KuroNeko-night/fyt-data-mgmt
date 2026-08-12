"""日清事项、指标、通报与会议待办维护服务。

各事项类别只接受自身实际需要的字段；切换类别时会清空无关旧值，避免前端隐藏字段
继续进入总览或导出结果。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

from web_backend.errors import ApiError
from web_backend.http.path_params import path_id
from web_backend.services.daily_management_types import DailyManagementDependencies


def _daily_brief_id(path: str) -> str:
    """解析日清事项的 32 位 UUID 十六进制主键。"""
    value = path_id(path, "/api/admin/daily-brief-items/")
    if len(value) != 32 or not value.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "事项编号无效")
    return value


_THREE_FIELD_BRIEF_CATEGORIES = {"escalation", "notice"}
_BRIEF_TEXT_LIMITS = {
    "unit": 80,
    "owner": 80,
    "description": 4000,
    "progress": 1000,
}


def _daily_brief_values(
    body: dict[str, object], deps: DailyManagementDependencies, require_date: bool,
) -> dict[str, str]:
    """读取并清洗日清事项共享字段，不在此阶段推断类别专属规则。"""
    return {
        "report_date": (
            deps.report_date(body.get("report_date"))
            if require_date else str(body.get("report_date") or "")
        ),
        "category": str(body.get("category") or "notice").strip(),
        "unit": str(body.get("unit") or "").strip(),
        "owner": str(body.get("owner") or "").strip(),
        "title": str(body.get("title") or "").strip(),
        "description": str(body.get("description") or "").strip(),
        "due_date": str(body.get("due_date") or "").strip(),
        "progress": str(body.get("progress") or "").strip(),
        "status": str(body.get("status") or "open").strip(),
    }


def _validate_daily_brief_kind(
    values: dict[str, str], deps: DailyManagementDependencies,
) -> None:
    """校验类别、状态和主标题，并按类别选择客户可理解的字段名称。"""
    category = values["category"]
    if category not in deps.brief_categories:
        raise ApiError(HTTPStatus.BAD_REQUEST, "事项类别无效")
    if values["status"] not in deps.brief_statuses:
        raise ApiError(HTTPStatus.BAD_REQUEST, "事项状态无效")
    if not values["title"] or len(values["title"]) > 160:
        label = (
            "事项"
            if category in _THREE_FIELD_BRIEF_CATEGORIES | {"meeting_todo", "past_todo"}
            else "指标名称"
        )
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{label}需要填写且不能超过 160 个字")


def _apply_daily_brief_category_rules(values: dict[str, str]) -> None:
    """清空当前类别不使用的字段，阻止前端隐藏旧值进入总览和导出。"""
    category = values["category"]
    if category in _THREE_FIELD_BRIEF_CATEGORIES:
        if not values["unit"] or not values["owner"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "重大/升级事项和通报需要填写单位、责任人和事项")
        # 三字段事项没有描述、日期、进展和流转状态，切换类别时必须清理历史待办值。
        values.update({"description": "", "due_date": "", "progress": "", "status": "open"})
    elif category == "process":
        # 过程指标可记录说明，但不参与待办完成日期和状态流转。
        values.update({"due_date": "", "progress": "", "status": "open"})


def _validate_daily_brief_content(values: dict[str, str]) -> None:
    """校验各文本长度并将可选完成日期归一化为 ISO 格式。"""
    if any(len(values[key]) > limit for key, limit in _BRIEF_TEXT_LIMITS.items()):
        raise ApiError(HTTPStatus.BAD_REQUEST, "事项内容过长")
    if not values["due_date"]:
        return
    try:
        values["due_date"] = datetime.strptime(values["due_date"], "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "事项完成日期无效") from exc


def _validate_daily_brief(
    body: dict[str, object],
    deps: DailyManagementDependencies,
    *,
    require_date: bool = True,
) -> dict[str, str]:
    """按事项类别校验实际需要的字段，并清空该类别不使用的内容。

    不同事项共享一张表，但表单字段并不相同。这里把通报、升级事项、过程指标等规则
    集中规范化，防止前端隐藏字段后旧值仍被提交并出现在总览。返回字典可直接用于新增
    或更新 SQL，调用方无需再次推断类别。
    """
    values = _daily_brief_values(body, deps, require_date)
    _validate_daily_brief_kind(values, deps)
    _apply_daily_brief_category_rules(values)
    _validate_daily_brief_content(values)
    return values

def list_daily_brief_items(handler: Any, deps: DailyManagementDependencies) -> None:
    """返回指定日期的事项与待办；旧 ``safety`` 类别不再进入该维护入口。"""
    handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date((query.get("date") or [deps.business_today().isoformat()])[0])
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT * FROM daily_brief_items WHERE report_date = ? AND category != 'safety' "  # 安全检查已迁移到专用文件资料。
            "ORDER BY updated_at DESC, id", (report_date,)
        ).fetchall()
    handler.send_json({"date": report_date, "items": [deps.daily_brief_public(row) for row in rows]})

def create_daily_brief_item(handler: Any, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """按类别规则新增日清事项，并记录创建管理员。"""
    actor = handler.require_user(admin=True)
    values = _validate_daily_brief(body, deps)
    item_id = uuid.uuid4().hex
    created = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        connection.execute(
            "INSERT INTO daily_brief_items(id, report_date, category, unit, owner, title, description, "
            "due_date, progress, status, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, values["report_date"], values["category"], values["unit"], values["owner"],
             values["title"], values["description"], values["due_date"], values["progress"],
             values["status"], actor["id"], created, created),
        )
        row = connection.execute("SELECT * FROM daily_brief_items WHERE id = ?", (item_id,)).fetchone()
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_brief_create:{item_id}", created),
        )
    handler.send_json({"message": "日清事项已添加", "item": deps.daily_brief_public(row)}, HTTPStatus.CREATED)

def update_daily_brief_item(handler: Any, path: str, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """按完整规范字段更新日清事项，确保切换类别时清理无关字段。"""
    actor = handler.require_user(admin=True)
    item_id = _daily_brief_id(path)
    values = _validate_daily_brief(body, deps)
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute(
            "UPDATE daily_brief_items SET report_date = ?, category = ?, unit = ?, owner = ?, title = ?, "
            "description = ?, due_date = ?, progress = ?, status = ?, updated_at = ? WHERE id = ?",
            (values["report_date"], values["category"], values["unit"], values["owner"], values["title"],
             values["description"], values["due_date"], values["progress"], values["status"], updated, item_id),
        ).rowcount
        if not changed:
            raise ApiError(HTTPStatus.NOT_FOUND, "日清事项不存在")
        row = connection.execute("SELECT * FROM daily_brief_items WHERE id = ?", (item_id,)).fetchone()
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_brief_update:{item_id}", updated),
        )
    handler.send_json({"message": "日清事项已更新", "item": deps.daily_brief_public(row)})

def delete_daily_brief_item(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """删除日清事项并写入审计日志；不存在时不伪装成功。"""
    actor = handler.require_user(admin=True)
    item_id = _daily_brief_id(path)
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute("DELETE FROM daily_brief_items WHERE id = ?", (item_id,)).rowcount
        if not changed:
            raise ApiError(HTTPStatus.NOT_FOUND, "日清事项不存在")
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_brief_delete:{item_id}", deps.now_iso()),
        )
    handler.send_json({"message": "日清事项已删除"})
