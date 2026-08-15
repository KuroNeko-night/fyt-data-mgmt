"""管理员回收站查询、分类恢复与彻底删除服务。

回收站中的 record_json 保存数据库记录，payload 保存文件内容。恢复器注册表按数据
类型重建记录，并在关联账号已删除、路径被占用或文件缺失时拒绝不完整恢复。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from web_backend.errors import ApiError


@dataclass(frozen=True)
class TrashDependencies:
    """回收站服务的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    storage_lock: Any
    data_root: Path
    now_iso: Callable[[], str]
    json_value: Callable[..., Any]
    json_list: Callable[..., list[Any]]
    library_categories: tuple[str, ...]
    library_unknown: str
    workshop_template_fields: tuple[str, ...]
    workshop_core: Any


def _trash_id(path: str, restore: bool = False) -> str:
    """解析回收站路由编号，并拒绝嵌套路径和非字母数字字符。

    路由编号只允许字母数字串，因此 ``%2F`` 等 URL 编码斜杠或 ``..`` 都会因包含非法
    字符被拒绝，不能构造子路径。
    """
    prefix = "/api/admin/trash/"
    suffix = "/restore" if restore else ""
    if not path.startswith(prefix) or (suffix and not path.endswith(suffix)):
        raise ApiError(HTTPStatus.BAD_REQUEST, "回收站编号无效")
    value = path[len(prefix):]
    if suffix:
        value = value[:-len(suffix)]
    value = value.strip("/")
    if not value or not value.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "回收站编号无效")
    return value


def _user_exists(connection: Any, user_id: object) -> bool:
    """检查可选关联账号是否仍存在，供恢复外键前使用。"""
    if user_id is None:
        return False
    return connection.execute(
        "SELECT 1 FROM users WHERE id = ?", (user_id,),
    ).fetchone() is not None


def _insert_record(connection: Any, table: str, columns: tuple[str, ...], record: dict) -> None:
    """按服务端固定表名和列清单插入记录，缺失旧字段自动取空值。"""
    connection.execute(
        f"INSERT INTO {table}({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",  # 值始终通过占位符绑定；表名和列名只来自内部常量。
        tuple(record.get(column) for column in columns),
    )


def _restore_job(
    connection: Any,
    record: dict,
    versions: list[dict],
    _images: list[dict],
    _deps: TrashDependencies,
) -> None:
    """恢复任务主记录及其结果版本，并兼容已删除的可选指派人。

    任务所有者是强外键，由主流程预先校验；指派人只是协作信息，账号已删除时回退为
    未指派。主记录必须先插入，随后版本记录的任务外键才能成立。
    """
    columns = (
        "id", "user_id", "assignee_id", "action", "title", "status", "progress",
        "logs", "result", "error", "files", "cancelled", "payload", "created_at",
        "updated_at", "retry_of",
    )
    values = dict(record)
    if values.get("assignee_id") is not None and not _user_exists(
        connection, values.get("assignee_id"),
    ):
        values["assignee_id"] = None  # 指派人已删除时恢复为未指派，不能因可选外键阻断整个任务。
    _insert_record(connection, "web_jobs", columns, values)
    version_columns = (
        "job_id", "user_id", "version", "result", "files", "status", "created_at",
    )
    for version in versions:
        _insert_record(connection, "web_job_versions", version_columns, version)


def _restore_upload(
    connection: Any,
    record: dict,
    _versions: list[dict],
    _images: list[dict],
    _deps: TrashDependencies,
) -> None:
    """恢复临时上传索引；文件本体由统一恢复主流程提前移回原位置。"""
    columns = ("handle", "user_id", "group_id", "name", "path", "size", "created_at")
    _insert_record(connection, "uploads", columns, record)


