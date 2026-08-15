"""管理层日清报告快照查询服务。

本模块把分散在任务、现场问题、考勤、事项、生产计划和人工资料表中的数据一次性查询，
再交给 ``core.daily_report_core`` 生成统一快照。它不重新计算 Excel 业务规则，只负责
选择正确日期范围、兼容两种到料来源，并把数据库行转换为 Core 可理解的公共结构。

安全边界：快照跨全部账号聚合，调用方必须已通过 admin 角色校验；数据库连接在快照
查询期间使用同一写锁，避免任务结果、考勤和计划来自不同的提交瞬间。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any, Callable

from web_backend.errors import ApiError


@dataclass(frozen=True)
class DailyReportDependencies:
    """日清快照查询所需的数据库、序列化和 Core 聚合回调。

    查询函数通过依赖注入复用日清维护服务的考勤 SQL 和服务端 Presenter，确保维护页、
    日清看板和导出报告对同一条记录采用完全一致的默认值与权限字段。
    """

    # 快照查询是跨账号只读聚合，但需要与写事务使用同一把锁以获得一致视图。
    db_lock: Any
    db: Callable[[], sqlite3.Connection]
    business_day_bounds: Callable[[Any], tuple[str, str]]
    workshop_issue_select: Callable[[], str]
    attendance_rows: Callable[[sqlite3.Connection, str], list[sqlite3.Row]]
    production_attendance_rows: Callable[[sqlite3.Connection, str], list[sqlite3.Row]]
    daily_attendance_public: Callable[[sqlite3.Row], dict[str, object]]
    daily_production_attendance_public: Callable[[sqlite3.Row], dict[str, object]]
    daily_brief_public: Callable[[sqlite3.Row], dict[str, object]]
    production_plan_public: Callable[[sqlite3.Row], dict[str, object]]
    daily_source_upload_public: Callable[[sqlite3.Row], dict[str, object]]
    workshop_issue_public: Callable[[sqlite3.Row, list[sqlite3.Row], sqlite3.Row], dict[str, object]]
    build_snapshot: Callable[..., dict[str, object]]
    now_iso: Callable[[], str]


def _query_daily_report_rows(
    connection: sqlite3.Connection,
    report_date: str,
    start: str,
    end: str,
    deps: DailyReportDependencies,
) -> dict[str, list[sqlite3.Row]]:
    """一次性查询日清看板所需的全部数据库行，返回按用途分组的结果。"""
    return {
        "arrival": connection.execute(  # 任务历史跨账号聚合，仅管理员可进入本函数。
            "SELECT j.id, j.title, j.updated_at, j.result, u.username, u.display_name "
            "FROM web_jobs j JOIN users u ON u.id = j.user_id "
            "WHERE j.status = 'completed' AND j.action IN ('web.arrival', 'arrival.run') "
            "AND j.updated_at >= ? AND j.updated_at < ? ORDER BY j.updated_at, j.id",
            (start, end),
        ).fetchall(),
        "issues": connection.execute(
            deps.workshop_issue_select() +
            "WHERE w.issue_date = ? AND w.status = 'published' ORDER BY w.created_at DESC",
            (report_date,),
        ).fetchall(),
        "images": connection.execute(
            "SELECT i.*, w.user_id FROM workshop_issue_images i "
            "JOIN workshop_issues w ON w.id = i.issue_id "
            "WHERE w.issue_date = ? AND w.status = 'published' "
            "ORDER BY i.issue_id, i.sort_order, i.created_at",
            (report_date,),
        ).fetchall(),
        "attendance": deps.attendance_rows(connection, report_date),
        "production_attendance": deps.production_attendance_rows(connection, report_date),
        "briefs": connection.execute(
            "SELECT * FROM daily_brief_items WHERE report_date = ? AND category != 'safety' "
            "ORDER BY CASE category WHEN 'escalation' THEN 0 WHEN 'notice' THEN 1 "
            "WHEN 'process' THEN 2 WHEN 'meeting_todo' THEN 3 ELSE 4 END, "
            "updated_at DESC, id",
            (report_date,),
        ).fetchall(),
        "plans": connection.execute(
            "SELECT p.*, COALESCE(u.display_name, u.username, '') AS uploaded_by_name "
            "FROM daily_production_plans p LEFT JOIN users u ON u.id = p.uploaded_by "
            "WHERE p.report_date = ? ORDER BY p.updated_at DESC, p.id",
            (report_date,),
        ).fetchall(),
        "monthly_plans": connection.execute(  # 当月计划可能由不同日期多次上传，Core 决定如何汇总。
            "SELECT p.*, COALESCE(u.display_name, u.username, '') AS uploaded_by_name "
            "FROM daily_production_plans p LEFT JOIN users u ON u.id = p.uploaded_by "
            "WHERE p.data_month = ? ORDER BY p.updated_at DESC, p.id",
            (report_date[:7],),
        ).fetchall(),
        "sources": connection.execute(
            "SELECT s.*, COALESCE(u.display_name, u.username, '') AS uploaded_by_name "
            "FROM daily_source_uploads s LEFT JOIN users u ON u.id = s.uploaded_by "
            "WHERE s.report_date = ? ORDER BY s.updated_at DESC, s.id",
            (report_date,),
        ).fetchall(),
    }


def _build_arrival_jobs(
    arrival_rows: list[sqlite3.Row],
    source_uploads: list[dict[str, object]],
) -> list[dict[str, object]]:
    """把任务结果与管理员直接上传的成品到料表规范为统一结构。

    历史任务的 ``result`` 可能损坏，解析失败时保留任务元数据并清空结果，不让单条坏
    记录拖垮整张管理看板。
    """
    arrival_jobs = []
    for row in arrival_rows:
        try:
            result = json.loads(row["result"] or "{}")
        except (TypeError, json.JSONDecodeError):
            result = {}
        arrival_jobs.append({
            "id": row["id"],
            "title": row["title"],
            "updated_at": row["updated_at"],
            "result": result,
            "username": row["username"],
            "display_name": row["display_name"],
            "source_kind": "task",
        })
    for upload in source_uploads:
        if upload["kind"] != "arrival":
            continue
        arrival_jobs.append({  # 人工成品上传伪装成任务结果，后续 Core 无需感知存储来源。
            "id": upload["id"], "title": upload["original_name"],
            "updated_at": upload["updated_at"], "result": upload["summary"],
            "username": "", "display_name": upload["uploaded_by_name"],
            "source_kind": "upload",
        })
    return arrival_jobs


def _group_issue_images(image_rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    """按问题编号分组图片记录，避免每条问题追加一次数据库往返。"""
    images_by_issue: dict[str, list[sqlite3.Row]] = {}
    for image in image_rows:
        images_by_issue.setdefault(str(image["issue_id"]), []).append(image)
    return images_by_issue


def _build_attendance_summary(
    attendance_people: list[dict[str, object]],
    production_groups: list[dict[str, object]],
) -> dict[str, object]:
    """汇总参会人员与生产班次的出勤指标。"""
    participant_present_count = sum(bool(item["present"]) for item in attendance_people)  # Python 布尔值可安全作为 0/1 求和。
    participant_absent_count = sum(not bool(item["present"]) for item in attendance_people)
    production_present_count = sum(int(item["attendance_count"]) for item in production_groups)
    production_staffing_count = sum(int(item["staffing_count"]) for item in production_groups)
    production_difference = production_staffing_count - production_present_count  # 保留负数，能揭示实际出勤超过编制。
    production_shortage_count = sum(max(int(item["difference"]), 0) for item in production_groups)  # 总缺勤只累计短缺，不用超编抵消。
    return {
        "people": attendance_people,
        "production_groups": production_groups,
        "present_count": participant_present_count + production_present_count,
        "absent_count": participant_absent_count + production_shortage_count,  # 管理层总缺口口径：个人缺勤加班次缺编。
        "participant_absent_count": participant_absent_count,
        "participant_present_count": participant_present_count,
        "participant_total": len(attendance_people),
        "production_present_count": production_present_count,
        "production_total": production_staffing_count,
        "production_staffing_count": production_staffing_count,
        "production_difference": production_difference,
        "production_shortage_count": production_shortage_count,
        "production_group_count": len({int(item["group_id"]) for item in production_groups}),  # 多班次仍只计一个班组。
        "production_shift_count": len(production_groups),
    }


def build_daily_report_snapshot(
    report_date: str,
    user: sqlite3.Row,
    deps: DailyReportDependencies,
) -> dict[str, object]:
    """查询全账号日清数据并生成指定业务日期的管理层快照。

    到料数据有两个合法来源：业务模块完成的任务结果，以及管理员直接上传的成品到料表。
    二者会规范为相同的 ``arrival_jobs`` 结构。生产计划同时查询当日数据和当月数据，
    供总览展示当天重点，并为月度生产与发运视图提供上下文。
    """
    if user["role"] != "admin":
        raise ApiError(HTTPStatus.FORBIDDEN, "仅管理员可以查看日清报告")
    parsed = datetime.strptime(report_date, "%Y-%m-%d").date()
    start, end = deps.business_day_bounds(parsed)  # 使用左闭右开区间，避免午夜任务重复归入两天。
    with deps.db_lock, deps.db() as connection:
        rows = _query_daily_report_rows(connection, report_date, start, end, deps)
    source_uploads = [deps.daily_source_upload_public(row) for row in rows["sources"]]
    arrival_jobs = _build_arrival_jobs(rows["arrival"], source_uploads)
    images_by_issue = _group_issue_images(rows["images"])
    issues = [
        deps.workshop_issue_public(row, images_by_issue.get(str(row["id"]), []), user)
        for row in rows["issues"]
    ]
    attendance_people = [deps.daily_attendance_public(row) for row in rows["attendance"]]
    production_groups = [deps.daily_production_attendance_public(row) for row in rows["production_attendance"]]
    attendance = _build_attendance_summary(attendance_people, production_groups)
    return deps.build_snapshot(  # 所有展示指标和导出数据都从同一 Core 快照派生。
        report_date,
        arrival_jobs,
        issues,
        attendance=attendance,
        brief_items=[deps.daily_brief_public(row) for row in rows["briefs"]],
        production_plans=[deps.production_plan_public(row) for row in rows["plans"]],
        monthly_production_plans=[deps.production_plan_public(row) for row in rows["monthly_plans"]],
        safety_uploads=[upload for upload in source_uploads if upload["kind"] == "safety"],
        source_uploads=source_uploads,
        generated_at=deps.now_iso(),
    )
