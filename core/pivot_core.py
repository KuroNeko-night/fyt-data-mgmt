# -*- coding: utf-8 -*-
"""销售采购表的识别、清洗、人工复核、聚合与原生透视表生成。

处理采用严格的两阶段协议：``analyze_workbooks`` 只读源文件并收集页签选择、疑似被删
行、单位冲突和规格归并等决策点；``apply_plan`` 根据最终选择生成清洗数据、静态汇总和
Excel 原生 OOXML 透视对象。结构化可信度分析随结果返回双端前端，不再依赖单独报告。

本模块是透视业务算法的唯一事实源，不依赖界面。它负责公式缓存提示、主数据补空、
增量缓存和 Web 任务产物隔离，但不会覆盖源文件。文件已按职责拆分：

- :mod:`core.pivot_analysis` —— 结构识别、分类、清洗与第一阶段复核计划；
- :mod:`core.pivot_clustering` —— 规格/单位归并与静态聚合；
- :mod:`core.pivot_ooxml` —— 原生透视缓存与 OOXML 部件注入；
- :mod:`core.pivot_reporting` —— 可信度评分与兼容文本报告。

本模块保留这些子模块的公开名称重导出，旧调用方仍可从 ``pivot_core`` 访问。
"""
import os
import datetime

import openpyxl
from openpyxl.styles import Border, Side, Alignment, Font, PatternFill
from openpyxl.styles.colors import Color
from openpyxl.utils import get_column_letter

from . import paths as _paths
from . import settings as _settings
from . import common_core                    # Progress 进度上报辅助
from . import incremental_cache
from . import material_catalog
from . import pivot_analysis
from . import pivot_clustering
from . import pivot_reporting
from .common_core import warn_if_uncached   # 公式未刷新检测(读关键表前告警)
from .pivot_ooxml import (  # 部分名称供旧调用方从 pivot_core 继续访问
    DATA_FIELD, FIELD_LABELS, ROW_FIELDS, _code_order_key, _is_blank, _num,
    build_fields_meta, cache_definition_xml, cache_records_xml, inject_pivots,
    meta_by_idx, pivot_table_xml,
)

# 可信度评分与兼容文本报告位于独立渲染层；保留原名称兼容旧调用。
assess_confidence = pivot_reporting.assess_confidence
write_confidence_report = pivot_reporting.write_confidence_report

# ---- 重导出拆分模块的公开名称，保持旧导入路径稳定 ----
from .pivot_analysis import (  # noqa: E402,F401  (兼容旧调用)
    CODE_ALIASES, EXCLUDE_SHEET_TOKENS, FIELD_CN, FINAL_ALIASES,
    HEADER_SCAN_ROWS, INFO_FIELDS, KEEP_TOKEN, KEY_FIELDS,
    L_CODE, L_FINAL, L_NAME, L_QTY, L_SPEC, L_UNIT, L_VER,
    MAX_BLOCKS, NAME_ALIASES, NAME_EXCLUDE, NAME_PACKAGING, NAME_ZUTUO,
    QTY_EXACT, SPEC_ALIASES, SUM_PREFIX, UNIT_ALIASES, VER_ALIASES,
    _PreviewCell, _SheetPreview, _analyze_stream_sheet, _assign_block_column,
    _block_from_anchor, _cell, _classify_by_name_and_cols,
    _complete_rows_from_catalog, _contains_any, _final_has_qty,
    _has_chinese, _has_token, _header_anchor_columns, _is_excluded_sheet,
    _is_valid_code, _is_zero, _last_col, _looks_like_pivot_output,
    _match_anchor, _norm, _preview_sheet, _sheet_name,
    analyze_workbooks, classify_sheet, clean_rows, clean_rows_ex,
    find_all_blocks, is_data_sheet, normalize_rows, normalize_stream_rows,
)
from .pivot_clustering import (  # noqa: E402,F401  (兼容旧调用)
    F_CODE, F_FINAL, F_NAME, F_QTY, F_SPEC, F_UNIT, F_VER,
    _compute_unit_best, _is_compound_unit, _name_unit_prior, _norm_key,
    _spec_base, _spec_gkey, _spec_keyof, _unit_gkey, _unit_key_sample,
    _unit_simplicity, aggregate, compute_spec_canon, compute_unit_best,
    drop_blank_code_rows, unify_specs, unify_units,
)

