"""共享文件数据库的上传、检索、替换、下载和回收站服务。

文件内容按上传账号隔离保存，数据库只记录受控路径和检索元数据。修改操作同时
维护主分类与多分类关联表；任何磁盘操作失败都应回滚数据库或恢复旧文件。
"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from web_backend.errors import ApiError


@dataclass(frozen=True)
class LibraryDependencies:
    """共享文件服务的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    data_root: Path
    storage_lock: Any
    max_upload_bytes: int
    user_quota_bytes: int
    allowed_roles: frozenset[str]
    now_iso: Callable[[], str]
    safe_name: Callable[[object], str]
    library_scope: Callable[[object], str]
    library_category: Callable[[object], str]
    library_category_catalog: Callable[[], list[dict[str, object]]]
    classify_library_file: Callable[..., dict[str, object]]
    library_file_public: Callable[[Any, Any], dict[str, object]]
    resolve_library_path: Callable[[Any], Path]
    write_audit: Callable[[int | None, str, int | None], None]
    unknown_category: str


def _library_select() -> str:
    """返回文件库记录及上传者、最后修改者信息的公共查询片段。"""
    return (
        "SELECT f.*, owner.username AS owner_username, owner.display_name AS owner_display_name, "
        "editor.username AS editor_username, editor.display_name AS editor_display_name "
        "FROM library_files f JOIN users owner ON owner.id = f.owner_id "
        "LEFT JOIN users editor ON editor.id = f.updated_by "
    )


def _request_length(headers: Any, maximum: int) -> int:
    """读取并校验上传请求长度，避免空文件和超限文件进入存储层。"""
    try:
        length = int(headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件大小无效") from exc
    if length <= 0:
        raise ApiError(HTTPStatus.BAD_REQUEST, "上传文件为空")
    if length > maximum:
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "单个文件不能超过 200 MB")
    return length


def _check_library_quota(
    connection: Any,
    owner_id: int,
    incoming: int,
    quota_bytes: int,
    replacing: int = 0,
) -> None:
    """校验账号文件库用量，替换文件时扣除原文件所占空间。"""
    used = int(connection.execute(  # 配额按所有者统计，团队可见性不会改变空间归属。
        "SELECT COALESCE(SUM(size), 0) AS n FROM library_files WHERE owner_id = ?",
        (owner_id,),
    ).fetchone()["n"])
    if used - replacing + incoming > quota_bytes:  # 替换时先扣除旧文件大小，避免等量替换被错误拒绝。
        raise ApiError(HTTPStatus.INSUFFICIENT_STORAGE, "账号数据库空间不足，请删除不再需要的文件")


def _library_file_id(path: str, suffix: str = "") -> str:
    """从文件库接口路径中解析 32 位文件编号。"""
    prefix = "/api/library/files/"
    ending = f"/{suffix}" if suffix else ""
    if not path.startswith(prefix) or ending and not path.endswith(ending):
        raise ApiError(HTTPStatus.BAD_REQUEST, "数据库文件编号无效")
    value = path[len(prefix):-len(ending)] if ending else path[len(prefix):]
    value = unquote(value).strip("/")  # URL 解码后再校验，阻止编码斜杠或额外路径段混入编号。
    if len(value) != 32 or not value.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "数据库文件编号无效")
    return value


def _library_row(
    file_id: str,
    user: Any,
    deps: LibraryDependencies,
    *,
    manage: bool = False,
) -> Any:
    """按可见范围读取文件，并在修改场景校验所有者权限。"""
    if user["role"] not in deps.allowed_roles:
        raise ApiError(HTTPStatus.FORBIDDEN, "只有班组长或管理员可以使用数据库")
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(  # 团队文件可见、私有文件仅所有者可见，管理员拥有全局读取权限。
            _library_select() +
            "WHERE f.id = ? AND (f.scope = 'team' OR f.owner_id = ? OR ? = 'admin')",
            (file_id, user["id"], user["role"]),
        ).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "数据库文件不存在")
    if manage and int(row["owner_id"]) != int(user["id"]) and user["role"] != "admin":  # 班组长可查看团队文件，但不能修改他人文件。
        raise ApiError(HTTPStatus.FORBIDDEN, "只有上传者或管理员可以修改该文件")
    return row


