# -*- coding: utf-8 -*-
"""到料、参会人员与生产班组考勤的结果投影。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .business_result_common import (
    MAX_DETAIL_ROWS,
    _basename,
    _integer,
    _mapping,
    _metric,
    _parameter,
    _quality,
    _quality_check,
    _ratio,
    _section,
    _sequence,
    _text,
    unwrap_result,
)


def _arrival_received_quantity(demand: object, shortage: object) -> object:
    """仅在需求数和缺口数可计算时返回已收数量。

    该推导只用于旧结果没有 ``received_quantity`` 的兼容显示，不写回源数据；任一输入
    缺失或不可转数值时返回空字符串而不是猜测。
    """
    if _text(demand).strip() == "" or _text(shortage).strip() == "":
        return ""
    try:
        value = float(demand) - float(shortage)
    except (TypeError, ValueError):
        return ""
    return int(value) if value.is_integer() else round(value, 4)


def _arrival_material(value: object) -> dict[str, object] | None:
    """兼容新的字典明细和旧的五列数组明细，并输出统一物料字段。

    新结构优先使用语义键，旧结构按历史五列顺序解释；已收数量缺失时才由需求减缺口
    推导，避免覆盖 Core 已提供的精确值。
    """
    if isinstance(value, Mapping):
        code = value.get("material_code", value.get("code"))
        name = value.get("material_name", value.get("name"))
        supplier = value.get("supplier", value.get("supplier_name"))
        demand = value.get("demand_quantity", value.get("demand"))
        shortage = value.get(
            "shortage_quantity",
            value.get("remain", value.get("remaining_quantity")),
        )
        received = value.get("received_quantity")
    else:
        values = _sequence(value)
        if len(values) < 5:
            return None
        code, name, supplier, demand, shortage = values[:5]
        received = None
    if received in (None, ""):
        received = _arrival_received_quantity(demand, shortage)
    return {
        "material_code": _text(code),
        "material_name": _text(name),
        "supplier": _text(supplier),
        "demand_quantity": _text(demand),
        "received_quantity": _text(received),
        "shortage_quantity": _text(shortage),
    }


def arrival_batches(value: object) -> list[dict[str, object]]:
    """读取到料结果中的批次指标与未到物料，兼容旧任务结构。

    每批次同时保留总类数、已到、未到和具体物料缺口；数量关系异常只标记 ``data_valid``，
    不让单个批次阻止其他批次展示。批次编号缺失时使用稳定的序号占位，保证 React 列表键
    和用户定位仍可用。
    """
    result = unwrap_result(value)
    rows: list[dict[str, object]] = []
    detailed_batches = _sequence(result.get("batches"))
    source = detailed_batches or _sequence(result.get("results"))
    for index, item in enumerate(source, start=1):
        if isinstance(item, Mapping):
            materials = [
                material for material in (
                    _arrival_material(value)
                    for value in _sequence(item.get("missing_materials", item.get("materials")))
                )
                if material is not None
            ]
            batch_no = _text(item.get("batch_no") or item.get("batch"))
            missing = _integer(
                item.get("missing_count", item.get("missing")), len(materials),
            )
            arrived = _integer(item.get("arrived_count", item.get("arrived", 0)))
            total = _integer(item.get("total_count", item.get("total", 0)))
            planned_quantity = item.get("planned_quantity", item.get("planned", item.get("plan")))
            actual_quantity = item.get("actual_quantity", item.get("actual"))
            difference_quantity = item.get(
                "difference_quantity", item.get("difference", item.get("diff"))
            )
        else:
            values = _sequence(item)
            if len(values) < 4:
                continue
            batch_no = _text(values[0])
            missing = _integer(values[1])
            arrived = _integer(values[2])
            total = _integer(values[3])
            materials = []
            planned_quantity = actual_quantity = difference_quantity = ""
        rate = round(max(0.0, min(100.0, arrived / total * 100)), 1) if total > 0 else 0.0  # 异常数据也不允许进度条超过 100%。
        row = {
            "id": f"arrival-{index}",
            "batch_no": batch_no or f"未命名批次 {index}",
            "missing_count": missing,
            "arrived_count": arrived,
            "total_count": total,
            "completion_rate": rate,
            "completion_label": f"{rate:.1f}%",
            "data_valid": total >= 0 and missing >= 0 and arrived >= 0 and missing + arrived == total,  # 用等式检查总类数与拆分是否闭合。
            "missing_materials": materials,
        }
        if planned_quantity not in (None, ""):
            row["planned_quantity"] = _text(planned_quantity)
        if actual_quantity not in (None, ""):
            row["actual_quantity"] = _text(actual_quantity)
        if difference_quantity not in (None, ""):
            row["difference_quantity"] = _text(difference_quantity)
        rows.append(row)
    return rows


def _present_arrival(value: object, limit: int) -> dict[str, object] | None:
    """生成到料结果投影：批次进度、未到物料明细和数量一致性提示。"""
    rows = arrival_batches(value)
    if not rows:
        return None
    total = sum(_integer(row["total_count"]) for row in rows)
    arrived = sum(_integer(row["arrived_count"]) for row in rows)
    missing = sum(_integer(row["missing_count"]) for row in rows)
    rate = round(max(0.0, min(100.0, arrived / total * 100)), 1) if total > 0 else 0.0
    notices = []
    if any(not bool(row["data_valid"]) for row in rows):  # 只提示异常，不擅自修正业务输出。
        notices.append({
            "tone": "warning",
            "title": "部分批次的数量关系需要核对",
            "message": "存在主料总类数与已到货、未收料合计不一致的批次，完成率已限制在 0% 到 100%。",
        })
    missing_material_rows = []
    batches_without_details = 0
    for row in rows:
        materials = _sequence(row.get("missing_materials"))
        if _integer(row.get("missing_count")) > 0 and not materials:
            batches_without_details += 1
        for material in materials:
            if not isinstance(material, Mapping):
                continue
            missing_material_rows.append({
                "batch_no": row.get("batch_no"),
                "material_code": material.get("material_code"),
                "material_name": material.get("material_name"),
                "supplier": material.get("supplier"),
                "demand_quantity": material.get("demand_quantity"),
                "received_quantity": material.get("received_quantity"),
                "shortage_quantity": material.get("shortage_quantity"),
            })
    if batches_without_details:
        notices.append({
            "tone": "info",
            "title": "部分历史任务只有数量汇总",
            "message": f"{batches_without_details} 个批次未保存物料级明细；重新处理源文件后即可在页面查看具体缺料与数量缺口。",
        })
    sections = [_section(
        "batches", "批次完成情况",
        [("batch_no", "批次"), ("total_count", "主料总类数"),
         ("arrived_count", "已到货"), ("missing_count", "未收料"),
         ("completion_label", "完成率")],
        rows,
        description="完成率按已到货类数除以主料总类数计算。",
        limit=limit,
    )]
    if missing_material_rows:
        sections.append(_section(
            "missing_materials", "未到物料明细",
            [("batch_no", "批次"), ("material_code", "物料编码"),
             ("material_name", "物料名称"), ("supplier", "供应商"),
             ("demand_quantity", "需求数"), ("received_quantity", "已收数"),
             ("shortage_quantity", "缺口数")],
            missing_material_rows,
            description="逐项列出尚未到齐的物料及数量缺口。",
            limit=MAX_DETAIL_ROWS,
        ))
    return {
        "kind": "arrival",
        "title": "到料明细结果",
        "summary": (
            f"共 {len(rows)} 个批次，到料完成率 {rate:.1f}%，仍有 {missing} 类未收料。"
            + (f" 已列出 {len(missing_material_rows)} 条未到物料明细。" if missing_material_rows else "")
        ),
        "metrics": [
            _metric("batches", "批次数", len(rows), tone="info"),
            _metric("completion", "到料完成率", f"{rate:.1f}%", note=f"{arrived} / {total} 类", tone="success" if rate >= 95 else "warning"),
            _metric("arrived", "已到货类数", arrived, tone="success"),
            _metric("missing", "未收料类数", missing, tone="danger" if missing else "success"),
        ],
        "sections": sections,
        "notices": notices,
    }


def _attendance_stats(value: object) -> Mapping[str, Any]:
    """从旧版考勤结果数组中提取第三项统计映射。"""
    values = _sequence(value)
    if len(values) >= 3 and isinstance(values[2], Mapping):
        return values[2]
    return {}


def _present_attendance(value: object, limit: int) -> dict[str, object] | None:
    """生成考勤填报投影，展示匹配覆盖、异常行、可信度和人工参数。"""
    result = unwrap_result(value)
    source_stat = _mapping(result.get("source_stat"))
    result_items = _sequence(result.get("results"))
    if not result_items and not _sequence(result.get("out_files")):
        return None
    rows = []
    totals = {"matched": 0, "unmatched": 0, "computed_work": 0, "anomalies": 0}
    for index, item in enumerate(result_items, start=1):
        values = _sequence(item)
        stats = _attendance_stats(item)
        for key in totals:
            totals[key] += _integer(stats.get(key))
        rows.append({
            "file": _basename(values[0] if values else f"考勤表{index}"),
            "matched": stats.get("matched"),
            "computed_work": stats.get("computed_work"),
            "unmatched": stats.get("unmatched"),
            "anomalies": stats.get("anomalies"),
        })
    observed = totals["matched"] + totals["unmatched"]
    match_rate = _ratio(totals["matched"], observed)
    anomaly_base = max(totals["computed_work"] + totals["unmatched"], 1)
    anomaly_rate = _ratio(totals["anomalies"], anomaly_base)
    conflicts = _integer(source_stat.get("conflicts"))
    score = round(100 - (100 - match_rate) * 0.5 - anomaly_rate * 0.35 - min(10, conflicts * 2))  # 评分只描述识别质量，不评价实际出勤。
    checks = [
        _quality_check(
            "success" if match_rate >= 95 else "warning" if match_rate >= 80 else "danger",
            "打卡匹配覆盖",
            f"已匹配 {totals['matched']} 行，未匹配 {totals['unmatched']} 行，覆盖率 {match_rate:.1f}%。",
        ),
        _quality_check(
            "success" if totals["anomalies"] == 0 else "warning",
            "工时异常",
            f"发现 {totals['anomalies']} 行异常，已在输出表中标记并写入异常核对报告。",
        ),
    ]
    if conflicts:
        checks.append(_quality_check(
            "warning", "重复打卡记录",
            f"发现 {conflicts} 组姓名与日期重复记录，已按本次选择的冲突策略处理。",
        ))
    parameters = _mapping(result.get("parameters"))
    conflict_labels = {"last": "后者覆盖", "first": "先者优先", "warn": "不覆盖，仅提示"}
    display_parameters = []
    if parameters:
        display_parameters = [
            _parameter("workday_hours", "白班标准工时", f"{_text(parameters.get('workday_hours'))} 小时"),
            _parameter("conflict", "重复记录", conflict_labels.get(_text(parameters.get("conflict")), _text(parameters.get("conflict")))),
            _parameter("auto_actual", "实际时间", "自动进退位" if parameters.get("auto_actual") else "保留人工值"),
            _parameter("day_max_hours", "白班上限", f"{_text(parameters.get('day_max_hours'))} 小时"),
            _parameter("night_shift", "夜班识别", "启用" if parameters.get("night_shift") else "关闭"),
        ]
    return {
        "kind": "attendance",
        "title": "考勤填报结果",
        "summary": f"已处理 {len(rows) or len(_sequence(result.get('out_files')))} 份考勤表，匹配覆盖率 {match_rate:.1f}%，发现 {totals['anomalies']} 行需核对。",
        "metrics": [
            _metric("files", "已填写表格", len(rows) or len(_sequence(result.get("out_files"))), tone="success"),
            _metric("records", "打卡记录", source_stat.get("records", 0), tone="info"),
            _metric("match_rate", "匹配覆盖率", f"{match_rate:.1f}%", note=f"{totals['matched']} / {observed} 行", tone="success" if match_rate >= 95 else "warning"),
            _metric("anomalies", "异常行", totals["anomalies"], tone="danger" if totals["anomalies"] else "success"),
        ],
        "quality": _quality(score, "评分只衡量数据识别与匹配过程，不代表员工出勤表现。", checks),
        "parameters": display_parameters,
        "sections": [_section(
            "files", "逐表处理概况",
            [("file", "目标表"), ("matched", "已匹配"), ("computed_work", "已算工时"),
             ("unmatched", "未匹配"), ("anomalies", "异常")],
            rows,
            description="异常与未匹配记录建议在正式输出表中继续人工核对。",
            limit=limit,
        )] if rows else [],
        "notices": [],
    }

def _present_attendance_archive(value: object, limit: int) -> dict[str, object] | None:
    """生成月度考勤归档的月份、人数和记录数指标。"""
    result = unwrap_result(value)
    if "persons" not in result or "days" not in result:
        return None
    persons = _integer(result.get("persons"))
    records = _integer(result.get("days"))
    return {
        "kind": "attendance_archive",
        "title": "考勤月度归档结果",
        "summary": f"已汇总 {persons} 人、{records} 条出勤记录，归档月份 {_text(result.get('month'))}。",
        "metrics": [
            _metric("month", "归档月份", result.get("month"), tone="info"),
            _metric("persons", "人员", persons, tone="success"),
            _metric("records", "出勤记录", records, tone="neutral"),
        ],
        "parameters": [],
        "sections": [],
        "notices": [],
    }
