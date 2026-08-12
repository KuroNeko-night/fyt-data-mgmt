# -*- coding: utf-8 -*-
"""发票、票货匹配、通用表格比对和对账单制作结果投影。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .business_result_common import (
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


def _present_invoice(value: object, limit: int) -> dict[str, object] | None:
    """生成发票统计投影，并按识别存疑比例计算辅助可信度。"""
    result = unwrap_result(value)
    if "count" not in result and "xlsx" not in result:
        return None
    count = _integer(result.get("count"))
    suspects = _integer(result.get("suspects"))
    total = count + suspects
    score = round(100 - _ratio(suspects, max(total, 1)) * 50)  # 存疑项最多扣一半分，已人工确认金额不在此评分。
    return {
        "kind": "invoice",
        "title": "发票统计结果",
        "summary": f"已确认并汇总 {count} 张发票，另有 {suspects} 项识别存疑。",
        "metrics": [
            _metric("count", "已汇总发票", count, tone="success"),
            _metric("suspects", "识别存疑", suspects, tone="danger" if suspects else "success"),
        ],
        "quality": _quality(
            score,
            "评分反映发票识别覆盖；金额、税额与费用项目仍以人工复核后的值为准。",
            [_quality_check(
                "success" if suspects == 0 else "warning",
                "识别存疑项",
                f"有 {suspects} 项未能稳定识别，已保留在复核资料中。" if suspects else "本次没有遗留识别存疑项。",
            )],
        ),
        "parameters": [],
        "sections": [],
        "notices": [],
    }


def _present_invoice_match(value: object, limit: int) -> dict[str, object] | None:
    """生成票货匹配投影，按供应商交集展示单侧异常。"""
    result = unwrap_result(value)
    if "matched" not in result or "no_invoice" not in result:
        return None
    matched = _integer(result.get("matched"))
    no_invoice = _integer(result.get("no_invoice"))
    no_purchase = _integer(result.get("no_purchase"))
    total = matched + no_invoice + no_purchase
    rate = _ratio(matched, total)  # 这里只衡量供应商覆盖，不代表金额逐笔一致。
    rows = ([{"supplier": item, "status": "无票采购"} for item in _sequence(result.get("no_invoice_suppliers"))]
            + [{"supplier": item, "status": "有发票无采购"} for item in _sequence(result.get("no_purchase_suppliers"))])
    return {
        "kind": "invoice_match",
        "title": "票货匹配结果",
        "summary": f"正常匹配 {matched} 家，仍有 {no_invoice} 家无票采购、{no_purchase} 家有发票无采购。",
        "metrics": [
            _metric("matched", "正常匹配", matched, tone="success"),
            _metric("rate", "供应商覆盖率", f"{rate:.1f}%", tone="success" if rate >= 95 else "warning"),
            _metric("no_invoice", "无票采购", no_invoice, tone="danger" if no_invoice else "success"),
            _metric("no_purchase", "有发票无采购", no_purchase, tone="danger" if no_purchase else "success"),
        ],
        "quality": _quality(
            round(rate),
            "评分按供应商名称交集计算，仅表示票货覆盖，不表示金额已完成逐笔勾稽。",
            [_quality_check(
                "success" if no_invoice + no_purchase == 0 else "warning",
                "票货覆盖",
                f"共有 {no_invoice + no_purchase} 家供应商只出现在单侧，需要后续业务核对。",
            )],
        ),
        "parameters": [],
        "sections": [_section(
            "exceptions", "待核对供应商",
            [("supplier", "供应商"), ("status", "状态")],
            rows,
            limit=limit,
        )] if rows else [],
        "notices": [],
    }


def _row_details(value: object) -> str:
    """把单侧表格行压缩成最多八个非空字段的客户可读摘要。"""
    row = _mapping(value)
    return "；".join(
        f"{_text(key)}：{_text(item)}"
        for key, item in list(row.items())[:8]  # 限制字段数量，避免单元格塞入整行宽表数据。
        if _text(item)
    )


def _present_compare(value: object, limit: int) -> dict[str, object] | None:
    """生成通用表格比对投影，区分值差异、单侧行和关键值质量。

    重复或空关键值会降低“能否稳定配对”的可信度；配对后发现的业务值差异不会扣分，
    因为差异正是该功能应识别的正常结果。
    """
    result = unwrap_result(value)
    counts = _mapping(result.get("counts"))
    if not counts and "diffs" not in result:
        return None
    matched = _integer(counts.get("matched"))
    diffs = [item for item in _sequence(result.get("diffs")) if isinstance(item, Mapping)]
    only_a = [item for item in _sequence(result.get("only_a")) if isinstance(item, Mapping)]
    only_b = [item for item in _sequence(result.get("only_b")) if isinstance(item, Mapping)]
    duplicate_count = _integer(counts.get("dup_a")) + _integer(counts.get("dup_b"))
    blank_count = _integer(counts.get("blank_a")) + _integer(counts.get("blank_b"))
    reliability_base = max(matched + len(only_a) + len(only_b) + blank_count, 1)
    score = round(100 - _ratio(duplicate_count + blank_count, reliability_base) * 70)  # 单侧业务记录不属于关键列质量缺陷。
    sections = []
    if diffs:
        sections.append(_section(
            "diffs", "值差异明细",
            [("key", _text(result.get("key")) or "关键值"), ("column", "列名"),
             ("a", "A 值"), ("b", "B 值")],
            diffs,
            limit=limit,
        ))
    only_rows = ([{"side": "只在 A", "key": item.get("key"), "details": _row_details(item.get("row"))} for item in only_a]
                 + [{"side": "只在 B", "key": item.get("key"), "details": _row_details(item.get("row"))} for item in only_b])
    if only_rows:
        sections.append(_section(
            "only", "单侧记录",
            [("side", "来源"), ("key", _text(result.get("key")) or "关键值"), ("details", "记录摘要")],
            only_rows,
            limit=limit,
        ))
    columns = [_text(item) for item in _sequence(result.get("columns")) if _text(item)]
    return {
        "kind": "compare",
        "title": "表格比对结果",
        "summary": f"按“{_text(result.get('key'))}”配对 {matched} 行，发现 {len(diffs)} 处值差异和 {len(only_rows)} 条单侧记录。",
        "metrics": [
            _metric("matched", "成功配对", matched, tone="success"),
            _metric("diffs", "值差异", len(diffs), tone="warning" if diffs else "success"),
            _metric("only_a", "只在 A", len(only_a), tone="danger" if only_a else "success"),
            _metric("only_b", "只在 B", len(only_b), tone="danger" if only_b else "success"),
            _metric("skipped", "重复/空关键值", duplicate_count + blank_count, tone="warning" if duplicate_count + blank_count else "success"),
        ],
        "quality": _quality(
            score,
            "评分只衡量关键列能否稳定配对；业务差异本身不会降低这项评分。",
            [
                _quality_check(
                    "success" if duplicate_count == 0 else "warning",
                    "关键值唯一性",
                    f"A、B 两表共发现 {duplicate_count} 个重复关键值。",
                ),
                _quality_check(
                    "success" if blank_count == 0 else "warning",
                    "关键值完整性",
                    f"有 {blank_count} 行关键值为空，未参与比对。",
                ),
            ],
        ),
        "parameters": [
            _parameter("key", "关键列", result.get("key")),
            _parameter("columns", "比较列", "、".join(columns) if columns else "未选择"),
        ],
        "sections": sections,
        "notices": [],
    }


def _present_reconcile_statement(value: object, limit: int) -> dict[str, object] | None:
    """生成对账单制作投影，按供应商、月份和文件展示最终输出。"""
    result = unwrap_result(value)
    files = [item for item in _sequence(result.get("files")) if isinstance(item, Mapping)]
    if not files and "total_rows" not in result:
        return None
    rows = [{
        "supplier": item.get("supplier"),
        "month": item.get("month"),
        "rows": item.get("rows"),
        "name": _basename(item.get("name") or item.get("path")),
    } for item in files]
    total_rows = _integer(result.get("total_rows"), sum(_integer(row["rows"]) for row in rows))
    suppliers = len({str(row["supplier"]).strip() for row in rows if str(row["supplier"]).strip()})  # 同一供应商跨月份或多文件只计一次。
    return {
        "kind": "reconcile_statement",
        "title": "对账单制作结果",
        "summary": f"已为 {suppliers} 个供应商生成 {len(rows)} 份对账单，共 {total_rows} 行。",
        "metrics": [
            _metric("suppliers", "供应商", suppliers, tone="info"),
            _metric("files", "输出文件", len(rows), tone="success"),
            _metric("rows", "数据行", total_rows, tone="neutral"),
        ],
        "sections": [_section(
            "files", "供应商对账单",
            [("supplier", "供应商"), ("month", "月份"),
             ("rows", "数据行"), ("name", "报告文件")],
            rows,
            description="可以继续从结果文件区下载或在线预览正式对账单。",
            limit=limit,
        )] if rows else [],
        "notices": [],
    }
