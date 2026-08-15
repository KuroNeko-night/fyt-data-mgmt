# -*- coding: utf-8 -*-
"""我司考勤明细与劳务公司月度工时的识别、填表和对账。

处理先聚合我司“数据来源”中的每人每日实际工时，再填入待对总表；随后识别不同格式的
劳务对账单，对双方名单、总工时和逐日工时进行比较。劳务表中的假、休和空白不参与逐日
比较。输出包括已填写总表、异常汇总和结构化可信度指标。

人工列映射、工作表选择、姓名配对、容差和重复姓名策略通过 ``common_core.Options``
进入同一业务逻辑。预分析只读文件，正式 ``run`` 才会创建输出，源文件不会被覆盖。
"""
import copy
import datetime
import logging
import os
from dataclasses import dataclass

import openpyxl

from . import common_core as cc
from . import reconcile_reporting

# 公共常量/工具统一来自 common_core（保留原内部名作别名，避免改动大量调用点）
TOL = cc.TOL
SKIP_MARKS = cc.SKIP_MARKS
_to_num = cc.to_num
_day_of = cc.day_of
_norm_name = cc.norm_name
_read_sheets = cc.read_sheets

# 报告与可信度实现已迁到独立渲染层；保留原名称兼容既有调用和测试。
COLS = reconcile_reporting.COLS
assess_credibility = reconcile_reporting.assess_credibility
write_summary = reconcile_reporting.write_summary
_write_credibility_sheet = reconcile_reporting._write_credibility_sheet


from .reconcile_sources import (
    LABOR_TOTAL_EXCLUDES, SOURCE_WORK_COLUMN_TIERS, _append_labor_meta,
    _collect_labor_candidates, _combined_header_text, _day_columns,
    _detect_source_header, _find_header_cell, _find_labor_day_layout,
    _find_labor_layout, _find_labor_name_position, _find_labor_total_column,
    _load_source_one, _parse_labor_rows, _source_header_columns, _source_row_record,
    load_labor, load_source,
)
from .reconcile_zong import (
    _apply_zong_role_overrides, _fill_zong_person, _find_zong_day_layout,
    _locate_zong, _scan_zong_role_columns, _source_day_value, _source_month_days,
    _target_source_month, _unmapped_person_days, _zong_day_columns,
    _zong_header_rows, _zong_names, fill_zong,
)
# ---------------------------------------------------------------------------
# 4) 对账比较：总工时 + 逐日；劳务公司"假/休/空白"不参与
# ---------------------------------------------------------------------------
def _cached_cell_value(ws, ws_v, row, column):
    """读取工作表单元格；公式文本优先回退到 ``data_only`` 副本的缓存结果。"""

    value = ws.cell(row, column).value
    if isinstance(value, str) and value.startswith("=") and ws_v is not None:
        return ws_v.cell(row, column).value
    return value


def _resolve_company_name(ws, row, layout, name, comp_map):
    """解析总表中的劳务公司名称，并屏蔽没有缓存结果的公式文本。"""

    company = comp_map.get(name)
    if not company and layout["comp_col"]:
        company = ws.cell(row, layout["comp_col"]).value
    if isinstance(company, str) and company.startswith("="):
        return ""
    return str(company).strip() if company is not None else ""


def _project_zong_rows(ws, layout, comp_map, skip, ws_v):
    """把总表行投影为纯内存结构，避免比较阶段反复访问 Excel 单元格。"""

    projected = {}
    for row in range(layout["data_start"], ws.max_row + 1):
        name = _norm_name(ws.cell(row, layout["name_col"]).value)
        if not name:
            continue
        days = {}
        for day, column in layout["day_cols"].items():
            value = _to_num(_cached_cell_value(ws, ws_v, row, column), skip=skip)
            if value is not None:
                days[day] = value
        total = None
        if layout["work_col"]:
            total = _to_num(
                _cached_cell_value(ws, ws_v, row, layout["work_col"]),
                skip=skip,
            )
        if total is None:
            total = round(sum(days.values()), 2)
        projected[name] = {
            "days": days,
            "total": total,
            "comp": _resolve_company_name(ws, row, layout, name, comp_map),
        }
    return projected


