"""日清参会人员、生产班组、班次与考勤维护服务。

本模块只处理人员和出勤主数据。生产人员按“班组 + 班次”维护编制与当日人数，
参会人员按名册逐人维护状态；历史快照不会因主数据后续调整被回写。全部写操作要求
admin，考勤保存为同一事务内的批量 upsert，主数据有历史记录时只停用不物理删除。
"""

from __future__ import annotations

import sqlite3
import uuid
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

from web_backend.errors import ApiError
from web_backend.http.path_params import path_id
from web_backend.services.daily_management_types import DailyManagementDependencies


def _daily_person_id(path: str) -> int:
    """解析参会人员整数主键，拒绝小数、负数和附加路径片段。"""
    value = path_id(path, "/api/admin/daily-people/")
    if not value.isdigit():
        raise ApiError(HTTPStatus.BAD_REQUEST, "人员编号无效")
    return int(value)


def _daily_production_group_id(path: str) -> int:
    """解析生产班组整数主键。"""
    value = path_id(path, "/api/admin/daily-production-groups/")
    if not value.isdigit():
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组编号无效")
    return int(value)


def _validate_daily_person(
    values: dict[str, object], deps: DailyManagementDependencies,
) -> tuple[str, str, str, str, int, bool]:
    """校验参会人员主数据并返回可直接入库的规范化字段。

    生产人员已经改为按班组和班次统计，因此人员名册只接受参会人员；排序值被钳制在
    有限范围，防止异常大整数影响前端排序和后续导出。
    """
    name = str(values.get("name") or "").strip()
    person_type = str(values.get("person_type") or "participant").strip()
    unit = str(values.get("unit") or "").strip()
    shift = str(values.get("shift") or "").strip()
    try:
        sort_order = int(values.get("sort_order") or 0)
    except (TypeError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "人员排序无效") from exc
    active = values.get("active", True)
    if not isinstance(active, bool):
        raise ApiError(HTTPStatus.BAD_REQUEST, "人员启用状态无效")
    if not name or len(name) > 40:
        raise ApiError(HTTPStatus.BAD_REQUEST, "参会人员姓名需要填写且不能超过 40 个字")
    if person_type not in deps.person_types:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产人员请按班组维护，人员名册只保存参会人员")
    if len(unit) > 80 or len(shift) > 40:
        raise ApiError(HTTPStatus.BAD_REQUEST, "单位、班组或班次内容过长")
    return name, person_type, unit, shift, max(-9999, min(sort_order, 9999)), active  # 统一在服务端约束排序边界。


