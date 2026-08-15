# -*- coding: utf-8 -*-
"""我司待对总表的布局识别与工时填表。

本模块从 ``reconcile_core.py`` 拆出，负责定位总表姓名/劳务公司/逐日/合计/对账时间列，
并把按姓名聚合的每日工时投影回总表。模块只读取和填写传入的工作表，不创建输出文件，
也不做劳务公司对账比较；比较和报告仍由 ``reconcile_core`` 与 ``reconcile_reporting`` 负责。
"""
import datetime

from . import common_core as cc

_day_of = cc.day_of
_norm_name = cc.norm_name

def _zong_header_rows(header):
    """返回待对总表需要扫描的 1 基表头行。"""

    return [header] if header else range(1, 4)


def _scan_zong_role_columns(ws, rows):
    """扫描总表表头，识别姓名、劳务公司、出勤工时和对账时间列。

    ``rows`` 是 1 基表头候选行；返回同结构的 1 基列号字典，未识别的可选列保持
    ``None``。“姓名”要求整格精确匹配，避免“姓名备注”等列抢先生效。
    """

    columns = {"name": None, "comp": None, "work": None, "check": None}
    for row in rows:
        if row < 1 or row > ws.max_row:
            continue
        for column in range(1, ws.max_column + 1):
            value = ws.cell(row, column).value
            if value is None:
                continue
            text = str(value)
            if columns["name"] is None and text.strip() == "姓名":
                columns["name"] = column
            if columns["comp"] is None and "劳务公司" in text:
                columns["comp"] = column
            if columns["work"] is None and "出勤工时" in text:
                columns["work"] = column
            if columns["check"] is None and "对账时间" in text:
                columns["check"] = column
    return columns


def _apply_zong_role_overrides(columns, roles):
    """把 Options 的零基人工列映射覆盖到 openpyxl 的 1 基列号。"""

    resolved = dict(columns)
    for role in ("name", "comp", "work", "check"):
        if role in roles:
            resolved[role] = roles[role] + 1
    return resolved


def _zong_day_columns(ws, row, work_col):
    """提取一个候选表头行中的日期列，并排除合计列右侧的数字表头。"""

    columns = {}
    for column in range(1, ws.max_column + 1):
        day = _day_of(ws.cell(row, column).value)
        if day is not None and (work_col is None or column < work_col):
            columns[day] = column
    return columns


def _find_zong_day_layout(ws, rows, work_col):
    """选择日期列数量最多的总表表头行，数量相同时保留更靠前的行。"""

    best_row = None
    best_columns = {}
    for row in rows:
        if row < 1 or row > ws.max_row:
            continue
        columns = _zong_day_columns(ws, row, work_col)
        if len(columns) > len(best_columns):
            best_row, best_columns = row, columns
    return best_row, best_columns


def _locate_zong(ws, opts=None, path=""):
    """
    定位我司待对总表中的姓名、劳务公司、逐日工时、合计工时和对账时间列。

    自动识别只扫描工作表前 3 行，这是为了兼容“第 1 行标题、第 2 行表头”一类
    常见模板，同时避免正文中偶然出现“姓名”“出勤工时”等文字时被误认成表头。
    管理员配置的 ``roles``、``header`` 和 ``data_start`` 优先于自动结果；其中角色列
    在配置中使用 0 基下标，而 openpyxl 使用 1 基下标，因此返回前需要加一转换。
    逐日列仍按单元格内容自动识别，以免管理员维护 28～31 个日期列的易错映射。

    返回字典中的 ``day_cols`` 采用 ``{日号: 列号}``，列号均为 openpyxl 的 1 基下标。
    劳务公司、合计和对账时间属于可选列，可以返回 ``None``；姓名列是后续匹配的
    必要主键，缺失时必须明确报错，不能沿用旧实现猜测为固定列。
    """
    opts = opts or cc.DEFAULTS
    roles = opts.resolve_roles(path)
    header = opts.resolve_header(path)
    ds_override = opts.resolve_data_start(path)
    scan_rows = _zong_header_rows(header)
    columns = _scan_zong_role_columns(ws, scan_rows)
    columns = _apply_zong_role_overrides(columns, roles)
    day_row, day_cols = _find_zong_day_layout(
        ws,
        _zong_header_rows(header),
        columns["work"],
    )
    # 数据从日期表头下一行开始；完全找不到日期行时按常见的“第 2 行表头”兼容推定第 3 行。
    data_start = ds_override if ds_override else ((day_row or 2) + 1)
    # 姓名是双方对齐的唯一键，错误猜列会生成看似成功但实际错配的报表，因此宁可中止。
    if columns["name"] is None:
        raise ValueError("总表未能识别到『姓名』列，请检查表头")
    return {
        # 可选列保持 None，让下游显式降级；不能用固定第 3 列冒充劳务公司列。
        "name_col": columns["name"], "comp_col": columns["comp"],
        "day_cols": day_cols, "work_col": columns["work"],
        "check_col": columns["check"], "data_start": data_start,
    }