def _restore_library_file(
    connection: Any,
    record: dict,
    _versions: list[dict],
    _images: list[dict],
    deps: TrashDependencies,
) -> None:
    """按当前分类注册表恢复文件库记录和多分类关联关系。

    历史记录可能包含淘汰分类、缺失默认字段或已删除的最后修改者。恢复时保留仍有效的
    分类顺序，把无效主分类降级为未知，并重建关系表，使两种分类表示重新一致。
    """
    valid_categories = set(deps.library_categories) | {deps.library_unknown}  # 过滤已淘汰分类，避免恢复旧记录污染当前索引。
    primary = str(record.get("category") or deps.library_unknown)
    if primary not in valid_categories:
        primary = deps.library_unknown
    categories = [
        str(value)
        for value in deps.json_list(record.get("categories"), [])
        if isinstance(value, str) and value in valid_categories
    ]
    if primary not in categories:
        categories.insert(0, primary)
    categories = list(dict.fromkeys(categories))  # 保留原顺序去重，主分类仍位于第一项。
    updated_by = record.get("updated_by")
    if updated_by is not None and not _user_exists(connection, updated_by):
        updated_by = None  # 最后修改者是可选信息，账号删除后安全回退为空。
    columns = (
        "id", "owner_id", "name", "path", "size", "content_type", "description",
        "scope", "created_at", "updated_at", "updated_by", "category", "categories",
        "confidence", "signals", "sheet", "category_sheets",
    )
    values = {
        **record,
        "content_type": record.get("content_type", "application/octet-stream"),
        "description": record.get("description", ""),
        "scope": record.get("scope", "team"),
        "updated_by": updated_by,
        "category": primary,
        "categories": json.dumps(categories, ensure_ascii=False),
        "confidence": int(record.get("confidence") or 0),
        "signals": record.get("signals", "[]")
        if isinstance(record.get("signals"), str)
        else json.dumps(record.get("signals") or [], ensure_ascii=False),
        "sheet": record.get("sheet", ""),
        "category_sheets": record.get("category_sheets", "{}")
        if isinstance(record.get("category_sheets"), str)
        else json.dumps(record.get("category_sheets") or {}, ensure_ascii=False),
    }
    _insert_record(connection, "library_files", columns, values)
    connection.executemany(
        "INSERT INTO library_file_categories(file_id, category) VALUES (?, ?)",
        [(record.get("id"), category) for category in categories],
    )


def _restore_workshop_issue(
    connection: Any,
    record: dict,
    _versions: list[dict],
    images: list[dict],
    deps: TrashDependencies,
) -> None:
    """按现行五类模板恢复现场问题、闭环信息和图片索引。

    旧记录先通过 Core 归一化问题类别、负责人和严重程度，再补齐闭环功能上线前缺少的
    字段。图片记录在问题主记录之后插入，以满足外键约束。
    """
    columns = (
        "id", "user_id", "issue_date", "cause", "primary_owner", "secondary_owner",
        "notes", "category", "severity", *deps.workshop_template_fields, "status",
        "resolution_status", "resolution_note", "resolved_at", "resolved_by",
        "created_at", "updated_at",
    )
    values = dict(record)
    values["category"] = deps.workshop_core.normalize_workshop_category(  # 旧问题类型按当前标准模板重新归一化。
        values.get("category"), values,
    )
    values["primary_owner"] = deps.workshop_core.workshop_issue_primary_owner(
        values["category"], values, values.get("primary_owner"),
    )
    values["severity"] = deps.workshop_core.workshop_issue_severity(
        values, values.get("severity") or "normal",
    )
    defaults = {
        "resolution_status": "open",
        "resolution_note": "",
        "resolved_at": "",
        "resolved_by": None,
    }
    for key, default in defaults.items():  # 兼容闭环功能上线前没有解决状态字段的历史记录。
        if values.get(key) is None:
            values[key] = default
    if values.get("resolved_by") is not None and not _user_exists(
        connection, values.get("resolved_by"),
    ):
        values["resolved_by"] = None
    _insert_record(connection, "workshop_issues", columns, values)
    image_columns = (
        "id", "issue_id", "name", "path", "size", "content_type", "width", "height",
        "sort_order", "created_at",
    )
    for image in images:
        if isinstance(image, dict):
            _insert_record(connection, "workshop_issue_images", image_columns, image)


def _restore_daily_plan(
    connection: Any,
    record: dict,
    _versions: list[dict],
    _images: list[dict],
    _deps: TrashDependencies,
) -> None:
    """恢复生产计划上传记录，并为旧记录补回可聚合的数据月份。"""
    columns = (
        "id", "report_date", "data_month", "original_name", "path", "size",
        "content_type", "summary", "uploaded_by", "created_at", "updated_at",
    )
    values = dict(record)
    values.setdefault("data_month", str(record.get("report_date") or "")[:7])
    _insert_record(connection, "daily_production_plans", columns, values)