def _production_group_sort_order(value: object) -> int:
    """解析并钳制生产班组排序值，拒绝无法转换为整数的输入。"""
    try:
        return max(-9999, min(int(value or 0), 9999))
    except (TypeError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组排序无效") from exc


def _production_group_active(value: object) -> bool:
    """校验生产班组启用状态，避免字符串 ``false`` 被当作真值入库。"""
    if not isinstance(value, bool):
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组启用状态无效")
    return value


def _production_shift(raw_shift: object) -> dict[str, object]:
    """规范化一个班次的编号、名称、编制、排序和启用状态。"""
    if not isinstance(raw_shift, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次格式无效")
    shift_name = str(raw_shift.get("name") or "").strip()
    if not shift_name or len(shift_name) > 40:
        raise ApiError(HTTPStatus.BAD_REQUEST, "班次名称需要填写且不能超过 40 个字")
    try:
        staffing_count = int(raw_shift.get("staffing_count") or 0)
        shift_sort_order = int(raw_shift.get("sort_order") or 0)
        shift_id = int(raw_shift["id"]) if raw_shift.get("id") is not None else None
    except (TypeError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次编制或排序无效") from exc
    shift_active = raw_shift.get("active", True)
    if not isinstance(shift_active, bool):
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次启用状态无效")
    if staffing_count < 0 or staffing_count > 100000:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次编制人数超出合理范围")
    return {
        "id": shift_id,  # None 表示新增班次，已有编号由同步阶段校验是否属于当前班组。
        "name": shift_name,
        "staffing_count": staffing_count,
        "sort_order": max(-9999, min(shift_sort_order, 9999)),
        "active": shift_active,
    }


def _production_shifts(raw_shifts: object) -> list[dict[str, object]] | None:
    """规范化可选班次快照，并拒绝空快照、超量或组内重名。"""
    if raw_shifts is None:
        return None  # 未提交 shifts 表示只修改班组字段，不能误删原有班次。
    if not isinstance(raw_shifts, list) or not raw_shifts or len(raw_shifts) > 12:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组至少需要一个班次，且不能超过 12 个")
    shifts: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for raw_shift in raw_shifts:
        shift = _production_shift(raw_shift)
        normalized_name = str(shift["name"]).casefold()  # Unicode 无关大小写比较不改变中文名称。
        if normalized_name in seen_names:
            raise ApiError(HTTPStatus.BAD_REQUEST, "同一班组内不能存在重名班次")
        seen_names.add(normalized_name)
        shifts.append(shift)
    return shifts


def _validate_daily_production_group(
    values: dict[str, object],
) -> tuple[str, int, bool, list[dict[str, object]] | None]:
    """校验生产班组名称及班次编制，返回可直接持久化的规范结构。

    ``shifts is None`` 表示调用方没有要求修改班次；空列表则是不合法的显式修改。二者
    必须区分，否则只编辑班组名称时可能误删全部班次。
    """
    name = str(values.get("name") or "").strip()
    if not name or len(name) > 80:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组名称需要填写且不能超过 80 个字")
    sort_order = _production_group_sort_order(values.get("sort_order"))
    active = _production_group_active(values.get("active", True))
    return name, sort_order, active, _production_shifts(values.get("shifts"))


def _daily_production_shift_rows(connection: Any, group_id: int) -> list[Any]:
    """读取班组的全部班次；停用项仍返回，供管理员维护和历史解释。"""
    return connection.execute(
        "SELECT * FROM daily_production_shifts WHERE group_id = ? "
        "ORDER BY active DESC, sort_order, name, id",
        (group_id,),
    ).fetchall()


def _sync_daily_production_shifts(
    connection: Any,
    group_id: int,
    shifts: list[dict[str, object]],
    updated: str,
    deps: DailyManagementDependencies,
) -> list[Any]:
    """同步班次主数据，并保留已有考勤历史和当天编制快照。

    客户端提交的是班次完整快照：存在编号的记录更新，无编号记录新增，未再提交的记录
    删除或停用。已有考勤历史的班次不能物理删除；更新编制时仅同步“今天”的考勤快照，
    过去日期继续保留当时编制，确保历史差异统计不会随主数据变化。
    """
    existing_rows = _daily_production_shift_rows(connection, group_id)
    existing = {int(row["id"]): row for row in existing_rows}
    requested_ids = {  # 先验证所有外来编号，避免部分更新后才发现跨班组编号。
        int(item["id"]) for item in shifts if item.get("id") is not None
    }
    unknown = sorted(requested_ids - set(existing))
    if unknown:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次不属于当前班组")
    # 班次名称有组内唯一约束。先把待更新记录改为随机占位名，允许“白班/夜班”互换名称。
    for shift_id in requested_ids:
        connection.execute(
            "UPDATE daily_production_shifts SET name = ? WHERE id = ?",
            (f"__fyt_pending_{shift_id}_{uuid.uuid4().hex}", shift_id),
        )
    for shift_id in existing:
        if shift_id in requested_ids:
            continue
        history = int(connection.execute(
            "SELECT COUNT(*) AS n FROM daily_production_shift_attendance WHERE shift_id = ?",
            (shift_id,),
        ).fetchone()["n"])
        if history:
            connection.execute(
                "UPDATE daily_production_shifts SET active = 0, updated_at = ? WHERE id = ?",
                (updated, shift_id),
            )
        else:
            connection.execute("DELETE FROM daily_production_shifts WHERE id = ?", (shift_id,))
    for item in shifts:
        values = (
            str(item["name"]), int(item["staffing_count"]), int(item["sort_order"]),
            int(bool(item["active"])), updated,
        )
        if item.get("id") is None:
            connection.execute(
                "INSERT INTO daily_production_shifts"
                "(group_id, name, staffing_count, sort_order, active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (group_id, *values[:-1], updated, updated),  # ``values`` 最后一项已是更新时间，插入需额外提供创建时间。
            )
        else:
            connection.execute(
                "UPDATE daily_production_shifts SET name = ?, staffing_count = ?, sort_order = ?, "
                "active = ?, updated_at = ? WHERE id = ?",
                (*values, int(item["id"])),
            )
            connection.execute(
                "UPDATE daily_production_shift_attendance SET staffing_count = ?, updated_at = ? "
                "WHERE shift_id = ? AND report_date = ?",
                (
                    int(item["staffing_count"]), updated, int(item["id"]),
                    deps.business_today().isoformat(),  # 只修正当日快照，不回写历史编制。
                ),
            )
    return _daily_production_shift_rows(connection, group_id)


def production_attendance_rows(connection: Any, report_date: str) -> list[Any]:
    """组合班组、班次与指定日期考勤，生成看板所需的完整行集。

    即使当天尚未填报，也要通过 ``LEFT JOIN`` 返回启用班次并以零出勤展示；已停用但
    当天存在历史记录的班次也保留，避免维护主数据后旧日报缺行。
    """
    return connection.execute(
        "SELECT a.id, ? AS report_date, g.id AS group_id, g.name AS group_name, "
        "s.id AS shift_id, s.name AS shift_name, COALESCE(a.staffing_count, s.staffing_count, 0) AS staffing_count, "
        "COALESCE(a.attendance_count, 0) AS attendance_count, COALESCE(a.note, '') AS note, "
        "a.updated_by, COALESCE(a.updated_at, '') AS updated_at "
        "FROM daily_production_groups g JOIN daily_production_shifts s ON s.group_id = g.id "
        "LEFT JOIN daily_production_shift_attendance a ON a.shift_id = s.id AND a.report_date = ? "
        "WHERE (g.active = 1 AND s.active = 1) OR a.id IS NOT NULL "  # 活跃主数据与历史快照取并集。
        "ORDER BY g.sort_order, g.name, g.id, s.sort_order, s.name, s.id",
        (report_date, report_date),
    ).fetchall()


def attendance_rows(connection: Any, report_date: str) -> list[Any]:
    """组合参会人员名册与指定日期考勤，未填报人员默认按出勤返回。

    默认出勤符合日常填报习惯，管理员只需关闭缺勤人员；停用人员仅在该日期已有考勤时
    返回，从而兼顾当前表单简洁和历史日报完整性。
    """
    return connection.execute(
        "SELECT a.id, ? AS report_date, p.id AS person_id, p.name, p.person_type, p.unit, p.shift, "
        "COALESCE(a.present, 1) AS present, COALESCE(a.status, 'present') AS status, "
        "COALESCE(a.reason, '') AS reason, a.updated_by, COALESCE(a.updated_at, '') AS updated_at "
        "FROM daily_people p LEFT JOIN daily_attendance a "
        "ON a.person_id = p.id AND a.report_date = ? "
        "WHERE p.person_type = 'participant' AND (p.active = 1 OR a.id IS NOT NULL) "
        "ORDER BY p.sort_order, p.name, p.id",
        (report_date, report_date),
    ).fetchall()

def list_daily_people(handler: Any, deps: DailyManagementDependencies) -> None:
    """返回管理员可维护的参会人员名册，停用人员排在末尾。"""
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT * FROM daily_people WHERE person_type = 'participant' "
            "ORDER BY active DESC, sort_order, name, id"
        ).fetchall()
    handler.send_json({"people": [deps.daily_person_public(row) for row in rows]})

def create_daily_person(handler: Any, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """新增参会人员主数据，并阻止姓名、单位和班次完全相同的重复记录。"""
    actor = handler.require_user(admin=True)
    name, person_type, unit, shift, sort_order, active = _validate_daily_person(body, deps)
    created = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        duplicate = connection.execute(
            "SELECT id FROM daily_people WHERE name = ? AND person_type = ? AND unit = ? AND shift = ?",
            (name, person_type, unit, shift),
        ).fetchone()
        if duplicate is not None:
            raise ApiError(HTTPStatus.CONFLICT, "相同人员已经存在")
        cursor = connection.execute(
            "INSERT INTO daily_people(name, person_type, unit, shift, sort_order, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, person_type, unit, shift, sort_order, int(active), created, created),
        )
        person_id = int(cursor.lastrowid)  # SQLite 自增主键在同一连接中读取，避免再次按名称查找产生歧义。
        row = connection.execute("SELECT * FROM daily_people WHERE id = ?", (person_id,)).fetchone()
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_person_create:{person_id}", created),
        )
    handler.send_json({"message": "日清人员已添加", "person": deps.daily_person_public(row)}, HTTPStatus.CREATED)

def update_daily_person(handler: Any, path: str, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """更新参会人员主数据，并在排除自身后检查复合重复项。

    姓名、人员类型、单位和班次共同定义业务重复；启停与排序可独立调整。更新和审计在
    同一事务中完成，历史考勤通过人员编号关联，不因显示字段修改而丢失。
    """
    actor = handler.require_user(admin=True)
    person_id = _daily_person_id(path)
    name, person_type, unit, shift, sort_order, active = _validate_daily_person(body, deps)
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        duplicate = connection.execute(
            "SELECT id FROM daily_people WHERE name = ? AND person_type = ? AND unit = ? AND shift = ? AND id <> ?",
            (name, person_type, unit, shift, person_id),
        ).fetchone()
        if duplicate is not None:
            raise ApiError(HTTPStatus.CONFLICT, "相同人员已经存在")
        changed = connection.execute(
            "UPDATE daily_people SET name = ?, person_type = ?, unit = ?, shift = ?, sort_order = ?, active = ?, updated_at = ? WHERE id = ?",
            (name, person_type, unit, shift, sort_order, int(active), updated, person_id),
        ).rowcount
        if not changed:
            raise ApiError(HTTPStatus.NOT_FOUND, "日清人员不存在")
        row = connection.execute("SELECT * FROM daily_people WHERE id = ?", (person_id,)).fetchone()
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_person_update:{person_id}", updated),
        )
    handler.send_json({"message": "日清人员已更新", "person": deps.daily_person_public(row)})

def delete_daily_person(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """删除从未使用的人员，或停用已有考勤历史的人员。

    物理删除有历史记录的人员会破坏旧日报外键和姓名解释，因此此时只设置 ``active=0``。
    """
    actor = handler.require_user(admin=True)
    person_id = _daily_person_id(path)
    with deps.db_lock, deps.db() as connection:
        row = connection.execute("SELECT * FROM daily_people WHERE id = ?", (person_id,)).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "日清人员不存在")
        history = int(connection.execute(
            "SELECT COUNT(*) AS n FROM daily_attendance WHERE person_id = ?", (person_id,)
        ).fetchone()["n"])
        if history:
            connection.execute(
                "UPDATE daily_people SET active = 0, updated_at = ? WHERE id = ?", (deps.now_iso(), person_id)
            )
            message = "人员已停用，历史考勤已保留"
        else:
            connection.execute("DELETE FROM daily_people WHERE id = ?", (person_id,))
            message = "日清人员已删除"
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_person_delete:{person_id}", deps.now_iso()),
        )
    handler.send_json({"message": message})

def list_daily_production_groups(handler: Any, deps: DailyManagementDependencies) -> None:
    """批量返回生产班组及班次，避免逐班组查询造成 N+1 SQL。"""
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT * FROM daily_production_groups ORDER BY active DESC, sort_order, name, id"
        ).fetchall()
        shift_rows = connection.execute(
            "SELECT * FROM daily_production_shifts ORDER BY group_id, active DESC, sort_order, name, id"
        ).fetchall()
    shifts_by_group: dict[int, list[sqlite3.Row]] = {}  # 在内存按班组分组后交给统一序列化器。
    for shift_row in shift_rows:
        shifts_by_group.setdefault(int(shift_row["group_id"]), []).append(shift_row)
    handler.send_json({
        "groups": [
            deps.production_group_public(row, shifts_by_group.get(int(row["id"]), []))
            for row in rows
        ]
    })

