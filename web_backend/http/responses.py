"""标准库 HTTP Handler 的 JSON、文件和异常响应辅助函数。"""

from __future__ import annotations

import json
import mimetypes
import shutil
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from web_backend.errors import ApiError


def send_json(
    handler: Any,
    payload: object,
    status: int = HTTPStatus.OK,
    cookie: str = "",
) -> None:
    """发送 UTF-8 JSON 响应，并禁止浏览器缓存接口数据。"""
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")  # 保留中文可读性；禁用 NaN/Infinity，避免生成浏览器无法解析的非标准 JSON。
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")  # API 可能包含账号和业务数据，禁止浏览器或代理复用旧响应。
    if cookie:
        handler.send_header("Set-Cookie", cookie)
    handler.end_headers()
    handler.wfile.write(raw)


def read_json(handler: Any, maximum_bytes: int) -> dict[str, object]:
    """读取受大小限制的 JSON 对象请求体。"""
    try:
        length = int(handler.headers.get("Content-Length", "0"))  # 标准库不会自动限制请求体，必须在读取前校验声明长度。
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请求内容长度无效") from exc
    if length < 0 or length > maximum_bytes:  # 读取前拒绝超限内容，避免大请求先占满内存再报错。
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "请求内容过大")
    try:
        data = json.loads(handler.rfile.read(length) or b"{}")  # 空请求体按空对象处理，兼容无需参数的旧调用。
    except (ValueError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请求内容不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "请求内容不是有效 JSON")
    return data


def run_request(handler: Any, action: Callable[[], None]) -> None:
    """统一把接口异常转换为稳定的 JSON 错误响应。"""
    try:
        action()
    except ApiError as exc:  # 业务可预期错误保留原状态码和面向用户的中文信息。
        handler.send_json({"error": exc.message}, exc.status)
    except Exception as exc:  # pragma: no cover - 未预期异常只记服务日志，不向客户端泄露堆栈和路径。
        handler.log_message("server error: %r", exc)
        handler.send_json(
            {"error": "服务器内部错误"},
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


def send_file(
    handler: Any,
    path: str | Path,
    *,
    content_type: str | None = None,
    file_name: str | None = None,
    disposition: str | None = "attachment",
    cache_control: str = "no-store",
    chunk_size: int = 1024 * 1024,
) -> None:
    """流式发送已授权文件，并统一长度、缓存和中文文件名响应头。

    调用方必须先完成资源所属与路径边界校验，本函数只处理 HTTP 传输。响应处置方式仅
    允许内联或附件，文件名按 RFC 5987 编码；内容以至少六十四 KiB 的块发送，避免大型
    表格、图片和备份整体进入内存。
    """
    target = Path(path)  # 路径权限应由调用方领域服务先校验；本函数只负责传输协议。
    media_type = content_type or mimetypes.guess_type(target.name)[0]
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", media_type or "application/octet-stream")
    handler.send_header("Content-Length", str(target.stat().st_size))
    if disposition:
        safe_disposition = "inline" if disposition == "inline" else "attachment"  # 只允许两个固定值，拒绝响应头注入。
        download_name = file_name or target.name
        handler.send_header(
            "Content-Disposition",
            f"{safe_disposition}; filename*=UTF-8''{quote(download_name)}",  # RFC 5987 编码可稳定下载中文文件名。
        )
    if cache_control:
        handler.send_header("Cache-Control", cache_control)
    handler.end_headers()
    with target.open("rb") as stream:
        shutil.copyfileobj(stream, handler.wfile, length=max(64 * 1024, chunk_size))  # 分块发送避免把大表格或备份整体读入内存。
