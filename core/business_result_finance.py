# -*- coding: utf-8 -*-
"""发票、票货匹配、通用表格比对和对账单制作结果投影。

本模块只消费任务输出的结构化结果，生成前端可展示的指标、可信度、参数和明细区块。
可信度评分分别描述发票识别覆盖、供应商覆盖、关键列配对质量和供应商数量覆盖，均不
代表金额或业务绩效；真实业务差异只作为风险提示，不会被投影层升级为任务失败。"""

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
    suspect_rows = [
        {"file": _basename(_mapping(item).get("file")), "reason": _text(_mapping(item).get("reason"))}
        for item in _sequence(result.get("suspect_summary"))
    ]
    suspect_rows = [row for row in suspect_rows if row["file"] or row["reason"]]
    sections = [
        _section(
            "suspects",
            "漏识别与跳过明细",
            [("file", "文件"), ("reason", "原因")],
            suspect_rows,
            description="这些 PDF 未被自动纳入增值税专用发票统计，可重新处理后逐项人工补录。",
            limit=limit,
        )
    ] if suspect_rows else []
    return {
        "kind": "invoice",
        "title": "发票统计结果",
        "summary": f"已确认并汇总 {count} 张发票，另有 {suspects} 项漏识别或跳过内容。",
        "metrics": [
            _metric("count", "已汇总发票", count, tone="success"),
            _metric("suspects", "漏识别/跳过", suspects, tone="danger" if suspects else "success"),
        ],
        "quality": _quality(
            score,
            "评分反映发票识别覆盖；金额、税额与费用项目仍以人工复核后的值为准。",
            [_quality_check(
                "success" if suspects == 0 else "warning",
                "识别覆盖",
                f"有 {suspects} 项未能自动纳入统计，明细见“漏识别与跳过明细”，可重新处理并人工补录。" if suspects else "本次没有遗留漏识别或跳过内容。",
            )],
        ),
        "parameters": [],
        "sections": sections,
        "notices": [{
            "tone": "info",
            "title": "人工补录入口",
            "message": "重新运行发票统计后，在“发票逐张复核”中点击“加入统计”，补全发票号码、销售方和金额即可纳入台账。",
        }] if suspects else [],
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


def _mapping_rows(value: object) -> list[Mapping[str, object]]:
    """读取结果明细并过滤掉非映射项。"""
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _compare_only_rows(
    only_a: list[Mapping[str, object]],
    only_b: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    """把两表单侧记录转换为带来源标记的统一明细。"""
    return (
        [{"side": "只在 A", "key": item.get("key"), "details": _row_details(item.get("row"))} for item in only_a]
        + [{"side": "只在 B", "key": item.get("key"), "details": _row_details(item.get("row"))} for item in only_b]
    )


def _compare_sections(
    diffs: list[Mapping[str, object]],
    only_rows: list[dict[str, object]],
    key_label: str,
    limit: int,
) -> list[dict[str, object]]:
    """生成值差异与单侧记录两个可选明细区块。"""
    sections = []
    if diffs:
        sections.append(_section(
            "diffs", "值差异明细",
            [("key", key_label), ("column", "列名"), ("a", "A 值"), ("b", "B 值")],
            diffs,
            limit=limit,
        ))
    if only_rows:
        sections.append(_section(
            "only", "单侧记录",
            [("side", "来源"), ("key", key_label), ("details", "记录摘要")],
            only_rows,
            limit=limit,
        ))
    return sections


def _compare_metrics(
    matched: int,
    diffs: list[Mapping[str, object]],
    only_a: list[Mapping[str, object]],
    only_b: list[Mapping[str, object]],
    skipped: int,
) -> list[dict[str, object]]:
    """生成表格比对的五项前端指标。"""
    return [
        _metric("matched", "成功配对", matched, tone="success"),
        _metric("diffs", "值差异", len(diffs), tone="warning" if diffs else "success"),
        _metric("only_a", "只在 A", len(only_a), tone="danger" if only_a else "success"),
        _metric("only_b", "只在 B", len(only_b), tone="danger" if only_b else "success"),
        _metric("skipped", "重复/空关键值", skipped, tone="warning" if skipped else "success"),
    ]


def _compare_quality(score: int, duplicate_count: int, blank_count: int) -> dict[str, object]:
    """生成只衡量关键列稳定配对能力的质量评分。"""
    return _quality(
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
    )


def _compare_parameters(key_value: object, columns: list[str]) -> list[dict[str, object]]:
    """生成关键列与比较列的人工参数。"""
    return [
        _parameter("key", "关键列", key_value),
        _parameter("columns", "比较列", "、".join(columns) if columns else "未选择"),
    ]


def _compare_column_texts(result: Mapping[str, object]) -> list[str]:
    """读取比较列名称，并过滤空文本。"""
    return [_text(item) for item in _sequence(result.get("columns")) if _text(item)]


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
    diffs = _mapping_rows(result.get("diffs"))
    only_a = _mapping_rows(result.get("only_a"))
    only_b = _mapping_rows(result.get("only_b"))
    duplicate_count = _integer(counts.get("dup_a")) + _integer(counts.get("dup_b"))
    blank_count = _integer(counts.get("blank_a")) + _integer(counts.get("blank_b"))
    reliability_base = max(matched + len(only_a) + len(only_b) + blank_count, 1)
    score = round(100 - _ratio(duplicate_count + blank_count, reliability_base) * 70)  # 单侧业务记录不属于关键列质量缺陷。
    only_rows = _compare_only_rows(only_a, only_b)
    key_text = _text(result.get("key"))
    key_label = key_text or "关键值"  # 明细表头有兜底名称；摘要保留原结果的空关键列语义。
    columns = _compare_column_texts(result)
    skipped = duplicate_count + blank_count
    return {
        "kind": "compare",
        "title": "表格比对结果",
        "summary": f"按“{key_text}”配对 {matched} 行，发现 {len(diffs)} 处值差异和 {len(only_rows)} 条单侧记录。",
        "metrics": _compare_metrics(matched, diffs, only_a, only_b, skipped),
        "quality": _compare_quality(score, duplicate_count, blank_count),
        "parameters": _compare_parameters(result.get("key"), columns),
        "sections": _compare_sections(diffs, only_rows, key_label, limit),
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