def create_daily_production_group(handler: Any, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """新增生产班组，并把班次配置作为同一事务的完整初始快照。

    旧前端没有班次字段时自动创建零编制白班以保持兼容；新前端提供的班次由统一同步器
    校验名称、编制、排序和启用状态。班组、班次和审计要么一起提交，要么一起回滚。
    """
    actor = handler.require_user(admin=True)
    name, sort_order, active, shifts = _validate_daily_production_group(body)
    if shifts is None:  # 兼容旧前端只维护班组的请求结构。
        shifts = [{"id": None, "name": "白班", "staffing_count": 0, "sort_order": 0, "active": True}]
    created = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        duplicate = connection.execute(
            "SELECT id FROM daily_production_groups WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if duplicate is not None:
            raise ApiError(HTTPStatus.CONFLICT, "相同生产班组已经存在")
        cursor = connection.execute(
            "INSERT INTO daily_production_groups(name, sort_order, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (name, sort_order, int(active), created, created),
        )
        group_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM daily_production_groups WHERE id = ?", (group_id,)
        ).fetchone()
        shift_rows = _sync_daily_production_shifts(connection, group_id, shifts, created, deps)
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_production_group_create:{group_id}", created),
        )
    handler.send_json({
        "message": "生产班组已添加",
        "group": deps.production_group_public(row, shift_rows),
    }, HTTPStatus.CREATED)

