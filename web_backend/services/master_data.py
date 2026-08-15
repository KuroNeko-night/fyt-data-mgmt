"""主数据正式档案、表格学习、冲突治理与合并服务。"""

from __future__ import annotations

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
class MasterDataDependencies:
    """主数据服务的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    data_root: Path
    max_upload_bytes: int
    now_iso: Callable[[], str]
    safe_name: Callable[[object], str]
    environment: Callable[[], Any]
    import_core: Any
    catalog_core: Any


def _batch_id(path: str, suffix: str = "") -> str:
    """从管理员路由中提取固定长度十六进制批次编号。"""
    prefix = "/api/admin/master-data/imports/"
    ending = f"/{suffix}" if suffix else ""
    if not path.startswith(prefix) or (ending and not path.endswith(ending)):
        raise ApiError(HTTPStatus.BAD_REQUEST, "主数据导入批次编号无效")
    value = path[len(prefix):]
    if ending:
        value = value[:-len(ending)]
    value = unquote(value.strip("/")).lower()  # URL 解码后再校验，阻止编码字符绕过格式约束。
    if len(value) != 32 or any(char not in "0123456789abcdef" for char in value):
        raise ApiError(HTTPStatus.BAD_REQUEST, "主数据导入批次编号无效")
    return value


def _api_error(exc: ValueError, deps: MasterDataDependencies) -> ApiError:
    """把 Core 主数据异常转换为稳定的 HTTP 状态码和客户文案。

    Core 保持与传输协议无关，只抛业务异常；重复导入映射为资源冲突，读取不到批次映射
    为资源不存在，其余校验失败映射为请求错误。这里不包含堆栈或服务器路径。
    """
    if isinstance(exc, deps.import_core.DuplicateImportError):  # 同一文件重复学习是资源冲突，前端可据 409 给出明确提示。
        return ApiError(HTTPStatus.CONFLICT, str(exc))
    message = str(exc) or "主数据导入操作失败"
    status = HTTPStatus.NOT_FOUND if "无法读取" in message else HTTPStatus.BAD_REQUEST  # Core 暂无 HTTP 依赖，入口层在此完成状态码映射。
    return ApiError(status, message)


def _record_audit(
    deps: MasterDataDependencies,
    actor_id: int | None,
    action: str,
    batch_id: str,
) -> None:
    """记录一条带批次编号的主数据管理审计。

    批次编号拼入受控动作文本，便于在现有审计表结构中追溯具体导入批次；调用方传入的
    动作名均为服务端常量，不接收浏览器任意审计文本。
    """
    with deps.db_lock, deps.db() as connection:
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor_id, f"{action}:{batch_id}", deps.now_iso()),
        )


def admin_catalog(
    handler: Any,
    body: dict[str, object] | None,
    deps: MasterDataDependencies,
) -> None:
    """查询或维护供应商和材料正式档案。

    空请求体表示只读查询；写操作通过固定白名单映射到 Core 的供应商和材料维护入口，
    绝不使用客户端值动态调用方法。所有操作在 Web 主数据环境中执行，成功后返回完整
    最新档案并记录管理员审计。
    """
    actor = handler.require_user(admin=True)
    with deps.environment():
        if body is None:
            handler.send_json(deps.catalog_core.list_all())
            return
        operation = str(body.get("op") or "")
        operations = {  # 白名单映射替代 getattr，客户端不能调用 catalog_core 的任意内部方法。
            "upsert_supplier": lambda: deps.catalog_core.upsert_supplier(
                str(body.get("name") or ""), str(body.get("code") or ""),
            ),
            "delete_supplier": lambda: deps.catalog_core.delete_supplier(
                str(body.get("name") or ""),
            ),
            "upsert_material": lambda: deps.catalog_core.upsert_material(
                str(body.get("code") or ""),
                str(body.get("name") or ""),
                spec=str(body.get("spec") or ""),
                unit=str(body.get("unit") or ""),
                supplier=str(body.get("supplier") or ""),
            ),
            "delete_material": lambda: deps.catalog_core.delete_material(
                str(body.get("code") or ""),
            ),
        }
        action = operations.get(operation)
        if action is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "不支持的主数据操作")
        try:
            action()
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        result = deps.catalog_core.list_all()
    _record_audit(deps, int(actor["id"]), "catalog", operation)
    handler.send_json(result)


def upload_import(handler: Any, deps: MasterDataDependencies) -> None:
    """接收管理员表格，安全保存后分析为待治理批次。

    接口限制扩展名、声明大小和安全文件名，按批次建立独立目录并分块写入临时文件；
    原子改名后才调用 Core 学习对应关系。重复文件、字段冲突和解析失败由 Core 转成稳定
    API 错误，任一步失败都会删除整个批次目录，避免留下未登记的原始业务表格。
    """
    actor = handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    raw_name = query.get("name", [""])[0]
    if not raw_name.strip():
        raise ApiError(HTTPStatus.BAD_REQUEST, "请选择要学习的 Excel 表格")
    name = deps.safe_name(raw_name)  # 去除目录片段和 Windows 非法字符，上传文件只能落在批次目录一层。
    if Path(name).suffix.lower() not in deps.import_core.SUPPORTED_EXTENSIONS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "仅支持 .xlsx、.xlsm 和 .xls 表格")
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件大小无效") from exc
    if length <= 0:
        raise ApiError(HTTPStatus.BAD_REQUEST, "上传表格为空")
    if length > deps.max_upload_bytes:
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "主数据表格不能超过 50 MB")
    batch_id = uuid.uuid4().hex  # 批次编号同时作为目录名和治理记录主键，便于追踪原始表格。
    # 导入表格按管理员账号隔离存放，与其他管理员及桌面端本地档案互不可见。
    folder = (
        deps.data_root / "users" / str(actor["id"])
        / "master-data-imports" / batch_id
    )
    temp_path = folder / ".uploading"  # 未完成文件使用临时名，分析器永远不会读取半上传内容。
    target = folder / name
    folder.mkdir(parents=True, exist_ok=False)
    try:
        remaining = length
        with temp_path.open("wb") as stream:  # 分块接收，避免 50 MB 工作簿整体进入内存。
            while remaining:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "表格上传不完整")
                stream.write(chunk)
                remaining -= len(chunk)
        os.replace(temp_path, target)  # 同一文件系统内原子改名，完成标志与文件可见性同步。
        try:
            with deps.environment():  # 临时切换主数据目录环境变量，保证 Web 数据与桌面本地数据隔离。
                batch = deps.import_core.analyze(
                    str(target),
                    original_name=name,
                    batch_id=batch_id,
                    uploader_id=int(actor["id"]),
                    uploader_name=str(actor["display_name"]),
                )
        except ValueError as exc:
            raise _api_error(exc, deps) from exc
    except Exception:  # 上传或分析任一步失败都移除整个批次目录，防止留下无法治理的孤立数据。
        shutil.rmtree(folder, ignore_errors=True)
        raise
    _record_audit(deps, int(actor["id"]), "master_data_upload", batch_id)
    handler.send_json(
        {"message": "表格分析完成", "batch": batch}, HTTPStatus.CREATED,
    )


def list_imports(handler: Any, deps: MasterDataDependencies) -> None:
    """列出主数据学习批次及待处理冲突摘要。

    列表读取必须在 Web 主数据环境上下文中执行，确保服务器不会误读桌面端本地目录。
    批次文件由 Core 的原子索引管理，本接口只负责管理员鉴权和响应封装。
    """
    handler.require_user(admin=True)
    with deps.environment():
        handler.send_json(deps.import_core.list_batches())


def get_import(handler: Any, path: str, deps: MasterDataDependencies) -> None:
    """读取一个主数据学习批次的候选关系、冲突与处理状态。

    批次编号先经过固定长度十六进制校验，Core 再判断索引和批次文件是否完整。读取失败
    统一交给异常映射器，前端不会看到内部文件路径。
    """
    handler.require_user(admin=True)
    batch_id = _batch_id(path)
    try:
        with deps.environment():
            batch = deps.import_core.get_batch(batch_id)
    except ValueError as exc:
        raise _api_error(exc, deps) from exc
    handler.send_json({"batch": batch})


def resolve_conflict(
    handler: Any,
    path: str,
    body: dict[str, object],
    deps: MasterDataDependencies,
) -> None:
    """保存管理员对单个冲突候选的取值决策。

    候选编号、决策类型和值由 Core 按批次当前状态再次校验；Web 只补充可信的操作者
    身份。处理后返回整个批次，让前端立即刷新剩余冲突数量和可合并状态。
    """
    actor = handler.require_user(admin=True)
    batch_id = _batch_id(path, "resolve")
    try:
        with deps.environment():
            batch = deps.import_core.resolve_conflict(
                batch_id,
                str(body.get("candidate_id") or ""),
                str(body.get("decision") or ""),
                value=str(body.get("value") or ""),
                actor_id=int(actor["id"]),
                actor_name=str(actor["display_name"]),
            )
    except ValueError as exc:
        raise _api_error(exc, deps) from exc
    _record_audit(deps, int(actor["id"]), "master_data_resolve", batch_id)
    handler.send_json({"message": "冲突处理已保存", "batch": batch})


def _change_batch_status(
    handler: Any,
    path: str,
    suffix: str,
    core_action: str,
    audit_action: str,
    message: str,
    deps: MasterDataDependencies,
) -> None:
    """执行确认或拒绝这类结构相同的批次状态变更。

    ``suffix``、Core 方法名、审计动作和提示文本都来自服务端固定调用点。虽然这里使用
    ``getattr`` 复用流程，但客户端不能选择方法名，因此不会形成任意 Core 调用入口。
    """
    actor = handler.require_user(admin=True)
    batch_id = _batch_id(path, suffix)
    action = getattr(deps.import_core, core_action)  # core_action 仅由服务端固定调用点传入，不读取客户端内容。
    try:
        with deps.environment():
            batch = action(
                batch_id,
                actor_id=int(actor["id"]),
                actor_name=str(actor["display_name"]),
            )
    except ValueError as exc:
        raise _api_error(exc, deps) from exc
    _record_audit(deps, int(actor["id"]), audit_action, batch_id)
    handler.send_json({"message": message, "batch": batch})


def confirm_import(handler: Any, path: str, deps: MasterDataDependencies) -> None:
    """确认已无未决冲突的学习批次，使其进入等待合并状态。"""
    _change_batch_status(
        handler,
        path,
        "confirm",
        "confirm_batch",
        "master_data_confirm",
        "批次已确认，等待合并",
        deps,
    )


def reject_import(handler: Any, path: str, deps: MasterDataDependencies) -> None:
    """拒绝当前学习批次，保留原始表格与治理记录供后续追溯。"""
    _change_batch_status(
        handler,
        path,
        "reject",
        "reject_batch",
        "master_data_reject",
        "导入批次已拒绝",
        deps,
    )


def merge_import(handler: Any, path: str, deps: MasterDataDependencies) -> None:
    """把已确认批次合并进正式主数据，并处理并发版本变化。

    Core 在写入前重新比较分析时看到的正式档案版本；若其他管理员已经更新主数据，批次
    会退回复核状态而不是覆盖较新的确认值。接口根据最终状态记录“合并”或“重新检查”
    审计动作，前端据此给出不同提示。
    """
    actor = handler.require_user(admin=True)
    batch_id = _batch_id(path, "merge")
    try:
        with deps.environment():
            batch = deps.import_core.merge_batch(
                batch_id,
                actor_id=int(actor["id"]),
                actor_name=str(actor["display_name"]),
            )
    except ValueError as exc:
        raise _api_error(exc, deps) from exc
    merged = batch.get("status") == "merged"  # 合并前 Core 会重新检查正式档案版本，变化时退回复核而非强行覆盖。
    _record_audit(
        deps,
        int(actor["id"]),
        "master_data_merge" if merged else "master_data_recheck",
        batch_id,
    )
    message = "主数据已安全合并" if merged else "正式主数据已变化，请重新处理冲突"
    handler.send_json({"message": message, "batch": batch})


def export_catalog(handler: Any, deps: MasterDataDependencies) -> None:
    """把当前正式主数据导出为临时 Excel 文件并流式返回。

    每次请求使用独立临时目录，避免并发导出互相覆盖。文件发送结束或客户端中断后都会
    删除临时目录；正式档案与导入批次不受清理影响，导出行为另行写入审计。
    """
    actor = handler.require_user(admin=True)
    folder = deps.data_root / "temp" / "master-data-export" / uuid.uuid4().hex  # 每次导出使用独立临时目录，避免并发覆盖。
    target = folder / "主数据库.xlsx"
    folder.mkdir(parents=True, exist_ok=False)
    try:
        with deps.environment():
            deps.import_core.export_catalog(str(target))
        handler.send_file(
            target,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
    finally:  # 响应成功或客户端中断都清理临时文件，不进入长期数据目录。
        shutil.rmtree(folder, ignore_errors=True)
    _record_audit(deps, int(actor["id"]), "master_data_export", "catalog")
