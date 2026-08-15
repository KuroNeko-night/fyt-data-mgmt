"""管理员数据总览、审计记录和资料维护服务。

覆盖系统管理页聚合数据、审计日志查询、任务删除与上传资料回收。全部接口要求
admin 角色；上传资料进入回收站时执行路径归属校验、文件移动和数据库删除的可补偿
事务，失败时把文件移回原位，避免出现半删除状态。
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from web_backend.errors import ApiError
from web_backend.http.path_params import path_id


@dataclass(frozen=True)
class AdminDataDependencies:
    """管理员数据服务的运行时依赖。"""

    # db_lock 串行化 SQLite 事务；storage_lock 只包围文件移动与索引删除的补偿段。
    db_lock: Any
    db: Callable[[], Any]
    storage_lock: Any
    data_root: Path
    # 删除任务前先从进程表摘除句柄并终止子进程，再移动结果文件。
    job_lock: Any
    job_processes: dict[str, Any]
    now_iso: Callable[[], str]
    # 用户投影与兼容 JSON 解析器保证脏数据不会阻断管理页；任务回收复用统一事务。
    user_public: Callable[[Any], dict[str, object]]
    json_list: Callable[..., list[Any]]
    move_job_to_trash: Callable[..., str | None]


def admin_data(handler: Any, deps: AdminDataDependencies) -> None:
    """返回系统管理页所需的账号、任务、上传资料与容量摘要。

    三组明细均限制数量，完整历史仍留在数据库；账号查询附带有效会话和任务数量，任务
    文件大小从兼容 JSON 中安全累计。响应只输出客户可理解的名称、状态和数量，不下发
    密码字段、任务参数、服务器路径或上传句柄对应的绝对位置。
    """
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        users = connection.execute(
            "SELECT u.*, COUNT(j.id) AS job_count, "
            "(SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id AND s.expires_at > ?) "
            "AS session_count FROM users u "
            "LEFT JOIN web_jobs j ON j.user_id = u.id GROUP BY u.id "
            "ORDER BY CASE u.status WHEN 'pending' THEN 0 WHEN 'disabled' THEN 1 ELSE 2 END, "
            "u.created_at DESC",
            (int(time.time()),),  # session_count 只统计尚未过期的设备会话。
        ).fetchall()
        jobs = connection.execute(
            "SELECT j.id, j.user_id, j.assignee_id, j.title, j.action, j.status, "
            "j.progress, j.error, j.files, j.created_at, j.updated_at, "
            "u.username, u.display_name, assignee.display_name AS assignee_display_name, "
            "assignee.username AS assignee_username "
            "FROM web_jobs j JOIN users u ON u.id = j.user_id "
            "LEFT JOIN users assignee ON assignee.id = j.assignee_id "
            "ORDER BY j.created_at DESC LIMIT 200"  # 管理页只展示近期明细，完整历史仍保留在数据库中。
        ).fetchall()
        uploads = connection.execute(
            "SELECT p.handle, p.user_id, p.name, p.size, p.group_id, p.created_at, "
            "u.username, u.display_name FROM uploads p JOIN users u ON u.id = p.user_id "
            "ORDER BY p.created_at DESC LIMIT 200"
        ).fetchall()

    public_jobs = []
    for row in jobs:
        files = deps.json_list(row["files"])  # 损坏或旧格式 JSON 由兼容读取器回退为空列表。
        public_jobs.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "title": row["title"],
            "status": row["status"],
            "progress": row["progress"],
            "error": row["error"],
            "assignee_id": row["assignee_id"],
            "assignee_display_name": row["assignee_display_name"],
            "file_count": len(files),
            "file_size": sum(  # 只累计结构合法的文件项，避免历史脏数据阻断管理员页面。
                int(item.get("size") or 0) for item in files if isinstance(item, dict)
            ),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    handler.send_json({
        "summary": {
            "users": len(users),
            "approved_users": sum(row["status"] == "approved" for row in users),
            "admins": sum(row["role"] == "admin" for row in users),
            "team_leaders": sum(row["role"] == "team_leader" for row in users),
            "pending_users": sum(row["status"] == "pending" for row in users),
            "disabled_users": sum(row["status"] == "disabled" for row in users),
            "jobs": len(jobs),
            "uploads": len(uploads),
            "job_files": sum(item["file_count"] for item in public_jobs),
            "job_bytes": sum(item["file_size"] for item in public_jobs),
            "upload_bytes": sum(int(row["size"] or 0) for row in uploads),
        },
        "users": [{
            **deps.user_public(row),
            "job_count": int(row["job_count"] or 0),
            "session_count": int(row["session_count"] or 0),
            "is_primary_admin": row["username"] == "admin",
        } for row in users],
        "jobs": public_jobs,
        "uploads": [{
            "handle": row["handle"],
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "name": row["name"],
            "size": row["size"],
            "group_id": row["group_id"],
            "created_at": row["created_at"],
        } for row in uploads],
    })


def admin_audit(handler: Any, deps: AdminDataDependencies) -> None:
    """返回最近管理操作，并保留已删除账号对应的空关联信息。"""
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT a.id, a.action, a.target_user_id, a.created_at, "
            "actor.username AS actor_username, actor.display_name AS actor_display_name, "
            "target.username AS target_username, target.display_name AS target_display_name "
            "FROM audit_log a LEFT JOIN users actor ON actor.id = a.actor_id "  # 使用 LEFT JOIN，账号删除后审计记录仍可读取。
            "LEFT JOIN users target ON target.id = a.target_user_id "
            "ORDER BY a.id DESC LIMIT 200"
        ).fetchall()
    handler.send_json({"audit": [{
        "id": row["id"],
        "action": row["action"],
        "target_user_id": row["target_user_id"],
        "created_at": row["created_at"],
        "actor_username": row["actor_username"],
        "actor_display_name": row["actor_display_name"],
        "target_username": row["target_username"],
        "target_display_name": row["target_display_name"],
    } for row in rows]})


def delete_job(handler: Any, path: str, deps: AdminDataDependencies) -> None:
    """终止指定后台任务，并把任务记录与结果文件一起移入回收站。

    先确认任务存在，再从共享进程表摘除并终止子进程，最后调用统一回收站事务。进程表
    和数据库使用不同锁域，避免等待子进程退出时长期占用 SQLite 写锁。
    """
    actor = handler.require_user(admin=True)
    job_id = path_id(path, "/api/admin/jobs/")
    with deps.db_lock, deps.db() as connection:
        exists = connection.execute(
            "SELECT 1 FROM web_jobs WHERE id = ?", (job_id,),
        ).fetchone()
    if exists is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    with deps.job_lock:  # 先从共享进程表摘除句柄，避免其他请求继续操作正在删除的任务。
        process = deps.job_processes.pop(job_id, None)
    if process and process.poll() is None:
        process.terminate()
    trash_id = deps.move_job_to_trash(
        job_id, int(actor["id"]), f"trash_job:{job_id}",
    )
    if trash_id is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    handler.send_json({"message": "任务及结果文件已移入回收站"})


def delete_upload(handler: Any, path: str, deps: AdminDataDependencies) -> None:
    """把一条临时上传记录及文件移动到可恢复回收站。

    路径必须位于该记录所属账号的上传根目录中，数据库中的绝对路径不能被直接信任。
    文件先移到回收站载荷位置，再删除索引并登记恢复元数据；若数据库事务失败，则把文件
    移回原位，避免出现只有磁盘内容或只有数据库记录的半删除状态。
    """
    actor = handler.require_user(admin=True)
    handle = path_id(path, "/api/admin/uploads/")
    with deps.storage_lock:  # 文件移动与数据库删除必须处于同一存储锁，防止并发下载读到半移动状态。
        with deps.db_lock, deps.db() as connection:
            row = connection.execute(
                "SELECT * FROM uploads WHERE handle = ?", (handle,),
            ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "上传资料不存在")
        target = Path(row["path"]).resolve()
        upload_root = (deps.data_root / "users" / str(row["user_id"]) / "uploads").resolve()
        if target == upload_root or upload_root not in target.parents:
            raise ApiError(HTTPStatus.BAD_REQUEST, "上传资料路径无效")
        trash_id = uuid.uuid4().hex
        relative = target.relative_to(deps.data_root.resolve()).as_posix()
        payload = deps.data_root / "trash" / trash_id / "payload"
        size = target.stat().st_size if target.is_file() else int(row["size"] or 0)
        if target.is_file():
            payload.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(payload))
        try:
            with deps.db_lock, deps.db() as connection:
                changed = connection.execute(
                    "DELETE FROM uploads WHERE handle = ?", (handle,),
                ).rowcount
                if not changed:
                    raise RuntimeError("上传资料记录已发生变化")
                connection.execute(
                    "INSERT INTO trash_items(id, kind, label, record_json, original_path, "
                    "size, deleted_by, deleted_at) VALUES (?, 'upload', ?, ?, ?, ?, ?, ?)",
                    (
                        trash_id,
                        row["name"],
                        json.dumps(dict(row), ensure_ascii=False),
                        relative,
                        size,
                        actor["id"],
                        deps.now_iso(),
                    ),
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                    (actor["id"], f"trash_upload:{handle}", deps.now_iso()),
                )
        except Exception:
            if payload.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(payload), str(target))
            raise
    handler.send_json({"message": "上传资料已移入回收站"})
