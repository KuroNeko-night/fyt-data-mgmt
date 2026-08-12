"""现场问题的发布、编辑、闭环、图片和报表服务。

本模块只编排 HTTP、权限、数据库记录和文件落盘；问题分类、模板字段、图片归一化和
Excel 导出规则仍由 ``core.workshop_issue_core`` 提供，避免 Web 端形成第二套业务规则。
图片文件和数据库记录需要保持一致，因此新增、删除及进入回收站均显式实现失败回滚。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from web_backend.errors import ApiError


@dataclass(frozen=True)
class WorkshopDependencies:
    """现场问题服务的运行时依赖。

    依赖由 ``web_server.py`` 统一装配，使本模块不直接导入服务端全局变量，也方便测试
    注入临时数据库、临时数据目录和固定时钟。``db_lock`` 保护 SQLite 连接操作，
    ``storage_lock`` 则覆盖文件系统与数据库必须同步变化的复合事务。
    """

    db_lock: Any
    db: Callable[[], Any]
    storage_lock: Any
    data_root: Path
    max_image_bytes: int
    max_images: int
    categories: dict[str, str]
    template_fields: dict[str, tuple[str, int, str]]
    now_iso: Callable[[], str]
    safe_name: Callable[[object], str]
    issue_date: Callable[[object], str]
    export_range: Callable[[dict[str, list[str]]], tuple[str, str]]
    issue_dir: Callable[[int, str], Path]
    resolve_image_path: Callable[[Any], Path]
    can_edit: Callable[[Any, Any], bool]
    can_resolve: Callable[[Any, Any], bool]
    can_delete: Callable[[Any, Any], bool]
    issue_public: Callable[[Any, list[Any], Any], dict[str, object]]
    tree_size: Callable[[Path], int]
    write_audit: Callable[[int | None, str, int | None], None]
    workshop_core: Any


def _workshop_issue_id(path: str, suffix: str = "") -> str:
    """从现场问题接口路径中解析问题编号，并拒绝可构造子路径的非法值。"""
    prefix = "/api/workshop/issues/"
    ending = f"/{suffix}" if suffix else ""
    if not path.startswith(prefix) or (ending and not path.endswith(ending)):
        raise ApiError(HTTPStatus.BAD_REQUEST, "问题编号无效")
    value = path[len(prefix):]
    if ending:
        value = value[:-len(ending)]
    value = unquote(value.strip("/"))  # 先解码再验证，防止用 ``%2F`` 绕过斜杠检查。
    if not value or "/" in value or not value.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "问题编号无效")
    return value


def workshop_issue_select() -> str:
    """返回现场问题、发布人和解决人信息的公共查询片段。

    统一查询片段可保证列表、编辑、导出看到相同的人员名称回退规则；解决人使用
    ``LEFT JOIN``，因为尚未闭环的问题没有 ``resolved_by`` 是正常状态。
    """
    return (
        "SELECT w.*, u.username, u.display_name, "
        "COALESCE(ru.display_name, ru.username, '') AS resolved_by_name "
        "FROM workshop_issues w "
        "JOIN users u ON u.id = w.user_id "
        "LEFT JOIN users ru ON ru.id = w.resolved_by "
    )


def _workshop_issue_row(
    issue_id: str,
    user: Any,
    deps: WorkshopDependencies,
    *,
    manage: bool = False,
) -> Any:
    """读取当前账号可见的问题，并在管理场景校验所有者权限。

    草稿仅对创建者和管理员可见，已发布记录对登录用户可见。管理校验只负责最外层
    所有权，班组长能否编辑、解决或删除还由调用方分别使用对应权限函数判断。
    """
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            workshop_issue_select() +
            "WHERE w.id = ? AND (w.status = 'published' OR w.user_id = ? OR ? = 'admin')",
            (issue_id, user["id"], user["role"]),
        ).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "车间问题不存在")
    if manage and int(row["user_id"]) != int(user["id"]) and user["role"] != "admin":
        raise ApiError(HTTPStatus.FORBIDDEN, "只有上传者或管理员可以管理这条问题")
    return row


def _workshop_issue_images(issue_id: str, deps: WorkshopDependencies) -> list[Any]:
    """按稳定顺序读取问题关联的全部图片记录。

    ``sort_order`` 保留人工上传顺序，``created_at`` 作为旧数据或同序号记录的稳定
    次级排序键，避免刷新页面后图片顺序随机变化。
    """
    with deps.db_lock, deps.db() as connection:
        return connection.execute(
            "SELECT i.*, w.user_id FROM workshop_issue_images i "
            "JOIN workshop_issues w ON w.id = i.issue_id "
            "WHERE i.issue_id = ? ORDER BY i.sort_order, i.created_at",
            (issue_id,),
        ).fetchall()


def _normalize_workshop_issue_payload(
    body: dict[str, object],
    deps: WorkshopDependencies,
    current: Any | None = None,
) -> dict[str, object]:
    """校验编辑字段，合并旧值并清空目标分类不使用的模板字段。

    ``body`` 可以是局部更新，因此缺失字段从 ``current`` 取旧值；但切换问题分类时，
    新分类不允许的字段必须清空，不能把旧分类数据悄悄带入导出报表。返回值只包含
    允许写回数据库的规范字段，调用方可直接据此构造参数化更新语句。
    """
    current_values = dict(current) if current is not None else {}

    def value(name: str, default: object = "") -> str:
        """读取请求值或旧值，并把数据库 ``NULL`` 统一规范为空字符串。"""
        raw = body[name] if name in body else current_values.get(name, default)
        return str(raw or "").strip()

    issue_date = deps.issue_date(value("issue_date"))
    cause = value("cause")
    legacy_primary_owner = value("primary_owner")
    secondary_owner = value("secondary_owner")
    notes = value("notes")
    category = value("category", "main_material") or "main_material"
    fallback_severity = value("severity", "normal") or "normal"
    raw_template_values = {field: value(field) for field in deps.template_fields}  # 全量读取后才能识别跨分类残留字段。
    if not cause:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请填写问题描述")
    if category not in deps.categories:
        raise ApiError(HTTPStatus.BAD_REQUEST, "现场问题只能选择主料异常、辅料异常、包装异常、海外问题或防错异常")
    template = deps.workshop_core.WORKSHOP_ISSUE_TEMPLATES[category]
    allowed_fields = set(deps.workshop_core.WORKSHOP_ISSUE_CATEGORY_ALLOWED_FIELDS[category])  # 以 Core 模板为唯一事实源。
    disallowed = [
        deps.template_fields[field][2]
        for field, field_value in raw_template_values.items()
        if field in body and field_value and field not in allowed_fields
    ]
    if disallowed:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            f"{template['label']}不使用以下字段：{'、'.join(disallowed)}",
        )
    if "secondary_owner" in body and secondary_owner:
        raise ApiError(HTTPStatus.BAD_REQUEST, "当前问题模板不使用次要负责人字段")
    if "notes" in body and notes and category != "error_proofing":
        raise ApiError(HTTPStatus.BAD_REQUEST, "只有防错异常模板可以填写备注")
    template_values = {  # 切换分类后主动清空无关列，保证数据库和模板语义一致。
        field: field_value if field in allowed_fields else ""
        for field, field_value in raw_template_values.items()
    }
    semantic_values = {**template_values, "cause": cause, "issue_date": issue_date}  # 必填项既可能是通用字段，也可能是模板字段。
    for field in template["required"]:
        if not str(semantic_values.get(field) or "").strip():
            label = dict(template["columns"]).get(field, "必填项")
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{template['label']}请填写{label}")
    primary_owner = deps.workshop_core.workshop_issue_primary_owner(
        category, semantic_values, legacy_primary_owner,
    )  # 兼容旧记录的负责人列，同时允许新模板从专用字段推导负责人。
    severity = deps.workshop_core.workshop_issue_severity(template_values, fallback_severity)  # 严重度按模板内容派生，旧值只作回退。
    limits = (
        (cause, 1000, "问题描述"),
        (primary_owner, 120, "负责人"),
        (notes, 2000, "备注"),
    )
    for field_value, limit, label in limits:
        if len(field_value) > limit:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{label}不能超过 {limit} 字")
    for field, field_value in template_values.items():
        _, limit, label = deps.template_fields[field]
        if len(field_value) > limit:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{label}不能超过 {limit} 字")
    return {
        "issue_date": issue_date,
        "cause": cause,
        "primary_owner": primary_owner,
        "secondary_owner": secondary_owner if current is not None else "",
        "notes": notes if category == "error_proofing" else "",
        "category": category,
        "severity": severity,
        **template_values,
    }


def _workshop_image_ids(path: str) -> tuple[str, str]:
    """从图片接口路径中解析问题编号和图片编号。

    两个编号均限定为字母数字串，既匹配 UUID 十六进制编号，也阻止路径穿越字符进入
    后续文件定位逻辑。
    """
    prefix = "/api/workshop/issues/"
    if not path.startswith(prefix):
        raise ApiError(HTTPStatus.BAD_REQUEST, "图片编号无效")
    parts = [unquote(value) for value in path[len(prefix):].strip("/").split("/")]
    if len(parts) != 3 or parts[1] != "images" or not parts[0].isalnum() or not parts[2].isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "图片编号无效")
    return parts[0], parts[2]


def create_workshop_issue(handler: Any, body: dict[str, object], deps: WorkshopDependencies) -> None:
    """创建现场问题草稿，并按问题类型校验可填写字段。

    新记录始终先保存为草稿，图片上传完成后再由发布接口做最终校验。历史客户端可能
    不提交 ``category``，此时允许先建立默认类型草稿；显式选择分类的新客户端则必须
    一次性满足该模板的必填字段。
    """
    user = handler.require_user()
    issue_date = deps.issue_date(body.get("issue_date"))
    cause = str(body.get("cause") or "").strip()
    legacy_primary_owner = str(body.get("primary_owner") or "").strip()
    secondary_owner = str(body.get("secondary_owner") or "").strip()
    notes = str(body.get("notes") or "").strip()
    category_was_supplied = bool(str(body.get("category") or "").strip())  # 区分旧客户端缺省值与用户明确选择。
    category = str(body.get("category") or "main_material").strip()
    fallback_severity = str(body.get("severity") or "normal").strip()
    raw_template_values = {  # 保留所有受支持模板列，便于统一识别“不属于当前类型”的输入。
        field: str(body.get(field) or "").strip()
        for field in deps.template_fields
    }
    if not cause:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请填写问题描述")
    if category not in deps.categories:
        raise ApiError(HTTPStatus.BAD_REQUEST, "现场问题只能选择主料异常、辅料异常、包装异常、海外问题或防错异常")
    template = deps.workshop_core.WORKSHOP_ISSUE_TEMPLATES[category]
    allowed_fields = set(deps.workshop_core.WORKSHOP_ISSUE_CATEGORY_ALLOWED_FIELDS[category])
    disallowed = [
        deps.template_fields[field][2]
        for field, value in raw_template_values.items()
        if value and field not in allowed_fields
    ]
    if disallowed:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            f"{template['label']}不使用以下字段：{'、'.join(disallowed)}",
        )
    if secondary_owner:
        raise ApiError(HTTPStatus.BAD_REQUEST, "当前问题模板不使用次要负责人字段")
    if notes and category != "error_proofing":
        raise ApiError(HTTPStatus.BAD_REQUEST, "只有防错异常模板可以填写备注")
    template_values = {
        field: value if field in allowed_fields else ""
        for field, value in raw_template_values.items()
    }
    semantic_values = {**template_values, "cause": cause, "issue_date": issue_date}
    if category_was_supplied:  # 旧客户端先建草稿再补字段，不在这里强制新模板必填项。
        for field in template["required"]:
            if not str(semantic_values.get(field) or "").strip():
                label = dict(template["columns"]).get(field, "必填项")
                raise ApiError(HTTPStatus.BAD_REQUEST, f"{template['label']}请填写{label}")
    primary_owner = deps.workshop_core.workshop_issue_primary_owner(
        category, semantic_values, legacy_primary_owner,
    )
    severity = deps.workshop_core.workshop_issue_severity(template_values, fallback_severity)
    limits = ((cause, 1000, "问题描述"), (primary_owner, 120, "负责人"),
              (notes, 2000, "备注"))
    for value, limit, label in limits:
        if len(value) > limit:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{label}不能超过 {limit} 字")
    for field, value in template_values.items():
        _, limit, label = deps.template_fields[field]
        if len(value) > limit:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{label}不能超过 {limit} 字")
    issue_id = uuid.uuid4().hex  # URL、目录名和数据库主键共用不含连字符的安全标识。
    created = deps.now_iso()
    template_columns = tuple(deps.template_fields)  # 字段顺序同时用于列名和值，避免动态 SQL 参数错位。
    columns = (
        "id", "user_id", "issue_date", "cause", "primary_owner", "secondary_owner",
        "notes", "category", "severity", *template_columns, "status", "created_at", "updated_at",
    )
    values = (
        issue_id, user["id"], issue_date, cause, primary_owner, secondary_owner,
        notes, category, severity,
        *(template_values[field] for field in template_columns),
        "draft", created, created,
    )
    with deps.db_lock, deps.db() as connection:
        connection.execute(
            f"INSERT INTO workshop_issues({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",  # 列名来自服务端常量，业务值仍全部参数化。
            values,
        )
        row = connection.execute(
            workshop_issue_select() + "WHERE w.id = ?", (issue_id,)
        ).fetchone()
    handler.send_json(
        {"message": "问题草稿已创建", "issue": deps.issue_public(row, [], user)},
        HTTPStatus.CREATED,
    )

def upload_workshop_issue_image(handler: Any, path: str, deps: WorkshopDependencies) -> None:
    """校验图片格式和数量限制后，为草稿或可编辑的已发布问题添加图片。

    请求体先流式写入临时目录，再由 Core 解码并规范图片；只有规范化成功后才进入
    全局存储临界区。最终文件先落盘、后写数据库，数据库失败时删除文件以维持一致性。
    """
    user = handler.require_user()
    issue_id = _workshop_issue_id(path, "images")
    row = _workshop_issue_row(issue_id, user, deps, manage=True)
    if not deps.can_edit(row, user):
        raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长本人或管理员可以编辑已发布问题")
    if row["status"] not in {"draft", "published"}:
        raise ApiError(HTTPStatus.CONFLICT, "当前问题状态不能添加图片")
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "图片大小无效") from exc
    if length <= 0:
        raise ApiError(HTTPStatus.BAD_REQUEST, "上传图片为空")
    if length > deps.max_image_bytes:
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "单张图片不能超过 15 MB")
    query = parse_qs(urlparse(handler.path).query)
    name = deps.safe_name(query.get("name", ["现场图片"])[0])
    image_id = uuid.uuid4().hex
    staging_root = deps.data_root / "temp" / "workshop-uploads"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f"{issue_id}-", dir=staging_root))  # 每次上传独占目录，避免同名临时文件互相覆盖。
    source_path = staging_dir / "source.uploading"
    final_path: Path | None = None
    try:
        remaining = length  # 严格按 Content-Length 读取，不能等待客户端无限追加数据。
        with source_path.open("wb") as stream:
            while remaining:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))  # 1 MiB 分块限制单次内存峰值。
                if not chunk:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "图片上传不完整")
                stream.write(chunk)
                remaining -= len(chunk)
        try:
            metadata = deps.workshop_core.normalize_image(source_path, staging_dir / "normalized")
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        normalized_path = Path(str(metadata["path"]))

        # 网络接收和图片解码不能占用全局存储锁，否则一个慢连接会阻塞所有上传。
        with deps.storage_lock:
            next_row = _workshop_issue_row(issue_id, user, deps, manage=True)
            if next_row["status"] not in {"draft", "published"}:
                raise ApiError(HTTPStatus.CONFLICT, "当前问题状态不能添加图片")
            with deps.db_lock, deps.db() as connection:
                image_count = int(connection.execute(
                    "SELECT COUNT(*) AS n FROM workshop_issue_images WHERE issue_id = ?",
                    (issue_id,),
                ).fetchone()["n"])
            if image_count >= deps.max_images:
                raise ApiError(
                    HTTPStatus.BAD_REQUEST,
                    f"每条问题最多上传 {deps.max_images} 张图片",
                )
            folder = deps.issue_dir(int(next_row["user_id"]), issue_id)
            folder.mkdir(parents=True, exist_ok=True)
            final_path = folder / f"{image_id}{normalized_path.suffix.lower()}"
            os.replace(normalized_path, final_path)  # 同卷原子移动，外部读取者不会看到半张图片。
            created = deps.now_iso()
            try:
                with deps.db_lock, deps.db() as connection:
                    connection.execute(
                        "INSERT INTO workshop_issue_images(id, issue_id, name, path, size, content_type, "
                        "width, height, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (image_id, issue_id, name, str(final_path), int(metadata["size"]),
                         str(metadata["content_type"]), int(metadata["width"]),
                         int(metadata["height"]), image_count, created),
                    )
                    connection.execute(
                        "UPDATE workshop_issues SET updated_at = ? WHERE id = ?",
                        (created, issue_id),
                    )
                    if next_row["status"] == "published":
                        connection.execute(
                            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) "
                            "VALUES (?, ?, ?, ?)",
                            (user["id"], f"workshop_image_add:{issue_id}:{image_id}", next_row["user_id"], created),
                        )
            except Exception:
                final_path.unlink(missing_ok=True)
                raise  # 数据库未记录时不能遗留无法管理的孤儿文件。
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
    images = _workshop_issue_images(issue_id, deps)
    next_row = _workshop_issue_row(issue_id, user, deps)
    handler.send_json({
        "message": "图片已上传",
        "issue": deps.issue_public(next_row, images, user),
    }, HTTPStatus.CREATED)

def update_workshop_issue(handler: Any, path: str, body: dict[str, object], deps: WorkshopDependencies) -> None:
    """按角色权限更新现场问题内容，并记录最后修改人。

    ``expected_updated_at`` 实现乐观并发控制：两个用户同时打开记录时，后提交者不会
    静默覆盖先提交者。即使客户端没有传时间戳，最终 SQL 仍用读取时的旧时间作条件，
    关闭校验与写入之间的竞态窗口。
    """
    user = handler.require_user()
    issue_id = _workshop_issue_id(path)
    with deps.storage_lock:
        row = _workshop_issue_row(issue_id, user, deps, manage=True)
        if not deps.can_edit(row, user):
            raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长本人或管理员可以编辑已发布问题")
        expected_updated_at = str(body.get("expected_updated_at") or "").strip()  # 前端快照版本，可提前给出更清晰的冲突提示。
        if expected_updated_at and expected_updated_at != str(row["updated_at"]):
            raise ApiError(HTTPStatus.CONFLICT, "问题已被其他人更新，请刷新后重新编辑")
        values = _normalize_workshop_issue_payload(body, deps, row)
        with deps.db_lock, deps.db() as connection:
            image_count = int(connection.execute(
                "SELECT COUNT(*) AS n FROM workshop_issue_images WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()["n"])
            if (
                row["status"] == "published"
                and values["category"] in deps.workshop_core.WORKSHOP_ISSUE_IMAGE_REQUIRED_CATEGORIES
                and image_count < 1
            ):
                raise ApiError(HTTPStatus.BAD_REQUEST, "该问题类型至少需要一张现场图片")
            updated = deps.now_iso()
            columns = (*values.keys(), "updated_at")
            changed = connection.execute(
                f"UPDATE workshop_issues SET {', '.join(f'{column} = ?' for column in columns)} "
                "WHERE id = ? AND updated_at = ?",
                (*values.values(), updated, issue_id, row["updated_at"]),  # WHERE 中再次比较版本，防止检查后被抢先更新。
            ).rowcount
            if not changed:
                raise ApiError(HTTPStatus.CONFLICT, "问题已被其他人更新，请刷新后重新编辑")
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                (user["id"], f"workshop_edit:{issue_id}", row["user_id"], updated),
            )
    next_row = _workshop_issue_row(issue_id, user, deps)
    images = _workshop_issue_images(issue_id, deps)
    handler.send_json({
        "message": "问题内容已更新",
        "issue": deps.issue_public(next_row, images, user),
    })

def publish_workshop_issue(handler: Any, path: str, deps: WorkshopDependencies) -> None:
    """校验图片后将问题草稿发布到日清看板，重复调用保持幂等。

    字段完整性已在创建和编辑阶段按 Core 模板校验；发布阶段再次检查强制图片规则，
    防止用户先删除图片再发布。已发布记录直接返回当前状态，不重复写审计日志。
    """
    user = handler.require_user()
    issue_id = _workshop_issue_id(path, "publish")
    with deps.storage_lock:
        row = _workshop_issue_row(issue_id, user, deps, manage=True)
        if row["status"] != "published":
            with deps.db_lock, deps.db() as connection:
                image_count = int(connection.execute(
                    "SELECT COUNT(*) AS n FROM workshop_issue_images WHERE issue_id = ?",
                    (issue_id,),
                ).fetchone()["n"])
                category = deps.workshop_core.normalize_workshop_category(
                    row["category"] if "category" in row.keys() else "", dict(row),
                )  # 旧数据库可能没有规范分类值，需要按字段内容回推真实类型。
                if category in deps.workshop_core.WORKSHOP_ISSUE_IMAGE_REQUIRED_CATEGORIES and image_count < 1:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "请至少上传一张现场图片")
                updated = deps.now_iso()
                connection.execute(
                    "UPDATE workshop_issues SET status = 'published', updated_at = ? WHERE id = ?",
                    (updated, issue_id),
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (user["id"], f"workshop_publish:{issue_id}", row["user_id"], updated),
                )
    next_row = _workshop_issue_row(issue_id, user, deps)
    images = _workshop_issue_images(issue_id, deps)
    handler.send_json({
        "message": "当天问题已发布" if row["status"] != "published" else "当天问题已经发布",
        "issue": deps.issue_public(next_row, images, user),
    })

def resolve_workshop_issue(handler: Any, path: str, body: dict[str, object], deps: WorkshopDependencies) -> None:
    """将已发布问题标记为已解决，并保存解决过程补充说明。

    闭环不会删除或改写原问题内容，而是独立记录解决人、时间和说明，便于看板统计及
    事后追溯。状态更新同样使用 ``updated_at`` 防止覆盖并发编辑。
    """
    user = handler.require_user()
    issue_id = _workshop_issue_id(path, "resolve")
    resolution_note = str(body.get("resolution_note") or "").strip()
    if not resolution_note:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请填写问题的解决情况")
    if len(resolution_note) > 2000:
        raise ApiError(HTTPStatus.BAD_REQUEST, "解决情况不能超过 2000 字")
    with deps.storage_lock:
        row = _workshop_issue_row(issue_id, user, deps, manage=True)
        if not deps.can_resolve(row, user):
            raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长本人或管理员可以推进问题闭环")
        if row["status"] != "published":
            raise ApiError(HTTPStatus.CONFLICT, "问题尚未发布，不能标记为已解决")
        expected_updated_at = str(body.get("expected_updated_at") or "").strip()
        if expected_updated_at and expected_updated_at != str(row["updated_at"]):
            raise ApiError(HTTPStatus.CONFLICT, "问题已被其他人更新，请刷新后重试")
        updated = deps.now_iso()
        with deps.db_lock, deps.db() as connection:
            changed = connection.execute(
                "UPDATE workshop_issues SET resolution_status = 'resolved', resolution_note = ?, "
                "resolved_at = ?, resolved_by = ?, updated_at = ? WHERE id = ? AND updated_at = ?",
                (resolution_note, updated, user["id"], updated, issue_id, row["updated_at"]),
            ).rowcount
            if not changed:
                raise ApiError(HTTPStatus.CONFLICT, "问题已被其他人更新，请刷新后重试")
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                (user["id"], f"workshop_resolve:{issue_id}", row["user_id"], updated),
            )
    next_row = _workshop_issue_row(issue_id, user, deps)
    images = _workshop_issue_images(issue_id, deps)
    handler.send_json({
        "message": "问题已标记为已解决",
        "issue": deps.issue_public(next_row, images, user),
    })

def reopen_workshop_issue(handler: Any, path: str, body: dict[str, object], deps: WorkshopDependencies) -> None:
    """重新打开已解决问题，并保留上次解决说明供追溯。

    这里只把 ``resolution_status`` 改回处理中，不清空解决说明、解决人和解决时间；
    管理层仍可看到此前为何曾被判定为解决。对未解决记录重复调用时直接幂等返回。
    """
    user = handler.require_user()
    issue_id = _workshop_issue_id(path, "reopen")
    with deps.storage_lock:
        row = _workshop_issue_row(issue_id, user, deps, manage=True)
        if not deps.can_resolve(row, user):
            raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长本人或管理员可以推进问题闭环")
        if row["status"] != "published":
            raise ApiError(HTTPStatus.CONFLICT, "问题尚未发布，不能重新打开")
        if row["resolution_status"] != "resolved":
            handler.send_json({
                "message": "问题当前仍在处理中",
                "issue": deps.issue_public(row, _workshop_issue_images(issue_id, deps), user),
            })
            return
        expected_updated_at = str(body.get("expected_updated_at") or "").strip()
        if expected_updated_at and expected_updated_at != str(row["updated_at"]):
            raise ApiError(HTTPStatus.CONFLICT, "问题已被其他人更新，请刷新后重试")
        updated = deps.now_iso()
        with deps.db_lock, deps.db() as connection:
            changed = connection.execute(
                "UPDATE workshop_issues SET resolution_status = 'open', updated_at = ? "
                "WHERE id = ? AND updated_at = ?",
                (updated, issue_id, row["updated_at"]),
            ).rowcount
            if not changed:
                raise ApiError(HTTPStatus.CONFLICT, "问题已被其他人更新，请刷新后重试")
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                (user["id"], f"workshop_reopen:{issue_id}", row["user_id"], updated),
            )
    next_row = _workshop_issue_row(issue_id, user, deps)
    images = _workshop_issue_images(issue_id, deps)
    handler.send_json({
        "message": "问题已重新打开",
        "issue": deps.issue_public(next_row, images, user),
    })

def list_workshop_issues(handler: Any, deps: WorkshopDependencies) -> None:
    """按日期返回全部已发布问题、图片元数据及闭环统计。

    图片一次性批量查询后在内存中按问题编号分组，避免为每条问题再执行一次 SQL 的
    N+1 查询。草稿不进入跨账号列表和管理看板。
    """
    user = handler.require_user()
    query = parse_qs(urlparse(handler.path).query)
    issue_date = deps.issue_date(query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0])
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            workshop_issue_select() +
            "WHERE w.issue_date = ? AND w.status = 'published' ORDER BY w.created_at DESC",
            (issue_date,),
        ).fetchall()
        image_rows = connection.execute(
            "SELECT i.*, w.user_id FROM workshop_issue_images i "
            "JOIN workshop_issues w ON w.id = i.issue_id "
            "WHERE w.issue_date = ? AND w.status = 'published' "
            "ORDER BY i.issue_id, i.sort_order, i.created_at",
            (issue_date,),
        ).fetchall()
    images_by_issue: dict[str, list[sqlite3.Row]] = {}
    for image in image_rows:
        images_by_issue.setdefault(str(image["issue_id"]), []).append(image)
    issues = [
        deps.issue_public(row, images_by_issue.get(str(row["id"]), []), user)
        for row in rows
    ]
    resolved_count = sum(issue["resolution_status"] == "resolved" for issue in issues)  # ``bool`` 可直接求和得到闭环数量。
    handler.send_json({
        "date": issue_date,
        "issues": issues,
        "summary": {
            "issue_count": len(issues),
            "image_count": len(image_rows),
            "open_count": len(issues) - resolved_count,
            "resolved_count": resolved_count,
        },
    })

def download_workshop_issue_image(handler: Any, path: str, deps: WorkshopDependencies) -> None:
    """在校验问题可见性、图片归属和受控路径后以内联返回现场图片。

    已发布问题图片对所有登录账号可见；草稿图片仅发布者和管理员可见。无权限与真实
    不存在统一返回资源不存在，避免泄露草稿编号；数据库命中后仍校验真实文件位于该
    账号的问题目录内，并使用短时私有缓存。
    """
    user = handler.require_user()
    issue_id, image_id = _workshop_image_ids(path)
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT i.*, w.user_id, w.status FROM workshop_issue_images i "
            "JOIN workshop_issues w ON w.id = i.issue_id "
            "WHERE i.id = ? AND i.issue_id = ?",
            (image_id, issue_id),
        ).fetchone()
    if row is None or (  # 对无权限者也返回“不存在”，避免泄露草稿编号是否真实存在。
        row["status"] != "published"
        and int(row["user_id"]) != int(user["id"])
        and user["role"] != "admin"
    ):
        raise ApiError(HTTPStatus.NOT_FOUND, "现场图片不存在")
    target = deps.resolve_image_path(row)  # 解析器负责确认数据库路径仍位于该账号的问题目录内。
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "现场图片已被移动或删除")
    handler.send_file(
        target,
        content_type=row["content_type"] or "application/octet-stream",
        file_name=str(row["name"]),
        disposition="inline",
        cache_control="private, max-age=300",
    )

def delete_workshop_issue_image(handler: Any, path: str, deps: WorkshopDependencies) -> None:
    """删除指定图片，并在失败时恢复暂存文件。

    可编辑的已发布问题允许修正图片，但强制图片类型至少保留一张。文件先原子改名为
    ``.deleting`` 暂存，再删除数据库记录；数据库失败时把暂存文件移回原处。
    """
    user = handler.require_user()
    issue_id, image_id = _workshop_image_ids(path)
    row = _workshop_issue_row(issue_id, user, deps, manage=True)
    if not deps.can_edit(row, user):
        raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长本人或管理员可以编辑已发布问题")
    with deps.storage_lock:
        with deps.db_lock, deps.db() as connection:
            image = connection.execute(
                "SELECT i.*, w.user_id FROM workshop_issue_images i "
                "JOIN workshop_issues w ON w.id = i.issue_id "
                "WHERE i.id = ? AND i.issue_id = ?",
                (image_id, issue_id),
            ).fetchone()
            if image is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "现场图片不存在")
            image_count = int(connection.execute(
                "SELECT COUNT(*) AS n FROM workshop_issue_images WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()["n"])
            category = deps.workshop_core.normalize_workshop_category(row["category"], dict(row))
            if (
                row["status"] == "published"
                and category in deps.workshop_core.WORKSHOP_ISSUE_IMAGE_REQUIRED_CATEGORIES
                and image_count <= 1
            ):
                raise ApiError(HTTPStatus.BAD_REQUEST, "该问题类型至少需要保留一张现场图片")
        target = deps.resolve_image_path(image)
        staging = target.with_name(f".{target.name}.{uuid.uuid4().hex}.deleting")  # 同目录暂存确保 ``os.replace`` 原子执行。
        if target.is_file():
            os.replace(target, staging)
        try:
            updated = deps.now_iso()
            with deps.db_lock, deps.db() as connection:
                changed = connection.execute(
                    "DELETE FROM workshop_issue_images WHERE id = ? AND issue_id = ?",
                    (image_id, issue_id),
                ).rowcount
                if not changed:
                    raise ApiError(HTTPStatus.CONFLICT, "图片状态已经发生变化")
                connection.execute(
                    "UPDATE workshop_issues SET updated_at = ? WHERE id = ?",
                    (updated, issue_id),
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (user["id"], f"workshop_image_delete:{issue_id}:{image_id}", row["user_id"], updated),
                )
        except Exception:
            if staging.is_file() and not target.exists():
                os.replace(staging, target)
            raise
        staging.unlink(missing_ok=True)  # 数据库事务成功后才真正清除文件。
    next_row = _workshop_issue_row(issue_id, user, deps)
    images = _workshop_issue_images(issue_id, deps)
    handler.send_json({
        "message": "现场图片已删除",
        "issue": deps.issue_public(next_row, images, user),
    })

def export_workshop_issues(handler: Any, deps: WorkshopDependencies) -> None:
    """按日期范围导出符合标准模板的现场问题报表。

    导出数据只包含已发布问题；图片路径在服务端逐个验证存在后才交给 Core 嵌入 Excel。
    报表生成于当前用户专属临时目录，并在响应完成后自动清理，不形成长期输出缓存。
    """
    user = handler.require_user()
    query = parse_qs(urlparse(handler.path).query)
    start_date, end_date = deps.export_range(query)
    deps.write_audit(int(user["id"]), f"export_workshop:{start_date}:{end_date}")  # 日期范围进入审计动作，便于追踪批量导出。
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            workshop_issue_select() +
            "WHERE w.issue_date BETWEEN ? AND ? AND w.status = 'published' "
            "ORDER BY w.issue_date, w.created_at, w.id",
            (start_date, end_date),
        ).fetchall()
        image_rows = connection.execute(
            "SELECT i.*, w.user_id FROM workshop_issue_images i "
            "JOIN workshop_issues w ON w.id = i.issue_id "
            "WHERE w.issue_date BETWEEN ? AND ? AND w.status = 'published' "
            "ORDER BY i.issue_id, i.sort_order, i.created_at",
            (start_date, end_date),
        ).fetchall()
    images_by_issue: dict[str, list[dict[str, object]]] = {}
    for image in image_rows:
        target = deps.resolve_image_path(image)
        if target.is_file():  # 数据库有记录但文件遗失时跳过该图，避免整份报表无法导出。
            images_by_issue.setdefault(str(image["issue_id"]), []).append({
                "name": image["name"], "path": str(target),
            })
    issues = [{
        "issue_date": row["issue_date"], "cause": row["cause"],
        "primary_owner": row["primary_owner"], "secondary_owner": row["secondary_owner"],
        "notes": row["notes"], "uploader_name": row["display_name"],
        "category": row["category"] if "category" in row.keys() else "other",
        "severity": row["severity"] if "severity" in row.keys() else "normal",
        "resolution_status": row["resolution_status"] if "resolution_status" in row.keys() else "open",
        "resolution_note": row["resolution_note"] if "resolution_note" in row.keys() else "",
        "resolved_at": row["resolved_at"] if "resolved_at" in row.keys() else "",
        "resolved_by_name": row["resolved_by_name"] if "resolved_by_name" in row.keys() else "",
        **{
            field: row[field] if field in row.keys() else ""
            for field in deps.template_fields
        },
        "created_at": row["created_at"],
        "images": images_by_issue.get(str(row["id"]), []),
    } for row in rows]
    export_root = deps.data_root / "users" / str(user["id"]) / "workshop-exports"  # 临时文件也按用户隔离。
    export_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="report-", dir=export_root) as temp_name:
        result = deps.workshop_core.run(
            issues, start_date=start_date, end_date=end_date, out_dir=temp_name,
        )
        target = Path(str(result["out_file"]))
        handler.send_file(
            target,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

def delete_workshop_issue(handler: Any, path: str, deps: WorkshopDependencies) -> None:
    """按权限删除草稿，或把已发布问题和图片整体移动到回收站。

    草稿从未对其他用户公开，可直接删除；已发布问题必须建立可恢复的回收站记录。
    已发布文件先移动到回收站载荷目录，再删除数据库记录；任一步失败都会把目录移回。
    """
    user = handler.require_user()
    issue_id = _workshop_issue_id(path)
    row = _workshop_issue_row(issue_id, user, deps, manage=True)
    if not deps.can_delete(row, user):
        raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长本人或管理员可以处理已发布问题")
    folder = deps.issue_dir(int(row["user_id"]), issue_id)
    if row["status"] == "draft":
        with deps.storage_lock:
            shutil.rmtree(folder, ignore_errors=True)
            with deps.db_lock, deps.db() as connection:
                connection.execute("DELETE FROM workshop_issues WHERE id = ?", (issue_id,))
        handler.send_json({"message": "未发布草稿已删除"})
        return
    images = _workshop_issue_images(issue_id, deps)
    trash_id = uuid.uuid4().hex
    relative = folder.resolve().relative_to(deps.data_root.resolve()).as_posix()  # 只保存相对路径，部署目录变化后仍可恢复。
    payload = deps.data_root / "trash" / trash_id / "payload"
    size = deps.tree_size(folder)
    label = f"{row['issue_date']} · {str(row['cause'])[:36]}"
    with deps.storage_lock:
        if folder.exists():
            payload.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(payload))  # 先保全图片，再移除数据库记录，避免不可恢复的数据丢失。
        try:
            with deps.db_lock, deps.db() as connection:
                changed = connection.execute(
                    "DELETE FROM workshop_issues WHERE id = ? AND status = 'published'", (issue_id,)
                ).rowcount
                if not changed:
                    raise ApiError(HTTPStatus.CONFLICT, "问题状态已经发生变化")
                connection.execute(
                    "INSERT INTO trash_items(id, kind, label, record_json, original_path, size, deleted_by, deleted_at) "
                    "VALUES (?, 'workshop_issue', ?, ?, ?, ?, ?, ?)",
                    (trash_id, label, json.dumps({
                        "issue": dict(row), "images": [dict(image) for image in images],
                    }, ensure_ascii=False), relative, size, user["id"], deps.now_iso()),
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (user["id"], f"workshop_trash:{issue_id}", row["user_id"], deps.now_iso()),
                )
        except Exception:
            if payload.exists() and not folder.exists():
                folder.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(payload), str(folder))
            raise  # 数据库删除或回收站登记失败时恢复原目录，问题仍保持可用。
    handler.send_json({"message": "问题已移入回收站"})