PIVOT_BASE = "数据透视表"
L_SUPPLIER = "供应商"
L_SUMMARY  = "汇总"
L_DIFF     = "差异"
L_RECEIVED = "实收"
L_DATE     = "日期"

# ---- 输出样式(与主程序一致: 微软雅黑, 蓝底表头, 细边框) ----
_FONT_NAME = "微软雅黑"
_thin = Side(style='thin')
_BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
_FONT = Font(name=_FONT_NAME, size=11)
_FONT_B = Font(name=_FONT_NAME, size=11, bold=True)
_BLUE = PatternFill(patternType='solid', fgColor=Color(theme=4, tint=0.3999755851924192))


def _st(cell, bold=False, fill=False):
    """为透视输出单元格应用统一边框、对齐和可选强调样式。"""
    cell.border = _BORDER
    cell.alignment = _CENTER
    cell.font = _FONT_B if bold else _FONT
    if fill:
        cell.fill = _BLUE


def write_clean_sheet(ws, rows):
    """用规范七字段重写清洗数据工作表。

    原合并区域和旧内容全部移除，第一行保留为空、第二行写表头、第三行开始写数据。这里
    不复制源样式，确保动态透视的数据源是连续、无合并且结构确定的 A 至 G 列区域。
    """
    # 解除合并并清空原内容
    for mc in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(mc))
    if ws.max_row >= 1:
        ws.delete_rows(1, ws.max_row)
    headers = [L_VER, L_CODE, L_NAME, L_SPEC, L_QTY, L_UNIT, L_FINAL]
    for j, h in enumerate(headers, start=1):
        ws.cell(row=2, column=j, value=h)
    r = 3
    for rec in rows:  # rec: [版本,编码,名称,规格,数量,单位,最终采购数量]
        for j in range(7):
            ws.cell(row=r, column=j + 1, value=rec[j])
        r += 1


def write_pivot_sheet(wb, base_name, agg):
    """创建静态可读的透视结果页，并返回实际唯一页名。

    前五列由原生透视对象接管，后五列是业务人员后续维护区。即使 OOXML 注入失败，静态
    聚合仍可直接使用；汇总列引用同行透视度量而不是写死数值，避免 Excel 刷新重排行时
    与实收、差异等静态列错位。
    """
    name = base_name
    i = 1
    while name in wb.sheetnames:
        i += 1
        name = "%s%d" % (base_name, i)
    ws = wb.create_sheet(title=name)

    headers = [L_CODE, L_NAME, L_SPEC, L_UNIT, SUM_PREFIX + L_FINAL,
               L_SUPPLIER, L_SUMMARY, L_DIFF, L_RECEIVED, L_DATE]
    for j, h in enumerate(headers, start=1):
        ws.cell(row=1, column=j, value=h)

    total = 0
    r = 2
    for code, nm, sp, un, s in agg:
        ws.cell(row=r, column=1, value=code)
        ws.cell(row=r, column=2, value=nm)
        ws.cell(row=r, column=3, value=sp)
        ws.cell(row=r, column=4, value=un)
        ws.cell(row=r, column=5, value=s)
        # 汇总列改为“同行 E(求和项:最终采购数量)”的公式而非静态值:
        # E 属于动态透视范围(A1:E…), Excel 打开刷新会按自身排序重排 A–E;
        # 若 G 写静态值, 刷新后 G 停在原顺序 -> 与重排后的 E 错位(用户所见“汇总≠最终采购数”)。
        # 用 =E{r} 让 G 始终等于同一行的 E, 无论 Excel 如何重排都对齐。
        ecell = "%s%d" % (get_column_letter(5), r)
        ws.cell(row=r, column=7, value="=%s" % ecell)   # 汇总 = 同行求和项
        # 差异 = 实收 - 汇总 (公式)
        rcv = "%s%d" % (get_column_letter(9), r)
        sm  = "%s%d" % (get_column_letter(7), r)
        ws.cell(row=r, column=8, value="=%s-%s" % (rcv, sm))
        try:
            total += float(s)
        except (ValueError, TypeError):
            pass
        r += 1

    if total == int(total):
        total = int(total)
    ws.cell(row=r, column=1, value="总计")
    ws.cell(row=r, column=5, value=total)
    return name