def upload_library_file(handler: Any, deps: LibraryDependencies) -> None:
    """上传共享数据库文件，执行分类识别、配额检查和元数据登记。

    存储锁把配额读取、文件落盘、桌面端分类器调用和数据库登记串成一个互斥流程；临时
    文件名避免分类器读到半上传内容，原子改名后才进入正式文件名。分类结果同时写入主
    分类列、JSON 多分类列和关联表，任一步失败都会删除整个隔离目录。
    """
    user = handler.require_role("admin", "team_leader")
    parsed = urlparse(handler.path)
    query = parse_qs(parsed.query)
    name = deps.safe_name(query.get("name", [""])[0])
    scope = deps.library_scope(query.get("scope", ["team"])[0])
    description = str(query.get("description", [""])[0]).strip()
    if len(description) > 500:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件说明不能超过 500 字")
    length = _request_length(handler.headers, deps.max_upload_bytes)
    file_id = uuid.uuid4().hex  # 文件编号同时作为隔离目录名，避免原始文件名影响路径结构。
    folder = deps.data_root / "users" / str(user["id"]) / "library" / file_id
    target = folder / name
    temp = folder / f".{file_id}.uploading"  # 完整上传前不使用正式文件名，分类器不会读到半文件。
    created = deps.now_iso()
    with deps.storage_lock:  # 配额检查、文件写入和元数据登记串行执行，避免并发上传同时越过配额。
        with deps.db_lock, deps.db() as connection:
            _check_library_quota(
                connection, int(user["id"]), length, deps.user_quota_bytes,
            )
        folder.mkdir(parents=True, exist_ok=False)
        remaining = length
        try:
            with temp.open("wb") as stream:
                while remaining:
                    chunk = handler.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "文件上传不完整")
                    stream.write(chunk)
                    remaining -= len(chunk)
            os.replace(temp, target)  # 同目录原子改名把“上传完成”与正式文件可见性绑定。
            classification = deps.classify_library_file(  # 复用桌面端分类器，Web 不维护第二套业务识别规则。
                target,
                log=lambda message: handler.log_message("数据库文件分类提示：%s", message),
            )
            with deps.db_lock, deps.db() as connection:
                connection.execute(
                    "INSERT INTO library_files(id, owner_id, name, path, size, content_type, description, scope, created_at, updated_at, updated_by, "
                    "category, categories, confidence, signals, sheet, category_sheets) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        file_id, user["id"], name, str(target), length,
                        mimetypes.guess_type(name)[0] or "application/octet-stream",
                        description, scope, created, created, user["id"], classification["category"],
                        json.dumps(classification["categories"], ensure_ascii=False), classification["confidence"],
                        json.dumps(classification["signals"], ensure_ascii=False), classification["sheet"],
                        json.dumps(classification["category_sheets"], ensure_ascii=False),
                    ),
                )
                connection.executemany(  # 多分类关联表支持一个文件同时出现在多个业务筛选中。
                    "INSERT INTO library_file_categories(file_id, category) VALUES (?, ?)",
                    [(file_id, category) for category in classification["categories"]],
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (user["id"], f"library_upload:{file_id}", user["id"], created),
                )
                row = connection.execute(
                    _library_select() + "WHERE f.id = ?", (file_id,)
                ).fetchone()
        except Exception:  # 上传、分类或写库任一步失败都删除整个文件目录，防止孤立内容占用配额。
            shutil.rmtree(folder, ignore_errors=True)
            raise
    handler.send_json({"message": "文件已上传到数据库", "file": deps.library_file_public(row, user)}, HTTPStatus.CREATED)

