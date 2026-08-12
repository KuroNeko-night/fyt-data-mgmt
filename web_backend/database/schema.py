"""Web SQLite 当前结构的声明式定义。

建表语句和索引集中在本模块，数据库初始化器只负责安排执行顺序。所有语句都必须可
重复执行；历史库缺列的兼容升级放在 :mod:`web_backend.database.migrations`，避免把
“当前完整结构”和“从旧版本走到当前版本的步骤”混在同一个巨型函数中。
"""

from __future__ import annotations

from typing import Any


BASE_SCHEMA_SQL = """
-- 身份、会话与登录防护。会话随账号删除，失败记录按客户端键独立限流。
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    approved_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    id TEXT,
    created_at TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_key TEXT PRIMARY KEY,
    failures INTEGER NOT NULL,
    window_started INTEGER NOT NULL,
    locked_until INTEGER NOT NULL DEFAULT 0,
    last_failed_at INTEGER NOT NULL
);

-- 可恢复删除和管理审计。回收站文件本体位于数据目录，表内只存恢复元数据。
CREATE TABLE IF NOT EXISTS trash_items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    record_json TEXT NOT NULL,
    original_path TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    deleted_by INTEGER,
    deleted_at TEXT NOT NULL,
    FOREIGN KEY(deleted_by) REFERENCES users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    target_user_id INTEGER,
    created_at TEXT NOT NULL
);

-- 业务任务的短期上传句柄，与长期共享文件库分开管理。
CREATE TABLE IF NOT EXISTS uploads (
    handle TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS library_files (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    description TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'team',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    category TEXT NOT NULL DEFAULT 'unknown',
    categories TEXT NOT NULL DEFAULT '[]',
    confidence INTEGER NOT NULL DEFAULT 0,
    signals TEXT NOT NULL DEFAULT '[]',
    sheet TEXT NOT NULL DEFAULT '',
    category_sheets TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS library_file_categories (
    file_id TEXT NOT NULL REFERENCES library_files(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    PRIMARY KEY(file_id, category)
);

-- 现场问题主记录与图片证据。模板专用字段保留为列，便于筛选和标准报表导出。
CREATE TABLE IF NOT EXISTS workshop_issues (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issue_date TEXT NOT NULL,
    cause TEXT NOT NULL,
    primary_owner TEXT NOT NULL,
    secondary_owner TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    severity TEXT NOT NULL DEFAULT 'normal',
    issue_source TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    batch_no TEXT NOT NULL DEFAULT '',
    team TEXT NOT NULL DEFAULT '',
    material_code TEXT NOT NULL DEFAULT '',
    material_name TEXT NOT NULL DEFAULT '',
    cause_analysis TEXT NOT NULL DEFAULT '',
    corrective_action TEXT NOT NULL DEFAULT '',
    responsibility_party TEXT NOT NULL DEFAULT '',
    discoverer TEXT NOT NULL DEFAULT '',
    issue_level TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL DEFAULT '',
    issue_type TEXT NOT NULL DEFAULT '',
    completion_date TEXT NOT NULL DEFAULT '',
    recurring TEXT NOT NULL DEFAULT '',
    carrier TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    tracking_status TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    resolution_status TEXT NOT NULL DEFAULT 'open',
    resolution_note TEXT NOT NULL DEFAULT '',
    resolved_at TEXT NOT NULL DEFAULT '',
    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workshop_issue_images (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL REFERENCES workshop_issues(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 后台任务、历史版本、参数模板和临时分享链接。
CREATE TABLE IF NOT EXISTS web_jobs (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    logs TEXT NOT NULL DEFAULT '[]',
    result TEXT,
    error TEXT,
    files TEXT NOT NULL DEFAULT '[]',
    cancelled INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT '{}',
    retry_of TEXT,
    assignee_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS web_job_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES web_jobs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    result TEXT,
    files TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, version)
);
CREATE TABLE IF NOT EXISTS web_templates (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS share_tokens (
    token TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    file_index INTEGER NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

-- 全局公告、定向消息及每个账号的公告已读状态。
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    read_at TEXT,
    FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS announcement_reads (
    announcement_id INTEGER NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at TEXT NOT NULL,
    PRIMARY KEY (announcement_id, user_id)
);

-- 日清参会人员逐人考勤；生产人员不再逐人维护，改由后续班组/班次表统计。
CREATE TABLE IF NOT EXISTS daily_people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    person_type TEXT NOT NULL DEFAULT 'participant',
    unit TEXT NOT NULL DEFAULT '',
    shift TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    person_id INTEGER NOT NULL REFERENCES daily_people(id) ON DELETE RESTRICT,
    present INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'present',
    reason TEXT NOT NULL DEFAULT '',
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(report_date, person_id)
);

-- 生产班组、旧版按组考勤，以及当前按班次保存编制快照的考勤结构。
CREATE TABLE IF NOT EXISTS daily_production_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_production_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    group_id INTEGER NOT NULL REFERENCES daily_production_groups(id) ON DELETE RESTRICT,
    attendance_count INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(report_date, group_id)
);
CREATE TABLE IF NOT EXISTS daily_production_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES daily_production_groups(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    staffing_count INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(group_id, name)
);
CREATE TABLE IF NOT EXISTS daily_production_shift_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    shift_id INTEGER NOT NULL REFERENCES daily_production_shifts(id) ON DELETE RESTRICT,
    staffing_count INTEGER NOT NULL DEFAULT 0,
    attendance_count INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(report_date, shift_id)
);

-- 日清事项和三类外部资料：生产计划、到料成品、安全检查成品。
CREATE TABLE IF NOT EXISTS daily_brief_items (
    id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'notice',
    unit TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    due_date TEXT NOT NULL DEFAULT '',
    progress TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_production_plans (
    id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    data_month TEXT NOT NULL DEFAULT '',
    original_name TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    summary TEXT NOT NULL DEFAULT '{}',
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_source_uploads (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    report_date TEXT NOT NULL,
    data_month TEXT NOT NULL DEFAULT '',
    original_name TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    summary TEXT NOT NULL DEFAULT '{}',
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


INDEX_STATEMENTS = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_id ON sessions(id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_library_files_updated ON library_files(updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_library_files_owner ON library_files(owner_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_library_file_categories_category "
    "ON library_file_categories(category, file_id)",
    "CREATE INDEX IF NOT EXISTS idx_workshop_issues_date "
    "ON workshop_issues(issue_date, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_workshop_issue_images_issue "
    "ON workshop_issue_images(issue_id, sort_order, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_daily_people_active "
    "ON daily_people(active, person_type, sort_order, name)",
    "CREATE INDEX IF NOT EXISTS idx_daily_attendance_date "
    "ON daily_attendance(report_date, person_id)",
    "CREATE INDEX IF NOT EXISTS idx_daily_production_groups_active "
    "ON daily_production_groups(active, sort_order, name)",
    "CREATE INDEX IF NOT EXISTS idx_daily_production_attendance_date "
    "ON daily_production_attendance(report_date, group_id)",
    "CREATE INDEX IF NOT EXISTS idx_daily_production_shifts_group "
    "ON daily_production_shifts(group_id, active, sort_order, name)",
    "CREATE INDEX IF NOT EXISTS idx_daily_production_shift_attendance_date "
    "ON daily_production_shift_attendance(report_date, shift_id)",
    "CREATE INDEX IF NOT EXISTS idx_daily_brief_date "
    "ON daily_brief_items(report_date, category, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_daily_plan_date "
    "ON daily_production_plans(report_date, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_daily_plan_month "
    "ON daily_production_plans(data_month, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_daily_source_date "
    "ON daily_source_uploads(kind, report_date, updated_at DESC)",
)


def create_current_schema(connection: Any) -> None:
    """创建空数据库所需的全部当前表；已有表保持不变。"""
    connection.executescript(BASE_SCHEMA_SQL)


def create_current_indexes(connection: Any) -> None:
    """在字段迁移完成后创建当前索引，避免旧表尚未补列时建索引失败。"""
    for statement in INDEX_STATEMENTS:
        connection.execute(statement)
