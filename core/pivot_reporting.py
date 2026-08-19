# -*- coding: utf-8 -*-
"""采购汇总结果的可信度评估与兼容文本报告。

本模块只处理已经形成的审计记录、人工复核选择和汇总指标，不读取工作簿，也不执行
规格/单位归并。结构化评分供双端前端直接展示；文本报告仅保留给旧版离线接口。
"""

from __future__ import annotations

import datetime
import os

from openpyxl.utils import get_column_letter


# 六字段规范行中的固定位置。这里不导入 pivot_core，避免报告层与业务层循环依赖。
F_CODE = 1
F_NAME = 2
F_SPEC = 3
F_UNIT = 4
F_FINAL = 5


def _source_findings(used_kinds):
    """评估采购量核心来源是否齐全。"""
    findings = []
    if not any("包装方案汇总" in kind for kind in used_kinds):
        findings.append((35, "严重", "未识别到'包装方案汇总'类表(通常是采购量核心来源), 结果可能严重缺料"))
    if not any("组托辅材" in kind for kind in used_kinds):
        findings.append((12, "警告", "未识别到'组托辅材'类表, 若本单本应含组托数据则会漏项"))
    return findings


def _file_findings(audits):
    """找出完全没有入选数据表的输入文件。"""
    by_file = {}
    for audit in audits:
        by_file.setdefault(audit["file"], []).append(audit)
    return [
        (15, "警告", "文件[%s]未识别出任何数据表, 请确认是否选错文件" % filename)
        for filename, file_audits in by_file.items()
        if not any(item["use"] for item in file_audits)
    ]


def _sheet_findings(used_audits):
    """评估入选页签的字段完整性和识别置信度。"""
    findings = []
    for audit in used_audits:
        missing = audit["missing"]
        if missing:
            missing_text = "/".join(missing)
            key_missing = any(field in ("材料编号", "最终采购数量") for field in missing)
            findings.append((
                10 if key_missing else 4,
                "严重" if key_missing else "提示",
                "表[%s/%s]缺失字段: %s" % (audit["file"], audit["sheet"], missing_text),
            ))
        confidence = audit["confidence"]
        if confidence and confidence < 75:
            # 低置信提示不重复扣分，字段和来源风险已经承担实际扣分。
            findings.append((
                0,
                "提示",
                "表[%s/%s]为低置信识别(%d分, %s)"
                % (audit["file"], audit["sheet"], confidence, audit["kind"]),
            ))
    return findings


def _result_findings(result):
    """检查总计和分组数等生成结果内部勾稽关系。"""
    findings = []
    clean_rows = result["clean_rows"]
    if clean_rows > 0 and result["total"] == 0:
        findings.append((30, "严重", "采购数量总计为 0, 数据虽有行但最终采购数量全为空/0, 请核对源列"))
    if clean_rows > 0 and result["groups"] > clean_rows:
        findings.append((
            20,
            "严重",
            "分组数(%d)大于清洗行数(%d), 逻辑异常" % (result["groups"], clean_rows),
        ))
    source_check = result.get("source_check")
    if isinstance(source_check, dict) and not source_check.get("passed", False):
        source_total = _fmt_number(source_check.get("source_total", 0))
        output_total = _fmt_number(source_check.get("output_total", result.get("total", 0)))
        difference = _fmt_number(source_check.get("difference", 0))
        if source_check.get("source_unparsed", 0):
            findings.append((
                30,
                "严重",
                "最终采购数汇总自检无法确认: 源数据有%d个非空数量无法解析"
                % source_check["source_unparsed"],
            ))
        else:
            findings.append((
                35,
                "严重",
                "最终采购数汇总自检异常: 源数据=%s, 最终表=%s, 差异(最终表-源数据)=%s"
                % (source_total, output_total, difference),
            ))
    return findings


def _confidence_level(score):
    """把零到一百分映射为稳定的可信、需复核、存疑三档结论。"""
    if score >= 85:
        return "可信"
    if score >= 60:
        return "需复核"
    return "存疑"


def assess_confidence(result):
    """用可解释扣分规则评估采购汇总结果，返回结构化风险提示。"""
    score = 100
    issues = []
    used_audits = [audit for audit in result["audit"] if audit["use"]]
    if result["processed"] == 0 or result["clean_rows"] == 0:
        score = 0
        issues.append(("严重", "未识别到任何有效数据表, 无法生成可信采购汇总"))

    findings = []
    findings.extend(_source_findings([audit["kind"] for audit in used_audits]))
    findings.extend(_file_findings(result["audit"]))
    findings.extend(_sheet_findings(used_audits))
    findings.extend(_result_findings(result))
    for penalty, severity, message in findings:
        score -= penalty
        issues.append((severity, message))
    score = max(0, min(100, score))
    return {"level": _confidence_level(score), "score": score, "issues": issues}


