# -*- coding: utf-8 -*-
"""我司工时来源与劳务公司对账单的识别层。

本模块从 ``reconcile_core.py`` 拆出，负责“数据来源”的姓名/日期/工时列识别与跨文件
聚合，以及劳务对账单的名称、逐日列和合计列自动布局识别。解析结果均为纯数据字典，
不写文件、不填总表、不生成报告；正式对账编排仍由 ``reconcile_core`` 负责。
"""
import os

from . import common_core as cc

# 公共常量/工具统一来自 common_core
TOL = cc.TOL
SKIP_MARKS = cc.SKIP_MARKS
_to_num = cc.to_num
_day_of = cc.day_of
_norm_name = cc.norm_name
_read_sheets = cc.read_sheets

# ---------------------------------------------------------------------------
# 1) 读取"数据来源"：姓名 / 日期 / 实际工作时间  -> {姓名:{日:工时}}
# ---------------------------------------------------------------------------
SOURCE_WORK_COLUMN_TIERS = (
    ("实际工作时间", "实际工时"),
    ("工作时长", "工作时间"),
    ("工时",),
)


def _source_header_columns(row):
    """从一行表头中识别姓名、日期和实际工时三列。

    ``row`` 为工作表的表头单元格序列；工时列按“实际工作时间/实际工时”、
    “工作时长/工作时间”、普通“工时”三级优先级匹配，并跳过已识别为姓名或日期的列。
    识别成功返回 ``(姓名列, 日期列, 工时列)`` 零基元组，否则返回 ``None``。
    """

    texts = [str(cell).replace("\n", "") if cell is not None else "" for cell in row]
    name_col = next((column for column, text in enumerate(texts) if "姓名" in text), None)
    date_col = next((column for column, text in enumerate(texts) if "日期" in text), None)
    if name_col is None or date_col is None:
        return None

    for tier in SOURCE_WORK_COLUMN_TIERS:
        for column, text in enumerate(texts):
            if column in (name_col, date_col):
                continue
            if any(keyword in text for keyword in tier):
                return name_col, date_col, column
    return None


def _detect_source_header(rows, roles=None, header=None):
    """定位我司工时来源表的姓名、日期和实际工时列。

    手动角色映射优先，指定表头时只检查该行，否则扫描前五行。工时列按“实际工时”、
    “工作时长”、普通“工时”三级匹配，防止加班工时或标准工时在明确列存在时抢先命中。
    返回零基表头行与列号，无法形成完整三列时返回 ``None``。
    """
    if roles and all(k in roles for k in ("name", "date", "work")):
        hdr0 = (header - 1) if header else 0
        return hdr0, roles["name"], roles["date"], roles["work"]
    candidates = [header - 1] if header else range(min(5, len(rows)))
    for row_index in candidates:
        if row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        joined = "".join(str(x) for x in row if x is not None)
        if "姓名" not in joined or "日期" not in joined:
            continue
        columns = _source_header_columns(row)
        if columns is not None:
            return row_index, *columns
    return None


def _source_row_record(row, name_col, date_col, work_col, skip):
    """把一行来源明细规范化为 ``(姓名, 日期键, 工时)``，无效行返回 ``None``。

    日期优先规范为完整 ``(年, 月, 日)``，旧表只有日号时才回退为纯日号键；
    ``skip`` 中的假、休等标记会令工时解析失败并丢弃整行，避免非出勤记录进入汇总。
    """

    if name_col >= len(row):
        return None
    name = _norm_name(row[name_col])
    if not name:
        return None
    raw_date = row[date_col] if date_col < len(row) else None
    date_key = cc.norm_date(raw_date)
    if date_key is None:
        date_key = _day_of(raw_date)
    if date_key is None:
        return None
    raw_work = row[work_col] if work_col < len(row) else None
    work = _to_num(raw_work, skip=skip)
    if work is None:
        return None
    return name, date_key, work


def _accumulate_source_sheet(rows, start, columns, data, days_seen, skip):
    """累加一个已识别页签中的有效工时明细，并返回纳入行数。

    直接修改调用方传入的 ``data`` 与 ``days_seen``：同一员工同一天存在多条记录时
    必须累加而不是覆盖，这是后续总表填写和逐日对账的共同事实基础。
    """

    count = 0
    for row in rows[start:]:
        record = _source_row_record(row, *columns, skip)
        if record is None:
            continue
        name, date_key, work = record
        person = data.setdefault(name, {})
        # 同一员工同一天可能有多段打卡或多个来源文件，工时需要累加而不是覆盖。
        person[date_key] = person.get(date_key, 0.0) + work
        days_seen.add(date_key)
        count += 1
    return count