# 原生透视缓存和 OOXML 归档注入位于 pivot_ooxml.py；本模块通过导入保留原公开名。
def process_workbook(in_path, out_path=None, log=None):
    """复刻 RunProcess: 打开工作簿, 对每张数据表清洗并生成一张透视结果表。

    不改动原文件(输出到 ``out_path``, 默认在原名后加 ``_透视结果``)。返回处理、跳过
    数量、逐表汇总、输出路径和动态透视注入错误。该兼容入口没有人工决策阶段，适用于
    旧调用；新双端流程应使用 ``analyze_workbooks`` 与 ``apply_plan``。
    """
    # 跳过源文件内嵌透视缓存的解析(只读单元格值,透视表另经 inject_pivots 写出)
    wb = common_core.load_data_only(in_path)
    src_names = list(wb.sheetnames)   # 先快照，避免循环时扫描到本函数新建的透视页。
    processed = 0; skipped = 0; detail = []; pivot_jobs = []
    for sn in src_names:
        ws = wb[sn]
        if not is_data_sheet(ws):
            skipped += 1
            continue
        rows = normalize_rows(ws)
        rows, d1, d2 = clean_rows(rows)
        rows = unify_specs(rows)
        rows = unify_units(rows)
        rows, _dbc = drop_blank_code_rows(rows)   # 剔除空编码行, 避免 (空白) 组
        agg = aggregate(rows)
        total = sum((x[4] for x in agg), 0)
        # 1) 把清洗后的数据写回源表(作为透视表数据源, 也方便手动操作)
        write_clean_sheet(ws, rows)
        # 2) 建透视表 sheet: 先渲染静态值(不刷新也可见), 稍后注入动态透视对象
        pv_name = write_pivot_sheet(wb, PIVOT_BASE, agg)
        # 源表清洗数据范围: A2:G(2+行数)
        src_ref = "A2:G%d" % (2 + len(rows))
        pivot_jobs.append({"sheet": pv_name, "src_sheet": sn, "src_ref": src_ref,
                           "rows": rows, "agg": agg, "name": pv_name})
        detail.append((sn, pv_name, d1, d2, len(agg), total))
        processed += 1

    if out_path is None:
        d = os.path.dirname(in_path)
        base = os.path.splitext(os.path.basename(in_path))[0]
        out_path = os.path.join(d, base + "_透视结果.xlsx")
    wb.save(out_path)  # 先保存完整静态结果，OOXML 注入失败时仍有可交付文件。
    # 3) 注入原生 OOXML 动态透视表(兼容 Excel/WPS); 失败则保留静态表
    pivot_error = ""
    if pivot_jobs:
        try:
            inject_pivots(out_path, pivot_jobs)
        except Exception as e:
            # 不再静默吞掉: 保留静态汇总值, 但至少报一句, 便于发现"透视表打不开却无人知"
            pivot_error = "%s: %s" % (type(e).__name__, e)
            if log:
                log("⚠ 动态透视表注入失败(已保留静态汇总值): %s" % pivot_error)
    return {'processed': processed, 'skipped': skipped,
            'sheets': detail, 'out': out_path, 'pivot_error': pivot_error}


def _safe_sheet_name(wb, base):
    """生成不含 Excel 禁用字符且不重复的工作表名。

    基础名称预留三位给数字后缀，最终始终不超过 31 字符；空名称回退为“数据”。
    """
    for ch in '[]:*?/\\':
        base = base.replace(ch, ' ')
    base = base.strip() or "数据"
    base = base[:28]
    name = base; i = 1
    while name in wb.sheetnames:
        i += 1
        suffix = str(i)
        name = base[:28 - len(suffix)] + suffix
    return name


