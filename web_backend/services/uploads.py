"""业务临时上传、上传句柄解析与账号目录隔离服务。"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from web_backend.errors import ApiError


@dataclass(frozen=True)
class UploadDependencies:
    """临时业务上传服务所需的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    data_root: Path
    max_upload_bytes: int
    now_iso: Callable[[], str]
    safe_name: Callable[[str], str]


def owned_upload_path(
    deps: UploadDependencies,
    path_value: str | Path,
    user_id: int,
) -> Path:
    """校验路径位于当前账号上传目录内，并返回解析后的真实绝对路径。

    路径先经 ``resolve`` 展开相对段、``..`` 和符号链接，再检查结果必须等于账号上传
    根目录或位于其子目录中；任何越界或解析失败都抛 ``ValueError``，由调用方统一转
    成客户端错误。允许返回批次目录本身，便于多文件业务直接引用目录。
    """
    root = (deps.data_root / "users" / str(user_id) / "uploads").resolve()  # 账号上传根是唯一允许业务任务读取的临时文件边界。
    try:
        resolved = Path(path_value).resolve()  # 展开 ..、符号链接和相对段后再判断，避免字符串前缀绕过。
    except OSError as exc:
        raise ValueError("上传文件不存在或不属于当前账号") from exc
    if resolved != root and root not in resolved.parents:  # 同时允许批次目录本身和其内部文件，拒绝所有兄弟账号目录。
        raise ValueError("上传文件不存在或不属于当前账号")
    return resolved


def resolve_uploads(
    deps: UploadDependencies,
    value: object,
    user_id: int,
) -> object:
    """递归解析当前账号的上传句柄，拒绝跨账号和目录越界引用。

    任务参数允许对象、列表和普通文本混合嵌套，只有不透明上传句柄和绝对路径需要解析。
    每次命中句柄都同时检查数据库的 ``user_id``、文件存在性和真实路径边界；即使数据库
    记录后来被篡改，也不能把任务指向其他账号或数据根外部。
    """
    if isinstance(value, dict):  # 任务参数可以任意嵌套，必须递归解析而不能只检查第一层。
        return {
            key: resolve_uploads(deps, item, user_id)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_uploads(deps, item, user_id) for item in value]
    if not isinstance(value, str):
        return value
    if value.startswith("upload:"):  # 单文件句柄必须同时匹配 handle 和当前 user_id。
        with deps.db_lock, deps.db() as connection:
            row = connection.execute(
                "SELECT path FROM uploads WHERE handle = ? AND user_id = ?",
                (value, user_id),
            ).fetchone()
        if row is None or not os.path.isfile(row["path"]):
            raise ValueError("上传文件不存在或不属于当前账号")
        return str(owned_upload_path(deps, row["path"], user_id))  # 数据库命中后仍做真实路径校验，防止记录被篡改。
    if value.startswith("upload-group:"):  # 批次句柄解析为目录，供发票扫描等多文件业务使用。
        group_id = value.split(":", 1)[1]
        with deps.db_lock, deps.db() as connection:
            row = connection.execute(
                "SELECT path FROM uploads "
                "WHERE group_id = ? AND user_id = ? LIMIT 1",
                (group_id, user_id),
            ).fetchone()
        if row is None:
            raise ValueError("上传批次不存在或不属于当前账号")
        return str(owned_upload_path(deps, Path(row["path"]).parent, user_id))
    if os.path.isabs(value):  # 人工复核阶段可能回传已解析绝对路径，仍必须重新验证账号归属。
        return str(owned_upload_path(deps, value, user_id))
    return value


def _request_length(handler: Any, maximum: int) -> int:
    """读取并校验上传请求声明的文件大小。"""
    try:
        length = int(handler.headers.get("Content-Length", "0"))  # 标准库不会自动限制请求体，读取前必须先检查声明大小。
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件大小无效") from exc
    if length <= 0:
        raise ApiError(HTTPStatus.BAD_REQUEST, "上传文件为空")
    if length > maximum:
        raise ApiError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "单个文件不能超过 200 MB",
        )
    return length


def upload_file(handler: Any, deps: UploadDependencies) -> None:
    """接收业务模块临时文件，并保存到当前账号的上传批次目录。

    文件名经过安全清理，批次编号只允许受控字符；请求体按声明长度分块读取，完整落盘
    后才登记不透明句柄。读取中断、长度不符或数据库写入失败都会删除孤立文件，保证
    上传索引和磁盘内容不会长期分叉。
    """
    user = handler.require_user()
    query = parse_qs(urlparse(handler.path).query)
    raw_name = str((query.get("name") or [""])[0])
    if not raw_name.strip():
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件名不能为空")
    name = deps.safe_name(raw_name)
    group_id = str((query.get("group") or [uuid.uuid4().hex])[0])  # 多文件业务复用同一批次号，单文件未提供时自动生成。
    # 批次号会拼入账号上传目录名，必须限制为字母数字和短横线，防止请求传入 ``..`` 等路径片段。
    if not group_id.replace("-", "").isalnum() or len(group_id) > 64:
        raise ApiError(HTTPStatus.BAD_REQUEST, "上传批次编号无效")
    length = _request_length(handler, deps.max_upload_bytes)

    handle = f"upload:{uuid.uuid4().hex}"  # 前端只持有不透明句柄，不接触服务器绝对路径。
    folder = deps.data_root / "users" / str(user["id"]) / "uploads" / group_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if target.exists():  # 同批次上传同名文件时保留两份，避免后上传内容静默覆盖前一份。
        target = folder / f"{target.stem}-{uuid.uuid4().hex[:8]}{target.suffix}"

    remaining = length
    try:
        with target.open("wb") as stream:  # 按 1 MiB 分块写入，避免 200 MB 文件整体驻留内存。
            while remaining:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "文件上传不完整")
                stream.write(chunk)
                remaining -= len(chunk)
        with deps.db_lock, deps.db() as connection:  # 文件完整落盘后才登记句柄，任务不会看到半文件。
            connection.execute(
                "INSERT INTO uploads(handle, user_id, group_id, name, path, size, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    handle,
                    user["id"],
                    group_id,
                    name,
                    str(target),
                    length,
                    deps.now_iso(),
                ),
            )
    except Exception:  # 流中断或数据库登记失败都删除孤立文件，保持磁盘与索引一致。
        target.unlink(missing_ok=True)
        raise

    handler.send_json({
        "handle": handle,
        "group": f"upload-group:{group_id}",
        "name": name,
        "size": length,
    }, HTTPStatus.CREATED)