def update_daily_production_group(handler: Any, path: str, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """更新班组属性，并仅在请求包含 ``shifts`` 时同步班次完整快照。"""
    actor = handler.require_user(admin=True)
    group_id = _daily_production_group_id(path)
    name, sort_order, active, shifts = _validate_daily_production_group(body)
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        duplicate = connection.execute(
            "SELECT id FROM daily_production_groups WHERE name = ? COLLATE NOCASE AND id <> ?", (name, group_id)
        ).fetchone()
        if duplicate is not None:
            raise ApiError(HTTPStatus.CONFLICT, "相同生产班组已经存在")
        changed = connection.execute(
            "UPDATE daily_production_groups SET name = ?, sort_order = ?, active = ?, updated_at = ? WHERE id = ?",
            (name, sort_order, int(active), updated, group_id),
        ).rowcount
        if not changed:
            raise ApiError(HTTPStatus.NOT_FOUND, "生产班组不存在")
        row = connection.execute(
            "SELECT * FROM daily_production_groups WHERE id = ?", (group_id,)
        ).fetchone()
        shift_rows = (
            _sync_daily_production_shifts(connection, group_id, shifts, updated, deps)
            if shifts is not None else _daily_production_shift_rows(connection, group_id)
        )
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_production_group_update:{group_id}", updated),
        )
    handler.send_json({
        "message": "生产班组已更新",
        "group": deps.production_group_public(row, shift_rows),
    })