def _default_choices(plan):
    """根据分析计划生成完整的系统默认选择。

    页签沿用分类结果，疑似被删行全部保持排除，规格和单位不设置人工覆盖。这样人工未
    修改任何项目时，第二阶段与自动处理口径一致。
    """
    return {
        "sheets": {s["id"]: bool(s["use"]) for s in plan["sheets"]},
        "held":   {(h["sid"], h["ridx"]): False for h in plan["held_index"]},
        "unit_overrides": {},   # {gk: unit}
        "spec_overrides": {},   # {gk: spec}
    }


def _sheet_audit_record(sheet, use):
    """构造单个页签的审计记录，后续只更新实际行数和人工保留数。"""
    return {
        "file": sheet["file"],
        "sheet": sheet["sheet"],
        "use": use,
        "kind": sheet["kind"],
        "confidence": sheet["confidence"],
        "reason": sheet["reason"],
        "cols": sheet["cols"],
        "missing": sheet["missing"],
        "rows": 0,
        "d1": sheet["d1"],
        "d2": sheet["d2"],
        "held_kept": 0,
    }


def _selected_sheet_rows(sheet, selected_held):
    """复制页签默认保留行，并追加人工明确恢复的疑似删除行。

    返回复制后的行、人工恢复条数和这些恢复行的最终采购数量合计。所有行都复制为新
    列表，确保第二阶段规格/单位归并不会反向修改第一阶段的只读分析计划。
    """
    rows = [list(row) for row in sheet["kept"]]
    kept_count = 0
    kept_total = 0.0
    for row_index, held in enumerate(sheet["held"]):
        if not selected_held.get((sheet["id"], row_index), False):
            continue
        row = list(held["rec"])
        rows.append(row)
        kept_count += 1
        try:
            kept_total += float(row[F_FINAL])
        except (TypeError, ValueError):
            # 选择本身仍然有效；无法解析的数量由后续清洗和可信度结果继续反映。
            pass
    return rows, kept_count, kept_total


def _collect_selected_plan_rows(plan, choices):
    """汇总第二阶段实际入选的页签和数据行，并生成页签级审计信息。"""
    selected_sheets = choices.get("sheets", {})
    selected_held = choices.get("held", {})
    summary = {
        "audit": [],
        "detail": [],
        "rows": [],
        "processed": 0,
        "skipped": 0,
        "d1": 0,
        "d2": 0,
        "held_kept_n": 0,
        "held_kept_total": 0.0,
    }

    for sheet in plan["sheets"]:
        use = selected_sheets.get(sheet["id"], sheet["use"])
        audit_record = _sheet_audit_record(sheet, use)
        if not use:
            summary["audit"].append(audit_record)
            summary["skipped"] += 1
            continue

        rows, kept_count, kept_total = _selected_sheet_rows(sheet, selected_held)
        summary["held_kept_n"] += kept_count
        summary["held_kept_total"] += kept_total
        if not rows:
            # 页签被勾选但没有任何可用行时，结果审计应反映最终未参与处理的事实。
            audit_record.update(use=False, kind="排除:未选中任何行")
            summary["audit"].append(audit_record)
            summary["skipped"] += 1
            continue

        summary["rows"].extend(rows)
        summary["d1"] += sheet["d1"]
        summary["d2"] += sheet["d2"]
        audit_record.update(rows=len(rows), held_kept=kept_count)
        summary["audit"].append(audit_record)
        summary["detail"].append((
            "%s / %s" % (sheet["file"], sheet["sheet"]),
            len(rows),
            sheet["d1"],
            sheet["d2"],
        ))
        summary["processed"] += 1
    return summary


