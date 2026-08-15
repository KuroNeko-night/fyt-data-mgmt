"""管理员账号审核、授权和安全维护服务。

覆盖注册审核、账号资料修改、角色授权、启用/停用、会话撤销、密码重置与账号删除。
全部写接口都要求管理员身份；角色矩阵只有业务成员、班组长和管理员三类，角色键由
配置白名单提供，普通成员只能通过 auth 模块维护自己的密码与会话。状态变更统一写入
audit_log，暂停、拒绝或重置密码时在同一事务中撤销目标账号会话，保证权限变化即时生效。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from web_backend.errors import ApiError
from web_backend.http.path_params import path_id, user_action_id


@dataclass(frozen=True)
class AdminAccountDependencies:
    """账号管理服务依赖。"""

    # 数据库、时间和展示依赖统一由组合根注入，服务不直接连接数据库。
    db_lock: Any
    db: Callable[[], Any]
    now_iso: Callable[[], str]
    # 角色白名单来自配置模块，服务端拒绝未定义权限值。
    role_choices: tuple[str, ...]
    # 公开投影只输出客户字段，绝不序列化盐值、摘要或内部路径。
    user_public: Callable[[Any], dict[str, object]]
    # 密码策略与摘要由配置/安全模块提供，服务只组合结果而不自行实现哈希。
    password_policy_error: Callable[[str], str | None]
    hash_password: Callable[[str], tuple[str, str]]
    # 删除账号前先创建可恢复备份；任务进程表由 job_lock 单独保护。
    create_web_backup: Callable[[int | None], dict[str, object]]
    job_lock: Any
    # 内存进程句柄与账号隔离目录只在此处受控访问。
    job_processes: dict[str, Any]
    data_root: Path


def list_users(handler: Any, deps: AdminAccountDependencies) -> None:
    """返回管理员账号维护页使用的账号列表。

    输出统一经过 ``user_public`` 投影，数据库中的密码盐和摘要即使新增字段也不会因为
    ``SELECT *`` 被意外序列化。排序把待审核申请置顶，其余账号保持创建时间倒序。
    """
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT * FROM users "
            "ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC"  # 待审核账号固定排在最前，减少管理员漏审。
        ).fetchall()
    handler.send_json({"users": [deps.user_public(row) for row in rows]})

def review_user(handler: Any, path: str, status: str, deps: AdminAccountDependencies) -> None:
    """批准或拒绝一条注册申请，并记录执行管理员和目标账号。

    ``status`` 只由路由表传入固定值，浏览器不能借此提交任意账号状态。管理员账号不走
    注册审核流程，拒绝审核管理员可避免错误地把系统恢复入口改成待审或拒绝状态。
    """
    actor = handler.require_user(admin=True)
    try:
        user_id = int(path.split("/")[4])  # 路由固定为 /api/admin/users/<id>/review，取第 5 段作为用户编号。
    except (IndexError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "用户编号无效") from exc
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["role"] == "admin":
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能审核管理员账号")
        approved_at = deps.now_iso() if status == "approved" else None  # 被拒绝时清空批准时间，避免前端误判曾通过审核。
        connection.execute("UPDATE users SET status = ?, approved_at = ? WHERE id = ?", (status, approved_at, user_id))
        connection.execute("INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)", (actor["id"], status, user_id, deps.now_iso()))
    handler.send_json({"message": "已更新用户状态"})

def update_user(handler: Any, path: str, body: dict[str, object], deps: AdminAccountDependencies) -> None:
    """修改非管理员账号的显示名称与审核状态。

    该接口用于管理页的一般资料维护，不承担角色授权；角色变化必须走独立接口，以便应用
    最后一名管理员保护和更细的审计动作。账号离开正常状态时同步撤销会话，确保权限变化
    不会等到旧 Cookie 自然过期后才生效。
    """
    actor = handler.require_user(admin=True)
    try:
        user_id = int(path_id(path, "/api/admin/users/"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "用户编号无效") from exc
    display_name = str(body.get("display_name") or "").strip()
    status = str(body.get("status") or "").strip()
    if not display_name or len(display_name) > 40:
        raise ApiError(HTTPStatus.BAD_REQUEST, "姓名需为 1-40 个字符")
    if status not in {"pending", "approved", "rejected", "disabled"}:  # 状态白名单与审核/启停协议一致，客户端不能提交任意状态。
        raise ApiError(HTTPStatus.BAD_REQUEST, "账号状态无效")
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["role"] == "admin" or target["id"] == actor["id"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能修改管理员账号或当前账号")
        approved_at = deps.now_iso() if status == "approved" else None  # 只有当前状态为通过时保留批准时间。
        connection.execute("UPDATE users SET display_name = ?, status = ?, approved_at = ? WHERE id = ?", (display_name, status, approved_at, user_id))
        if status != "approved":
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        connection.execute("INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)", (actor["id"], "update_user", user_id, deps.now_iso()))
    handler.send_json({"message": "账号资料已更新"})

def update_user_role(handler: Any, path: str, body: dict[str, object], deps: AdminAccountDependencies) -> None:
    """调整账号角色，并保护当前管理员、内置管理员和最后一名管理员。

    角色必须来自配置白名单，待审核账号不能直接提升为管理员。调用者不能修改自己的
    管理员权限，内置 ``admin`` 不能降权；发生角色变化时根据前后角色记录授予或撤销
    的精确审计动作，便于追溯班组长和管理员权限流转。
    """
    actor = handler.require_user(admin=True)
    user_id = user_action_id(path, "role")
    role = str(body.get("role") or "").strip()
    if role not in deps.role_choices:  # 角色白名单由配置模块维护，拒绝客户端提交未定义权限。
        raise ApiError(HTTPStatus.BAD_REQUEST, "账号权限无效")
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["id"] == actor["id"]:  # 防止管理员误降权自己后失去系统管理入口。
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能修改当前账号的管理员权限")
        if target["username"] == "admin" and role != "admin":  # 内置账号作为恢复入口，永远不能撤销管理员权限。
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能撤销内置管理员权限")
        if role == "admin" and target["status"] != "approved":
            raise ApiError(HTTPStatus.BAD_REQUEST, "只有已通过审核且正常使用的账号可以设为管理员")
        if target["role"] == role:
            handler.send_json({"message": "账号权限未发生变化"})
            return
        if role == "user":
            admin_count = connection.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'").fetchone()["n"]  # 降权前确认系统仍保留管理员。
            if admin_count <= 1:
                raise ApiError(HTTPStatus.BAD_REQUEST, "系统至少需要保留一名管理员")
        previous_role = str(target["role"] or "user")  # 审计动作需要知道角色变更方向，而不只是最终值。
        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        # 审计记录保留角色变更的实际方向，便于管理员回溯“授予”和“撤销”操作。
        if role == "admin":
            action = "grant_admin"
        elif previous_role == "admin":
            action = "revoke_admin"
        elif role == "team_leader":
            action = "grant_team_leader"
        elif previous_role == "team_leader":
            action = "revoke_team_leader"
        else:
            action = "revoke_privileged_role"
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
            (actor["id"], action, user_id, deps.now_iso()),
        )
    messages = {
        "admin": "已授予管理员权限",
        "team_leader": "已授予班组长权限",
        "user": "已恢复为业务成员",
    }
    handler.send_json({"message": messages[role]})

def update_user_access(handler: Any, path: str, body: dict[str, object], deps: AdminAccountDependencies) -> None:
    """在正常使用与暂停使用之间切换非管理员账号。

    只允许 ``approved`` 与 ``disabled`` 两种状态互相切换，待审核和已拒绝申请仍应通过
    审核流程处理。暂停账号时删除全部会话，使已打开页面的下一次请求立即失去权限。
    """
    actor = handler.require_user(admin=True)
    user_id = user_action_id(path, "access")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise ApiError(HTTPStatus.BAD_REQUEST, "账号访问状态无效")
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["id"] == actor["id"] or target["role"] == "admin":
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能暂停当前账号或管理员账号")
        if enabled and target["status"] != "disabled":  # 恢复只接受明确暂停的账号，重复调用不会伪装成功。
            raise ApiError(HTTPStatus.BAD_REQUEST, "只有已暂停的账号可以恢复使用")
        if not enabled and target["status"] != "approved":
            raise ApiError(HTTPStatus.BAD_REQUEST, "只有正常使用的账号可以暂停")
        status = "approved" if enabled else "disabled"
        connection.execute(
            "UPDATE users SET status = ?, approved_at = ? WHERE id = ?",
            (status, deps.now_iso() if enabled else target["approved_at"], user_id),
        )
        if not enabled:
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
            (actor["id"], "enable_user" if enabled else "disable_user", user_id, deps.now_iso()),
        )
    handler.send_json({"message": "账号已恢复使用" if enabled else "账号已暂停并退出所有设备"})

def revoke_user_sessions(handler: Any, path: str, deps: AdminAccountDependencies) -> None:
    """强制指定账号退出所有设备，并把撤销数量返回给管理员。

    当前管理员不能通过此接口退出自己，避免管理页面在事务完成后突然失去会话；管理员
    若要退出当前设备应使用普通退出接口，若要管理自己的其他设备应使用账号安全页面。
    """
    actor = handler.require_user(admin=True)
    user_id = user_action_id(path, "sessions/revoke")
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["id"] == actor["id"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能强制退出当前账号")
        revoked = connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,)).rowcount
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
            (actor["id"], "revoke_sessions", user_id, deps.now_iso()),
        )
    handler.send_json({"message": f"已退出该账号的 {revoked} 个登录会话"})

def reset_user_password(handler: Any, path: str, body: dict[str, object], deps: AdminAccountDependencies) -> None:
    """为其他账号设置符合策略的新密码，并撤销该账号全部会话。

    管理员代为重置不要求知道旧密码，但不能重置当前账号；当前账号必须走需要旧密码的
    自助修改流程。密码摘要与会话删除位于同一事务，避免密码已变而旧会话仍有效。
    """
    actor = handler.require_user(admin=True)
    user_id = user_action_id(path, "password")
    if user_id == actor["id"]:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请在账号安全页面修改当前账号密码")
    password = str(body.get("password") or "")
    policy_error = deps.password_policy_error(password)
    if policy_error:
        raise ApiError(HTTPStatus.BAD_REQUEST, policy_error)
    salt, digest = deps.hash_password(password)
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["role"] == "admin":
            # 与其他账号管理接口一致：管理员（含内置 admin 恢复入口）的密码只能通过
            # 需要旧密码的自助修改或 out-of-band 重置脚本处理，避免管理员之间横向接管。
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能通过此接口重置管理员账号密码")
        connection.execute(
            "UPDATE users SET salt = ?, password_hash = ? WHERE id = ?", (salt, digest, user_id)
        )
        revoked = connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,)).rowcount
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, 'reset_password', ?, ?)",
            (actor["id"], user_id, deps.now_iso()),
        )
    handler.send_json({"message": f"密码已重置，并退出该账号的 {revoked} 个登录会话"})

def delete_user(handler: Any, path: str, deps: AdminAccountDependencies) -> None:
    """备份后删除非管理员账号、关联记录、运行进程和用户目录。

    操作分为三个阶段：先生成可恢复备份，再在事务内重新校验账号状态并级联删除记录，
    最后终止内存中的任务进程并删除隔离目录。备份期间目标账号可能被其他管理员修改，
    因而删除事务必须再次读取并校验，不能沿用备份前的旧查询结果。
    """
    actor = handler.require_user(admin=True)
    try:
        user_id = int(path_id(path, "/api/admin/users/"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "用户编号无效") from exc
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
        if target["role"] == "admin" or target["id"] == actor["id"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "不能删除管理员账号或当前账号")
    safety = deps.create_web_backup(actor["id"])  # 删除账号前先生成完整备份，为误操作保留恢复入口。
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None or target["role"] == "admin" or target["id"] == actor["id"]:
            raise ApiError(HTTPStatus.CONFLICT, "账号状态已变化，请刷新后重试")
        job_ids = [row["id"] for row in connection.execute("SELECT id FROM web_jobs WHERE user_id = ?", (user_id,)).fetchall()]  # 删除前保存任务编号，提交后再终止运行进程。
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        connection.execute("INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, NULL, ?)", (actor["id"], f"delete_user:{user_id}", deps.now_iso()))
    with deps.job_lock:  # 先从共享进程表摘除句柄，避免其他请求继续操作已删除账号的任务。
        processes = [deps.job_processes.pop(job_id, None) for job_id in job_ids]
    for process in processes:  # 进程终止放在数据库提交之后，避免长时间等待子进程占用数据库锁。
        if process and process.poll() is None:
            process.terminate()
    shutil.rmtree(deps.data_root / "users" / str(user_id), ignore_errors=True)  # 每个账号目录独立，删除范围不会越出用户根目录。
    handler.send_json({"message": f"账号及其资料已删除，删除前备份：{safety['id']}"})