def delete_daily_production_group(handler: Any, path: str, deps: DailyManagementDependencies) -> None:
    """删除从未使用的班组，或停用存在新旧考勤历史的班组和班次。

    历史检查同时覆盖迁移前按班组保存的考勤表和当前按班次保存的考勤表。存在任一历史
    时不能物理删除，否则旧日报失去班组解释；此时只停用主数据，保留编制与出勤快照。
    """
    actor = handler.require_user(admin=True)
    group_id = _daily_production_group_id(path)
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT * FROM daily_production_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "生产班组不存在")
        legacy_history = int(connection.execute(
            "SELECT COUNT(*) AS n FROM daily_production_attendance WHERE group_id = ?", (group_id,)
        ).fetchone()["n"])
        history = int(connection.execute(
            "SELECT COUNT(*) AS n FROM daily_production_shift_attendance a "
            "JOIN daily_production_shifts s ON s.id = a.shift_id WHERE s.group_id = ?",
            (group_id,),
        ).fetchone()["n"]) + legacy_history  # 迁移前的按班组考勤表同样属于不可丢失历史。
        if history:
            connection.execute(
                "UPDATE daily_production_groups SET active = 0, updated_at = ? WHERE id = ?", (updated, group_id)
            )
            connection.execute(
                "UPDATE daily_production_shifts SET active = 0, updated_at = ? WHERE group_id = ?",
                (updated, group_id),
            )
            message = "生产班组已停用，历史出勤已保留"
        else:
            connection.execute("DELETE FROM daily_production_shifts WHERE group_id = ?", (group_id,))
            connection.execute("DELETE FROM daily_production_groups WHERE id = ?", (group_id,))
            message = "生产班组已删除"
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], f"daily_production_group_delete:{group_id}", updated),
        )
    handler.send_json({"message": message})