def _fmt_number(value):
    """把报告数值显示为整数或最多四位有效小数。"""
    try:
        number = float(value)
        return str(int(number)) if number == int(number) else ("%.4f" % number).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "" if value is None else str(value)


def _fmt_cols(columns):
    """把字段列映射渲染为“编码=K列”一类可读文本。"""
    if not columns:
        return "(无)"
    names = ["版本", "编码", "名称", "规格", "单位", "最终采购数量"]
    parts = [
        "%s=%s列" % (names[index], get_column_letter(column))
        for index, column in enumerate(columns)
        if column
    ]
    return "  ".join(parts) if parts else "(无)"


def _append_review_section(lines, result, separator):
    """追加人工恢复行、单位冲突和规格归并的最终采用值。"""
    review = result.get("review")
    if not review:
        return
    lines.extend((separator, "【人工复核项】(生成前弹窗展示; 默认=系统选择)", separator))
    plan = review.get("plan", {})
    held = plan.get("held_index", []) if plan else []
    lines.append(
        "● 疑似真实但被删的行 —— 有最终采购量却被清洗删除 (共 %d 条, 本次纳入 %d 条, 纳入采购量合计 %s):"
        % (review.get("held_total_n", 0), review.get("held_kept_n", 0), _fmt_number(review.get("held_kept_total", 0)))
    )
    if not held:
        lines.append("    (无) 未发现此类行。")
    else:
        selected_held = review.get("choices", {}).get("held", {})
        for held_row in held:
            row = held_row["rec"]
            kept = selected_held.get((held_row["sid"], held_row["ridx"]), False)
            no_code = "" if held_row.get("has_code") else " [无有效编码]"
            lines.append(
                "    [%s] %s %s %s %s  采购量=%s  删除原因:%s%s  来源:%s"
                % (
                    "已纳入" if kept else "已删除",
                    row[F_CODE], row[F_NAME], row[F_SPEC], row[F_UNIT],
                    _fmt_number(row[F_FINAL]), held_row.get("reason", "?"), no_code,
                    held_row["sheet"],
                )
            )
    lines.append("")
    _append_conflict_section(
        lines,
        "单位聚类冲突",
        review.get("unit_conflicts", []),
        review.get("choices", {}).get("unit_overrides", {}),
        "dist",
    )
    _append_conflict_section(
        lines,
        "规格聚类归并",
        review.get("spec_merges", []),
        review.get("choices", {}).get("spec_overrides", {}),
        "variants",
    )


def _append_conflict_section(lines, title, conflicts, overrides, distribution_key):
    """追加单位或规格冲突段落，统一标记人工覆盖项。"""
    lines.append("● %s (共 %d 处, 人工改动 %d 处):" % (title, len(conflicts), len(overrides)))
    if not conflicts:
        lines.append("    (无) %s。" % ("所有分组单位唯一" if distribution_key == "dist" else "无同料多写法归并"))
    for conflict in conflicts:
        group_key = conflict["gk"]
        final_value = overrides.get(group_key, conflict["default"])
        distribution = " / ".join(
            "%s×%d" % (value if value else "(空)", count)
            for value, count in conflict[distribution_key].items()
        )
        manual = "  <-人工改" if group_key in overrides else ""
        if distribution_key == "dist":
            prefix = "%s %s %s" % (conflict["code"], conflict["name"], conflict["spec"])
            label = "分布"
        else:
            prefix = "%s %s" % (conflict["code"], conflict["name"])
            label = "写法"
        lines.append("    %s | %s: %s | 采用: %s%s" % (prefix, label, distribution, final_value, manual))
    lines.append("")


def _source_check_lines(result, fallback_total):
    """把来源与最终表的数量自检转换为兼容文本报告行。"""
    source_check = result.get("source_check")
    if not isinstance(source_check, dict):
        return [
            "  来源最终采购数   : %s" % _fmt_number(fallback_total),
            "  最终表采购数     : %s" % _fmt_number(fallback_total),
            "  数量差异         : 0",
            "  来源与最终表自检 : 未执行",
        ]
    return [
        "  来源最终采购数   : %s" % _fmt_number(source_check.get("source_total", fallback_total)),
        "  最终表采购数     : %s" % _fmt_number(source_check.get("output_total", fallback_total)),
        "  数量差异         : %s" % _fmt_number(source_check.get("difference", 0)),
        "  来源与最终表自检 : %s" % source_check.get("status", "未执行"),
    ]