def list_library_files(handler: Any, deps: LibraryDependencies) -> None:
    """按权限、分类、范围和关键词分页筛选共享数据库文件。

    可见性条件始终由 SQL 绑定当前账号和角色，团队文件、私有文件及管理员全局读取不会
    依赖前端隐藏。分页、分类关联表、关键词和空间摘要在同一数据库锁域内读取，确保
    返回的文件列表与配额统计来自近似同一快照，空结果仍保持稳定的第一页结构。
    """
    user = handler.require_role("admin", "team_leader")
    query = parse_qs(urlparse(handler.path).query)
    try:
        page = max(1, int(query.get("page", ["1"])[0]))
        page_size = min(100, max(1, int(query.get("page_size", ["20"])[0])))  # 服务端限制分页上限，前端不能请求无限列表。
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "分页参数无效") from exc
    mode = str(query.get("scope", ["all"])[0]).strip().lower()
    if mode not in {"all", "team", "private", "mine"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "筛选范围无效")
    category_filter = str(query.get("category", [""])[0]).strip()
    if category_filter:
        category_filter = deps.library_category(category_filter)
    needle = str(query.get("q", [""])[0]).strip()[:100]
    where = ["(f.scope = 'team' OR f.owner_id = ? OR ? = 'admin')"]  # 可见性条件始终存在，后续筛选只能收窄范围。
    params: list[object] = [user["id"], user["role"]]
    if mode == "team":
        where.append("f.scope = 'team'")
    elif mode == "private":
        where.append("f.scope = 'private'")
    elif mode == "mine":
        where.append("f.owner_id = ?")
        params.append(user["id"])
    if category_filter:
        where.append(  # 使用关联表筛选多分类，不能只检查主 category 字段。
            "EXISTS (SELECT 1 FROM library_file_categories fc "
            "WHERE fc.file_id = f.id AND fc.category = ?)"
        )
        params.append(category_filter)
    if needle:
        where.append("(f.name LIKE ? OR f.description LIKE ? OR owner.display_name LIKE ? OR owner.username LIKE ?)")
        like = f"%{needle}%"  # 查询值仍作为 SQL 参数绑定，不拼接进 SQL 结构。
        params.extend([like, like, like, like])
    condition = " AND ".join(where)
    with deps.db_lock, deps.db() as connection:
        total = int(connection.execute(
            "SELECT COUNT(*) AS n FROM library_files f JOIN users owner ON owner.id = f.owner_id WHERE " + condition,
            tuple(params),
        ).fetchone()["n"])
        pages = max(1, (total + page_size - 1) // page_size)  # 空结果也返回第一页，前端分页状态保持稳定。
        page = min(page, pages)
        rows = connection.execute(
            _library_select() + "WHERE " + condition +
            " ORDER BY f.updated_at DESC, f.id DESC LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
        summary = connection.execute(
            "SELECT COUNT(*) AS visible_count, "
            "SUM(CASE WHEN f.scope = 'team' THEN 1 ELSE 0 END) AS team_count, "
            "SUM(CASE WHEN f.owner_id = ? THEN 1 ELSE 0 END) AS own_count "
            "FROM library_files f WHERE f.scope = 'team' OR f.owner_id = ? OR ? = 'admin'",
            (user["id"], user["id"], user["role"]),
        ).fetchone()
        own_bytes = int(connection.execute(
            "SELECT COALESCE(SUM(size), 0) AS n FROM library_files WHERE owner_id = ?",
            (user["id"],),
        ).fetchone()["n"])
        category_rows = connection.execute(
            "SELECT fc.category, COUNT(*) AS n FROM library_file_categories fc "
            "JOIN library_files f ON f.id = fc.file_id "
            "WHERE f.scope = 'team' OR f.owner_id = ? OR ? = 'admin' GROUP BY fc.category",
            (user["id"], user["role"]),
        ).fetchall()
    handler.send_json({
        "files": [deps.library_file_public(row, user) for row in rows],
        "pagination": {"page": page, "page_size": page_size, "total": total, "pages": pages},
        "summary": {
            "visible_count": int(summary["visible_count"] or 0),
            "team_count": int(summary["team_count"] or 0),
            "own_count": int(summary["own_count"] or 0),
            "own_bytes": own_bytes,
            "quota_bytes": deps.user_quota_bytes,
            "category_counts": {row["category"]: int(row["n"]) for row in category_rows},
        },
        "categories": deps.library_category_catalog(),
    })

def update_library_file(handler: Any, path: str, body: dict[str, object], deps: LibraryDependencies) -> None:
    """更新共享文件的名称、分类、说明和访问范围。

    只有所有者或管理员能修改，班组长对他人文件仅有读取权。人工重新分类会把置信度
    固定为确定值并重建多分类关联，避免旧自动识别信号继续误导筛选；未改分类时保留
    原识别证据和置信度。
    """
    user = handler.require_user()
    file_id = _library_file_id(path)
    row = _library_row(file_id, user, deps, manage=True)
    raw_name = body.get("name", row["name"])
    if not str(raw_name or "").strip():
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件名不能为空")
    name = deps.safe_name(str(raw_name))
    description = str(body.get("description", row["description"]) or "").strip()
    scope = deps.library_scope(body.get("scope", row["scope"]))
    category = deps.library_category(body.get("category", row["category"]))
    if len(description) > 500:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件说明不能超过 500 字")
    category_changed = category != str(row["category"] or deps.unknown_category)  # 人工改类后不再保留自动识别的置信度与信号。
    if category_changed:
        category_values = (
            category, json.dumps([category], ensure_ascii=False), 100,  # 人工选择视为确定结论，置信度固定为 100。
            json.dumps(["人工指定类别"], ensure_ascii=False), "", "{}",
        )
    else:
        category_values = (
            row["category"], row["categories"], row["confidence"], row["signals"],
            row["sheet"], row["category_sheets"],
        )
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute(
            "UPDATE library_files SET name = ?, description = ?, scope = ?, updated_at = ?, updated_by = ?, "
            "category = ?, categories = ?, confidence = ?, signals = ?, sheet = ?, category_sheets = ? WHERE id = ?",
            (name, description, scope, updated, user["id"], *category_values, file_id),
        ).rowcount
        if changed:
            if category_changed:  # 主表与关联表必须同步重建，避免筛选结果仍含旧分类。
                connection.execute("DELETE FROM library_file_categories WHERE file_id = ?", (file_id,))
                connection.execute(
                    "INSERT INTO library_file_categories(file_id, category) VALUES (?, ?)",
                    (file_id, category),
                )
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                (user["id"], f"library_{'reclassify' if category_changed else 'update'}:{file_id}", row["owner_id"], updated),
            )
            next_row = connection.execute(
                _library_select() + "WHERE f.id = ?", (file_id,)
            ).fetchone()
    if not changed:
        raise ApiError(HTTPStatus.NOT_FOUND, "数据库文件不存在")
    handler.send_json({"message": "文件信息已更新", "file": deps.library_file_public(next_row, user)})

def replace_library_file(handler: Any, path: str, deps: LibraryDependencies) -> None:
    """替换共享文件内容，并重新识别分类、更新时间和校验值。

    新内容先写入临时文件，旧内容移动到同目录备份位，再原子替换正式路径；分类器和
    数据库更新成功后才删除旧备份。任一步失败都清理新内容并恢复旧文件，确保数据库中
    的路径始终指向可读的完整文件，且替换过程受存储锁保护。
    """
    user = handler.require_user()
    file_id = _library_file_id(path, "content")
    row = _library_row(file_id, user, deps, manage=True)
    query = parse_qs(urlparse(handler.path).query)
    name = deps.safe_name(query.get("name", [row["name"]])[0])
    length = _request_length(handler.headers, deps.max_upload_bytes)
    old_target = deps.resolve_library_path(row)
    folder = old_target.parent
    new_target = folder / name
    temp = folder / f".{file_id}.replacement"
    backup = folder / f".{file_id}.previous"  # 数据库更新成功前保留旧内容，失败可原位恢复。
    updated = deps.now_iso()
    with deps.storage_lock:  # 替换期间阻止下载、删除或另一替换操作看到中间状态。
        with deps.db_lock, deps.db() as connection:
            _check_library_quota(
                connection, int(row["owner_id"]), length, deps.user_quota_bytes,
                int(row["size"] or 0),
            )
        remaining = length
        try:
            with temp.open("wb") as stream:
                while remaining:
                    chunk = handler.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "文件上传不完整")
                    stream.write(chunk)
                    remaining -= len(chunk)
            if old_target.is_file():
                os.replace(old_target, backup)
            os.replace(temp, new_target)  # 新文件先就位再更新数据库，路径永远指向完整文件。
            classification = deps.classify_library_file(
                new_target,
                log=lambda message: handler.log_message("数据库文件分类提示：%s", message),
            )
            with deps.db_lock, deps.db() as connection:
                changed = connection.execute(
                    "UPDATE library_files SET name = ?, path = ?, size = ?, content_type = ?, updated_at = ?, updated_by = ?, "
                    "category = ?, categories = ?, confidence = ?, signals = ?, sheet = ?, category_sheets = ? WHERE id = ?",
                    (
                        name, str(new_target), length,
                        mimetypes.guess_type(name)[0] or "application/octet-stream",
                        updated, user["id"], classification["category"],
                        json.dumps(classification["categories"], ensure_ascii=False), classification["confidence"],
                        json.dumps(classification["signals"], ensure_ascii=False), classification["sheet"],
                        json.dumps(classification["category_sheets"], ensure_ascii=False), file_id,
                    ),
                ).rowcount
                if not changed:
                    raise ApiError(HTTPStatus.NOT_FOUND, "数据库文件不存在")
                connection.execute("DELETE FROM library_file_categories WHERE file_id = ?", (file_id,))
                connection.executemany(
                    "INSERT INTO library_file_categories(file_id, category) VALUES (?, ?)",
                    [(file_id, category) for category in classification["categories"]],
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (user["id"], f"library_replace:{file_id}", row["owner_id"], updated),
                )
                next_row = connection.execute(
                    _library_select() + "WHERE f.id = ?", (file_id,)
                ).fetchone()
            backup.unlink(missing_ok=True)  # 元数据提交完成后旧内容才失去恢复价值。
        except Exception:  # 清理新文件并恢复旧文件，保证数据库仍指向可读内容。
            temp.unlink(missing_ok=True)
            new_target.unlink(missing_ok=True)
            if backup.exists():
                os.replace(backup, old_target)
            raise
    handler.send_json({"message": "文件内容已替换", "file": deps.library_file_public(next_row, user)})