def list_daily_attendance(handler: Any, deps: DailyManagementDependencies) -> None:
    """返回指定业务日期的参会人员和生产班次考勤表单数据。"""
    handler.require_user(admin=True)
    query = parse_qs(urlparse(handler.path).query)
    report_date = deps.report_date((query.get("date") or [deps.business_today().isoformat()])[0])
    with deps.db_lock, deps.db() as connection:
        rows = attendance_rows(connection, report_date)
        production_rows = production_attendance_rows(connection, report_date)
    handler.send_json({
        "date": report_date,
        "attendance": [deps.daily_attendance_public(row) for row in rows],
        "production_groups": [deps.production_attendance_public(row) for row in production_rows],
    })

def _normalize_attendance_records(
    records: object,
) -> list[tuple[int, bool, str, str]]:
    """校验并规范化参会人员考勤，数据库事务外不保留原始请求对象。"""
    if not isinstance(records, list) or len(records) > 1000:
        raise ApiError(HTTPStatus.BAD_REQUEST, "考勤记录格式无效")
    normalized: list[tuple[int, bool, str, str]] = []
    for item in records:
        if not isinstance(item, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "考勤记录格式无效")
        try:
            person_id = int(item.get("person_id"))
        except (TypeError, ValueError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "人员编号无效") from exc
        present = item.get("present")
        if not isinstance(present, bool):
            raise ApiError(HTTPStatus.BAD_REQUEST, "出勤状态无效")
        reason = str(item.get("reason") or "").strip()
        status = str(item.get("status") or ("present" if present else "absent")).strip()
        if len(reason) > 500 or len(status) > 32:
            raise ApiError(HTTPStatus.BAD_REQUEST, "考勤原因或状态内容过长")
        if present:
            status = "present"
        elif status == "present":
            status = "absent"
        normalized.append((person_id, present, status, reason))
    return normalized


def _normalize_production_attendance(
    records: object,
) -> list[tuple[int | None, int | None, int, str]]:
    """校验生产考勤输入；兼容旧客户端只提交班组编号的记录。"""
    if not isinstance(records, list) or len(records) > 200:
        raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组出勤格式无效")
    normalized: list[tuple[int | None, int | None, int, str]] = []
    for item in records:
        if not isinstance(item, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组出勤格式无效")
        # shift_id 优先；旧客户端只提交 group_id 时由后续解析选择排序最前的班次。
        try:
            shift_id = int(item["shift_id"]) if item.get("shift_id") is not None else None
            group_id = int(item["group_id"]) if item.get("group_id") is not None else None
            attendance_count = int(item.get("attendance_count") or 0)
        except (TypeError, ValueError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次或出勤人数无效") from exc
        if shift_id is None and group_id is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "生产班次编号缺失")
        note = str(item.get("note") or "").strip()
        if not 0 <= attendance_count <= 100000:
            raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组出勤人数超出合理范围")
        if len(note) > 500:
            raise ApiError(HTTPStatus.BAD_REQUEST, "生产班组备注不能超过 500 个字")
        normalized.append((shift_id, group_id, attendance_count, note))
    return normalized


def _validate_participant_ids(
    connection: Any,
    records: list[tuple[int, bool, str, str]],
) -> None:
    """一次查询验证全部参会人员编号，避免逐条访问数据库。"""
    if not records:
        return
    requested_ids = {record[0] for record in records}
    placeholders = ",".join("?" for _ in requested_ids)
    valid_ids = {
        int(row["id"])
        for row in connection.execute(
            "SELECT id FROM daily_people "
            f"WHERE person_type = 'participant' AND id IN ({placeholders})",
            tuple(sorted(requested_ids)),
        ).fetchall()
    }
    if requested_ids - valid_ids:
        raise ApiError(HTTPStatus.BAD_REQUEST, "考勤中包含不存在的人员")


def _resolve_production_attendance(
    connection: Any,
    records: list[tuple[int | None, int | None, int, str]],
) -> list[tuple[int, int, int, str]]:
    """批量解析班次及旧班组编号，并返回保存考勤所需的编制快照。"""
    direct_ids = {shift_id for shift_id, _, _, _ in records if shift_id is not None}
    group_ids = {group_id for _, group_id, _, _ in records if group_id is not None}
    direct_rows = _load_shift_rows_by_id(connection, direct_ids)
    fallback_rows = _load_first_shift_by_group(connection, group_ids)
    resolved: list[tuple[int, int, int, str]] = []
    seen_shift_ids: set[int] = set()
    for shift_id, group_id, attendance_count, note in records:
        row = direct_rows.get(shift_id) if shift_id is not None else fallback_rows.get(group_id)
        if row is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "出勤记录中包含不存在的生产班次")
        resolved_shift_id = int(row["id"])
        if resolved_shift_id in seen_shift_ids:
            raise ApiError(HTTPStatus.BAD_REQUEST, "同一生产班次不能重复提交")
        seen_shift_ids.add(resolved_shift_id)
        resolved.append((
            resolved_shift_id,
            int(row["staffing_count"] or 0),
            attendance_count,
            note,
        ))
    return resolved