def _roster_anomalies(zong, labor):
    """生成双方名单差集异常，顺序保持为“仅我司、仅劳务公司”。"""

    anomalies = []
    zong_names = set(zong)
    labor_names = set(labor)
    for name in sorted(zong_names - labor_names):
        anomalies.append({
            "姓名": name,
            "所属劳务公司": zong[name]["comp"],
            "异常类型": "仅我司名单有",
            "我司出勤工时": zong[name]["total"],
            "劳务公司工时": "",
            "差异": "",
            "差异明细": "该员工不在任何劳务公司对账单中",
            "来源文件": "",
        })
    for name in sorted(labor_names - zong_names):
        source = labor[name].get("source", "")
        anomalies.append({
            "姓名": name,
            "所属劳务公司": source,
            "异常类型": "仅劳务公司有",
            "我司出勤工时": "",
            "劳务公司工时": labor[name]["total"],
            "差异": "",
            "差异明细": "该员工不在我司总表中",
            "来源文件": source,
        })
    return anomalies


def _daily_difference_details(our_days, labor_days, tolerance):
    """返回逐日工时差异文本；劳务侧没有数值的日期不参与比较。"""

    details = []
    for day in sorted(set(our_days) | set(labor_days)):
        labor_value = labor_days.get(day)
        if labor_value is None:
            continue
        our_value = our_days.get(day, 0.0)
        if abs(our_value - labor_value) > tolerance:
            details.append(
                "%d日:我司%s/劳务%s" % (day, _fmt(our_value), _fmt(labor_value))
            )
    return details


def _matched_person_anomalies(name, our_data, labor_data, tolerance):
    """比较一名双方共有人员的总工时与逐日工时，返回零到两条异常。"""

    anomalies = []
    our_total = our_data["total"] or 0.0
    labor_total = labor_data["total"] or 0.0
    source = labor_data.get("source", "")
    common = {
        "姓名": name,
        "所属劳务公司": our_data["comp"],
        "我司出勤工时": round(our_total, 2),
        "劳务公司工时": round(labor_total, 2),
        "差异": round(our_total - labor_total, 2),
        "来源文件": source,
    }
    if abs(our_total - labor_total) > tolerance:
        anomalies.append({**common, "异常类型": "总工时不一致", "差异明细": ""})

    day_details = _daily_difference_details(
        our_data["days"], labor_data["days"], tolerance,
    )
    if day_details:
        anomalies.append({
            **common,
            "异常类型": "逐日工时不一致",
            "差异明细": "；".join(day_details),
        })
    return anomalies


def reconcile(ws, lay, labor, comp_map=None, log=None, tol=None, skip=None, ws_v=None):
    """
    比较已填写的我司总表与合并后的劳务公司数据，返回结构化异常列表。

    ``labor`` 的结构为 ``{姓名: {days: {日号: 工时}, total: 合计, source: 文件名}}``。
    名单差异、总工时差异和逐日差异分别生成记录，便于汇总表按异常类型筛选。
    ``tol`` 控制浮点和表格小数造成的允许误差；``skip`` 交给数值解析器过滤
    “假”“休”等非出勤标记。

    ``ws`` 必须是可写工作簿，以保留公式、样式和最终输出；``ws_v`` 是同一原文件的
    ``data_only`` 副本，仅在 ``ws`` 单元格是公式文本时提供上次由 Excel 缓存的结果。
    若缓存不存在，后续会按逐日数值求和，而不会把公式字符串误当作工时。
    """
    def _lg(m):
        """统一转发对账阶段日志，允许核心逻辑在桌面端和 Web 端复用。"""
        if log:
            log(m)

    tolerance = TOL if tol is None else tol
    zong = _project_zong_rows(ws, lay, comp_map or {}, skip, ws_v)
    anomalies = _roster_anomalies(zong, labor)
    for name in sorted(set(zong) & set(labor)):
        anomalies.extend(_matched_person_anomalies(
            name, zong[name], labor[name], tolerance,
        ))
    _lg("  对账完成：共 %d 条异常" % len(anomalies))
    return anomalies


def _fmt(x):
    """把对账明细中的数值格式化为整数或最多两位小数，减少无意义的小数尾数。"""
    if x is None:
        return "-"
    if float(x).is_integer():
        return str(int(x))
    return str(round(x, 2))