def _append_report_body(lines, result, separator):
    """追加风险、来源审计、人工复核与勾稽校验主体。"""
    lines.append("【风险清单】")
    if result["issues"]:
        order = {"严重": 0, "警告": 1, "提示": 2}
        for level, message in sorted(result["issues"], key=lambda item: order.get(item[0], 3)):
            mark = {"严重": "✗", "警告": "!", "提示": "·"}.get(level, "·")
            lines.append("  [%s] %s %s" % (level, mark, message))
    else:
        lines.append("  (无) 未发现风险项。")
    lines.extend(("", separator, "【数据来源识别明细】(共扫描 %d 个文件)" % result["files"], separator))
    used = [audit for audit in result["audit"] if audit["use"]]
    skipped = [audit for audit in result["audit"] if not audit["use"]]
    lines.append("● 已纳入采购汇总的数据表 (%d 张):" % len(used))
    if not used:
        lines.append("    (无)")
    for audit in used:
        lines.extend((
            "  ─ [%s] 工作表《%s》" % (audit["file"], audit["sheet"]),
            "     类型: %s   置信度: %d" % (audit["kind"], audit["confidence"]),
            "     依据: %s" % audit["reason"],
            "     字段: %s" % _fmt_cols(audit["cols"]),
            "     贡献: 保留 %d 行 (清洗删除 版本%d / 采购量%d)" % (audit["rows"], audit["d1"], audit["d2"]),
        ))
        if audit["missing"]:
            lines.append("     ⚠ 缺失字段: %s" % "/".join(audit["missing"]))
    lines.extend(("", "● 已跳过的工作表 (%d 张):" % len(skipped)))
    if not skipped:
        lines.append("    (无)")
    for audit in skipped:
        lines.append("  ─ [%s]《%s》: %s — %s" % (audit["file"], audit["sheet"], audit["kind"], audit["reason"]))
    lines.append("")
    _append_review_section(lines, result, separator)
    total = result["total"]
    try:
        total = int(total) if float(total) == int(total) else total
    except (TypeError, ValueError):
        pass
    check = "通过" if result["groups"] <= result["clean_rows"] and result["clean_rows"] > 0 else "异常"
    lines.extend((
        separator,
        "【汇总与勾稽校验】",
        separator,
        "  清洗后合并数据行 : %d 行" % result["clean_rows"],
        "  物料分组(去重后) : %d 组" % result["groups"],
        "  最终采购数量总计 : %s" % total,
        "  清洗删除小计     : 版本序号 %d 行 / 最终采购量为空或0 %d 行" % (result["d1"], result["d2"]),
        "  勾稽(分组数<=行数): %s" % check,
    ))
    lines.extend(_source_check_lines(result, total))
    lines.extend((
        "",
        separator,
        "说明: 本报告由程序按规则自动生成, 仅供复核参考。评分为扣分制,",
        "      严重项每项重扣、警告次之、提示轻扣; >=85 可信, 60-84 需复核, <60 存疑。",
        separator,
    ))


def write_confidence_report(out_path, in_paths, result):
    """生成兼容旧调用的独立可信度文本报告并返回路径。"""
    base = os.path.splitext(os.path.basename(out_path))[0]
    report_path = os.path.join(os.path.dirname(out_path), base + "_可信度分析报告.txt")
    separator = "=" * 66
    lines = [
        separator,
        "           采购汇总 · 可信度分析报告",
        separator,
        "生成时间   : %s" % (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "采购汇总   : %s" % os.path.basename(out_path),
        "",
        "【总体结论】  可信度: %s   评分: %d/100" % (result["level"], result["score"]),
    ]
    tip = {
        "可信": "识别与汇总逻辑一致, 可直接使用(仍建议抽查关键料号)。",
        "需复核": "存在需关注项, 请对照下方风险清单核对后使用。",
        "存疑": "存在严重问题, 结果可能不可用, 务必人工核对源数据。",
    }
    lines.extend(("            %s" % tip.get(result["level"], ""), ""))
    _append_report_body(lines, result, separator)
    with open(report_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return report_path