def _load_source_one(path, data, days_seen, log=None, opts=None):
    """读取一个我司工时来源文件并累加到跨文件汇总。

    每个页签独立判断是否为明细页，支持按文件覆盖工作表、表头、列映射、数据起始行和
    假休标记。日期优先保留完整年月日，只有旧格式缺年月时才回退日号，避免跨月同一日
    被错误相加。返回实际纳入的明细条数。
    """
    def _lg(m):
        """仅在调用方提供日志回调时转发单文件识别信息。"""
        if log:
            log(m)

    opts = opts or cc.DEFAULTS
    fname = os.path.basename(path)
    roles = opts.resolve_roles(path)
    header = opts.resolve_header(path)
    ds_override = opts.resolve_data_start(path)
    want_sheet = opts.resolve_sheet(path)
    skip = opts.skip_set()
    file_cnt = 0
    for sname, rows in _read_sheets(path):
        if want_sheet and sname != want_sheet:
            continue
        if not rows:
            _lg("  · [跳过] %s / %s（空表）" % (fname, sname))
            continue
        det = _detect_source_header(rows, roles=roles, header=header)
        if det is None:
            _lg("  · [跳过] %s / %s（无 姓名/日期/实际工时 列，非考勤明细）" % (fname, sname))
            continue
        hdr_idx, col_name, col_date, col_work = det
        # 人工数据起始行优先于“表头下一行”，兼容表头下方还有说明行或合并行的旧模板。
        start = (ds_override - 1) if ds_override else (hdr_idx + 1)
        cnt = _accumulate_source_sheet(
            rows,
            start,
            (col_name, col_date, col_work),
            data,
            days_seen,
            skip,
        )
        file_cnt += cnt
        _lg("  · [读取] %s / %s：%d 条明细" % (fname, sname, cnt))
    return file_cnt


def load_source(paths, log=None, opts=None):
    """
    自动识别表头，聚合每人每日"实际工作时间"。支持单个路径或路径列表（多文件）。
    每个文件的每个子表都会自动判断是否为考勤明细，非明细子表自动跳过。
    返回 ``data`` 与 ``days_seen``。日期键可能是完整 ``(年, 月, 日)`` 元组，也可能是
    兼容旧表的纯日号；多个文件按同一姓名和日期累加工时。
    """
    def _lg(m):
        """按需转发跨文件处理日志。"""
        if log:
            log(m)

    opts = opts or cc.DEFAULTS
    if isinstance(paths, str):
        paths = [paths]
    data = {}
    days_seen = set()
    for p in paths:
        _lg("  文件：%s" % os.path.basename(p))
        _load_source_one(p, data, days_seen, log=log, opts=opts)
    return data, days_seen


# ---------------------------------------------------------------------------
# 2) 通用解析"待对数据"(劳务公司)：格式各异，自动识别
# ---------------------------------------------------------------------------
LABOR_TOTAL_EXCLUDES = (
    "天数", "工价", "金额", "工资", "餐补", "薪资", "扣发",
    "保险", "补贴", "单价", "小时工", "备注",
)


def _find_header_cell(row, keyword):
    """返回首个包含指定关键字的零基列号，找不到时返回 ``None``。"""

    for column, cell in enumerate(row):
        if cell is not None and keyword in str(cell):
            return column
    return None


def _find_labor_name_position(rows, roles, header):
    """确定劳务表姓名表头行和姓名列，并保持人工列映射的最高优先级。"""

    name_row = name_col = None
    if header:
        header_index = header - 1
        if 0 <= header_index < len(rows):
            name_row = header_index
            name_col = roles.get("name")
            if name_col is None:
                name_col = _find_header_cell(rows[header_index], "姓名")

    if name_row is None or name_col is None:
        for row_index, row in enumerate(rows[:6]):
            detected_col = _find_header_cell(row, "姓名")
            if detected_col is not None:
                name_row, name_col = row_index, detected_col
                break

    # 人工指定姓名列最终生效，但仍要求能够定位一个真实表头行，以免把普通明细误认成考勤表。
    if "name" in roles:
        name_col = roles["name"]
    if name_row is None or name_col is None:
        return None
    return name_row, name_col