def _restore_daily_source(
    connection: Any,
    record: dict,
    _versions: list[dict],
    _images: list[dict],
    _deps: TrashDependencies,
) -> None:
    """恢复到料或安全检查成品资料，并兼容旧版缺失月份字段。"""
    columns = (
        "id", "kind", "report_date", "data_month", "original_name", "path", "size",
        "content_type", "summary", "uploaded_by", "created_at", "updated_at",
    )
    values = dict(record)
    values.setdefault("data_month", str(record.get("report_date") or "")[:7])
    _insert_record(connection, "daily_source_uploads", columns, values)


RESTORERS = {  # 新增可恢复类型只需注册恢复函数，主流程无需扩展长条件分支。
    "job": _restore_job,
    "upload": _restore_upload,
    "library_file": _restore_library_file,
    "workshop_issue": _restore_workshop_issue,
    "daily_production_plan": _restore_daily_plan,
    "daily_source_upload": _restore_daily_source,
}


def list_trash(handler: Any, deps: TrashDependencies) -> None:
    """返回最近五百条回收站摘要，不下发恢复载荷和服务器路径。

    删除操作人使用左连接，账号后来被删除时回收站记录仍可展示。详细 ``record_json``
    只在服务端恢复流程内部解析，管理页面无需接触可能含绝对路径的原始记录。
    """
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT t.id, t.kind, t.label, t.size, t.deleted_at, "
            "u.username AS deleted_by_username, u.display_name AS deleted_by_name "
            "FROM trash_items t LEFT JOIN users u ON u.id = t.deleted_by "
            "ORDER BY t.deleted_at DESC LIMIT 500"
        ).fetchall()
    handler.send_json({"trash": [dict(row) for row in rows]})


def _stored_parts(item: Any, deps: TrashDependencies) -> tuple[dict, list[dict], list[dict]]:
    """解析不同回收站类型的主记录、任务版本和现场图片子记录。

    普通类型直接保存一条记录；任务和现场问题需要额外保存一对多子记录，因此使用带
    ``job`` 或 ``issue`` 外层的结构。任何损坏 JSON 都拒绝恢复，避免文件先回原位却无法
    重建数据库索引。
    """
    stored = deps.json_value(item["record_json"], None)  # 损坏 JSON 不能继续恢复文件，否则会产生无索引数据。
    if not isinstance(stored, dict):
        raise ApiError(HTTPStatus.CONFLICT, "回收站记录已损坏，无法恢复")
    if item["kind"] == "job" and isinstance(stored.get("job"), dict):
        versions = stored.get("versions")
        return (
            stored["job"],
            [value for value in versions if isinstance(value, dict)]
            if isinstance(versions, list) else [],
            [],
        )
    if item["kind"] == "workshop_issue" and isinstance(stored.get("issue"), dict):
        images = stored.get("images")
        return (
            stored["issue"],
            [],
            [value for value in images if isinstance(value, dict)]
            if isinstance(images, list) else [],
        )
    return stored, [], []


def _owner_id(kind: str, record: dict) -> object:
    """按记录类型提取必须存在的所属账号字段。

    文件库使用 ``owner_id``，日清资料使用 ``uploaded_by``，其余用户数据使用
    ``user_id``。集中处理可避免主恢复流程散落类型分支。
    """
    if kind == "library_file":
        return record.get("owner_id")
    if kind in {"daily_production_plan", "daily_source_upload"}:
        return record.get("uploaded_by")
    return record.get("user_id")


def _restore_target(item: Any, deps: TrashDependencies) -> Path:
    """解析并校验回收站记录的原始恢复路径。

    保存的路径必须相对于 Web 数据根，解析后不得等于数据根本身或越出其子目录；目标
    已存在时也拒绝覆盖，防止恢复旧数据破坏当前同名业务文件。
    """
    root = deps.data_root.resolve()
    target = (deps.data_root / str(item["original_path"] or "")).resolve()  # 展开 .. 和符号链接后校验真实恢复位置。
    if target == root or root not in target.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "恢复路径无效")
    if target.exists():  # 不覆盖当前同名数据，要求管理员先处理冲突。
        raise ApiError(HTTPStatus.CONFLICT, "原位置已有同名数据，无法恢复")
    return target


