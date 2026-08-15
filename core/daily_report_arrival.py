# -*- coding: utf-8 -*-
"""日清看板的到料批次与供应商缺口聚合。

本模块只消费已完成权限过滤的到料任务结果，把单个批次的物料缺口展开为供应商维度的
需求、实收和缺口汇总，并最终生成日清快照中的到料区块。数量字段统一经过
:mod:`daily_report_values` 规范，未填写供应商的物料以“未填写供应商”占位进入风险总量，
避免缺口因来源字段缺失而消失。模块不读取原始上传文件，也不负责持久化。"""

from __future__ import annotations

from typing import Any, Mapping

from . import business_result_core
from .daily_report_values import integer, normalized_number, number, text

_QUANTITY_FIELDS = ("demand_quantity", "received_quantity", "shortage_quantity")


def _new_supplier_total(supplier: str) -> dict[str, object]:
    """创建一个独立的供应商数量累加器，避免多处重复维护字段集合。"""

    return {
        "supplier": supplier,
        "demand_quantity": 0.0,
        "received_quantity": 0.0,
        "shortage_quantity": 0.0,
        "material_count": 0,
    }


def _add_quantity_fields(target: dict[str, object], source: Mapping[str, object]) -> None:
    """把来源中的三类数量累加到目标；无效文本不改变已有汇总。"""

    for field in _QUANTITY_FIELDS:
        amount = number(source.get(field))
        if amount is not None:
            target[field] = float(target[field]) + amount


def _normalize_supplier_total(item: Mapping[str, object]) -> dict[str, object]:
    """压缩无意义的 ``.0``，并控制浮点尾数不污染 API 与 Excel。"""

    normalized = dict(item)
    for field in _QUANTITY_FIELDS:
        normalized[field] = normalized_number(normalized.get(field))
    return normalized


def _sort_supplier_totals(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """按缺口降序、供应商名称升序生成稳定排行。"""

    return sorted(
        items,
        key=lambda item: (-float(item["shortage_quantity"]), str(item["supplier"])),
    )


def supplier_distribution(materials: object) -> list[dict[str, object]]:
    """按供应商汇总单个批次的需求、实收、缺口与物料条目数。"""

    grouped: dict[str, dict[str, object]] = {}
    source_rows = materials if isinstance(materials, list) else []
    for material in source_rows:
        if not isinstance(material, Mapping):
            continue
        # 未维护供应商的物料仍需进入风险总量，统一占位后可在看板提示人工维护。
        supplier = text(material.get("supplier")).strip() or "未填写供应商"
        target = grouped.setdefault(supplier, _new_supplier_total(supplier))
        target["material_count"] = int(target["material_count"]) + 1
        _add_quantity_fields(target, material)
    normalized = [_normalize_supplier_total(item) for item in grouped.values()]
    return _sort_supplier_totals(normalized)


def aggregate_supplier_distribution(
    batches: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    """把多个批次的供应商缺口合并为当天总览排行。"""

    totals: dict[str, dict[str, object]] = {}
    for batch in batches:
        distributions = batch.get("supplier_distribution")
        if not isinstance(distributions, list):
            continue
        for supplier_item in distributions:
            if not isinstance(supplier_item, Mapping):
                continue
            supplier = text(supplier_item.get("supplier")).strip() or "未填写供应商"
            target = totals.setdefault(supplier, _new_supplier_total(supplier))
            target["material_count"] = int(target["material_count"]) + integer(
                supplier_item.get("material_count")
            )
            _add_quantity_fields(target, supplier_item)
    normalized = [_normalize_supplier_total(item) for item in totals.values()]
    return _sort_supplier_totals(normalized)


def _batch_row(
    job: Mapping[str, Any],
    job_index: int,
    batch: Mapping[str, Any],
    batch_index: int,
) -> dict[str, object]:
    """为标准批次补充稳定标识、任务来源和供应商风险排行。"""

    row = dict(batch)
    row.update({
        # 任务 ID 为空的旧数据用遍历序号兜底，保证弹窗仍有本次快照内稳定的定位键。
        "id": f"{text(job.get('id')) or job_index}-{batch_index}",
        "job_id": text(job.get("id")),
        "job_title": text(job.get("title")) or "到料明细",
        "uploader": text(job.get("display_name") or job.get("username")) or "未知账号",
        "completed_at": text(job.get("completed_at") or job.get("updated_at")),
    })
    row["supplier_distribution"] = supplier_distribution(row.get("missing_materials"))
    return row


def _arrival_batches(arrival_jobs: list[Mapping[str, Any]]) -> list[dict[str, object]]:
    """展开每个任务中的标准批次，并保留任务与批次的原始顺序。"""

    batches: list[dict[str, object]] = []
    for job_index, job in enumerate(arrival_jobs, start=1):
        projected = business_result_core.arrival_batches(job.get("result"))
        for batch_index, batch in enumerate(projected, start=1):
            batches.append(_batch_row(job, job_index, batch, batch_index))
    return batches


def _completion_rate(arrived_categories: int, total_categories: int) -> float:
    """按类别总数加权重算完成率，并限制异常输入不能越过 0～100。"""

    if total_categories <= 0:
        return 0.0
    raw = arrived_categories / total_categories * 100
    return round(max(0.0, min(100.0, raw)), 1)


def build_arrival_snapshot(arrival_jobs: list[Mapping[str, Any]]) -> dict[str, object]:
    """将业务任务和人工成品上传统一整理为日清到料快照。"""

    batches = _arrival_batches(arrival_jobs)
    total_categories = sum(integer(row.get("total_count")) for row in batches)
    arrived_categories = sum(integer(row.get("arrived_count")) for row in batches)
    missing_categories = sum(integer(row.get("missing_count")) for row in batches)
    missing_detail_count = sum(
        len(details)
        for row in batches
        if isinstance((details := row.get("missing_materials")), list)
    )
    # source_kind 只有 upload 代表管理员直接上传成品；其他来源均属于业务处理任务。
    upload_count = sum(str(job.get("source_kind") or "") == "upload" for job in arrival_jobs)
    return {
        "job_count": len(arrival_jobs),
        "upload_count": upload_count,
        "task_count": len(arrival_jobs) - upload_count,
        "batch_count": len(batches),
        "total_categories": total_categories,
        "arrived_categories": arrived_categories,
        "missing_categories": missing_categories,
        "missing_material_detail_count": missing_detail_count,
        "completion_rate": _completion_rate(arrived_categories, total_categories),
        "invalid_batch_count": sum(not bool(row.get("data_valid")) for row in batches),
        "supplier_distribution": aggregate_supplier_distribution(batches),
        "batches": batches,
    }


__all__ = ["aggregate_supplier_distribution", "build_arrival_snapshot", "supplier_distribution"]