def _day_columns(row, name_col):
    """从一行中提取姓名列右侧的 ``日号 -> 零基列号`` 映射。"""

    columns = {}
    for column, cell in enumerate(row):
        if column <= name_col:
            continue
        day = _day_of(cell)
        if day is not None:
            columns[day] = column
    return columns


def _find_labor_day_layout(rows, name_row, name_col):
    """在姓名表头行及其下一行中选择日期列最多的布局。"""

    candidates = []
    for row_index in (name_row, name_row + 1):
        if row_index < len(rows):
            candidates.append((row_index, _day_columns(rows[row_index], name_col)))
    if not candidates:
        return None
    # ``max`` 在数量相同时保留先出现的姓名表头行，与原先的稳定选择规则一致。
    best = max(candidates, key=lambda item: len(item[1]))
    return best if len(best[1]) >= 10 else None


def _combined_header_text(rows, header_rows, column):
    """合并同一列在多层表头中的文字，供合计列语义判断使用。"""

    parts = []
    for row_index in header_rows:
        if column < len(rows[row_index]) and rows[row_index][column] is not None:
            parts.append(str(rows[row_index][column]))
    return "".join(parts)


def _find_labor_total_column(rows, name_row, day_row, day_cols):
    """在日期区右侧按“工时/出勤、合计/总计”两级优先级寻找合计列。

    只在日期列最右侧之后查找，避免把姓名、编号等左侧列误判为合计；合并多层表头
    文字后先排除天数、工价、金额等干扰词。找不到明确合计列时返回 ``None``，由
    调用方回退为逐日求和。
    """

    header_rows = [row for row in (name_row, day_row) if row < len(rows)]
    start_column = max(day_cols.values()) + 1
    stop_column = max((len(rows[row]) for row in header_rows), default=0)
    for keywords in (("工时", "出勤"), ("合计", "总计")):
        for column in range(start_column, stop_column):
            text = _combined_header_text(rows, header_rows, column)
            if not text or any(word in text for word in LABOR_TOTAL_EXCLUDES):
                continue
            if any(word in text for word in keywords):
                return column
    return None


def _find_labor_layout(rows, roles=None, header=None, data_start=None):
    """
    在一个 sheet 内自动识别布局。返回 dict 或 None：
      name_row  含"姓名"的行下标
      name_col  姓名所在列
      day_row   日期/日号所在行下标
      day_cols  {日(int): 列下标}
      total_col 合计/出勤工时列（可能为 None）
      data_start 数据起始行下标
    手动姓名和合计列映射、表头行、数据起始行优先；逐日列始终自动识别。日期行在姓名
    表头及下一行中选择可映射日号最多的一行，至少识别十天才认为是考勤表。合计列只在
    日期区右侧寻找，并排除工资、金额、天数等常见干扰列。
    """
    roles = roles or {}
    name_position = _find_labor_name_position(rows, roles, header)
    if name_position is None:
        return None
    name_row, name_col = name_position
    day_layout = _find_labor_day_layout(rows, name_row, name_col)
    if day_layout is None:
        return None
    day_row, day_cols = day_layout
    total_col = roles.get("total")
    if total_col is None:
        total_col = _find_labor_total_column(rows, name_row, day_row, day_cols)
    start_row = (data_start - 1) if data_start else (max(name_row, day_row) + 1)
    return {
        "name_col": name_col, "day_row": day_row, "day_cols": day_cols,
        "total_col": total_col, "data_start": start_row,
    }


def _collect_labor_candidates(path, roles, header, data_start, wanted_sheet, log):
    """读取并评估全部页签，返回 ``(有效候选列表, 被跳过页签名列表)``。

    每个候选形如 ``(页签名, 行数据, 布局)``；被跳过的页签通过 ``log`` 记录原因，
    供可信度诊断和用户核对。未命中 ``wanted_sheet`` 的页签直接忽略，不进入候选。
    """

    filename = os.path.basename(path)
    candidates = []
    skipped = []
    for sheet_name, rows in _read_sheets(path):
        if wanted_sheet and sheet_name != wanted_sheet:
            continue
        layout = _find_labor_layout(rows, roles=roles, header=header, data_start=data_start)
        if layout is not None:
            candidates.append((sheet_name, rows, layout))
            continue
        skipped.append(sheet_name)
        log("  · [跳过] %s / %s（非考勤明细）" % (filename, sheet_name))
    return candidates, skipped