def _build_selected_pivot_workbook(selected_rows, choices):
    """规范化入选行并构造静态清洗页、汇总页和待注入透视任务。"""
    workbook = openpyxl.Workbook()
    default_sheet = workbook.active
    if not selected_rows:
        return workbook, [], [], 0, 0

    rows = unify_specs(
        selected_rows,
        overrides=choices.get("spec_overrides") or None,
    )
    rows = unify_units(
        rows,
        overrides=choices.get("unit_overrides") or None,
    )
    rows, _blank_code_count = drop_blank_code_rows(rows)
    aggregated = aggregate(rows)
    groups = len(aggregated)
    total = sum((item[4] for item in aggregated), 0)

    clean_name = _safe_sheet_name(workbook, "清洗数据")
    clean_sheet = workbook.create_sheet(title=clean_name)
    write_clean_sheet(clean_sheet, rows)
    pivot_name = write_pivot_sheet(workbook, PIVOT_BASE, aggregated)
    source_ref = "A2:G%d" % (2 + len(rows))
    pivot_jobs = [{
        "sheet": pivot_name,
        "src_sheet": clean_name,
        "src_ref": source_ref,
        "rows": rows,
        "agg": aggregated,
        "name": pivot_name,
    }]
    if default_sheet.title in workbook.sheetnames:
        workbook.remove(default_sheet)
    return workbook, rows, pivot_jobs, groups, total


def _inject_pivot_jobs(out_path, pivot_jobs, log):
    """尝试注入 Excel 原生透视对象，失败时返回摘要而不破坏静态结果。"""
    if not pivot_jobs:
        return ""
    try:
        inject_pivots(out_path, pivot_jobs)
        return ""
    except Exception as error:
        pivot_error = "%s: %s" % (type(error).__name__, error)
        if log:
            log("⚠ 动态透视表注入失败(已保留静态汇总值): %s" % pivot_error)
        return pivot_error


def _build_apply_result(plan, choices, out_path, selection, clean_rows,
                        groups, total, pivot_error):
    """组装第二阶段稳定返回协议，并附加可信度结论和人工复核摘要。"""
    result = {
        "processed": selection["processed"],
        "skipped": selection["skipped"],
        "sheets": selection["detail"],
        "pivot_error": pivot_error,
        "out": out_path,
        "files": plan["files"],
        "groups": groups,
        "total": total,
        "d1": selection["d1"],
        "d2": selection["d2"],
        "audit": selection["audit"],
        "clean_rows": len(clean_rows),
        "review": {
            "plan": plan,
            "choices": choices,
            "details_cached": True,
            "held_kept_n": selection["held_kept_n"],
            "held_kept_total": selection["held_kept_total"],
            "held_total_n": len(plan["held_index"]),
            "unit_conflicts": plan["unit_conflicts"],
            "spec_merges": plan["spec_merges"],
        },
    }
    result.update(assess_confidence(result))
    # 可信度和逐表依据已由结构化结果承载，不再生成需要用户另行打开的辅助文本。
    result["report"] = ""
    return result


def apply_plan(plan, choices, out_path, log=None):
    """按人工最终选择合并、规范化、聚合并写出透视结果。

    每张页先复制已保留行，再追加人工明确勾选的 ``held`` 行；规格和单位覆盖在所有入选
    行合并后统一应用。函数先保存静态清洗页和汇总页，再尝试注入原生透视对象。注入失败
    只记录 ``pivot_error``，不把已经可用的静态结果改判失败。返回值含审计、可信度和复核
    明细，供双端直接展示。
    """
    selection = _collect_selected_plan_rows(plan, choices)
    workbook, clean_rows, pivot_jobs, groups, total = _build_selected_pivot_workbook(
        selection["rows"], choices,
    )
    # 静态结果先落盘，保证动态透视对象注入失败时仍有可交付的清洗页和汇总页。
    workbook.save(out_path)
    pivot_error = _inject_pivot_jobs(out_path, pivot_jobs, log)
    return _build_apply_result(
        plan,
        choices,
        out_path,
        selection,
        clean_rows,
        groups,
        total,
        pivot_error,
    )


def process_workbooks(in_paths, out_path, choices=None):
    """兼容旧调用的一步式“分析后立即应用”入口。

    未传选择时使用系统默认决策，因此不会提供人工确认停顿；Web/Tauri 人工复核流程应
    分别调用两阶段入口。
    """
    plan = analyze_workbooks(in_paths)
    if choices is None:
        choices = _default_choices(plan)
    return apply_plan(plan, choices, out_path)


def _fmt_num(v):
    """数值展示: 整数去掉小数点。"""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else ("%.4f" % f).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "" if v is None else str(v)


