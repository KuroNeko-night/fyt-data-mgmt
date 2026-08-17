# -*- coding: utf-8 -*-
"""对账、销售透视、采购、送货与供应商批次等业务结果投影。

本模块覆盖运营类任务的统一结果展示。各投影函数只读取任务输出的结构化统计、明细和
可信度信息，并按列白名单裁剪前端可见字段；完整明细和正式报告仍由输出文件承载。
采购、送货等数量差异会被呈现为风险提示，但不会因此判定业务任务失败。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .business_result_common import (
    _basename,
    _integer,
    _mapping,
    _metric,
    _number,
    _parameter,
    _quality,
    _quality_check,
    _ratio,
    _section,
    _sequence,
    _text,
    unwrap_result,
)


def _reconcile_rows(anomalies: list[Mapping[str, object]]) -> list[dict[str, object]]:
    """把对账异常转换为前端稳定字段，避免页面依赖原始中文键名。"""

    return [{
        "name": item.get("姓名"),
        "company": item.get("所属劳务公司"),
        "type": item.get("异常类型"),
        "our_hours": item.get("我司出勤工时"),
        "labor_hours": item.get("劳务公司工时"),
        "difference": item.get("差异"),
        "detail": item.get("差异明细"),
    } for item in anomalies]


def _reconcile_quality_checks(credibility: Mapping[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    """转换可信度检查并单独收集警告文案，保持检查级别和提示级别一致。"""

    checks: list[dict[str, object]] = []
    warnings: list[str] = []
    tones = {"严重": "danger", "警告": "warning", "正常": "success", "通过": "success"}
    for check in _sequence(credibility.get("checks")):
        if not isinstance(check, Mapping):
            continue
        level = _text(check.get("级别"))
        title = _text(check.get("项目")) or "核查项"
        message = _text(check.get("说明"))
        checks.append(_quality_check(tones.get(level, "info"), title, message))
        if level in {"警告", "严重"}:
            warnings.append(f"{title}：{message}")
    return checks, warnings


def _reconcile_parameters(result: Mapping[str, object]) -> list[dict[str, object]]:
    """把工时对账参数翻译成客户可读标签，空参数时返回空列表。"""

    parameters = _mapping(result.get("parameters"))
    if not parameters:
        return []
    conflict_labels = {"last": "后者覆盖", "first": "先者优先", "warn": "不覆盖，仅提示"}
    return [
        _parameter("tolerance", "工时差异容差", f"{_text(parameters.get('tolerance'))} 小时"),
        _parameter(
            "conflict",
            "重复记录策略",
            conflict_labels.get(_text(parameters.get("conflict")), _text(parameters.get("conflict"))),
        ),
    ]


def _reconcile_metrics(level, score, tone, matched, diff_people, only_us, only_labor):
    """组装工时对账的四项核心指标。"""
    return [
        _metric("credibility", "可信度", f"{level} · {score}/100", tone=tone),
        _metric("matched", "成功匹配", matched, note="双方名单成功配对人数", tone="success"),
        _metric("diff_people", "工时差异人数", diff_people, tone="danger" if diff_people else "success"),
        _metric("single_side", "单方名单", only_us + only_labor, note=f"我司独有 {only_us}，劳务独有 {only_labor}", tone="warning" if only_us + only_labor else "success"),
    ]


def _present_reconcile(value: object, limit: int) -> dict[str, object] | None:
    """生成工时对账投影，整合异常、双方独有名单和可信度检查。"""
    result = unwrap_result(value)
    anomalies = [item for item in _sequence(result.get("anomalies")) if isinstance(item, Mapping)]
    metrics = _mapping(result.get("metrics"))
    credibility = _mapping(result.get("credibility"))
    if not anomalies and not metrics and not credibility:
        return None
    score = _integer(credibility.get("score"))
    level = _text(credibility.get("level")) or "未评级"
    anomaly_count = _integer(metrics.get("anomaly_count"), len(anomalies))
    matched = _integer(metrics.get("matched_pairs"))
    only_us = _integer(metrics.get("only_us"))
    only_labor = _integer(metrics.get("only_labor"))
    diff_people = _integer(metrics.get("diff_people"))
    tone = "success" if score >= 85 else "warning" if score >= 70 else "danger"  # 对账使用更谨慎的 70 分预警阈值。
    rows = _reconcile_rows(anomalies)
    quality_checks, warnings = _reconcile_quality_checks(credibility)
    notices = []
    if warnings:
        notices.append({
            "tone": "warning",
            "title": "可信度检查提示",
            "message": "；".join(warnings[:5]),
        })
    display_parameters = _reconcile_parameters(result)
    return {
        "kind": "reconcile",
        "title": "工时对账结果",
        "summary": f"可信度 {level}（{score}/100），匹配 {matched} 人，发现 {anomaly_count} 条异常。",
        "metrics": _reconcile_metrics(
            level, score, tone, matched, diff_people, only_us, only_labor,
        ),
        "quality": _quality(score, "综合名单覆盖、重复姓名、工时差异和文件识别情况评估。", quality_checks, level=level),
        "parameters": display_parameters,
        "sections": [_section(
            "anomalies", "异常明细",
            [("name", "姓名"), ("company", "所属劳务公司"), ("type", "异常类型"),
             ("our_hours", "我司工时"), ("labor_hours", "劳务工时"),
             ("difference", "差异"), ("detail", "差异明细")],
            rows,
            description="前端展示有限条明细，完整异常清单仍保存在输出报告中。",
            limit=limit,
        )] if rows else [],
        "notices": notices,
    }


def _pivot_quality_checks(issues):
    """把销售透视的结构风险转换为前端可信度检查。"""
    checks = []
    for item in issues:
        values = _sequence(item)
        if len(values) < 2:
            continue
        issue_level, message = _text(values[0]), _text(values[1])
        checks.append(_quality_check(
            "danger" if issue_level == "严重" else "warning" if issue_level == "警告" else "info",
            issue_level or "核查提示",
            message,
        ))
    if not checks:
        checks.append(_quality_check("success", "识别与汇总", "没有发现需要额外提示的结构风险。"))
    return checks


def _pivot_metrics(result, used, audit, groups, total, review):
    """组装销售透视的五个核心指标。"""
    return [
        _metric("files", "源文件", result.get("files", 0), tone="info"),
        _metric("sheets", "纳入工作表", len(used), note=f"共识别 {len(audit)} 张", tone="success"),
        _metric("groups", "物料分组", groups, tone="success"),
        _metric("total", "采购数量合计", total, tone="neutral"),
        _metric("held", "人工恢复行", review.get("held_kept_n", 0), tone="info"),
    ]


def _present_pivot(value: object, limit: int) -> dict[str, object] | None:
    """生成销售透视投影，展示工作表识别、人工恢复行和动态透视提示。"""
    result = unwrap_result(value)
    audit = [item for item in _sequence(result.get("audit")) if isinstance(item, Mapping)]
    if not audit and "groups" not in result and "score" not in result:
        return None
    used = [item for item in audit if bool(item.get("use"))]  # “纳入”以人工复核后的 use 为准。
    score = _integer(result.get("score"))
    level = _text(result.get("level")) or "未评级"
    groups = _integer(result.get("groups"))
    total = result.get("total", 0)
    issues = _sequence(result.get("issues"))
    checks = _pivot_quality_checks(issues)
    rows = [{
        "file": _basename(item.get("file")),
        "sheet": item.get("sheet"),
        "status": "已纳入" if item.get("use") else "已排除",
        "kind": item.get("kind"),
        "confidence": f"{_integer(item.get('confidence'))}/100",
        "reason": item.get("reason"),
    } for item in audit]
    review = _mapping(result.get("review"))
    notices = []
    if _text(result.get("pivot_error")):
        notices.append({
            "tone": "warning",
            "title": "动态透视表未写入",
            "message": "静态汇总值已正常保留；如需 Excel 内可刷新透视表，请查看正式结果文件中的说明。",
        })
    return {
        "kind": "pivot",
        "title": "销售透视结果",
        "summary": f"已从 {len(used)} 张工作表汇总 {groups} 个物料分组，采购数量合计 {_text(total)}。",
        "metrics": _pivot_metrics(result, used, audit, groups, total, review),
        "quality": _quality(score, "评分依据逐表类型识别、关键字段完整度、采购数量勾稽和人工复核结果。", checks, level=level),
        "parameters": [],
        "sections": [_section(
            "sheets", "工作表识别明细",
            [("file", "文件"), ("sheet", "工作表"), ("status", "处理"),
             ("kind", "识别类型"), ("confidence", "识别可信度"), ("reason", "判断依据")],
            rows,
            description="可信度分析已合并到页面，不再另行生成 TXT 辅助文件。",
            limit=limit,
        )] if rows else [],
        "notices": notices,
    }


def _row_summary(row: Mapping[str, object]) -> dict[str, object]:
    """从采购对账行提取可展示的物料、规格、批次和数量字段。"""
    return {
        "material": row.get("name"),
        "spec": row.get("spec"),
        "batch": row.get("batch"),
        "number": row.get("no"),
        "quantity": row.get("qty"),
    }


def _purchase_conflict_rows(conflicts: list[object]) -> list[dict[str, object]]:
    """把左右数量疑点转换为稳定的前端行，忽略损坏的历史配对项。"""
    rows: list[dict[str, object]] = []
    for item in conflicts:
        values = _sequence(item)
        if (
            len(values) < 2
            or not isinstance(values[0], Mapping)
            or not isinstance(values[1], Mapping)
        ):
            continue
        left = _row_summary(values[0])
        right = _row_summary(values[1])
        rows.append({
            "material": left["material"] or right["material"],
            "spec": left["spec"] or right["spec"],
            "batch": left["batch"] or right["batch"],
            "left_quantity": left["quantity"],
            "right_quantity": right["quantity"],
            "difference": round(
                _number(left["quantity"]) - _number(right["quantity"]), 4,
            ),
        })
    return rows


def _purchase_unmatched_rows(
    left_name: str,
    right_name: str,
    left_rows: list[Mapping[str, object]],
    right_rows: list[Mapping[str, object]],
    matched_left: list[bool],
    matched_right: list[bool],
) -> list[dict[str, object]]:
    """按源表顺序汇总双方未配对记录，并移除仅用于排序的内部字段。"""
    output: list[dict[str, object]] = []
    sides = (
        ("left", left_name, left_rows, matched_left),
        ("right", right_name, right_rows, matched_right),
    )
    for side_key, side_name, rows, matched in sides:
        for index, row in enumerate(rows):
            if index < len(matched) and matched[index]:
                continue
            summary = _row_summary(row)
            output.append({
                "side": side_name,
                "material": summary["material"],
                "spec": summary["spec"],
                "batch": summary["batch"],
                "number": summary["number"],
                "quantity": summary["quantity"],
                # 固定宽度序号保证左表在前，且同侧保持原文件顺序。
                "_sort": f"{side_key}-{index:08d}",
            })
    output.sort(key=lambda item: _text(item.get("_sort")))
    for item in output:
        item.pop("_sort", None)
    return output


def _purchase_quality_checks(
    rate: float,
    pair_count: int,
    conflict_count: int,
    weak_pairs: int,
) -> list[dict[str, object]]:
    """生成配对覆盖、数量一致性和弱依据三类可信度检查。"""
    checks = [
        _quality_check(
            "success" if rate >= 95 else "warning" if rate >= 70 else "danger",
            "配对覆盖",
            f"成功配对 {pair_count} 对，以双方较大有效行数计算覆盖率 {rate:.1f}%。",
        ),
        _quality_check(
            "success" if not conflict_count else "warning",
            "数量一致性",
            f"发现 {conflict_count} 处名称、规格、批次接近但数量不同的疑点。",
        ),
    ]
    if weak_pairs:
        checks.append(_quality_check(
            "warning",
            "弱依据配对",
            f"有 {weak_pairs} 对记录主要依赖名称、规格或近似批次匹配，建议抽查。",
        ))
    return checks


def _purchase_sections(
    conflict_rows: list[dict[str, object]],
    unmatched_rows: list[dict[str, object]],
    left_name: str,
    right_name: str,
    limit: int,
) -> list[dict[str, object]]:
    """按是否存在数据组装数量疑点和未配对明细两个可选区块。"""
    sections: list[dict[str, object]] = []
    if conflict_rows:
        sections.append(_section(
            "quantity_conflicts",
            "数量不一致疑点",
            [
                ("material", "物料"),
                ("spec", "规格"),
                ("batch", "批次"),
                ("left_quantity", left_name + "数量"),
                ("right_quantity", right_name + "数量"),
                ("difference", "差值"),
            ],
            conflict_rows,
            description="名称、规格和批次接近，但双方数量不同，建议优先人工核对。",
            limit=limit,
        ))
    if unmatched_rows:
        sections.append(_section(
            "unmatched",
            "未配对明细",
            [
                ("side", "来源"),
                ("number", "编号"),
                ("material", "物料"),
                ("spec", "规格"),
                ("batch", "批次"),
                ("quantity", "数量"),
            ],
            unmatched_rows,
            description="完整未配对清单和上色结果仍保存在正式输出报告中。",
            limit=limit,
        ))
    return sections


def _purchase_metrics(
    pairs, rate, base_total, left_name, right_name,
    left_unmatched, right_unmatched, conflict_rows,
):
    """组装采购对账的五项核心指标。"""
    return [
        _metric("pairs", "成功配对", len(pairs), tone="success"),
        _metric(
            "match_rate",
            "匹配率",
            f"{rate:.1f}%",
            note=f"以双方较大有效行数 {base_total} 为分母",
            tone="success" if rate >= 95 else "warning",
        ),
        _metric(
            "left_unmatched",
            f"{left_name}未配对",
            left_unmatched,
            tone="danger" if left_unmatched else "success",
        ),
        _metric(
            "right_unmatched",
            f"{right_name}未配对",
            right_unmatched,
            tone="danger" if right_unmatched else "success",
        ),
        _metric(
            "quantity_conflicts",
            "数量疑点",
            len(conflict_rows),
            tone="warning" if conflict_rows else "success",
        ),
    ]


def _present_purchase(value: object, limit: int) -> dict[str, object] | None:
    """生成采购数量对账投影，展示配对率、数量疑点和单侧记录。

    投影拆成“基础统计、疑点行、未配对行、可信度和区块”五个步骤；真实业务差异只影响
    风险提示，不会被误判为程序执行失败。
    """
    result = unwrap_result(value)
    left_rows = [
        item for item in _sequence(result.get("rows1"))
        if isinstance(item, Mapping)
    ]
    right_rows = [
        item for item in _sequence(result.get("rows2"))
        if isinstance(item, Mapping)
    ]
    matched_left = [bool(item) for item in _sequence(result.get("matched1"))]
    matched_right = [bool(item) for item in _sequence(result.get("matched2"))]
    pairs = _sequence(result.get("pairs"))
    conflicts = _sequence(result.get("qty_conflicts"))
    if not left_rows and not right_rows and not pairs and not conflicts:
        return None

    left_name = _text(result.get("name1")) or "我方"
    right_name = _text(result.get("name2")) or "供方"
    base_total = max(len(left_rows), len(right_rows), 1)
    rate = round(len(pairs) / base_total * 100, 1)
    # 弱依据只按第三列可信度是否 <=1 判断，保留精确阈值便于审计调整。
    weak_pairs = sum(
        1
        for item in pairs
        if len(_sequence(item)) >= 3
        and _number(_sequence(item)[2]) <= 1
    )
    conflict_rows = _purchase_conflict_rows(conflicts)
    unmatched_rows = _purchase_unmatched_rows(
        left_name,
        right_name,
        left_rows,
        right_rows,
        matched_left,
        matched_right,
    )
    left_unmatched = max(0, len(left_rows) - sum(matched_left))
    right_unmatched = max(0, len(right_rows) - sum(matched_right))
    # 评分从匹配率起步，疑点与弱依据仅按占比扣分，不把业务差异判为失败。
    quality_score = round(max(
        0.0,
        rate
        - _ratio(len(conflict_rows), base_total) * 0.25
        - _ratio(weak_pairs, base_total) * 0.15,
    ))

    return {
        "kind": "purchase",
        "title": "采购对账结果",
        "summary": (
            f"成功配对 {len(pairs)} 对，匹配率 {rate:.1f}%，"
            f"发现 {len(conflict_rows)} 处数量疑点。"
        ),
        "metrics": _purchase_metrics(
            pairs, rate, base_total, left_name, right_name,
            left_unmatched, right_unmatched, conflict_rows,
        ),
        "quality": _quality(
            quality_score,
            "评分反映配对依据与数据覆盖，不会把真实业务差异判为程序错误。",
            _purchase_quality_checks(
                rate, len(pairs), len(conflict_rows), weak_pairs,
            ),
        ),
        "parameters": [
            _parameter("name1", "左侧名称", left_name),
            _parameter("name2", "右侧名称", right_name),
        ],
        "sections": _purchase_sections(
            conflict_rows,
            unmatched_rows,
            left_name,
            right_name,
            limit,
        ),
        "notices": [],
    }


def _shipping_review_metrics(
    total, full_match, match_rate, quantity_match, quantity_diff,
    name_issues, only_package, only_review, obsolete,
):
    """组装发运评审的七项核心指标。"""
    return [
        _metric("total", "核对物料", total, tone="info"),
        _metric("full_match", "完整一致", full_match, note=f"一致率 {match_rate:.1f}%", tone="success" if full_match == total else "warning"),
        _metric("quantity_match", "数量一致", quantity_match, tone="success" if quantity_diff == 0 else "warning"),
        _metric("quantity_diff", "数量差异", quantity_diff, tone="danger" if quantity_diff else "success"),
        _metric("name_issues", "名称问题", name_issues, tone="warning" if name_issues else "success"),
        _metric("one_side", "单侧物料", only_package + only_review, tone="danger" if only_package + only_review else "success"),
        _metric("obsolete", "已排除作废", obsolete, tone="info"),
    ]


def _shipping_review_checks(quantity_diff, name_issues, only_package, only_review):
    """生成数量、名称和双方覆盖三类核对结果。"""
    return [
        _quality_check(
            "success" if quantity_diff == 0 else "warning",
            "数量核对",
            "双方汇总数量全部一致。" if quantity_diff == 0 else f"有 {quantity_diff} 个物料汇总数量不一致。",
        ),
        _quality_check(
            "success" if name_issues == 0 else "warning",
            "名称核对",
            "双方名称全部一致。" if name_issues == 0 else f"有 {name_issues} 个物料存在名称缺失或不一致。",
        ),
        _quality_check(
            "success" if only_package + only_review == 0 else "warning",
            "双方覆盖",
            "两侧物料范围完全对应。" if only_package + only_review == 0 else f"有 {only_package + only_review} 个物料只出现在一侧。",
        ),
    ]


def _present_shipping_review(value: object, limit: int) -> dict[str, object] | None:
    """生成发运评审对比投影，在线展示数量差异、名称问题和单侧物料。"""

    result = unwrap_result(value)
    counts = _mapping(result.get("counts"))
    details = [item for item in _sequence(result.get("details")) if isinstance(item, Mapping)]
    if not counts and not details:
        return None
    total = _integer(counts.get("total_materials"), len(details))
    full_match = _integer(counts.get("full_match"))
    quantity_match = _integer(counts.get("quantity_match"))
    quantity_diff = _integer(counts.get("quantity_diff"))
    name_issues = _integer(counts.get("name_issues"))
    only_package = _integer(counts.get("only_package"))
    only_review = _integer(counts.get("only_review"))
    obsolete = _integer(result.get("obsolete_rows"))
    exceptions = [item for item in details if _text(item.get("status")) != "一致"]
    # 完整一致率以核对物料数为分母，避免空表出现除零。
    match_rate = _ratio(full_match, max(total, 1))
    return {
        "kind": "shipping_review",
        "title": "发运评审对比结果",
        "summary": (
            f"共核对 {total} 个物料，完整一致 {full_match} 个，"
            f"数量差异 {quantity_diff} 个，名称问题 {name_issues} 个。"
        ),
        "metrics": _shipping_review_metrics(
            total, full_match, match_rate, quantity_match, quantity_diff,
            name_issues, only_package, only_review, obsolete,
        ),
        "quality": _quality(
            round(match_rate),
            "评分表示物料数量、名称与双方覆盖的完整一致比例，不代表生产或交付绩效。",
            _shipping_review_checks(
                quantity_diff, name_issues, only_package, only_review,
            ),
        ),
        "parameters": [
            _parameter("package_sheet", "包装工作表", result.get("package_sheet")),
            _parameter("review_sheet", "评审工作表", result.get("review_sheet")),
        ],
        "sections": [_section(
            "exceptions",
            "需要关注的物料",
            [
                ("code", "物料号"),
                ("package_name", "包装物料描述"),
                ("review_name", "评审中文名称"),
                ("package_quantity", "包装数量"),
                ("review_quantity", "评审总数"),
                ("difference", "差异"),
                ("status", "状态"),
            ],
            exceptions,
            description="完整明细、包装透视和已作废 BOX 审计均保存在正式报告中。",
            limit=limit,
        )] if exceptions else [],
        "notices": ["本次所有物料的数量和名称均完全一致。"] if not exceptions else [],
    }


def _delivery_quality(
    *,
    rows: int,
    matched: int,
    missing: list[str],
    supplier_used: bool,
    case_used: bool,
    case_hit: int,
) -> tuple[float, int, list[dict[str, object]]]:
    """计算送货计划的两类字段覆盖率，并生成可信度核对项。

    评分只衡量自动补全是否充分，不把业务行数本身当成质量。没有供应商来源时保留历史
    基准分 75，表达“计划可生成但需要人工维护”；参考计划只占 15%，避免 CASE/班组
    缺失掩盖供应商主字段的风险。
    """
    supplier_rate = _ratio(matched, rows) if supplier_used else 0.0
    case_rate = _ratio(case_hit, rows) if case_used else 0.0
    # 无供应商来源时保留 75 分历史基准，表达“可生成但需人工维护”。
    score = 75 if rows else 0
    if supplier_used:
        score = round(supplier_rate)
    if case_used:
        score = round(score * 0.85 + case_rate * 0.15)

    checks = []
    if supplier_used:
        checks.append(_quality_check(
            "success" if not missing else "warning",
            "供应商匹配",
            f"已匹配 {matched} / {rows} 行，仍有 {len(missing)} 个物料编码需要补充供应商。",
        ))
    else:
        checks.append(_quality_check(
            "warning", "供应商信息待补充",
            "本次没有可用的供应商来源，系统已尝试从主数据库补全，剩余空白需人工确认。",
        ))
    if case_used:
        checks.append(_quality_check(
            "success" if case_rate >= 90 else "warning",
            "CASE 与班组沿用",
            f"参考计划命中 {case_hit} / {rows} 行，覆盖率 {case_rate:.1f}%。",
        ))
    return supplier_rate, score, checks


def _delivery_missing_sections(missing: list[str], limit: int) -> list[dict[str, object]]:
    """把待补供应商编码转换为受预览条数限制的明细区块。"""
    if not missing:
        return []
    return [_section(
        "missing", "待补供应商物料",
        [("material_code", "物料编码")],
        ({"material_code": item} for item in missing),
        description="这些物料已保留在送货计划中，但供应商代码或名称需要人工补充。",
        limit=limit,
    )]


def _delivery_metrics(rows, matched, missing, supplier_used, case_used, case_hit):
    """组装送货计划的四项核心指标。"""
    return [
        _metric("rows", "计划行数", rows, tone="success"),
        _metric("supplier", "供应商匹配", f"{matched} / {rows}" if supplier_used else "待补充", tone="success" if supplier_used and not missing else "warning"),
        _metric("missing", "待补物料", len(missing), tone="danger" if missing else "success"),
        _metric("case", "CASE/班组命中", f"{case_hit} / {rows}" if case_used else "未使用参考计划", tone="info"),
    ]


def _present_delivery(value: object, limit: int) -> dict[str, object] | None:
    """生成送货计划投影，聚焦供应商补全和参考计划字段覆盖。

    供应商或 CASE/班组未命中时，Core 会在结果中保留待补物料；投影不从输出表反向分析，
    只使用结构化统计和主数据覆盖信息。
    """
    result = unwrap_result(value)
    if "rows" not in result and "plan_path" not in result:
        return None
    rows = _integer(result.get("rows"))
    matched = _integer(result.get("matched"))
    missing = [_text(item) for item in _sequence(result.get("missing")) if _text(item)]
    supplier_used = bool(result.get("supplier_used"))
    case_used = bool(result.get("case_used"))
    case_hit = _integer(result.get("case_hit"))
    supplier_rate, score, checks = _delivery_quality(
        rows=rows,
        matched=matched,
        missing=missing,
        supplier_used=supplier_used,
        case_used=case_used,
        case_hit=case_hit,
    )
    return {
        "kind": "delivery",
        "title": "送货计划结果",
        "summary": f"已生成 {rows} 行送货计划" + (f"，供应商匹配率 {supplier_rate:.1f}%" if supplier_used else "，供应商信息按可用主数据补全") + "。",
        "metrics": _delivery_metrics(
            rows, matched, missing, supplier_used, case_used, case_hit,
        ),
        "quality": _quality(score, "评分聚焦供应商及参考计划字段的自动补全覆盖，空白项仍保留给人工维护。", checks),
        "parameters": [
            _parameter("order_type", "订单类型", result.get("order_type") or "未指定"),
            _parameter("supplier_source", "供应商来源", "输入文件或主数据库" if supplier_used else "主数据库与人工补充"),
            _parameter("case_source", "CASE/班组", "参考计划" if case_used else "未沿用"),
        ],
        "sections": _delivery_missing_sections(missing, limit),
        "notices": [],
    }


def _present_supplier_batch(value: object, limit: int) -> dict[str, object] | None:
    """生成供应商批次表投影，展示输出、交付日期和未匹配供应商。

    “原厂”记录是明确业务排除项，因此单独计数但不降低质量评分；未匹配供应商才代表
    无法归属到输出文件的识别风险。
    """
    result = unwrap_result(value)
    if "generated" not in result and not _sequence(result.get("files")):
        return None
    suppliers = [_text(item) for item in _sequence(result.get("suppliers")) if _text(item)]
    files = [_basename(item) for item in _sequence(result.get("files")) if _text(item)]
    batch_dates = _mapping(result.get("batch_dates"))
    rows = _integer(result.get("rows"))
    unmatched = _integer(result.get("unmatched_count"))
    excluded = _integer(result.get("excluded_original_count"))
    quality_score = round(100 - _ratio(unmatched, max(rows + unmatched, 1)) * 60)  # 排除原厂不进入分母或扣分。
    detail_rows = [{"batch": batch, "delivery_date": date} for batch, date in batch_dates.items()]
    return {
        "kind": "supplier_batch",
        "title": "供应商批次表结果",
        "summary": f"已为 {len(suppliers)} 家供应商生成 {len(files)} 份批次表，共 {rows} 行。",
        "metrics": [
            _metric("suppliers", "供应商", len(suppliers), tone="info"),
            _metric("files", "输出文件", len(files), tone="success"),
            _metric("rows", "批次明细", rows, tone="neutral"),
            _metric("unmatched", "未匹配供应商", unmatched, tone="danger" if unmatched else "success"),
            _metric("excluded", "已排除原厂", excluded, tone="info"),
        ],
        "quality": _quality(
            quality_score,
            "评分依据供应商归属覆盖；“原厂”记录属于规则性排除，不降低可信度。",
            [_quality_check(
                "success" if unmatched == 0 else "warning",
                "供应商归属",
                f"有 {unmatched} 条记录未匹配供应商，未写入任何供应商批次表。" if unmatched else "所有纳入记录均已匹配供应商。",
            )],
        ),
        "parameters": [],
        "sections": [_section(
            "delivery_dates", "批次交付日期",
            [("batch", "批次"), ("delivery_date", "交付日期")],
            detail_rows,
            description="这里展示本次人工确认并写入各供应商批次表的交付日期。",
            limit=limit,
        )] if detail_rows else [],
        "notices": [],
    }


def _present_purchase_plan(value: object, limit: int) -> dict[str, object] | None:
    """生成采购计划导入投影，并展示本次自动学习的新主数据。"""
    result = unwrap_result(value)
    if "generated" not in result and not _sequence(result.get("files")):
        return None
    files = [_basename(item) for item in _sequence(result.get("files")) if _text(item)]
    new_materials = [_text(item) for item in _sequence(result.get("new_materials")) if _text(item)]
    new_suppliers = [_text(item) for item in _sequence(result.get("new_suppliers")) if _text(item)]
    rows = _integer(result.get("rows"))
    excluded = _integer(result.get("excluded_original_count"))
    sections = [_section(
        "files", "生成的采购计划",
        [("name", "文件")],
        ({"name": item} for item in files),
        limit=limit,
    )] if files else []
    discovered = ([{"type": "新材料", "value": item} for item in new_materials]
                  + [{"type": "新供应商", "value": item} for item in new_suppliers])
    if discovered:
        sections.append(_section(
            "catalog", "本次发现的新主数据",
            [("type", "类型"), ("value", "内容")],
            discovered,
            description="系统已自动学习，可在主数据维护中继续确认和修正。",
            limit=limit,
        ))
    return {
        "kind": "purchase_plan",
        "title": "采购计划导入结果",
        "summary": f"已生成 {len(files)} 个批次采购计划，共写入 {rows} 行。",
        "metrics": [
            _metric("files", "采购计划", len(files), tone="success"),
            _metric("rows", "写入行数", rows, tone="neutral"),
            _metric("excluded", "已排除原厂", excluded, tone="info"),
            _metric("new_catalog", "新主数据", len(discovered), note=f"材料 {len(new_materials)}，供应商 {len(new_suppliers)}", tone="warning" if discovered else "success"),
        ],
        "parameters": [],
        "sections": sections,
        "notices": [],
    }


def _present_purchase_diff(value: object, limit: int) -> dict[str, object] | None:
    """生成实收差异清单的轻量指标投影；完整差异仍由输出文件承载。"""
    result = unwrap_result(value)
    if "rows" not in result or "path" not in result:
        return None
    rows = _integer(result.get("rows"))
    excluded = _integer(result.get("excluded_original_count"))
    return {
        "kind": "purchase_diff",
        "title": "实收差异清单结果",
        "summary": f"已提取 {rows} 条实收与计划不一致记录。",
        "metrics": [
            _metric("rows", "差异记录", rows, tone="warning" if rows else "success"),
            _metric("excluded", "已排除原厂", excluded, tone="info"),
        ],
        "parameters": [],
        "sections": [],
        "notices": [],
    }