def _load_shift_rows_by_id(connection: Any, shift_ids: set[int]) -> dict[int, Any]:
    """批量读取直接提交的班次，返回按班次编号索引的行。"""
    if not shift_ids:
        return {}
    placeholders = ",".join("?" for _ in shift_ids)
    rows = connection.execute(
        "SELECT s.id, s.staffing_count FROM daily_production_shifts s "
        "JOIN daily_production_groups g ON g.id = s.group_id "
        f"WHERE s.id IN ({placeholders})",
        tuple(sorted(shift_ids)),
    ).fetchall()
    return {int(row["id"]): row for row in rows}


def _load_first_shift_by_group(connection: Any, group_ids: set[int]) -> dict[int, Any]:
    """为旧客户端的每个班组选择排序最前的班次。"""
    if not group_ids:
        return {}
    placeholders = ",".join("?" for _ in group_ids)
    rows = connection.execute(
        "SELECT group_id, id, staffing_count FROM daily_production_shifts "
        f"WHERE group_id IN ({placeholders}) "
        "ORDER BY group_id, active DESC, sort_order, name, id",
        tuple(sorted(group_ids)),
    ).fetchall()
    first_by_group: dict[int, Any] = {}
    for row in rows:
        first_by_group.setdefault(int(row["group_id"]), row)
    return first_by_group


def save_daily_attendance(handler: Any, body: dict[str, object], deps: DailyManagementDependencies) -> None:
    """在一个事务中保存参会人员与生产班次的当日考勤。

    输入规范化与班次解析分别由小函数完成。班次采用批量查询，避免班组较多时产生逐条
    SQL；保存的 staffing_count 是当天编制快照，后续修改主数据不会篡改历史差异。
    """
    actor = handler.require_user(admin=True)
    report_date = deps.report_date(body.get("date"))
    attendance = _normalize_attendance_records(body.get("records"))
    production = _normalize_production_attendance(body.get("production_groups", []))
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        _validate_participant_ids(connection, attendance)
        resolved_production = _resolve_production_attendance(connection, production)  # 班次解析在写入前完成，任一条非法输入都整体回滚。
        connection.executemany(
            "INSERT INTO daily_attendance"
            "(report_date, person_id, present, status, reason, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(report_date, person_id) DO UPDATE SET "
            "present = excluded.present, status = excluded.status, reason = excluded.reason, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            [
                (report_date, person_id, int(present), status, reason, actor["id"], updated)
                for person_id, present, status, reason in attendance
            ],
        )
        connection.executemany(
            "INSERT INTO daily_production_shift_attendance"
            "(report_date, shift_id, staffing_count, attendance_count, note, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(report_date, shift_id) DO UPDATE SET "
            "staffing_count = excluded.staffing_count, "
            "attendance_count = excluded.attendance_count, note = excluded.note, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            [
                (
                    report_date,
                    shift_id,
                    staffing_count,
                    attendance_count,
                    note,
                    actor["id"],
                    updated,
                )
                for shift_id, staffing_count, attendance_count, note in resolved_production
            ],
        )
        rows = attendance_rows(connection, report_date)
        production_rows = production_attendance_rows(connection, report_date)
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (
                actor["id"],
                f"daily_attendance_save:{report_date}:{len(attendance)}:{len(resolved_production)}",
                updated,
            ),
        )
    handler.send_json({
        "message": "当天考勤已保存",
        "date": report_date,
        "attendance": [deps.daily_attendance_public(row) for row in rows],
        "production_groups": [
            deps.production_attendance_public(row) for row in production_rows
        ],
    })