def _cacheable_result(result):
    """生成可 JSON 持久化的销售透视缓存快照。

    完整复核计划体积大且 ``choices`` 含元组键，不能直接写 JSON。缓存仅保留汇总数量、
    冲突列表和“详细计划未缓存”标记；再次命中缓存时前端仍能展示业务结果，但不会把旧
    逐行计划误当成当前可编辑决策。
    """
    compact = dict(result)
    review = result.get("review")
    if isinstance(review, dict):
        compact["review"] = {
            "details_cached": False,
            "held_kept_n": review.get("held_kept_n", 0),
            "held_kept_total": review.get("held_kept_total", 0),
            "held_total_n": review.get("held_total_n", 0),
            "unit_conflicts": review.get("unit_conflicts", []),
            "spec_merges": review.get("spec_merges", []),
        }
    return compact


def _materialize_web_cache(cached, out_dir):
    """把同一用户缓存产物复制到当前 Web 任务输出目录。

    缓存索引可跨任务复用，但下载路径必须属于当前任务运行目录。每个存在的产物使用
    ``unique_path`` 复制并改写结果路径，避免不同任务共享绝对文件引用。
    """
    import shutil

    result = dict(cached)
    for key in ("out", "report"):
        source = result.get(key)
        if not source or not os.path.isfile(source):
            continue
        target = common_core.unique_path(
            os.path.join(out_dir, os.path.basename(source)))
        shutil.copy2(source, target)
        result[key] = target
    result["out_dir"] = out_dir
    return result


def _prepare_run(in_paths, out_dir):
    """整理透视入口参数，并计算与用户/目录隔离相关的缓存范围。"""
    st = _settings.get_settings()  # 每次运行读取当前设置，确保界面刚保存的参数立即生效。
    paths = [in_paths] if isinstance(in_paths, str) else list(in_paths)  # 防止字符串被逐字符遍历。
    resolver = material_catalog.CatalogResolver()  # 主数据签名参与缓存键，关系变更后自动失效。
    web_root = os.environ.get("FYT_WEB_OUTPUT_ROOT", "").strip()  # Web 任务必须隔离桌面绝对路径。
    if out_dir is not None:
        cache_scope = os.path.abspath(out_dir)  # 显式目录属于调用方，不能与其他目录复用。
    elif web_root:
        cache_scope = "web-user-cache"  # Web 输出目录由运行时注入，键只需表达隔离域。
    else:
        cache_scope = {"mode": st.output_mode, "custom_root": st.custom_output_root}
    return st, paths, resolver, web_root, cache_scope


def _try_cached_pivot(cache_key, web_root, out_dir, st, log, progress):
    """读取缓存并在 Web 场景物化文件；缓存异常统一返回未命中。"""
    try:
        cached = incremental_cache.get(cache_key)  # 缓存索引损坏不能阻断本次完整计算。
        if not cached:
            return None
        if web_root:
            out_dir = _paths.resolve_output_dir("pivot", **st.output_kwargs())  # 复制到当前任务目录。
            cached = _materialize_web_cache(cached, out_dir)
        log("[缓存] 输入文件和处理参数未变化，已复用现有透视结果。")
        if progress:
            progress(100)  # 缓存命中无需再模拟分析阶段进度。
        return cached
    except (OSError, ValueError, TypeError) as error:
        log("[缓存] 无法读取缓存，已回退完整处理：%s" % error)
        return None


def _build_pivot_result(paths, choices, out_dir, resolver, log, progress):
    """执行未命中缓存时的分析、应用选择和输出写盘阶段。"""
    fill_counts: dict[str, int] = {}  # 记录主数据补空数量，供日志和可信度诊断使用。
    prog = common_core.Progress(progress, stages=[("analyze", 55), ("apply", 45)])
    fname = "%s透视结果.xlsx" % _beijing_date()  # 同日输出通过 unique_path 自动避免覆盖。
    out_path = common_core.unique_path(os.path.join(out_dir, fname))
    for path in paths:
        warn_if_uncached(path, log, what="最终采购数量")  # 公式未刷新会导致数量漏算，需提前提示。
    log("① 分析 %d 个文件..." % len(paths))
    prog.stage("analyze")
    plan = analyze_workbooks(paths, on_file=prog.tick, resolver=resolver, fill_counts=fill_counts)
    material_catalog.log_fill_summary(log, "销售透视", fill_counts)
    if choices is None:
        choices = _default_choices(plan)  # 未进入人工复核时使用分析阶段生成的默认方案。
    log("② 应用选择、聚合并写出...")
    prog.stage("apply")
    result = apply_plan(plan, choices, out_path, log=log)
    result.setdefault("out_dir", out_dir)  # 统一返回目录，供桌面和 Web 投影使用。
    prog.done()
    log("   分组 %d 项，合计 %s；可信度【%s】%d/100"
        % (result.get("groups", 0), _fmt_num(result.get("total", 0)),
           result.get("level", "?"), result.get("score", 0)))
    log("已保存：%s" % out_path)
    return result


