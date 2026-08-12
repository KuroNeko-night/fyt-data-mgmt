"""API 路径参数解析与编号校验。"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import unquote

from web_backend.errors import ApiError


def path_id(path: str, prefix: str) -> str:
    """读取固定前缀后的单段编号，拒绝空值和嵌套路径。"""
    value = unquote(path[len(prefix):].strip("/")) if path.startswith(prefix) else ""  # 先确认前缀再切片，避免错误路由被当成合法编号。
    if not value or "/" in value:
        raise ApiError(HTTPStatus.BAD_REQUEST, "编号无效")  # 解码后再次拒绝斜杠，可拦截 %2F 形式的嵌套路径。
    return value


def user_action_id(path: str, suffix: str) -> int:
    """解析管理员账号动作路径中的数字用户编号。"""
    prefix = "/api/admin/users/"
    ending = f"/{suffix}"
    value = path[len(prefix):-len(ending)] if path.startswith(prefix) and path.endswith(ending) else ""  # 同时锁定首尾，避免动作名混入用户编号。
    if not value.isdigit():
        raise ApiError(HTTPStatus.BAD_REQUEST, "用户编号无效")
    return int(value)