def download_library_file(handler: Any, path: str, deps: LibraryDependencies) -> None:
    """校验共享文件访问权限后发送原始文件。"""
    user = handler.require_role("admin", "team_leader")
    file_id = _library_file_id(path, "download")
    row = _library_row(file_id, user, deps)
    target = deps.resolve_library_path(row)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "数据库文件已被移动或删除")
    deps.write_audit(int(user["id"]), f"download_library:{row['name']}")
    handler.send_file(
        target,
        content_type=row["content_type"] or "application/octet-stream",
        file_name=str(row["name"]),
    )

def delete_library_file(handler: Any, path: str, deps: LibraryDependencies) -> None:
    """把共享文件及其元数据移动到可恢复回收站。

    删除只允许所有者或管理员执行；文件先移到回收站载荷，再删除主表并写入完整记录，
    失败时移回原路径。记录保存相对路径和分类元数据，后续恢复服务可以在新部署目录
    下重新建立索引而不依赖旧绝对路径。
    """
    user = handler.require_user()
    file_id = _library_file_id(path)
    row = _library_row(file_id, user, deps, manage=True)
    target = deps.resolve_library_path(row)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "数据库文件已被移动或删除")
    trash_id = uuid.uuid4().hex
    relative = target.relative_to(deps.data_root.resolve()).as_posix()  # 回收站保存相对路径，迁移部署目录后仍能恢复。
    payload = deps.data_root / "trash" / trash_id / "payload"
    size = target.stat().st_size
    with deps.storage_lock:  # 文件移动与记录删除不能和下载、替换并发执行。
        payload.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(payload))
        try:
            with deps.db_lock, deps.db() as connection:
                connection.execute("DELETE FROM library_files WHERE id = ?", (file_id,))
                connection.execute(
                    "INSERT INTO trash_items(id, kind, label, record_json, original_path, size, deleted_by, deleted_at) "
                    "VALUES (?, 'library_file', ?, ?, ?, ?, ?, ?)",
                    (
                        trash_id, row["name"], json.dumps(dict(row), ensure_ascii=False),
                        relative, size, user["id"], deps.now_iso(),
                    ),
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (user["id"], f"library_trash:{file_id}", row["owner_id"], deps.now_iso()),
                )
        except Exception:  # 回收站记录写入失败时把文件移回原位，避免“文件消失但无恢复记录”。
            if payload.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(payload), str(target))
            raise
    handler.send_json({"message": "文件已移入回收站"})