def _save_pivot_cache(cache_key, result, log):
    """保存透视结果索引；缓存写入失败不影响已经生成的业务文件。"""
    if not cache_key:
        return
    artifacts = [path for path in (result.get("out"), result.get("report")) if path]
    try:
        incremental_cache.put(cache_key, "pivot", _cacheable_result(result), artifacts)
    except (OSError, ValueError, TypeError) as error:
        log("[缓存] 结果索引保存失败，不影响本次输出：%s" % error)


# 统一运行入口供 Tauri 与 Web 桥接调用，包含缓存、进度、主数据补空和正式两阶段执行。
def run(in_paths, choices=None, out_dir=None, log=None, progress=None):
    """执行销售表透视并返回输出、可信度和结构化复核结果。

    输入可为单路径或路径列表。增量缓存键包含文件内容、人工选择、输出作用域、主数据
    签名和算法版本；Web 命中缓存后仍会复制产物到当前用户任务目录。缓存故障只回退完整
    处理，不影响业务。未提供人工选择时使用默认选择，输出目录由统一路径系统解析。
    """
    log = log or (lambda *a, **k: None)  # 业务核心不依赖 UI，缺省时使用空日志回调。
    st, in_paths, resolver, web_root, cache_scope = _prepare_run(in_paths, out_dir)
    cache_key = ""
    if st.get("enable_incremental_cache", True):
        try:
            cache_key = incremental_cache.make_key(
                "pivot", in_paths,
                {"choices": choices, "output": cache_scope,
                 "catalog": resolver.signature},
                engine_version="pivot-v3")
            cached = _try_cached_pivot(cache_key, web_root, out_dir, st, log, progress)
            if cached is not None:
                return cached
        except (OSError, ValueError, TypeError) as error:
            log("[缓存] 无法读取缓存，已回退完整处理：%s" % error)
    if out_dir is None:
        out_dir = _paths.resolve_output_dir("pivot", **st.output_kwargs())  # 统一目录策略。
    result = _build_pivot_result(in_paths, choices, out_dir, resolver, log, progress)
    _save_pivot_cache(cache_key, result, log)
    return result


def analyze(in_paths, log=None, progress=None):
    """仅第一阶段：分析并返回决策计划（供界面做人工复核）。

    ``log`` 与 ``progress`` 只报告状态，不改变分析结果。该入口读取全部源文件并返回
    人工复核计划，不创建输出文件。
    """
    if isinstance(in_paths, str):
        in_paths = [in_paths]  # 兼容直接传单个路径字符串的调用方，避免 len/遍历按字符计。
    if log:
        log("正在分析 %d 个文件…" % len(in_paths))
    on_file = None
    if progress:
        def on_file(done, total):
            """把按文件完成数转换为整数百分比。"""
            progress(int(done * 100 / total) if total else 100)
    resolver = material_catalog.CatalogResolver()
    fill_counts: dict[str, int] = {}
    result = analyze_workbooks(
        in_paths, on_file=on_file, resolver=resolver, fill_counts=fill_counts)
    material_catalog.log_fill_summary(log, "销售透视", fill_counts)
    return result


def _beijing_date():
    """返回北京时间的紧凑日期字符串，用于输出文件命名。"""
    return (datetime.datetime.now(datetime.timezone.utc) +
            datetime.timedelta(hours=8)).strftime("%Y%m%d")
