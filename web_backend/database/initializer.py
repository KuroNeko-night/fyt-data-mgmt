"""Web 数据库初始化入口。

本模块只安排建表、幂等升级、历史迁移和启动清理的执行顺序。具体 SQL 结构与迁移规则
分别位于 ``schema`` 和 ``migrations``，使新增版本时可以独立审查当前结构和升级路径。
全部步骤共用一个 SQLite 事务：任一步失败都会回滚，避免服务带着半迁移数据库启动。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import migrations, schema


def initialize(
    *,
    db_lock: Any,
    db_factory: Callable[[], Any],
    now_iso: Callable[[], str],
    hash_password: Callable[[str], tuple[str, str]],
    password_policy_error: Callable[[str], str | None],
    workshop_issue_template_fields: dict[str, tuple[str, str]],
) -> None:
    """创建或升级 Web 数据库，并把旧版本数据迁移到当前字段模型。

    调用方必须传入可重入数据库锁。首次部署没有管理员记录时，只接受环境变量提供的
    合规密码；初始化过程不会生成固定密码，也不会把凭据写到页面或日志。
    """
    with db_lock, db_factory() as connection:
        schema.create_current_schema(connection)
        migrations.upgrade_additive_columns(
            connection,
            workshop_issue_template_fields,
        )
        migrations.normalize_library_categories(connection)
        migrations.backfill_sessions(connection, now_iso)
        migrations.backfill_daily_plan_month(connection)
        migrations.normalize_workshop_issues(connection)
        migrations.migrate_legacy_production_attendance(connection, now_iso)
        schema.create_current_indexes(connection)
        _ensure_initial_admin(
            connection,
            now_iso=now_iso,
            hash_password=hash_password,
            password_policy_error=password_policy_error,
        )
        _cleanup_runtime_state(connection)


def _ensure_initial_admin(
    connection: Any,
    *,
    now_iso: Callable[[], str],
    hash_password: Callable[[str], tuple[str, str]],
    password_policy_error: Callable[[str], str | None],
) -> None:
    """首次建库时创建唯一默认管理员账号，但绝不提供固定默认密码。"""
    admin = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        ("admin",),
    ).fetchone()
    if admin is not None:
        return
    initial_password = _load_initial_admin_password()
    if not initial_password:
        raise RuntimeError(
            "首次启动必须通过 FYT_ADMIN_PASSWORD、FYT_ADMIN_PASSWORD_FILE 或服务控制台设置管理员密码"
        )
    policy_error = password_policy_error(initial_password)
    if policy_error:
        raise RuntimeError(f"管理员初始密码不符合要求：{policy_error}")
    salt, digest = hash_password(initial_password)
    created_at = now_iso()
    connection.execute(
        "INSERT INTO users"
        "(username, display_name, salt, password_hash, role, status, created_at, approved_at) "
        "VALUES (?, ?, ?, ?, 'admin', 'approved', ?, ?)",
        ("admin", "系统管理员", salt, digest, created_at, created_at),
    )
    # 建号成功后立即清除进程环境中的明文密码，避免其在服务进程整个生命周期内驻留，
    # 可通过 /proc/<pid>/environ 或等价手段被读取。文件来源的 Docker secret 由部署方管理。
    os.environ.pop("FYT_ADMIN_PASSWORD", None)


def _load_initial_admin_password() -> str:
    """读取首次建库密码，优先使用进程环境，其次读取受控密码文件。

    Docker 使用 ``FYT_ADMIN_PASSWORD_FILE`` 指向只读 secret，避免把真实密码写入镜像、
    Compose 文件或容器环境。文件只允许一行且最多 128 个字符；错误消息不回显路径或
    内容，防止部署日志泄露敏感信息。已有管理员时不会调用本函数。
    """
    password = os.environ.get("FYT_ADMIN_PASSWORD", "")
    if password:
        return password
    source = os.environ.get("FYT_ADMIN_PASSWORD_FILE", "").strip()
    if not source:
        return ""
    try:
        with Path(source).open("r", encoding="utf-8") as handle:
            content = handle.read(130)
    except OSError as exc:
        raise RuntimeError("无法读取首次管理员密码文件") from exc
    password = content.rstrip("\r\n")
    if len(content) > 129 or "\n" in password or "\r" in password:
        raise RuntimeError("首次管理员密码文件必须只包含一行，且不能超过 128 个字符")
    return password


def _cleanup_runtime_state(connection: Any) -> None:
    """清理过期安全状态，并把重启前未结束的任务明确标记为中断。"""
    now_timestamp = int(time.time())
    connection.execute(
        "DELETE FROM sessions WHERE expires_at < ?",
        (now_timestamp,),
    )
    connection.execute(
        "DELETE FROM login_attempts WHERE last_failed_at < ?",
        (now_timestamp - 86400,),
    )
    connection.execute(
        "UPDATE web_jobs SET status = 'interrupted', error = ? "
        "WHERE status IN ('queued', 'running')",
        ("服务端重启，任务已中断",),
    )
