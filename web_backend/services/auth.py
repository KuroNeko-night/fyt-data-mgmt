"""账号注册、登录、密码和会话服务。

服务函数不直接导入 ``web_server``，所有易变运行参数通过依赖对象传入，
这样测试可以注入临时数据库，部署配置也不会被模块导入时固定。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable

from ..errors import ApiError
from ..http.context import session_token
from ..http.path_params import path_id


@dataclass(frozen=True)
class AuthDependencies:
    """认证服务所需的运行时依赖。"""

    db: Callable[[], sqlite3.Connection]
    db_lock: Any
    now_iso: Callable[[], str]
    hash_password: Callable[[str], tuple[str, str]]
    verify_password: Callable[[str, str, str], bool]
    password_policy_error: Callable[[str], str]
    user_public: Callable[[sqlite3.Row], dict[str, object]]
    session_days: int
    touch_interval_seconds: int
    login_failure_limit: int
    login_window_seconds: int
    login_lock_seconds: int


def register(handler: Any, body: dict[str, object], deps: AuthDependencies) -> None:
    """创建待审核账号，并返回不包含密码信息的申请结果。"""
    username = str(body.get("username", "")).strip().lower()  # 账号统一小写，避免 Alice 与 alice 绕过唯一约束形成视觉重复。
    display_name = str(body.get("display_name", "")).strip()
    password = str(body.get("password", ""))
    if not (3 <= len(username) <= 32) or not username.replace("_", "").replace("-", "").isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "账号需为 3-32 位字母、数字、下划线或短横线")
    policy_error = deps.password_policy_error(password)
    if policy_error:
        raise ApiError(HTTPStatus.BAD_REQUEST, policy_error)
    if not display_name:
        display_name = username
    salt, digest = deps.hash_password(password)  # 盐值与摘要一并生成；数据库只保存不可逆摘要，不保存明文密码。
    try:
        with deps.db_lock, deps.db() as connection:
            connection.execute(
                "INSERT INTO users(username, display_name, salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, display_name[:40], salt, digest, deps.now_iso()),
            )
    except sqlite3.IntegrityError as exc:
        raise ApiError(HTTPStatus.CONFLICT, "账号已存在，请直接登录或联系管理员") from exc
    handler.send_json({"message": "注册申请已提交，请等待管理员审核"}, HTTPStatus.CREATED)


def login(handler: Any, body: dict[str, object], deps: AuthDependencies) -> None:
    """执行账号状态、失败限流、密码校验并创建新会话。

    失败计数按来源地址和规范化账号组合隔离，且不存在的账号也走同样的失败路径，减少
    账号枚举和单账号拖累全体用户的风险。密码校验成功后才清除失败窗口；待审核、拒绝
    和暂停账号在密码正确后仍按账号状态拒绝。会话令牌只写入 HttpOnly Cookie 或响应
    结果，数据库保存的设备编号与令牌分离，便于管理页撤销设备而不暴露秘密。
    """
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))
    now = int(time.time())
    address = str(handler.client_address[0] if handler.client_address else "")[:64]
    attempt_key = hashlib.sha256(f"{address}\0{username}".encode("utf-8")).hexdigest()  # 失败计数按“来源地址+账号”隔离，避免一个账号拖累全体用户。
    with deps.db_lock, deps.db() as connection:
        attempt = connection.execute(
            "SELECT * FROM login_attempts WHERE attempt_key = ?", (attempt_key,)
        ).fetchone()
        if attempt and int(attempt["locked_until"] or 0) > now:
            minutes = max(1, (int(attempt["locked_until"]) - now + 59) // 60)
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, f"登录尝试次数过多，请在 {minutes} 分钟后重试")
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    valid = bool(row and deps.verify_password(password, row["salt"], row["password_hash"]))  # 不存在的账号也走统一失败响应，避免通过接口枚举账号。
    if not valid:
        with deps.db_lock, deps.db() as connection:
            attempt = connection.execute(
                "SELECT * FROM login_attempts WHERE attempt_key = ?", (attempt_key,)
            ).fetchone()
            if attempt is None or now - int(attempt["window_started"]) > deps.login_window_seconds:  # 窗口过期后重新计数，而不是沿用历史失败次数。
                failures = 1
                window_started = now
            else:
                failures = int(attempt["failures"]) + 1
                window_started = int(attempt["window_started"])
            locked_until = now + deps.login_lock_seconds if failures >= deps.login_failure_limit else 0  # 达到阈值才锁定，普通失败不会持续延长锁定。
            connection.execute(
                "INSERT INTO login_attempts(attempt_key, failures, window_started, locked_until, last_failed_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(attempt_key) DO UPDATE SET "
                "failures = excluded.failures, window_started = excluded.window_started, "
                "locked_until = excluded.locked_until, last_failed_at = excluded.last_failed_at",
                (attempt_key, failures, window_started, locked_until, now),
            )
        if failures >= deps.login_failure_limit:
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, "登录尝试次数过多，请在 15 分钟后重试")
        raise ApiError(HTTPStatus.UNAUTHORIZED, "账号或密码不正确")
    if row["status"] == "pending":
        raise ApiError(HTTPStatus.FORBIDDEN, "账号正在等待管理员审核")
    if row["status"] == "rejected":
        raise ApiError(HTTPStatus.FORBIDDEN, "注册申请未通过，请联系管理员")
    if row["status"] == "disabled":
        raise ApiError(HTTPStatus.FORBIDDEN, "账号已暂停使用，请联系管理员")
    token = secrets.token_urlsafe(36)  # 高熵令牌只放在 Cookie/请求头中，数据库用于精确撤销会话。
    session_id = uuid.uuid4().hex  # 对外设备编号与秘密令牌分离，删除设备时不暴露令牌。
    timestamp = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        connection.execute("DELETE FROM login_attempts WHERE attempt_key = ?", (attempt_key,))
        connection.execute(
            "INSERT INTO sessions(token, user_id, expires_at, id, created_at, last_seen_at, ip_address, user_agent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                token, row["id"], now + deps.session_days * 86400, session_id, timestamp,
                timestamp, address, str(handler.headers.get("User-Agent", ""))[:300],
            ),
        )
    secure = "; Secure" if handler.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""  # 反向代理终止 TLS 时仍让浏览器仅经 HTTPS 携带 Cookie。
    cookie = f"fyt_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={deps.session_days * 86400}{secure}"
    handler.send_json({"token": token, "user": deps.user_public(row)}, cookie=cookie)


def logout(handler: Any, deps: AuthDependencies) -> None:
    """删除当前会话并清除浏览器中的会话 Cookie。"""
    token = session_token(handler)  # 同时兼容桌面端请求头和浏览器 Cookie 的退出路径。
    with deps.db_lock, deps.db() as connection:  # 修改密码、撤销其他设备和写审计记录在同一事务中完成。
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
    handler.send_json(
        {"message": "已退出登录"},
        cookie="fyt_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
    )


def change_password(handler: Any, body: dict[str, object], deps: AuthDependencies) -> None:
    """校验旧密码与新密码策略，更新摘要并让其他设备退出登录。

    新密码不能与当前密码相同；新盐和摘要、其他会话撤销及审计记录在同一事务中完成。
    当前请求令牌被保留，用户无需在本设备重新登录，其他设备下一次请求立即失效。
    """
    user = handler.require_user()
    token = session_token(handler)
    current_password = str(body.get("current_password") or "")
    new_password = str(body.get("new_password") or "")
    if not deps.verify_password(current_password, user["salt"], user["password_hash"]):
        raise ApiError(HTTPStatus.BAD_REQUEST, "当前密码不正确")
    policy_error = deps.password_policy_error(new_password)
    if policy_error:
        raise ApiError(HTTPStatus.BAD_REQUEST, policy_error)
    if deps.verify_password(new_password, user["salt"], user["password_hash"]):
        raise ApiError(HTTPStatus.BAD_REQUEST, "新密码不能与当前密码相同")
    salt, digest = deps.hash_password(new_password)
    with deps.db_lock, deps.db() as connection:
        connection.execute(
            "UPDATE users SET salt = ?, password_hash = ? WHERE id = ?",
            (salt, digest, user["id"]),
        )
        connection.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token <> ?", (user["id"], token)
        )
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, 'change_password', ?, ?)",
            (user["id"], user["id"], deps.now_iso()),
        )
    handler.send_json({"message": "密码已更新，其他设备已退出登录"})


def list_sessions(handler: Any, deps: AuthDependencies) -> None:
    """列出当前账号仍有效的登录设备。"""
    user = handler.require_user()
    token = session_token(handler)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT id, token, created_at, last_seen_at, ip_address, user_agent, expires_at "
            "FROM sessions WHERE user_id = ? AND expires_at > ? ORDER BY last_seen_at DESC",
            (user["id"], int(time.time())),
        ).fetchall()
    handler.send_json({"sessions": [{
        "id": row["id"], "created_at": row["created_at"], "last_seen_at": row["last_seen_at"],
        "ip_address": row["ip_address"], "user_agent": row["user_agent"],
        "expires_at": row["expires_at"], "current": hmac.compare_digest(row["token"], token),  # 常量时间比较避免泄露令牌匹配细节。
    } for row in rows]})


def delete_session(handler: Any, path: str, deps: AuthDependencies) -> None:
    """删除当前账号指定的登录设备。"""
    user = handler.require_user()
    session_id = path_id(path, "/api/auth/sessions/")
    with deps.db_lock, deps.db() as connection:
        deleted = connection.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?", (session_id, user["id"])
        ).rowcount
    if not deleted:
        raise ApiError(HTTPStatus.NOT_FOUND, "登录设备不存在或已经退出")
    handler.send_json({"message": "该设备已退出登录"})
