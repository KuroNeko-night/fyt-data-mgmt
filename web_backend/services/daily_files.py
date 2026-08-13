"""日清生产计划、到料成品、安全检查资料与报告下载服务。

本模块集中处理二进制上传、Core 分析、账号目录隔离、受控下载和可补偿回收站事务。
文件解析规则仍由各 Core 提供，本层不复制表格业务算法。
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from web_backend.errors import ApiError
from web_backend.services.daily_management_types import DailyManagementDependencies


def _daily_plan_id(path: str, suffix: str = "") -> str:
    """从生产计划接口路径提取计划编号，并可剥离 ``download`` 等动作后缀。"""
    prefix = "/api/admin/daily-production-plans/"
    ending = f"/{suffix}" if suffix else ""
    if not path.startswith(prefix) or (ending and not path.endswith(ending)):
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产计划编号无效")
    value = path[len(prefix):-len(ending)] if ending else path[len(prefix):]
    value = unquote(value).strip("/")  # 解码后再验证，避免编码斜杠进入后续路径逻辑。
    if len(value) != 32 or not value.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产计划编号无效")
    return value


def _daily_source_id(path: str, suffix: str = "") -> str:
    """从日清资料接口路径提取上传编号，并校验固定长度标识。"""
    prefix = "/api/admin/daily-source-uploads/"
    ending = f"/{suffix}" if suffix else ""
    if not path.startswith(prefix) or (ending and not path.endswith(ending)):
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清资料编号无效")
    value = path[len(prefix):-len(ending)] if ending else path[len(prefix):]
    value = unquote(value).strip("/")
    if len(value) != 32 or not value.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清资料编号无效")
    return value


def _request_length(headers: Any, maximum: int) -> int:
    """读取上传长度并执行服务端统一的请求体上限检查。

    服务使用原始流接收文件，必须在读取前获得可信的 ``Content-Length``，否则无法判断
    上传是否中途断开，也无法限制慢速、无限请求占用连接。
    """
    try:
        length = int(headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件大小无效") from exc
    if length <= 0:
        raise ApiError(HTTPStatus.BAD_REQUEST, "上传文件为空")
    if length > maximum:
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "单个文件不能超过 200 MB")
    return length


def _receive_upload_stream(
    handler: Any,
    target: Path,
    length: int,
    *,
    incomplete_message: str,
) -> None:
    """按声明长度把请求体流式写入目标文件，拒绝中途断开的上传。"""
    remaining = length
    with target.open("wb") as stream:
        while remaining:
            chunk = handler.rfile.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ApiError(HTTPStatus.BAD_REQUEST, incomplete_message)
            stream.write(chunk)
            remaining -= len(chunk)

def _daily_plan_select() -> str:
    """返回生产计划及上传者显示名称的公共查询片段。"""
    return (
        "SELECT p.*, COALESCE(u.display_name, u.username, '') AS uploaded_by_name "
        "FROM daily_production_plans p LEFT JOIN users u ON u.id = p.uploaded_by "
    )


def _resolve_daily_plan_path(row: Any, deps: DailyManagementDependencies) -> Path:
    """将生产计划记录解析到允许的数据目录内。

    ``uploaded_by is None`` 兼容迁移前存放在公共数据目录的旧记录；新记录必须位于上传者
    专属目录。数据库路径在使用前解析并做父目录校验，不能直接信任历史字符串。
    """
    target = Path(row["path"]).resolve()
    if row["uploaded_by"] is None:
        root = deps.data_root.resolve()
    else:
        root = (deps.data_root / "users" / str(row["uploaded_by"]) / "daily-production-plans").resolve()
    if root not in target.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产计划文件路径无效")
    return target


def _daily_source_select() -> str:
    """返回日清资料及上传者显示名称的公共查询片段。"""
    return (
        "SELECT s.*, COALESCE(u.display_name, u.username, '') AS uploaded_by_name "
        "FROM daily_source_uploads s LEFT JOIN users u ON u.id = s.uploaded_by "
    )


def _resolve_daily_source_path(row: Any, deps: DailyManagementDependencies) -> Path:
    """将日清资料记录解析到允许的数据目录内，兼容旧公共路径并阻止越界访问。"""
    target = Path(row["path"]).resolve()
    if row["uploaded_by"] is None:
        root = deps.data_root.resolve()
    else:
        root = (deps.data_root / "users" / str(row["uploaded_by"]) / "daily-sources").resolve()
    if root not in target.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清资料文件路径无效")
    return target


@dataclass(frozen=True)
class DailyFileTrashSpec:
    """日清文件记录进入回收站时的受控数据库参数。"""

    table: str
    kind: str
    audit_prefix: str
    conflict_message: str


@dataclass(frozen=True)
class DailySourceUploadSpec:
    """一次日清成品资料上传在落盘前已经验证的请求参数。"""

    kind: str
    report_date: str
    original_name: str
    length: int
    upload_id: str
    folder: Path
    target: Path


_PLAN_TRASH = DailyFileTrashSpec(
    table="daily_production_plans",
    kind="daily_production_plan",
    audit_prefix="daily_plan_trash",
    conflict_message="生产计划状态已经发生变化",
)
_SOURCE_TRASH = DailyFileTrashSpec(
    table="daily_source_uploads",
    kind="daily_source_upload",
    audit_prefix="daily_source_trash",
    conflict_message="日清资料状态已经发生变化",
)


def _move_daily_file_to_trash(
    row: Any,
    record_id: str,
    target: Path,
    actor_id: int,
    spec: DailyFileTrashSpec,
    deps: DailyManagementDependencies,
) -> None:
    """以可补偿事务把日清文件目录和数据库记录整体移入回收站。"""
    folder = target.parent
    trash_id = uuid.uuid4().hex
    relative = folder.resolve().relative_to(deps.data_root.resolve()).as_posix()
    payload = deps.data_root / "trash" / trash_id / "payload"
    size = deps.tree_size(folder)
    with deps.storage_lock:
        payload.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder), str(payload))
        try:
            deleted_at = deps.now_iso()
            with deps.db_lock, deps.db() as connection:
                changed = connection.execute(
                    f"DELETE FROM {spec.table} WHERE id = ?",
                    (record_id,),
                ).rowcount
                if not changed:
                    raise ApiError(HTTPStatus.CONFLICT, spec.conflict_message)
                connection.execute(
                    "INSERT INTO trash_items"
                    "(id, kind, label, record_json, original_path, size, deleted_by, deleted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        trash_id,
                        spec.kind,
                        row["original_name"],
                        json.dumps(dict(row), ensure_ascii=False),
                        relative,
                        size,
                        actor_id,
                        deleted_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                    (actor_id, f"{spec.audit_prefix}:{record_id}", deleted_at),
                )
        except Exception:
            if payload.exists() and not folder.exists():
                folder.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(payload), str(folder))
            raise

def upload_daily_production_plan(handler: Any, deps: DailyManagementDependencies) -> None:
    """接收生产计划文件，调用 Core 分析并保存可视化摘要。

    原文件按上传者和计划编号隔离。只有分析成功后才建立数据库记录；任意异常都会删除
    整个计划目录，防止无索引文件长期占用空间。
    """
    actor = handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date((query.get("date") or [deps.business_today().isoformat()])[0])
    original_name = deps.safe_name((query.get("name") or [""])[0])
    if Path(original_name).suffix.lower() not in deps.production_plan_core.SUPPORTED_EXTENSIONS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产计划仅支持 .xlsx 或 .xlsm 文件")
    length = _request_length(handler.headers, deps.request_max_upload_bytes)
    if length > deps.max_upload_bytes:
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "生产计划文件不能超过 50 MB")
    plan_id = uuid.uuid4().hex
    folder = deps.data_root / "users" / str(actor["id"]) / "daily-production-plans" / plan_id
    target = folder / original_name
    folder.mkdir(parents=True, exist_ok=True)
    try:
        _receive_upload_stream(
            handler,
            target,
            length,
            incomplete_message="生产计划文件上传不完整",
        )
        try:
            summary = deps.production_plan_core.analyze(target, report_date=report_date)  # 摘要供图表使用，不只是表格预览。
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        created = deps.now_iso()
        with deps.db_lock, deps.db() as connection:
            connection.execute(
                "INSERT INTO daily_production_plans(id, report_date, data_month, original_name, path, size, content_type, "
                "summary, uploaded_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, report_date, report_date[:7], original_name, str(target), length,
                 mimetypes.guess_type(original_name)[0] or "application/octet-stream",
                 json.dumps(summary, ensure_ascii=False), actor["id"], created, created),
            )
            row = connection.execute(_daily_plan_select() + "WHERE p.id = ?", (plan_id,)).fetchone()
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                (actor["id"], f"daily_plan_upload:{plan_id}", created),
            )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise  # 解析或入库失败时不保留孤儿上传目录。
    handler.send_json({"message": "生产计划已上传", "plan": deps.production_plan_public(row)}, HTTPStatus.CREATED)

def list_daily_production_plans(handler: Any, deps: DailyManagementDependencies) -> None:
    """返回指定日期的生产计划及其已解析摘要。"""
    handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date((query.get("date") or [deps.business_today().isoformat()])[0])
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            _daily_plan_select() + "WHERE p.report_date = ? ORDER BY p.updated_at DESC, p.id",
            (report_date,),
        ).fetchall()
    handler.send_json({"date": report_date, "plans": [deps.production_plan_public(row) for row in rows]})

def download_daily_production_plan(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """下载生产计划原文件，并记录管理员审计事件。"""
    actor = handler.require_user(admin=True)
    plan_id = _daily_plan_id(path, "download")
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(_daily_plan_select() + "WHERE p.id = ?", (plan_id,)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "生产计划不存在")
    target = _resolve_daily_plan_path(row, deps)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "生产计划文件已丢失")
    deps.write_audit(int(actor["id"]), f"daily_plan_download:{plan_id}")
    handler.send_file(
        target,
        content_type=row["content_type"] or "application/octet-stream",
        file_name=str(row["original_name"]),
    )

def delete_daily_production_plan(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """将生产计划目录和数据库记录作为一个可补偿操作移入回收站。

    计划原文件与解析摘要位于同一隔离目录，删除时整体移动并保存相对恢复路径。数据库
    删除或回收站登记失败会把目录移回原位，成功后历史资料仍可由统一恢复器重建。
    """
    actor = handler.require_user(admin=True)
    plan_id = _daily_plan_id(path)
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(_daily_plan_select() + "WHERE p.id = ?", (plan_id,)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "生产计划不存在")
    target = _resolve_daily_plan_path(row, deps)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "生产计划文件已丢失，无法移入回收站")
    _move_daily_file_to_trash(
        row,
        plan_id,
        target,
        int(actor["id"]),
        _PLAN_TRASH,
        deps,
    )
    handler.send_json({"message": "生产计划已移入回收站"})


def _daily_source_upload_spec(
    handler: Any,
    actor_id: int,
    deps: DailyManagementDependencies,
) -> DailySourceUploadSpec:
    """解析并校验日清上传参数，尚未创建目录或读取请求体。"""
    query = parse_qs(urlparse(handler.path).query)
    kind = str((query.get("kind") or [""])[0]).strip().lower()
    if kind not in {"arrival", "safety"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清资料类型无效")
    report_date = deps.report_date(
        (query.get("date") or [deps.business_today().isoformat()])[0]
    )
    original_name = deps.safe_name((query.get("name") or [""])[0])
    supported = (
        deps.safety_check_core.SUPPORTED_EXTENSIONS
        if kind == "safety" else {".xlsx", ".xlsm"}
    )
    if Path(original_name).suffix.lower() not in supported:
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清资料仅支持 .xlsx 或 .xlsm 文件")
    length = _request_length(handler.headers, deps.request_max_upload_bytes)
    if length > deps.max_upload_bytes:
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "日清资料文件不能超过 50 MB")
    upload_id = uuid.uuid4().hex
    folder = deps.data_root / "users" / str(actor_id) / "daily-sources" / upload_id
    return DailySourceUploadSpec(
        kind=kind,
        report_date=report_date,
        original_name=original_name,
        length=length,
        upload_id=upload_id,
        folder=folder,
        target=folder / original_name,
    )


def _analyze_daily_source(
    spec: DailySourceUploadSpec,
    deps: DailyManagementDependencies,
) -> dict[str, object]:
    """调用对应 Core 解析成品资料，并拒绝表内日期与看板日期不一致。"""
    try:
        if spec.kind == "safety":
            summary = deps.safety_check_core.analyze(
                spec.target,
                image_dir=spec.folder / "images",
            )
            date_label = "文件内检查日期"
        else:
            summary = deps.arrival_core.analyze_finished_report(spec.target)
            date_label = "文件名中的到料日期"
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    file_date = str(summary.get("report_date") or "")
    if file_date and file_date != spec.report_date:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            f"{date_label}为 {file_date}，请切换到该日期后上传",
        )
    return summary


def _insert_daily_source(
    spec: DailySourceUploadSpec,
    summary: dict[str, object],
    actor_id: int,
    deps: DailyManagementDependencies,
) -> Any:
    """在一个 SQLite 事务中写入资料记录和审计记录，并返回展示所需联表行。"""
    created = deps.now_iso()
    content_type = mimetypes.guess_type(spec.original_name)[0] or "application/octet-stream"
    with deps.db_lock, deps.db() as connection:
        connection.execute(
            "INSERT INTO daily_source_uploads(id, kind, report_date, data_month, original_name, path, size, "
            "content_type, summary, uploaded_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                spec.upload_id, spec.kind, spec.report_date, spec.report_date[:7],
                spec.original_name, str(spec.target), spec.length, content_type,
                json.dumps(summary, ensure_ascii=False), actor_id, created, created,
            ),
        )
        row = connection.execute(
            _daily_source_select() + "WHERE s.id = ?", (spec.upload_id,),
        ).fetchone()
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor_id, f"daily_source_upload:{spec.kind}:{spec.upload_id}", created),
        )
    return row


def upload_daily_source(handler: Any, deps: DailyManagementDependencies) -> None:
    """接收成品到料或安全检查资料，解析后直接写入日清看板。

    此入口用于人工上传已经完成的业务成品，不替代“每日到料表制作”等业务模块。文件中
    已包含批次、料种和日期等信息，服务端只要求选择看板日期并核对解析出的文件日期。
    安全检查解析产生的图片与源文件保存在同一上传目录，便于整体回收和恢复。
    """
    actor = handler.require_user(admin=True)
    actor_id = int(actor["id"])
    spec = _daily_source_upload_spec(handler, actor_id, deps)
    spec.folder.mkdir(parents=True, exist_ok=True)
    try:
        _receive_upload_stream(
            handler,
            spec.target,
            spec.length,
            incomplete_message="日清资料文件上传不完整",
        )
        summary = _analyze_daily_source(spec, deps)
        # 文件先完整落盘并通过 Core 校验，数据库记录才可见；否则列表会短暂暴露无效路径。
        row = _insert_daily_source(spec, summary, actor_id, deps)
    except Exception:
        shutil.rmtree(spec.folder, ignore_errors=True)
        raise  # 文件日期不符、解析失败或入库失败都不留下不可见上传。
    title = "安全检查日报" if spec.kind == "safety" else "每日到料资料"
    handler.send_json({"message": f"{title}已上传并完成解析", "upload": deps.source_upload_public(row)}, HTTPStatus.CREATED)

def list_daily_sources(handler: Any, deps: DailyManagementDependencies) -> None:
    """按日期返回到料和安全检查资料，可选按资料类型过滤。"""
    handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date((query.get("date") or [deps.business_today().isoformat()])[0])
    kind = str((query.get("kind") or [""])[0]).strip().lower()
    if kind and kind not in {"arrival", "safety"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清资料类型无效")
    with deps.db_lock, deps.db() as connection:
        sql = _daily_source_select() + "WHERE s.report_date = ? "
        params: list[object] = [report_date]
        if kind:  # 查询结构固定，筛选值仍使用占位参数，不能拼接用户输入。
            sql += "AND s.kind = ? "
            params.append(kind)
        rows = connection.execute(sql + "ORDER BY s.updated_at DESC, s.id", tuple(params)).fetchall()
    handler.send_json({"date": report_date, "uploads": [deps.source_upload_public(row) for row in rows]})

def download_daily_source(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """下载日清资料源文件，并记录下载审计。"""
    actor = handler.require_user(admin=True)
    upload_id = _daily_source_id(path, "download")
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(_daily_source_select() + "WHERE s.id = ?", (upload_id,)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "日清资料不存在")
    target = _resolve_daily_source_path(row, deps)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "日清资料文件已丢失")
    deps.write_audit(int(actor["id"]), f"daily_source_download:{upload_id}")
    handler.send_file(
        target,
        content_type=row["content_type"] or "application/octet-stream",
        file_name=str(row["original_name"]),
    )

def download_daily_source_image(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """返回安全检查解析出的单张图片，并阻止文件名越出 ``images`` 目录。"""
    handler.require_user(admin=True)
    prefix = "/api/admin/daily-source-uploads/"
    tail = path[len(prefix):] if path.startswith(prefix) else ""
    parts = tail.split("/images/", 1)
    if len(parts) != 2:
        raise ApiError(HTTPStatus.BAD_REQUEST, "安全检查图片路径无效")
    upload_id = unquote(parts[0]).strip("/")
    file_name = deps.safe_name(unquote(parts[1]).strip("/"))  # 丢弃目录分隔符，只允许受控文件名。
    if len(upload_id) != 32 or not upload_id.isalnum() or not file_name:
        raise ApiError(HTTPStatus.BAD_REQUEST, "安全检查图片路径无效")
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(_daily_source_select() + "WHERE s.id = ?", (upload_id,)).fetchone()
    if row is None or row["kind"] != "safety":
        raise ApiError(HTTPStatus.NOT_FOUND, "安全检查图片不存在")
    source = _resolve_daily_source_path(row, deps)
    image_root = (source.parent / "images").resolve()
    target = (image_root / file_name).resolve()
    if image_root not in target.parents or not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "安全检查图片不存在")
    handler.send_file(
        target,
        content_type=mimetypes.guess_type(file_name)[0],
        disposition=None,
        cache_control="private, max-age=300",
    )

def delete_daily_source(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """将日清资料、解析图片和索引记录整体移入回收站。

    到料成品和安全检查共用资料目录，其中安全检查还包含解析图片，因此必须移动整个
    目录而非只移动原表格。数据库删除和审计失败时恢复目录，确保总览不会留下无文件
    索引，回收站也不会出现无法还原的半份资料。
    """
    actor = handler.require_user(admin=True)
    upload_id = _daily_source_id(path)
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(_daily_source_select() + "WHERE s.id = ?", (upload_id,)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "日清资料不存在")
    target = _resolve_daily_source_path(row, deps)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "日清资料文件已丢失，无法移入回收站")
    _move_daily_file_to_trash(
        row,
        upload_id,
        target,
        int(actor["id"]),
        _SOURCE_TRASH,
        deps,
    )
    handler.send_json({"message": "日清资料已移入回收站"})

def daily_report(handler: Any, deps: DailyManagementDependencies) -> None:
    """返回指定业务日期的管理层日清快照。

    快照聚合逻辑集中在独立服务中；本函数只处理管理员权限和日期规范化，避免 API 入口
    再次复制到料、考勤、问题和计划的选择规则。
    """
    user = handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date(
        (query.get("date") or [deps.business_today().isoformat()])[0]
    )
    handler.send_json(deps.build_daily_report_snapshot(report_date, user))

def export_daily_report(handler: Any, deps: DailyManagementDependencies) -> None:
    """以同一份看板快照生成并下载指定业务日期的日清 Excel。

    看板和导出共享快照，保证两处指标一致。Core 返回的文件路径必须位于专用报表目录，
    即使 Core 或历史配置返回异常路径也不会被下载接口任意读取。
    """
    user = handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date(
        (query.get("date") or [deps.business_today().isoformat()])[0]
    )
    snapshot = deps.build_daily_report_snapshot(report_date, user)
    report_root = deps.data_root / "reports" / "daily"
    result = deps.daily_report_core.run(snapshot, out_dir=str(report_root))
    target = Path(str(result["out_file"])).resolve()  # 不信任跨模块返回的路径，下载前重新校验。
    allowed_root = report_root.resolve()
    if allowed_root not in target.parents or not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "日清报告生成失败")
    deps.write_audit(int(user["id"]), f"export_daily_report:{report_date}")
    handler.send_file(
        target,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