# ---------------------------------------------------------------------------
# 5) 可信度评估与异常工作簿渲染
# ---------------------------------------------------------------------------
# 实现位于 reconcile_reporting.py；本模块顶部保留公开名称兼容旧调用。
# ---------------------------------------------------------------------------
# 人工确认：只读预分析(不写文件),供复核对话框展示识别结果与姓名匹配
# ---------------------------------------------------------------------------
def analyze(target_path, source_paths, labor_paths, opts=None):
    """只读分析三类输入文件，返回人工复核所需的结构计划，不创建任何输出文件。

    plan = {
      "target": {file, sheet, sheets:[可选工作表], name_col, comp_col, work_col,
                 check_col, day_cols, header/ data_start, names:[总表姓名]},
      "sources": [{file, sheet, people}],           # 各数据来源识别概况
      "labor":   [{file, sheet, people, names:[]}],  # 各对账单识别概况
      "labor_names": [...],                          # 对账单合并后的全部姓名
      "only_labor": [...],   # 仅对账单有(待配对到我司)
      "only_zong":  [...],   # 仅我司总表有(可作为配对目标)
    }

    此阶段与正式 ``run`` 共用结构识别和加载函数，保证复核界面展示的工作表、列和姓名
    与最终执行口径一致。所有工作簿都以只读或 ``data_only`` 方式打开并在 ``finally``
    中关闭；人工确认只产生选择数据，不允许绕过正式执行阶段直接修改原文件。
    """
    opts = opts or cc.DEFAULTS
    if isinstance(source_paths, str):
        # 统一成列表，避免单个路径被后续循环按字符逐个处理。
        source_paths = [source_paths]

    # 待对表优先使用人工指定页签，其次寻找约定的“总表”，最后才使用首个工作表。
    want_zong = opts.resolve_sheet(target_path)
    wb = openpyxl.load_workbook(target_path, read_only=True, data_only=True)
    try:
        sheetnames = list(wb.sheetnames)  # 一并返回全部页签，供复核界面允许用户改选。
        if want_zong and want_zong in sheetnames:
            ws = wb[want_zong]; used_sheet = want_zong
        elif "总表" in sheetnames:
            ws = wb["总表"]; used_sheet = "总表"
        else:
            ws = wb.worksheets[0]; used_sheet = ws.title
        lay = _locate_zong(ws, opts=opts, path=target_path)  # 与正式填表完全共用识别规则。
        zong_names = sorted(_zong_names(ws, lay))
    finally:
        wb.close()
    target_info = {
        "file": os.path.basename(target_path), "sheet": used_sheet,
        "sheets": sheetnames,
        "name_col": lay["name_col"], "comp_col": lay["comp_col"],
        "work_col": lay["work_col"], "check_col": lay["check_col"],
        "day_cols": sorted(lay["day_cols"].keys()),
        "data_start": lay["data_start"], "names": zong_names,
    }

    # 工时来源在预分析阶段只展示识别人数，不参与我司与劳务姓名的人工配对。
    sources_info = []
    for p in source_paths:
        one, _ = load_source([p], log=None, opts=opts)
        sources_info.append({"file": os.path.basename(p), "people": len(one)})

    # 每份劳务表分别保留解析概况，同时合并姓名集合，用于计算双方独有名单。
    labor_info = []
    labor_names = set()
    for p in labor_paths:
        meta = []
        one = load_labor(p, log=None, meta=meta, opts=opts)
        m = meta[0] if meta else {}
        labor_names |= set(one.keys())  # 集合只用于预览差集；正式冲突策略仍在 run 中执行。
        labor_info.append({"file": os.path.basename(p),
                           "sheet": m.get("sheet"), "people": len(one),
                           "names": sorted(one.keys())})

    zset = set(zong_names)
    return {
        "target": target_info,
        "sources": sources_info,
        "labor": labor_info,
        "labor_names": sorted(labor_names),
        "only_labor": sorted(labor_names - zset),
        "only_zong": sorted(zset - labor_names),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
RUN_STAGES = [
    ("read_src", 18),
    ("fill", 27),
    ("read_labor", 18),
    ("compare", 27),
    ("assess", 3),
    ("summary", 7),
]


class _RunReporter:
    """统一管理阶段进度、实时日志和写入可信度报告的完整日志。"""

    def __init__(self, log, progress):
        """保存回调与进度对象，并初始化供可信度页使用的运行日志缓冲。"""
        self._callback = log
        self._progress = cc.Progress(progress, stages=RUN_STAGES)
        self.lines = []

    def log(self, message):
        """记录字符串化日志，并在调用端提供回调时同步转发。"""

        self.lines.append(str(message))
        if self._callback:
            self._callback(message)

    def stage(self, name):
        """进入指定处理阶段并更新总体进度。"""

        self._progress.stage(name)

    def done(self):
        """标记全部处理阶段完成。"""

        self._progress.done()

    def text(self):
        """返回可写入 Excel 可信度页的完整运行日志。"""

        return "\n".join(self.lines)


@dataclass
class _RunContext:
    """保存一次对账任务的只读配置，避免阶段函数携带大量平行参数。"""

    target_path: str
    source_paths: list
    labor_paths: list
    out_dir: str
    timestamp: str
    opts: object
    aliases: dict
    reporter: _RunReporter


@dataclass
class _SourceStage:
    """数据来源阶段的聚合结果。"""

    data: dict
    days_seen: set


@dataclass
class _TargetStage:
    """待对总表阶段的工作簿、布局、缓存值和已填写输出。"""

    workbook: object
    worksheet: object
    values_workbook: object
    values_worksheet: object
    stats: dict
    company_map: dict
    filled_path: str

    def close(self):
        """尽最大努力释放两个工作簿，不让清理异常覆盖真正的业务异常。"""

        _safe_close_workbook(self.workbook)
        _safe_close_workbook(self.values_workbook)


@dataclass
class _LaborStage:
    """劳务文件合并结果及可信度诊断信息。"""

    data: dict
    meta: list
    duplicate_count: int


def _path_list(paths):
    """把单个路径与路径序列统一为新列表，避免后续误遍历字符串字符。"""

    return [paths] if isinstance(paths, str) else list(paths)


def _apply_review_choices(opts, target_path, choices, log):
    """把人工确认转换为本次任务专用配置，并返回姓名别名映射。

    返回 ``(opts, aliases)``：传入 ``choices`` 时深拷贝配置再写入，确保复核选择只
    影响当前任务；未提供选择时直接返回原配置对象。``aliases`` 为
    ``{劳务姓名: 我司姓名}`` 字典，供后续内存索引改写。
    """

    aliases = {}
    if not choices:
        return opts, aliases

    aliases = dict(choices.get("aliases") or {})
    target_sheet = choices.get("target_sheet")
    target_roles = choices.get("target_roles") or {}
    if target_sheet or target_roles:
        opts = copy.deepcopy(opts)  # 复核结果只对当前任务生效，绝不能污染共享默认配置。
        filename = os.path.basename(target_path)
        file_mapping = dict(opts.columns.get(filename) or {})
        if target_sheet:
            file_mapping["sheet"] = target_sheet
        if target_roles:
            roles = dict(file_mapping.get("roles") or {})
            for role, column in target_roles.items():
                if column:
                    # 复核界面使用 Excel 的 1 基列号，Options 内部统一保存为 0 基列号。
                    roles[role] = int(column) - 1
            file_mapping["roles"] = roles
        opts.columns[filename] = file_mapping
        log(
            "采用人工确认的待对表结构："
            + ("工作表=%s " % target_sheet if target_sheet else "")
            + ("列映射 %d 项" % len(target_roles) if target_roles else "")
        )
    if aliases:
        log("采用人工姓名配对 %d 组(比对时视为同一人)" % len(aliases))
    return opts, aliases


def _resolve_run_output_dir(target_path, out_dir):
    """解析并创建本次任务输出目录，保留旧版源文件旁输出的兼容回退。"""

    if out_dir is None:
        return _unified_out_dir("reconcile", src=target_path) or cc.make_out_dir(target_path)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _build_run_context(target_path, source_paths, labor_paths, out_dir, opts, choices,
                       reporter):
    """规范化一次运行的路径、选项、人工确认和输出位置。

    统一字符串/列表形式的输入路径，应用人工复核选择，解析并创建输出目录，返回
    后续各阶段共享的 ``_RunContext``。所有副作用（建目录、写日志）集中在本步。
    """

    options = opts or cc.DEFAULTS
    options, aliases = _apply_review_choices(options, target_path, choices, reporter.log)
    output_dir = _resolve_run_output_dir(target_path, out_dir)
    context = _RunContext(
        target_path=target_path,
        source_paths=_path_list(source_paths),
        labor_paths=_path_list(labor_paths),
        out_dir=output_dir,
        timestamp=cc.timestamp(),
        opts=options,
        aliases=aliases,
        reporter=reporter,
    )
    reporter.log("采用选项：" + options.summary())
    reporter.log("输出文件夹：%s" % output_dir)
    return context


def _read_source_stage(context):
    """读取并聚合我司工时来源，返回人员工时和覆盖日期集合。"""

    context.reporter.stage("read_src")
    context.reporter.log("① 读取数据来源 ...")
    for path in context.source_paths:
        # 读取公式结果前先警告无缓存，避免 data_only 副本把公式显示为空值。
        cc.warn_if_uncached(path, context.reporter.log, what="工时")
    data, days_seen = load_source(
        context.source_paths,
        log=context.reporter.log,
        opts=context.opts,
    )
    context.reporter.log("   共 %d 人、覆盖 %d 天" % (len(data), len(days_seen)))
    return _SourceStage(data=data, days_seen=days_seen)


def _select_target_sheet(workbook, wanted_sheet):
    """按人工/配置页签、“总表”、首个页签的顺序选择待对工作表。"""

    if wanted_sheet:
        if wanted_sheet not in workbook.sheetnames:
            raise ValueError("待对表中找不到工作表 '%s'" % wanted_sheet)
        return workbook[wanted_sheet]
    return workbook["总表"] if "总表" in workbook.sheetnames else workbook.worksheets[0]


def _safe_close_workbook(workbook):
    """尽最大努力关闭工作簿；该清理动作不能覆盖主流程异常。"""

    if workbook is None:
        return
    try:
        workbook.close()
    except Exception:
        pass


def _extract_company_map(values_worksheet, layout):
    """从 ``data_only`` 总表中提取姓名对应的劳务公司公式缓存值。"""

    company_map = {}
    for row in range(layout["data_start"], values_worksheet.max_row + 1):
        name = _norm_name(values_worksheet.cell(row, layout["name_col"]).value)
        if not name:
            continue
        value = (
            values_worksheet.cell(row, layout["comp_col"]).value
            if layout["comp_col"]
            else None
        )
        # 公式没有缓存结果时跳过，避免把公式文本当成劳务公司名称写入比较结果。
        if value is not None and not (isinstance(value, str) and value.startswith("=")):
            company_map[name] = str(value).strip()
    return company_map


def _load_target_value_projection(context, wanted_sheet, layout):
    """加载总表公式缓存副本；失败时记录提示并返回空的增强信息。"""

    values_workbook = None
    try:
        values_workbook = cc.load_data_only(context.target_path)
        values_worksheet = _select_target_sheet(values_workbook, wanted_sheet)
        company_map = _extract_company_map(values_worksheet, layout)
        return values_workbook, values_worksheet, company_map
    except Exception as exc:
        _safe_close_workbook(values_workbook)
        context.reporter.log(
            "   ⚠ 读取总表缓存值失败(所属劳务公司/公式列将退回原始值)：%s" % exc
        )
        return None, None, {}


def _prepare_target_stage(context, source):
    """填写待对总表、保存已填写副本，并保留比较阶段需要的工作簿句柄。"""

    context.reporter.stage("fill")
    context.reporter.log("② 填写待对表·总表 ...")
    wanted_sheet = context.opts.resolve_sheet(context.target_path)
    workbook = openpyxl.load_workbook(context.target_path)
    values_workbook = None
    try:
        worksheet = _select_target_sheet(workbook, wanted_sheet)
        stats = fill_zong(
            worksheet,
            source.data,
            log=context.reporter.log,
            opts=context.opts,
            path=context.target_path,
        )
        values_workbook, values_worksheet, company_map = _load_target_value_projection(
            context, wanted_sheet, stats["layout"],
        )
        base = os.path.splitext(os.path.basename(context.target_path))[0]
        filled_path = cc.out_path(
            context.out_dir,
            base,
            "_已填写",
            ".xlsx",
            ts=context.timestamp,
        )
        # 先保存“已填写”副本再继续比较：即使后续对账失败，填表成果也已落盘。
        workbook.save(filled_path)
        context.reporter.log("   已保存：%s" % os.path.basename(filled_path))
        return _TargetStage(
            workbook=workbook,
            worksheet=worksheet,
            values_workbook=values_workbook,
            values_worksheet=values_worksheet,
            stats=stats,
            company_map=company_map,
            filled_path=filled_path,
        )
    except Exception:
        # 失败路径必须释放工作簿，避免 Windows 下输入/输出文件保持锁定并阻断重试。
        _safe_close_workbook(values_workbook)
        _safe_close_workbook(workbook)
        raise


def _merge_labor_file(target, incoming, source_name, conflict, log):
    """把一个劳务文件并入人员索引，返回本文件触发的重复姓名数量。

    直接修改 ``target`` 并在每人记录上写入 ``source`` 字段。重复姓名按 ``conflict``
    策略处理：``first`` 保留先读取者，``warn`` 仅提示不覆盖，其余值按后者覆盖。
    """

    duplicates = 0
    for name, info in incoming.items():
        info["source"] = source_name
        if name in target:
            duplicates += 1
            if conflict == "first":
                log("   ⚠ 姓名重复：%s 已存在，按【先者优先】保留先读取的" % name)
                continue
            if conflict == "warn":
                log("   ⚠ 姓名重复：%s 出现在多个劳务文件，按【不覆盖仅提示】保留先者" % name)
                continue
            log("   ⚠ 姓名重复：%s 同时出现在多个劳务公司文件，后者覆盖" % name)
        target[name] = info
    return duplicates


def _apply_name_aliases(labor, aliases, log):
    """在内存索引中应用人工姓名配对，拒绝覆盖已存在的真实人员。"""

    applied = 0
    for labor_name, our_name in aliases.items():
        labor_name = _norm_name(labor_name)
        our_name = _norm_name(our_name)
        if not labor_name or not our_name or labor_name == our_name:
            continue
        if labor_name in labor and our_name not in labor:
            labor[our_name] = labor.pop(labor_name)
            applied += 1
            log("   ↔ 姓名配对：劳务「%s」= 我司「%s」" % (labor_name, our_name))
    if applied:
        log("   已应用 %d 组姓名配对" % applied)


def _read_labor_stage(context):
    """读取全部劳务文件，按冲突策略合并姓名并应用人工配对。"""

    context.reporter.stage("read_labor")
    context.reporter.log("③ 读取待对数据(劳务公司) ...")
    labor = {}
    meta = []
    duplicate_count = 0
    for path in context.labor_paths:
        cc.warn_if_uncached(path, context.reporter.log, what="工时")
        incoming = load_labor(
            path,
            log=context.reporter.log,
            meta=meta,
            opts=context.opts,
        )
        duplicate_count += _merge_labor_file(
            labor,
            incoming,
            os.path.basename(path),
            context.opts.conflict,
            context.reporter.log,
        )
    context.reporter.log("   劳务公司合计 %d 人" % len(labor))
    _apply_name_aliases(labor, context.aliases, context.reporter.log)
    return _LaborStage(data=labor, meta=meta, duplicate_count=duplicate_count)


def _compare_target_stage(context, target, labor):
    """执行双方工时比较，并返回异常列表和本次总表姓名集合。"""

    context.reporter.stage("compare")
    context.reporter.log("④ 对账比较 ...")
    anomalies = reconcile(
        target.worksheet,
        target.stats["layout"],
        labor.data,
        comp_map=target.company_map,
        log=context.reporter.log,
        tol=context.opts.tolerance,
        skip=context.opts.skip_set(),
        ws_v=target.values_worksheet,
    )
    names = _zong_names(target.worksheet, target.stats["layout"])
    return anomalies, names


def _build_run_metrics(source, target, labor, zong_names, anomalies):
    """根据各阶段结构化结果构造可信度评估指标。"""

    labor_names = set(labor.data)
    matched_names = zong_names & labor_names
    difference_people = {
        anomaly["姓名"]
        for anomaly in anomalies
        if anomaly["异常类型"] in ("总工时不一致", "逐日工时不一致")
    }
    return {
        "source_people": len(source.data),
        "source_days": len(source.days_seen),
        "source_unmatched": len(set(source.data) - zong_names),
        "zong_people": len(zong_names),
        "filled_people": target.stats.get("filled_people", 0),
        "labor_meta": labor.meta,
        "labor_duplicate_names": labor.duplicate_count,
        "labor_people": len(labor.data),
        "matched_pairs": len(matched_names),
        "only_us": len(zong_names - labor_names),
        "only_labor": len(labor_names - zong_names),
        "diff_people": len(difference_people),
        "anomaly_count": len(anomalies),
    }


def _assess_run(context, metrics):
    """执行可信度评估，并把需要人工关注的结论写入实时日志。"""

    context.reporter.stage("assess")
    credibility = assess_credibility(metrics)
    context.reporter.log(
        "⑤ 可信度评估：【%s】 %d/100" % (credibility["level"], credibility["score"])
    )
    for check in credibility["checks"]:
        if check["级别"] in ("警告", "严重"):
            context.reporter.log(
                "   [%s] %s：%s" % (check["级别"], check["项目"], check["说明"])
            )
    return credibility


def _write_summary_stage(context, anomalies, credibility):
    """生成含可信度页和运行日志的异常汇总工作簿。"""

    context.reporter.stage("summary")
    context.reporter.log("⑥ 生成异常汇总表（含可信度报告）...")
    summary_path = os.path.join(
        context.out_dir,
        "对账异常汇总_%s.xlsx" % context.timestamp,
    )
    write_summary(
        anomalies,
        summary_path,
        credibility=credibility,
        log_text=context.reporter.text(),
    )
    context.reporter.log("   已保存：%s" % os.path.basename(summary_path))
    context.reporter.done()
    return summary_path


def run(target_path, source_paths, labor_paths, out_dir=None, log=None, opts=None,
        choices=None, progress=None):
    """
    执行“来源工时填表 -> 劳务数据合并 -> 双方对账 -> 可信度评估 -> 报告输出”。

    ``target_path`` 是保留原样式和公式的我司待对表；``source_paths`` 支持单个路径或
    多文件列表；``labor_paths`` 是一组劳务公司对账单。``opts`` 统一承载容差、重复
    姓名冲突策略、排除词和人工列映射。

    ``choices`` 来自 ``analyze`` 后的人工确认，格式为
    ``{"target_sheet": 页签, "target_roles": {角色: 1基列号},
    "aliases": {劳务姓名: 我司姓名}}``。选择只作用于本次运行：函数会深拷贝配置，
    不污染全局设置；姓名别名也仅改写内存中的劳务索引，不修改任何原始表格。

    ``progress`` 接收 0～100 的阶段进度。返回值同时包含两个输出路径、填表统计、
    结构化异常、可信度及其原始指标，供桌面端和 Web 端复用同一结果投影。
    """
    reporter = _RunReporter(log, progress)
    context = _build_run_context(
        target_path,
        source_paths,
        labor_paths,
        out_dir,
        opts,
        choices,
        reporter,
    )
    source = _read_source_stage(context)
    target = _prepare_target_stage(context, source)
    try:
        labor = _read_labor_stage(context)
        anomalies, zong_names = _compare_target_stage(context, target, labor)
    finally:
        # 劳务解析或比较任一阶段失败都必须释放工作簿，避免 Windows 下锁住输入和输出文件。
        target.close()
    metrics = _build_run_metrics(source, target, labor, zong_names, anomalies)
    credibility = _assess_run(context, metrics)
    summary_path = _write_summary_stage(context, anomalies, credibility)
    return {
        "filled_path": target.filled_path,
        "summary_path": summary_path,
        "stats": target.stats,
        "anomalies": anomalies,
        "credibility": credibility,
        "metrics": metrics,
        "parameters": {
            "tolerance": context.opts.tolerance,
            "conflict": context.opts.conflict,
            "skip_extra": sorted(context.opts.skip_extra),
        },
    }


def _unified_out_dir(feature, src=None):
    """
    通过统一路径与设置模块解析业务输出目录，旧环境不可用时返回 ``None``。

    ``src`` 只在“输出到源文件旁”模式下用于确定基准目录。这里保留宽容回退是为了兼容
    早期脚本直接复制单个核心文件运行的场景；正式桌面端和 Web 端均应成功走统一路径。
    本函数不自行创建第二套目录规则，调用方只会在返回 ``None`` 时使用公共兼容助手。
    """
    try:
        from . import paths as _paths
        from . import settings as _settings
        st = _settings.get_settings()
        kw = st.output_kwargs()
        if src and not kw.get("src_path"):
            # 显式配置的 src_path 优先，避免覆盖调用环境已经选定的源文件基准。
            kw["src_path"] = src
        return _paths.resolve_output_dir(feature, **kw)
    except Exception as exc:
        # 兼容入口不能阻断对账主流程；正式环境中的路径问题会由后续输出创建操作暴露，
        # 这里记日志避免静默掩盖真实配置或权限错误。
        logging.getLogger(__name__).warning("统一输出目录不可用：%s", exc)
        return None
