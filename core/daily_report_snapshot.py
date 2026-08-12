# -*- coding: utf-8 -*-
"""日清看板稳定快照的总装入口。

各业务域的归一化与聚合已经拆到独立模块：到料、现场问题、考勤和生产台账可分别
维护，本模块只负责日期校验、轻量安全检查摘要和最终结构装配。Web 看板与 Excel
导出继续消费同一份快照，因此拆分不会造成统计口径分叉。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .daily_report_arrival import (
    aggregate_supplier_distribution as _aggregate_supplier_distribution,
    build_arrival_snapshot as _build_arrival_snapshot,
    supplier_distribution as _supplier_distribution,
)
from .daily_report_attendance import (
    attendance_unit_summary as _attendance_unit_summary,
    normalize_attendance_snapshot as _normalize_attendance_snapshot,
)
from .daily_report_production import production_ledger as _production_ledger
from .daily_report_values import (
    integer as _integer,
    normalized_number,
    number as _number,
    text as _text,
    validate_date as _validate_date,
)
from .daily_report_workshop import (
    build_workshop_snapshot as _build_workshop_snapshot,
    normalize_workshop_issue as _normalize_workshop_issue,
)


def _normalize_quantity_summary(item: Mapping[str, object]) -> dict[str, object]:
    """保留旧内部辅助入口，并委托统一数量规范化工具完成转换。"""

    normalized = dict(item)
    for field in ("demand_quantity", "received_quantity", "shortage_quantity"):
        normalized[field] = normalized_number(normalized.get(field))
    return normalized


def _safety_snapshot(uploads: object) -> dict[str, object]:
    """使用当天最后一次安全检查上传生成总览，同时保留完整上传列表。"""

    rows = (
        [dict(item) for item in uploads if isinstance(item, Mapping)]
        if isinstance(uploads, list)
        else []
    )
    # 服务端已按更新时间倒序查询；首条就是管理员最后确认版本，不能把重复上传相加。
    latest = rows[0] if rows else {}
    summary = latest.get("summary") if isinstance(latest.get("summary"), Mapping) else {}
    return {
        "upload_count": len(rows),
        "latest_upload": latest or None,
        "total_checks": _integer(summary.get("total_checks")),
        "qualified_count": _integer(summary.get("qualified_count")),
        "unqualified_count": _integer(summary.get("unqualified_count")),
        "pending_count": _integer(summary.get("pending_count")),
        "qualification_rate": float(summary.get("qualification_rate", 0) or 0),
        "image_count": _integer(summary.get("image_count")),
        "category_summary": list(summary.get("category_summary") or []),
        "records": list(summary.get("records") or []),
        "uploads": rows,
    }


def build_snapshot(
    report_date: object,
    arrival_jobs: list[Mapping[str, Any]],
    workshop_issues: list[Mapping[str, Any]],
    *,
    attendance: Mapping[str, Any] | None = None,
    brief_items: list[Mapping[str, Any]] | None = None,
    production_plans: list[Mapping[str, Any]] | None = None,
    monthly_production_plans: list[Mapping[str, Any]] | None = None,
    safety_uploads: list[Mapping[str, Any]] | None = None,
    source_uploads: list[Mapping[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
    """把服务端已完成权限过滤的数据装配为页面与报告共用的日清快照。

    参数较多是因为该函数是跨业务域的稳定公开入口；具体处理已经委托给独立聚合器，
    这里保持显式关键字参数可让调用方和类型检查直接看出每份数据的业务含义。
    """

    date_text = _validate_date(report_date)
    # 各聚合器只接收本业务域输入；某一域新增字段时不再扩大其他域函数的认知范围。
    arrival_data = _build_arrival_snapshot(arrival_jobs)
    workshop_data = _build_workshop_snapshot(workshop_issues, date_text)
    attendance_data = _normalize_attendance_snapshot(attendance)
    ledger_plans = monthly_production_plans or production_plans or []
    return {
        "date": date_text,
        # 数据库存 UTC；生成时间也固定为 UTC，页面再按业务时区转换展示。
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
        "scope": "all",
        "definitions": {
            "arrival": "到料按任务完成时间归入 Asia/Shanghai 业务日期。",
            "workshop": "现场问题按填写的问题日期统计，只包含已发布记录。",
            "safety": "安全检查按文件内检查日期归档；同日多次上传时总览采用最后上传的一份。",
            "production": "订单台账按订单号聚合，月度统计按表内月份或发运日期归档。",
        },
        "arrival": arrival_data,
        "workshop": workshop_data,
        "safety_checks": _safety_snapshot(safety_uploads or []),
        "attendance": attendance_data,
        "brief_items": [dict(item) for item in (brief_items or [])],
        "production_plans": [dict(item) for item in (production_plans or [])],
        # 优先使用整月资料；旧调用方未传该参数时回退到当日计划列表。
        "production_ledger": _production_ledger(ledger_plans, date_text),
        "source_uploads": [dict(item) for item in (source_uploads or [])],
    }


__all__ = ["build_snapshot"]