def _parse_labor_rows(rows, layout, skip):
    """按已确认的劳务表布局解析人员逐日工时，并统计合计口径不一致人数。

    逐日单元格中解析为 ``None``（含 ``skip`` 假、休标记）的日期不纳入该人员的
    逐日字典；表内合计列存在时优先采用，缺失时才使用逐日数字求和。返回
    ``({姓名: {"days": 日号->工时, "total": 合计或None}}, 合计不一致人数)``。
    """

    result = {}
    mismatch = 0
    name_col = layout["name_col"]
    day_cols = layout["day_cols"]
    total_col = layout["total_col"]
    for row in rows[layout["data_start"]:]:
        if name_col >= len(row):
            continue
        name = _norm_name(row[name_col])
        if not name or name in ("合计", "合计：", "总计", "总出勤工时"):
            continue
        days = {
            day: value
            for day, column in day_cols.items()
            if column < len(row) and (value := _to_num(row[column], skip=skip)) is not None
        }
        stated_total = (
            _to_num(row[total_col], skip=skip)
            if total_col is not None and total_col < len(row)
            else None
        )
        day_sum = round(sum(days.values()), 2) if days else None
        if stated_total is not None and day_sum is not None and abs(stated_total - day_sum) > TOL:
            mismatch += 1
        total = stated_total if stated_total is not None else day_sum
        if days or total is not None:
            result[name] = {"days": days, "total": total}
    return result, mismatch


def _append_labor_meta(meta, filename, sheet_name, result, layout, mismatch, skipped,
                       candidate_count):
    """把单个劳务文件的解析诊断写入可信度指标列表。"""

    if meta is None:
        return
    meta.append({
        "file": filename,
        "sheet": sheet_name,
        "people": len(result),
        "day_cols": len(layout["day_cols"]) if layout else 0,
        "has_total_col": bool(layout and layout["total_col"] is not None),
        "total_sum_mismatch": mismatch,
        "skipped": skipped,
        "n_candidates": candidate_count,
    })


def load_labor(path, log=None, meta=None, opts=None):
    """
    返回 {姓名: {"days":{日:工时}, "total":合计或None}}。
    合计优先取表内"合计/出勤工时"列；无该列时用逐日数字求和。
    meta: 可选 list，追加本文件的诊断信息（供可信度评估用）。
    支持按文件覆盖姓名、合计列、表头、数据起始行、工作表和假休标记。多个有效页签时
    选择日列最多者，而不是依赖页签顺序。表内合计优先；没有合计时按有效逐日数字求和，
    同时统计表内合计与逐日和不一致人数，作为可信度判断依据。
    """
    def _lg(m):
        """按需转发劳务文件布局识别日志。"""
        if log:
            log(m)

    opts = opts or cc.DEFAULTS
    fname = os.path.basename(path)
    roles = opts.resolve_roles(path)
    header = opts.resolve_header(path)
    ds_override = opts.resolve_data_start(path)
    want_sheet = opts.resolve_sheet(path)
    skip = opts.skip_set()
    candidates, skipped = _collect_labor_candidates(
        path, roles, header, ds_override, want_sheet, _lg,
    )
    if not candidates:
        _lg("  ⚠ %s：未识别到考勤子表" % fname)
        _append_labor_meta(meta, fname, None, {}, None, 0, skipped, 0)
        return {}
    candidates.sort(key=lambda x: len(x[2]["day_cols"]), reverse=True)
    # Python 排序稳定，同日列数平局时保留工作簿中更靠前的页签。
    sname, rows, lay = candidates[0]
    result, mismatch = _parse_labor_rows(rows, lay, skip)
    total_note = "有合计列" if lay["total_col"] is not None else "无合计列(按逐日求和)"
    _lg("  · [读取] %s / %s：识别 %d 人，%d 个日列，%s" % (
        fname, sname, len(result), len(lay["day_cols"]), total_note,
    ))
    if mismatch:
        _lg("      注意：%d 人的表内合计与逐日求和不一致（合计列可能识别有误）" % mismatch)
    _append_labor_meta(meta, fname, sname, result, lay, mismatch, skipped, len(candidates))
    return result


# ---------------------------------------------------------------------------
# 3) 填写待对表·总表
# ---------------------------------------------------------------------------
