"""Web SQLite 的幂等字段升级与历史数据迁移。

每个公开迁移函数只处理一个相对独立的数据域。初始化器在同一连接事务中依次调用，
所以任一步失败都会整体回滚；函数本身仍须可重复执行，以支持服务端每次启动安全检查
数据库结构。迁移不得删除仍有业务意义的历史记录。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from core import library as core_library
from core import workshop_issue_core


_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _table_columns(connection: Any, table: str) -> set[str]:
    """返回表的现有列名；表名只接受程序内定义的普通 SQL 标识符。"""
    if not _SQL_IDENTIFIER.fullmatch(table):
        raise ValueError(f"非法数据库表名：{table}")
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _add_missing_columns(
    connection: Any,
    table: str,
    definitions: Mapping[str, str],
) -> None:
    """按受控定义为旧表补列，已经存在的列保持原值和原约束。"""
    existing = _table_columns(connection, table)
    for name, definition in definitions.items():
        if not _SQL_IDENTIFIER.fullmatch(name):
            raise ValueError(f"非法数据库列名：{name}")
        if name in existing:
            continue
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        existing.add(name)


def upgrade_additive_columns(
    connection: Any,
    workshop_issue_template_fields: Mapping[str, tuple[str, str]],
) -> None:
    """补齐历代新增列；这里只做不破坏数据的加法升级。"""
    _add_missing_columns(
        connection,
        "web_jobs",
        {
            "payload": "TEXT NOT NULL DEFAULT '{}'",
            "retry_of": "TEXT",
            "assignee_id": "INTEGER",
        },
    )
    _add_missing_columns(
        connection,
        "library_files",
        {
            "category": "TEXT NOT NULL DEFAULT 'unknown'",
            "categories": "TEXT NOT NULL DEFAULT '[]'",
            "confidence": "INTEGER NOT NULL DEFAULT 0",
            "signals": "TEXT NOT NULL DEFAULT '[]'",
            "sheet": "TEXT NOT NULL DEFAULT ''",
            "category_sheets": "TEXT NOT NULL DEFAULT '{}'",
        },
    )
    _add_missing_columns(
        connection,
        "sessions",
        {
            "id": "TEXT",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "last_seen_at": "TEXT NOT NULL DEFAULT ''",
            "ip_address": "TEXT NOT NULL DEFAULT ''",
            "user_agent": "TEXT NOT NULL DEFAULT ''",
        },
    )
    _add_missing_columns(
        connection,
        "workshop_issues",
        {
            "category": "TEXT NOT NULL DEFAULT 'other'",
            "severity": "TEXT NOT NULL DEFAULT 'normal'",
            "resolution_status": "TEXT NOT NULL DEFAULT 'open'",
            "resolution_note": "TEXT NOT NULL DEFAULT ''",
            "resolved_at": "TEXT NOT NULL DEFAULT ''",
            "resolved_by": "INTEGER",
            **{
                field: definition[0]
                for field, definition in workshop_issue_template_fields.items()
            },
        },
    )
    _add_missing_columns(
        connection,
        "daily_production_plans",
        {"data_month": "TEXT NOT NULL DEFAULT ''"},
    )


def normalize_library_categories(connection: Any) -> None:
    """统一文件库主类别、JSON 多标签和关系表三种表示。"""
    valid_categories = set(core_library.CATEGORIES) | {core_library.UNKNOWN}
    rows = connection.execute(
        "SELECT id, category, categories FROM library_files"
    ).fetchall()
    for row in rows:
        primary = str(row["category"] or core_library.UNKNOWN)
        if primary not in valid_categories:
            primary = core_library.UNKNOWN
        try:
            raw_categories = json.loads(row["categories"] or "[]")
        except (TypeError, json.JSONDecodeError):
            raw_categories = []
        categories = _valid_category_list(raw_categories, valid_categories)
        if primary not in categories:
            categories.insert(0, primary)
        categories = list(dict.fromkeys(categories))
        serialized = json.dumps(categories, ensure_ascii=False)
        if primary != row["category"] or serialized != (row["categories"] or ""):
            connection.execute(
                "UPDATE library_files SET category = ?, categories = ? WHERE id = ?",
                (primary, serialized, row["id"]),
            )
        _replace_library_category_links(connection, str(row["id"]), categories)


def _valid_category_list(raw: object, valid_categories: set[str]) -> list[str]:
    """从历史 JSON 值中保留受支持且顺序稳定的类别名称。"""
    if not isinstance(raw, list):
        return []
    return [
        value
        for value in raw
        if isinstance(value, str) and value in valid_categories
    ]


def _replace_library_category_links(
    connection: Any,
    file_id: str,
    categories: list[str],
) -> None:
    """以规范类别列表重建单个文件的关系表记录。"""
    connection.execute(
        "DELETE FROM library_file_categories WHERE file_id = ?",
        (file_id,),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO library_file_categories(file_id, category) VALUES (?, ?)",
        [(file_id, category) for category in categories],
    )


def backfill_sessions(connection: Any, now_iso: Callable[[], str]) -> None:
    """为旧会话生成公开编号和管理页需要的时间字段。"""
    connection.execute(
        "UPDATE sessions SET id = lower(hex(randomblob(16))) WHERE id IS NULL OR id = ''"
    )
    migration_time = now_iso()
    connection.execute(
        "UPDATE sessions SET created_at = ?, last_seen_at = ? "
        "WHERE created_at = '' OR last_seen_at = ''",
        (migration_time, migration_time),
    )


def backfill_daily_plan_month(connection: Any) -> None:
    """从 ISO 业务日期回填旧生产计划的月份索引。"""
    connection.execute(
        "UPDATE daily_production_plans SET data_month = substr(report_date, 1, 7) "
        "WHERE data_month IS NULL OR data_month = ''"
    )


def normalize_workshop_issues(connection: Any) -> None:
    """把历史问题类别、负责人和等级归一到当前五类模板。"""
    for legacy_issue in connection.execute("SELECT * FROM workshop_issues").fetchall():
        values = dict(legacy_issue)
        category = workshop_issue_core.normalize_workshop_category(
            values.get("category"), values,
        )
        primary_owner = workshop_issue_core.workshop_issue_primary_owner(
            category,
            values,
            values.get("primary_owner"),
        )
        severity = workshop_issue_core.workshop_issue_severity(
            values,
            values.get("severity") or "normal",
        )
        if (
            category == values.get("category")
            and primary_owner == values.get("primary_owner")
            and severity == values.get("severity")
        ):
            continue
        connection.execute(
            "UPDATE workshop_issues SET category = ?, primary_owner = ?, severity = ? WHERE id = ?",
            (category, primary_owner, severity, values["id"]),
        )


def migrate_legacy_production_attendance(
    connection: Any,
    now_iso: Callable[[], str],
) -> None:
    """把旧版逐人/按组生产考勤迁移为当前按班组班次的编制快照。"""
    migration_time = now_iso()
    _create_groups_from_legacy_people(connection, migration_time)
    _ensure_default_production_shifts(connection, migration_time)
    _aggregate_legacy_people_attendance(connection, migration_time)
    _copy_group_attendance_to_shifts(connection)


def _create_groups_from_legacy_people(connection: Any, migration_time: str) -> None:
    """从旧生产人员的单位或姓名建立班组主数据。"""
    rows = connection.execute(
        "SELECT id, name, unit, sort_order, active, created_at, updated_at "
        "FROM daily_people WHERE person_type = 'production' ORDER BY sort_order, id"
    ).fetchall()
    for row in rows:
        group_name = str(row["unit"] or row["name"] or "").strip()
        if not group_name:
            continue
        connection.execute(
            "INSERT OR IGNORE INTO daily_production_groups"
            "(name, sort_order, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                group_name,
                int(row["sort_order"] or 0),
                int(row["active"] or 0),
                row["created_at"] or migration_time,
                row["updated_at"] or migration_time,
            ),
        )


def _ensure_default_production_shifts(connection: Any, migration_time: str) -> None:
    """为还没有新版班次的历史班组补一个默认白班。"""
    connection.execute(
        "INSERT INTO daily_production_shifts"
        "(group_id, name, staffing_count, sort_order, active, created_at, updated_at) "
        "SELECT g.id, '白班', 0, 0, g.active, COALESCE(NULLIF(g.created_at, ''), ?), "
        "COALESCE(NULLIF(g.updated_at, ''), ?) FROM daily_production_groups g "
        "WHERE NOT EXISTS (SELECT 1 FROM daily_production_shifts s WHERE s.group_id = g.id)",
        (migration_time, migration_time),
    )


def _aggregate_legacy_people_attendance(connection: Any, migration_time: str) -> None:
    """把逐人出勤聚合为“日期 + 班组”的人数和备注。"""
    rows = connection.execute(
        "SELECT a.report_date, p.name, p.unit, a.present, a.reason, a.updated_by, a.updated_at "
        "FROM daily_attendance a JOIN daily_people p ON p.id = a.person_id "
        "WHERE p.person_type = 'production' ORDER BY a.report_date, p.sort_order, p.id"
    ).fetchall()
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        group_name = str(row["unit"] or row["name"] or "").strip()
        if not group_name:
            continue
        key = (str(row["report_date"]), group_name)
        target = grouped.setdefault(
            key,
            {
                "count": 0,
                "notes": [],
                "updated_by": row["updated_by"],
                "updated_at": row["updated_at"] or migration_time,
            },
        )
        _merge_legacy_attendance_row(target, row)
    for (report_date, group_name), values in grouped.items():
        _insert_legacy_group_attendance(
            connection,
            report_date,
            group_name,
            values,
        )


def _merge_legacy_attendance_row(target: dict[str, object], row: Any) -> None:
    """将一条旧人员考勤合并进班组聚合器。"""
    if bool(row["present"]):
        target["count"] = int(target["count"]) + 1
    reason = str(row["reason"] or "").strip()
    notes = target["notes"]
    if reason and isinstance(notes, list):
        notes.append(f"{row['name']}：{reason}")
    if str(row["updated_at"] or "") > str(target["updated_at"] or ""):
        target["updated_at"] = row["updated_at"]
        target["updated_by"] = row["updated_by"]


def _insert_legacy_group_attendance(
    connection: Any,
    report_date: str,
    group_name: str,
    values: dict[str, object],
) -> None:
    """写入一组幂等的旧班组考勤聚合结果。"""
    group_row = connection.execute(
        "SELECT id FROM daily_production_groups WHERE name = ?",
        (group_name,),
    ).fetchone()
    if group_row is None:
        return
    notes = values["notes"] if isinstance(values["notes"], list) else []
    connection.execute(
        "INSERT OR IGNORE INTO daily_production_attendance"
        "(report_date, group_id, attendance_count, note, updated_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            report_date,
            int(group_row["id"]),
            int(values["count"]),
            "；".join(notes),
            values["updated_by"],
            values["updated_at"],
        ),
    )


def _copy_group_attendance_to_shifts(connection: Any) -> None:
    """把旧按组考勤落到该组排序最前的班次，重复启动不会复制。"""
    connection.execute(
        "INSERT OR IGNORE INTO daily_production_shift_attendance"
        "(report_date, shift_id, staffing_count, attendance_count, note, updated_by, updated_at) "
        "SELECT a.report_date, s.id, s.staffing_count, a.attendance_count, a.note, a.updated_by, a.updated_at "
        "FROM daily_production_attendance a JOIN daily_production_groups g ON g.id = a.group_id "
        "JOIN daily_production_shifts s ON s.id = ("
        "SELECT s2.id FROM daily_production_shifts s2 WHERE s2.group_id = g.id "
        "ORDER BY s2.active DESC, s2.sort_order, s2.name, s2.id LIMIT 1)"
    )