def _source_month_days(src_data):
    """统计来源数据中每个年月覆盖过的日号集合。"""

    months = {}
    for person in src_data.values():
        for date_key in person:
            if isinstance(date_key, tuple):
                months.setdefault(date_key[:2], set()).add(date_key[2])
    return months


def _target_source_month(month_days):
    """选择覆盖日数最多的月份；并列时保留来源中先出现的月份。"""

    return max(month_days, key=lambda month: len(month_days[month])) if month_days else None


def _source_day_value(person, target_month, day):
    """读取某人的指定日工时，优先完整年月日键并兼容旧版纯日号键。"""

    if target_month is not None:
        full_date = (target_month[0], target_month[1], day)
        if full_date in person:
            return person[full_date]
    return person.get(day)


def _unmapped_person_days(person, target_month, used_days):
    """统计属于目标月份但总表没有对应日期列的来源工时条数。"""

    overflow = 0
    for date_key in person:
        day = date_key[2] if isinstance(date_key, tuple) else date_key
        in_target = (
            not isinstance(date_key, tuple)
            or (target_month is not None and date_key[:2] == target_month)
        )
        if in_target and day not in used_days:
            overflow += 1
    return overflow


def _fill_zong_person(ws, row, layout, person, target_month, checked_at):
    """填写一名人员的逐日工时、合计和对账时间，返回写入格数与溢出天数。"""

    total = 0.0
    filled_cells = 0
    used_days = set()
    for day, column in layout["day_cols"].items():
        value = _source_day_value(person, target_month, day)
        if value is None:
            continue
        ws.cell(row, column).value = value
        total += value
        filled_cells += 1
        used_days.add(day)
    if layout["work_col"]:
        ws.cell(row, layout["work_col"]).value = round(total, 2)
    if layout["check_col"]:
        ws.cell(row, layout["check_col"]).value = checked_at
    return filled_cells, _unmapped_person_days(person, target_month, used_days)


def fill_zong(ws, src_data, log=None, opts=None, path=""):
    """
    把工时来源按姓名和日号写入我司总表，并计算目标月份的出勤工时合计。

    来源键既可能是新版 ``(年, 月, 日)``，也可能是旧版纯日号。本函数先选择覆盖
    日数最多的年月作为总表主月份，再仅把该月数据投射到只有“1～31 日”列的模板。
    这种选择不会把跨月数据悄悄相加；无法落入总表日期列的数据会记录提示。
    """
    def _lg(m):
        """把填表阶段日志转交给调用方；未提供回调时保持静默。"""
        if log:
            log(m)

    lay = _locate_zong(ws, opts=opts, path=path)
    # 无日期列时继续执行会把所有人的合计写成 0，属于危险的“成功结果”，因此直接拒绝。
    if not lay["day_cols"]:
        raise ValueError("总表未能识别到任何『日期』列(日期表头行识别失败)，请检查表头")
    month_days = _source_month_days(src_data)
    # 总表逐日列只有日号、没有年月维度，必须先选定主月份，不能把跨月数据写进同一列。
    target_ym = _target_source_month(month_days)
    if len(month_days) > 1:
        # 总表仅有日号、没有年月维度，跨月内容无法无歧义地写入同一组列，必须告知用户取舍。
        _lg("  注意：数据来源跨 %d 个月份 %s，总表逐日列仅对应主月份 %s，其余月份不并入逐日"
            % (len(month_days), sorted("%d-%02d" % ym for ym in month_days),
               ("%d-%02d" % target_ym) if target_ym else "-"))

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    filled_people = 0
    filled_cells = 0
    unmatched = []
    for r in range(lay["data_start"], ws.max_row + 1):
        nm = _norm_name(ws.cell(r, lay["name_col"]).value)
        if not nm:
            continue
        if nm not in src_data:
            unmatched.append(nm)
            continue
        person = src_data[nm]
        person_cells, overflow = _fill_zong_person(ws, r, lay, person, target_ym, now)
        filled_cells += person_cells
        if overflow:
            _lg("  · 提示：%s 有 %d 天工时无对应日列，未计入合计" % (nm, overflow))
        filled_people += 1
    _lg("  总表已填 %d 人、%d 个日格子；数据来源中有 %d 人未在总表找到"
        % (filled_people, filled_cells, len(set(src_data) - _zong_names(ws, lay))))
    return {"filled_people": filled_people, "filled_cells": filled_cells,
            "unmatched_in_zong": unmatched, "layout": lay}


def _zong_names(ws, lay):
    """收集总表中的规范化姓名集合，供名单交集、缺失人员和填写覆盖率计算使用。"""
    names = set()
    for r in range(lay["data_start"], ws.max_row + 1):
        nm = _norm_name(ws.cell(r, lay["name_col"]).value)
        if nm:
            names.add(nm)
    return names


