"""Web 请求的会话令牌、当前账号与角色权限上下文。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Callable

from web_backend.errors import ApiError


@dataclass(frozen=True)
class RequestContextDependencies:
    """请求账号上下文所需的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    now_iso: Callable[[], str]
    touch_interval_seconds: int
    role_label: Callable[[object], str]


def session_token(handler: Any) -> str:
    """优先读取请求头令牌，再兼容浏览器会话 Cookie。"""
    token = handler.headers.get("X-Session-Token", "")  # 桌面端与自动化客户端不依赖浏览器 Cookie。
    if token:
        return token
    cookie = handler.headers.get("Cookie", "")  # 浏览器同源请求由 HttpOnly Cookie 自动携带令牌。
    return next(
        (
            part.split("=", 1)[1]  # 只切第一处分隔符，令牌内容即使含“=”也不会被截断。
            for part in cookie.split("; ")
            if part.startswith("fyt_session=")
        ),
        "",
    )


def current_user(handler: Any, deps: RequestContextDependencies) -> Any | None:
    """校验会话，并按节流周期刷新最近活动时间。"""
    token = session_token(handler)
    if not token:
        return None
    threshold = (
        datetime.now(timezone.utc)
        - timedelta(seconds=deps.touch_interval_seconds)
    ).isoformat(timespec="seconds")  # 只有旧于阈值的会话才写 last_seen_at，降低高频轮询产生的写锁。
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ? AND u.status = 'approved'",
            (token, int(time.time())),  # expires_at 使用 Unix 秒，避免字符串时区比较产生歧义。
        ).fetchone()
        if row is not None:
            connection.execute(
                "UPDATE sessions SET last_seen_at = ? "
                "WHERE token = ? AND (last_seen_at = '' OR last_seen_at < ?)",
                (deps.now_iso(), token, threshold),  # SQL 条件在数据库内原子判断，多个并发请求不会反复刷新。
            )
        return row


def require_user(
    handler: Any,
    deps: RequestContextDependencies,
    admin: bool = False,
) -> Any:
    """要求请求已登录，并可进一步限制为管理员。"""
    row = current_user(handler, deps)
    if row is None:
        raise ApiError(HTTPStatus.UNAUTHORIZED, "请先登录")
    if admin and row["role"] != "admin":
        raise ApiError(HTTPStatus.FORBIDDEN, "只有管理员可以执行此操作")
    return row


def require_role(
    handler: Any,
    deps: RequestContextDependencies,
    *roles: str,
) -> Any:
    """要求当前账号属于指定角色之一。"""
    row = require_user(handler, deps)
    allowed = {str(role) for role in roles}  # 集合查找同时去除调用方意外传入的重复角色。
    if row["role"] not in allowed:
        labels = "、".join(deps.role_label(role) for role in roles)
        raise ApiError(HTTPStatus.FORBIDDEN, f"只有{labels}可以使用此功能")
    return row
