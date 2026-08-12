# -*- coding: utf-8 -*-
"""日清看板的月度生产订单台账聚合。"""

from __future__ import annotations

from typing import Mapping

from .daily_report_values import number, text


def _order_ledger(plan: Mapping[str, object]) -> Mapping[str, object]:
    """从一份生产计划上传记录中安全取得订单台账节点。"""

    summary = plan.get("summary")
    if not isinstance(summary, Mapping):
        return {}
    insights = summary.get("insights")
    if not isinstance(insights, Mapping):
        return {}
    ledger = insights.get("order_ledger")
    return ledger if isinstance(ledger, Mapping) else {}


def _merge_month_orders(
    ledger: Mapping[str, object],
    key: str,
    month: str,
    target: dict[str, dict[str, object]],
) -> bool:
    """合并某类订单并返回该上传文件是否贡献了目标月份数据。"""

    orders = ledger.get(key)
    if not isinstance(orders, list):
        return False
    contributed = False
    for order in orders:
        if not isinstance(order, Mapping) or str(order.get("month") or "") != month:
            continue
        order_no = text(order.get("order_no")).strip()
        if not order_no:
            continue
        # 服务端按新到旧传入文件；首次出现的订单即管理员最后上传的版本。
        target.setdefault(order_no, dict(order))
        contributed = True
    return contributed


def _source_file(plan: Mapping[str, object]) -> dict[str, object]:
    """只保留看板追溯来源需要的公开元数据。"""

    return {
        "id": plan.get("id"),
        "original_name": plan.get("original_name"),
        "updated_at": plan.get("updated_at"),
        "uploaded_by_name": plan.get("uploaded_by_name"),
    }


def _collect_orders(
    plans: object,
    month: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """按订单号收集目标月份的最新正式、零星订单及有效来源文件。"""

    formal_by_order: dict[str, dict[str, object]] = {}
    sporadic_by_order: dict[str, dict[str, object]] = {}
    source_files: list[dict[str, object]] = []
    source_plans = plans if isinstance(plans, list) else []
    for plan in source_plans:
        if not isinstance(plan, Mapping):
            continue
        ledger = _order_ledger(plan)
        has_formal = _merge_month_orders(ledger, "formal_orders", month, formal_by_order)
        has_sporadic = _merge_month_orders(ledger, "sporadic_orders", month, sporadic_by_order)
        if has_formal or has_sporadic:
            # 无目标月份订单的上传记录不显示为来源，避免管理层误判数据覆盖范围。
            source_files.append(_source_file(plan))
    return list(formal_by_order.values()), list(sporadic_by_order.values()), source_files


def _flatten_formal_details(
    formal_orders: list[dict[str, object]],
    field: str,
) -> list[dict[str, object]]:
    """展开正式订单内嵌明细，并为每行补回所属订单号。"""

    rows: list[dict[str, object]] = []
    for order in formal_orders:
        details = order.get(field)
        if not isinstance(details, list):
            continue
        for item in details:
            if isinstance(item, Mapping):
                rows.append(dict(item, order_no=order.get("order_no")))
    return rows


def _sum_number(rows: list[dict[str, object]], field: str) -> float:
    """安全累加数量列；带逗号文本可解析，其他脏值按缺失跳过。"""

    return sum(parsed for row in rows if (parsed := number(row.get(field))) is not None)


def _today_shipments(
    formal: list[dict[str, object]],
    sporadic: list[dict[str, object]],
    report_date: str,
) -> list[dict[str, object]]:
    """提取当日发运订单，并标注正式或零星订单类型。"""

    rows = [
        dict(item, order_kind="正式订单")
        for item in formal
        if item.get("shipment_date") == report_date
    ]
    rows.extend(
        dict(item, order_kind="零星订单")
        for item in sporadic
        if report_date in (item.get("shipment_dates") or [])
    )
    return rows


def production_ledger(plans: object, report_date: str) -> dict[str, object]:
    """按报告月份聚合生产计划中的最新订单、缺件、危包与当日发运。"""

    month = report_date[:7]
    formal, sporadic, source_files = _collect_orders(plans, month)
    missing_parts = _flatten_formal_details(formal, "missing_parts")
    hazardous_packages = _flatten_formal_details(formal, "hazardous_packages")
    formal_completed = sum(bool(item.get("completed")) for item in formal)
    sporadic_completed = sum(bool(item.get("completed")) for item in sporadic)
    return {
        "month": month,
        "source_file_count": len(source_files),
        "source_files": source_files,
        "formal_total": len(formal),
        "formal_completed": formal_completed,
        "formal_pending": len(formal) - formal_completed,
        "formal_quantity": _sum_number(formal, "quantity"),
        "sporadic_total": len(sporadic),
        "sporadic_completed": sporadic_completed,
        "sporadic_pending": len(sporadic) - sporadic_completed,
        "sporadic_pallets": _sum_number(sporadic, "pallet_count"),
        "sporadic_volume_cbm": round(_sum_number(sporadic, "volume_cbm"), 4),
        "missing_part_count": len(missing_parts),
        "outstanding_missing_part_count": sum(not bool(item.get("completed")) for item in missing_parts),
        "hazardous_package_count": len(hazardous_packages),
        "outstanding_hazardous_package_count": sum(
            not bool(item.get("completed")) for item in hazardous_packages
        ),
        "today_shipments": _today_shipments(formal, sporadic, report_date),
        "formal_orders": formal,
        "sporadic_orders": sporadic,
        "missing_parts": missing_parts,
        "hazardous_packages": hazardous_packages,
    }


__all__ = ["production_ledger"]