def restore_trash(handler: Any, path: str, deps: TrashDependencies) -> None:
    """根据回收站数据类型恢复数据库记录、子记录和所属文件。

    恢复器必须来自显式注册表，所属账号仍存在且原路径未被占用；现场问题还要求图片
    载荷完整。文件先移回目标，再在事务中重建主表和关联表；数据库阶段失败时将文件
    退回回收站，成功后才删除回收站目录和索引。
    """
    actor = handler.require_user(admin=True)
    trash_id = _trash_id(path, restore=True)
    with deps.storage_lock:  # 恢复与彻底删除、定期清理、业务写入不能同时操作同一 payload。
        with deps.db_lock, deps.db() as connection:
            item = connection.execute(
                "SELECT * FROM trash_items WHERE id = ?", (trash_id,),
            ).fetchone()
        if item is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "回收站记录不存在")
        restorer = RESTORERS.get(str(item["kind"]))  # 只调用显式注册的恢复器，未知 kind 不做猜测。
        if restorer is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "回收站数据类型无效")
        record, versions, images = _stored_parts(item, deps)
        target = _restore_target(item, deps)
        # 跨部署恢复时 record_json 里的旧绝对路径已失效；用本次恢复目标重写 path，
        # 保证恢复出的记录在后续下载时仍能通过当前数据根下的路径校验，而不是指向旧目录。
        if "path" in record:
            record["path"] = str(target)
        for image in images:
            if isinstance(image, dict) and "path" in image:
                image["path"] = str(target / Path(str(image.get("name") or "")).name)
        payload = deps.data_root / "trash" / trash_id / "payload"
        if item["kind"] == "workshop_issue" and not payload.exists():  # 现场问题图片是报告的一部分，缺失时拒绝半恢复。
            raise ApiError(HTTPStatus.CONFLICT, "现场图片已不存在，无法恢复这条问题")
        if payload.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(payload), str(target))
        try:
            with deps.db_lock, deps.db() as connection:
                owner_id = _owner_id(str(item["kind"]), record)  # 所属账号是强关联，账号已删除时不能恢复孤儿数据。
                if owner_id is not None and not _user_exists(connection, owner_id):
                    raise ApiError(HTTPStatus.CONFLICT, "所属账号已不存在，无法恢复")
                restorer(connection, record, versions, images, deps)
                connection.execute("DELETE FROM trash_items WHERE id = ?", (trash_id,))
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                    (actor["id"], f"restore_trash:{trash_id}", deps.now_iso()),
                )
        except Exception:  # 数据库恢复失败时把文件移回回收站，保持两部分状态一致。
            if target.exists() and not payload.exists():
                payload.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(payload))
            raise
        shutil.rmtree(deps.data_root / "trash" / trash_id, ignore_errors=True)
    handler.send_json({"message": "数据已恢复到原位置"})


def delete_trash(handler: Any, path: str, deps: TrashDependencies) -> None:
    """永久删除一条回收站载荷和索引，并记录不可恢复操作审计。

    文件目录先删除，再移除数据库索引；即使载荷已因历史清理缺失，目录删除仍保持幂等。
    存储锁保证该过程不会与恢复或周期清理同时操作同一回收站编号。
    """
    actor = handler.require_user(admin=True)
    trash_id = _trash_id(path)
    with deps.storage_lock:  # 彻底删除期间阻止恢复或维护线程并发操作同一目录。
        with deps.db_lock, deps.db() as connection:
            exists = connection.execute(
                "SELECT 1 FROM trash_items WHERE id = ?", (trash_id,),
            ).fetchone()
        if exists is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "回收站记录不存在")
        shutil.rmtree(deps.data_root / "trash" / trash_id, ignore_errors=True)
        with deps.db_lock, deps.db() as connection:
            deleted = connection.execute(
                "DELETE FROM trash_items WHERE id = ?", (trash_id,),
            ).rowcount
            if deleted:
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                    (actor["id"], f"delete_trash:{trash_id}", deps.now_iso()),
                )
        if not deleted:
            raise ApiError(HTTPStatus.NOT_FOUND, "回收站记录不存在")
    handler.send_json({"message": "回收站数据已彻底删除"})
