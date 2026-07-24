# -*- coding: utf-8 -*-
"""
对账核心逻辑
============
流程：
1. 从"数据来源"(姓名/日期/实际工作时间明细)聚合每人每日工时；
2. 按姓名+日期填入"待对表·总表"每日列，出勤工时 = 当月合计；
3. 通用解析"待对数据"(劳务公司提供，格式各异，含 .xls)；
4. 对比：总工时 + 逐日。劳务公司表中的"假/休/空白"不参与对比；
5. 输出：填好的待对表 + 异常汇总表。

兼容 Windows 10/11 + Python 3.13。
"""
import os
import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from . import common_core as cc
from .common_core import Options

# 公共常量/工具统一来自 common_core（保留原内部名作别名，避免改动大量调用点）
TOL = cc.TOL
SKIP_MARKS = cc.SKIP_MARKS
_to_num = cc.to_num
_day_of = cc.day_of
_norm_name = cc.norm_name
_read_sheets = cc.read_sheets


# ---------------------------------------------------------------------------
# 1) 读取"数据来源"：姓名 / 日期 / 实际工作时间  -> {姓名:{日:工时}}
# ---------------------------------------------------------------------------
def _detect_source_header(rows, roles=None, header=None):
    """在一个 sheet 里找 姓名/日期/实际工时 表头。返回 (hdr_idx, col_name, col_date, col_work) 或 None。
    手动列映射(roles)优先；header 限定行；否则前5行自动识别。"""
    if roles and all(k in roles for k in ("name", "date", "work")):
        hdr0 = (header - 1) if header else 0
        return hdr0, roles["name"], roles["date"], roles["work"]
    cand = [header - 1] if header else range(min(5, len(rows)))
    for i in cand:
        if i < 0 or i >= len(rows):
            continue
        row = rows[i]
        joined = "".join(str(x) for x in row if x is not None)
        if "姓名" not in joined or "日期" not in joined:
            continue
        texts = [str(cell).replace("\n", "") if cell is not None else "" for cell in row]
        col_name = col_date = None
        for c, t in enumerate(texts):
            if col_name is None and "姓名" in t:
                col_name = c
            elif col_date is None and "日期" in t:
                col_date = c
        # 工时列分级匹配:先认最明确的"实际工作时间/实际工时",没有再退"工作时长/工时"。
        # 分级避免"加班工时""标准工时"等干扰列在存在真列时被误抢(它们含"工时")。
        col_work = None
        for tier in (("实际工作时间", "实际工时"), ("工作时长", "工作时间"), ("工时",)):
            for c, t in enumerate(texts):
                if c in (col_name, col_date):
                    continue
                if any(k in t for k in tier):
                    col_work = c
                    break
            if col_work is not None:
                break
        if col_name is not None and col_date is not None and col_work is not None:
            return i, col_name, col_date, col_work
    return None


def _load_source_one(path, data, days_seen, log=None, opts=None):
    """读取单个数据来源文件的所有子表，聚合进 data。返回本文件读入的明细条数。
    honor per-file 手动列映射/表头/工作表/数据起始行/自定义假休标记。"""
    def _lg(m):
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
        start = (ds_override - 1) if ds_override else (hdr_idx + 1)
        cnt = 0
        for row in rows[start:]:
            if col_name >= len(row):
                continue
            nm = _norm_name(row[col_name])
            if not nm:
                continue
            # 以完整 (年,月,日) 为 key,避免跨月同号日被相加合并;
            # 只有日号(缺年月)的旧格式退回当月第几天,行为与旧版一致
            key = cc.norm_date(row[col_date]) if col_date < len(row) else None
            if key is None:
                key = _day_of(row[col_date]) if col_date < len(row) else None
            if key is None:
                continue
            work = _to_num(row[col_work], skip=skip) if col_work < len(row) else None
            if work is None:
                continue
            data.setdefault(nm, {})
            data[nm][key] = data[nm].get(key, 0.0) + work
            days_seen.add(key)
            cnt += 1
        file_cnt += cnt
        _lg("  · [读取] %s / %s：%d 条明细" % (fname, sname, cnt))
    return file_cnt


def load_source(paths, log=None, opts=None):
    """
    自动识别表头，聚合每人每日"实际工作时间"。支持单个路径或路径列表（多文件）。
    每个文件的每个子表都会自动判断是否为考勤明细，非明细子表自动跳过。
    返回 (data, days_seen)：data={姓名:{日(int):工时(float)}}，days_seen=出现过的日集合。
    """
    def _lg(m):
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
def _find_labor_layout(rows, roles=None, header=None, data_start=None):
    """
    在一个 sheet 内自动识别布局。返回 dict 或 None：
      name_row  含"姓名"的行下标
      name_col  姓名所在列
      day_row   日期/日号所在行下标
      day_cols  {日(int): 列下标}
      total_col 合计/出勤工时列（可能为 None）
      data_start 数据起始行下标
    手动列映射(roles: name/total)与 header(1-based) 优先。逐日列始终自动识别。
    """
    roles = roles or {}
    name_row = name_col = None
    if header:                       # 手动指定表头行
        hr0 = header - 1
        if 0 <= hr0 < len(rows):
            name_row = hr0
            if "name" in roles:
                name_col = roles["name"]
            else:
                for c, cell in enumerate(rows[hr0]):
                    if cell is not None and "姓名" in str(cell):
                        name_col = c; break
    if name_row is None or name_col is None:
        for i, row in enumerate(rows[:6]):
            for c, cell in enumerate(row):
                if cell is not None and "姓名" in str(cell):
                    name_row, name_col = i, c
                    break
            if name_row is not None:
                break
    if "name" in roles:              # 手动姓名列最终生效
        name_col = roles["name"]
    if name_row is None or name_col is None:
        return None

    # 日期行：在 name_row 及其下一行里找"能映射成 1~31 的连续列最多"的那一行
    best = None
    for dr in (name_row, name_row + 1):
        if dr >= len(rows):
            continue
        day_cols = {}
        for c, cell in enumerate(rows[dr]):
            if c <= name_col:
                continue
            d = _day_of(cell)
            if d is not None:
                day_cols[d] = c
        if best is None or len(day_cols) > len(best[1]):
            best = (dr, day_cols)
    if not best or len(best[1]) < 10:   # 至少要识别到 10 个日列才算有效
        return None
    day_row, day_cols = best

    # 合计列：日期列之后的表头列里，找"工时合计"性质的列。
    # 优先级：含"工时"或"出勤" > 含"合计"/"总计"。并排除 天数/工价/金额/工资/餐补/薪资/扣发/保险 等干扰列。
    max_day_col = max(day_cols.values())
    hdr_rows = [r for r in (name_row, day_row) if r < len(rows)]
    EXCLUDE = ("天数", "工价", "金额", "工资", "餐补", "薪资", "扣发",
               "保险", "补贴", "单价", "小时工", "备注")

    def _header_text(c):
        parts = []
        for hr in hdr_rows:
            if c < len(rows[hr]) and rows[hr][c] is not None:
                parts.append(str(rows[hr][c]))
        return "".join(parts)

    total_col = None
    # 第一遍：优先"工时/出勤"（更精确）
    for c in range(max_day_col + 1, max((len(rows[hr]) for hr in hdr_rows), default=0)):
        t = _header_text(c)
        if not t or any(x in t for x in EXCLUDE):
            continue
        if ("工时" in t) or ("出勤" in t):
            total_col = c
            break
    # 第二遍：退而求其次"合计/总计"
    if total_col is None:
        for c in range(max_day_col + 1, max((len(rows[hr]) for hr in hdr_rows), default=0)):
            t = _header_text(c)
            if not t or any(x in t for x in EXCLUDE):
                continue
            if ("合计" in t) or ("总计" in t):
                total_col = c
                break

    if "total" in roles:                       # 手动指定合计列
        total_col = roles["total"]
    ds = (data_start - 1) if data_start else (max(name_row, day_row) + 1)
    return {
        "name_col": name_col, "day_row": day_row, "day_cols": day_cols,
        "total_col": total_col, "data_start": ds,
    }


def load_labor(path, log=None, meta=None, opts=None):
    """
    返回 {姓名: {"days":{日:工时}, "total":合计或None}}。
    合计优先取表内"合计/出勤工时"列；无该列时用逐日数字求和。
    meta: 可选 list，追加本文件的诊断信息（供可信度评估用）。
    honor per-file 手动列映射(name/total)/表头/数据起始行/指定工作表/自定义假休标记。
    """
    def _lg(m):
        if log:
            log(m)

    opts = opts or cc.DEFAULTS
    fname = os.path.basename(path)
    roles = opts.resolve_roles(path)
    header = opts.resolve_header(path)
    ds_override = opts.resolve_data_start(path)
    want_sheet = opts.resolve_sheet(path)
    skip = opts.skip_set()
    # 先评估所有子表，选"日列数最多"的有效考勤子表（不依赖 sheet 顺序）
    candidates = []
    skipped = []
    for sname, rows in _read_sheets(path):
        if want_sheet and sname != want_sheet:
            continue
        lay = _find_labor_layout(rows, roles=roles, header=header, data_start=ds_override)
        if lay:
            candidates.append((sname, rows, lay))
        else:
            skipped.append(sname)
            _lg("  · [跳过] %s / %s（非考勤明细）" % (fname, sname))
    if not candidates:
        _lg("  ⚠ %s：未识别到考勤子表" % fname)
        if meta is not None:
            meta.append({"file": fname, "sheet": None, "people": 0,
                         "day_cols": 0, "has_total_col": False,
                         "total_sum_mismatch": 0, "skipped": skipped,
                         "n_candidates": 0})
        return {}
    candidates.sort(key=lambda x: len(x[2]["day_cols"]), reverse=True)
    sname, rows, lay = candidates[0]

    result = {}
    nc = lay["name_col"]
    day_cols = lay["day_cols"]
    tc = lay["total_col"]
    mismatch = 0   # 表内合计 与 逐日求和 不一致的人数（合计列疑似识别错误的信号）
    for row in rows[lay["data_start"]:]:
        if nc >= len(row):
            continue
        nm = _norm_name(row[nc])
        if not nm or nm in ("合计", "合计：", "总计", "总出勤工时"):
            continue
        days = {}
        for d, c in day_cols.items():
            if c < len(row):
                v = _to_num(row[c], skip=skip)
                if v is not None:
                    days[d] = v
        stated = None
        if tc is not None and tc < len(row):
            stated = _to_num(row[tc], skip=skip)
        day_sum = round(sum(days.values()), 2) if days else None
        if stated is not None and day_sum is not None and abs(stated - day_sum) > TOL:
            mismatch += 1
        total = stated if stated is not None else day_sum
        if not days and total is None:
            continue
        result[nm] = {"days": days, "total": total}
    tc_note = "有合计列" if tc is not None else "无合计列(按逐日求和)"
    _lg("  · [读取] %s / %s：识别 %d 人，%d 个日列，%s"
        % (fname, sname, len(result), len(day_cols), tc_note))
    if mismatch:
        _lg("      注意：%d 人的表内合计与逐日求和不一致（合计列可能识别有误）" % mismatch)
    if meta is not None:
        meta.append({"file": fname, "sheet": sname, "people": len(result),
                     "day_cols": len(day_cols), "has_total_col": tc is not None,
                     "total_sum_mismatch": mismatch, "skipped": skipped,
                     "n_candidates": len(candidates)})
    return result


# ---------------------------------------------------------------------------
# 3) 填写待对表·总表
# ---------------------------------------------------------------------------
def _locate_zong(ws, opts=None, path=""):
    """
    定位总表结构。返回 dict:
      name_col 姓名列, comp_col 所属劳务公司列, day_cols {日:列}, work_col 出勤工时列,
      check_col 对账时间列, data_start 数据起始行
    手动列映射(roles: name/comp/work/check, 0-based)与 header/data_start 优先；逐日列始终自动。
    """
    opts = opts or cc.DEFAULTS
    roles = opts.resolve_roles(path)
    header = opts.resolve_header(path)
    ds_override = opts.resolve_data_start(path)
    name_col = comp_col = work_col = check_col = None
    day_row = None
    day_cols = {}
    scan = [header] if header else range(1, 4)   # 表头通常在前 3 行
    for r in scan:
        if r < 1 or r > ws.max_row:
            continue
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if v is None:
                continue
            t = str(v)
            if name_col is None and t.strip() == "姓名":
                name_col = c
            if comp_col is None and "劳务公司" in t:
                comp_col = c
            if work_col is None and "出勤工时" in t:
                work_col = c
            if check_col is None and "对账时间" in t:
                check_col = c
    # 手动列映射覆盖（0-based -> 1-based）
    if "name" in roles: name_col = roles["name"] + 1
    if "comp" in roles: comp_col = roles["comp"] + 1
    if "work" in roles: work_col = roles["work"] + 1
    if "check" in roles: check_col = roles["check"] + 1
    # 日期行：含最多可映射日期的行
    for r in (scan if header else range(1, 4)):
        if r < 1 or r > ws.max_row:
            continue
        tmp = {}
        for c in range(1, ws.max_column + 1):
            d = _day_of(ws.cell(r, c).value)
            if d is not None and (work_col is None or c < work_col):
                tmp[d] = c
        if len(tmp) > len(day_cols):
            day_cols = tmp
            day_row = r
    data_start = ds_override if ds_override else ((day_row or 2) + 1)
    # 识别不到"姓名"列时不再静默回退硬编码列(旧代码 name_col or 2),明确报错交上层中止
    if name_col is None:
        raise ValueError("总表未能识别到『姓名』列，请检查表头")
    return {
        # comp_col 允许为 None(旧代码 or 3 会误指第3列),下游已按 None 兜底
        "name_col": name_col, "comp_col": comp_col,
        "day_cols": day_cols, "work_col": work_col,
        "check_col": check_col, "data_start": data_start,
    }


def fill_zong(ws, src_data, log=None, opts=None, path=""):
    """把数据来源逐日填入总表，出勤工时=当月合计。返回统计信息。"""
    def _lg(m):
        if log:
            log(m)

    lay = _locate_zong(ws, opts=opts, path=path)
    # 日期表头识别失败(day_cols 为空)属结构识别失败,不能静默给每人写 work=0
    if not lay["day_cols"]:
        raise ValueError("总表未能识别到任何『日期』列(日期表头行识别失败)，请检查表头")
    # src_data 的 key 现为 (年,月,日) 元组或纯日号:先定出总表对应的目标年月
    month_days = {}   # (年,月) -> 该月出现的日数,用于选主月份并提示跨月
    for person in src_data.values():
        for k in person:
            if isinstance(k, tuple):
                month_days.setdefault(k[:2], set()).add(k[2])
    target_ym = max(month_days, key=lambda ym: len(month_days[ym])) if month_days else None
    if len(month_days) > 1:   # 数据跨多个月份:总表按天号列只能落一个月,提示避免误解
        _lg("  注意：数据来源跨 %d 个月份 %s，总表逐日列仅对应主月份 %s，其余月份不并入逐日"
            % (len(month_days), sorted("%d-%02d" % ym for ym in month_days),
               ("%d-%02d" % target_ym) if target_ym else "-"))

    def _day_val(person, d):
        """取某人第 d 天工时:优先目标年月的 (y,m,d),回退纯日号 key。"""
        if target_ym is not None and (target_ym[0], target_ym[1], d) in person:
            return person[(target_ym[0], target_ym[1], d)]
        if d in person:      # 兼容只有日号(无年月)的旧数据
            return person[d]
        return None

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
        total = 0.0
        used_days = set()
        for d, col in lay["day_cols"].items():
            v = _day_val(person, d)
            if v is not None:
                ws.cell(r, col).value = v
                total += v
                filled_cells += 1
                used_days.add(d)
        # 源数据有、总表无对应日列的工时会被漏出合计:统计溢出天数并提示
        overflow = 0
        for k in person:
            kd = k[2] if isinstance(k, tuple) else k
            in_target = (not isinstance(k, tuple)) or (target_ym is not None and k[:2] == target_ym)
            if in_target and kd not in used_days:
                overflow += 1
        if overflow:
            _lg("  · 提示：%s 有 %d 天工时无对应日列，未计入合计" % (nm, overflow))
        if lay["work_col"]:
            ws.cell(r, lay["work_col"]).value = round(total, 2)
        if lay["check_col"]:
            ws.cell(r, lay["check_col"]).value = now
        filled_people += 1
    _lg("  总表已填 %d 人、%d 个日格子；数据来源中有 %d 人未在总表找到"
        % (filled_people, filled_cells, len(set(src_data) - _zong_names(ws, lay))))
    return {"filled_people": filled_people, "filled_cells": filled_cells,
            "unmatched_in_zong": unmatched, "layout": lay}


def _zong_names(ws, lay):
    names = set()
    for r in range(lay["data_start"], ws.max_row + 1):
        nm = _norm_name(ws.cell(r, lay["name_col"]).value)
        if nm:
            names.add(nm)
    return names


# ---------------------------------------------------------------------------
# 4) 对账比较：总工时 + 逐日；劳务公司"假/休/空白"不参与
# ---------------------------------------------------------------------------
def reconcile(ws, lay, labor, comp_map=None, log=None, tol=None, skip=None, ws_v=None):
    """
    读取(已填好的)总表每人每日工时，与 labor(合并后的劳务公司数据)对比。
    返回异常记录列表 anomalies。
    labor: {姓名: {"days":{日:h}, "total":h, "source":文件名}}
    comp_map: {姓名: 所属劳务公司}（用于解析公式列的缓存值）
    tol: 工时比对容差；None 用默认 TOL。
    ws_v: 可选,同一总表的 data_only 副本;当可写簿里读到公式串时取其缓存值,
          避免公式列(如出勤工时)被当 None 而丢数。
    """
    def _lg(m):
        if log:
            log(m)

    def _cell_val(r, c):
        """读单元格值;可写簿读到公式串(以 = 开头)时回退 data_only 副本的缓存值。"""
        v = ws.cell(r, c).value
        if isinstance(v, str) and v.startswith("=") and ws_v is not None:
            return ws_v.cell(r, c).value
        return v

    if tol is None:
        tol = TOL
    comp_map = comp_map or {}
    anomalies = []
    zong = {}   # 姓名 -> {"days":{}, "total":, "comp":}
    for r in range(lay["data_start"], ws.max_row + 1):
        nm = _norm_name(ws.cell(r, lay["name_col"]).value)
        if not nm:
            continue
        comp = comp_map.get(nm)
        if not comp:
            raw = ws.cell(r, lay["comp_col"]).value if lay["comp_col"] else ""
            # 忽略公式串，公式无缓存时留空
            comp = "" if (isinstance(raw, str) and raw.startswith("=")) else raw
        comp = str(comp).strip() if comp is not None else ""
        days = {}
        for d, col in lay["day_cols"].items():
            v = _to_num(_cell_val(r, col), skip=skip)
            if v is not None:
                days[d] = v
        total = _to_num(_cell_val(r, lay["work_col"]), skip=skip) if lay["work_col"] else None
        if total is None:
            total = round(sum(days.values()), 2)
        zong[nm] = {"days": days, "total": total, "comp": comp}

    labor_names = set(labor.keys())
    zong_names = set(zong.keys())

    # 4a. 仅我司有 / 仅劳务公司有
    for nm in sorted(zong_names - labor_names):
        anomalies.append({
            "姓名": nm, "所属劳务公司": zong[nm]["comp"], "异常类型": "仅我司名单有",
            "我司出勤工时": zong[nm]["total"], "劳务公司工时": "",
            "差异": "", "差异明细": "该员工不在任何劳务公司对账单中", "来源文件": "",
        })
    for nm in sorted(labor_names - zong_names):
        anomalies.append({
            "姓名": nm, "所属劳务公司": labor[nm].get("source", ""), "异常类型": "仅劳务公司有",
            "我司出勤工时": "", "劳务公司工时": labor[nm]["total"],
            "差异": "", "差异明细": "该员工不在我司总表中", "来源文件": labor[nm].get("source", ""),
        })

    # 4b. 双方都有：比总工时 + 逐日
    for nm in sorted(zong_names & labor_names):
        z = zong[nm]
        l = labor[nm]
        zt = z["total"] or 0.0
        lt = l["total"] or 0.0
        # 总工时
        if abs(zt - lt) > tol:
            anomalies.append({
                "姓名": nm, "所属劳务公司": z["comp"], "异常类型": "总工时不一致",
                "我司出勤工时": round(zt, 2), "劳务公司工时": round(lt, 2),
                "差异": round(zt - lt, 2), "差异明细": "",
                "来源文件": l.get("source", ""),
            })
        # 逐日：仅对劳务公司有数字的日子比较（假/休/空白已在 _to_num 过滤）
        diff_days = []
        all_days = set(z["days"]) | set(l["days"])
        for d in sorted(all_days):
            lv = l["days"].get(d)
            if lv is None:      # 劳务公司当天为假/休/空 -> 不对比
                continue
            zv = z["days"].get(d, 0.0)
            if abs(zv - lv) > tol:
                diff_days.append("%d日:我司%s/劳务%s" % (d, _fmt(zv), _fmt(lv)))
        if diff_days:
            anomalies.append({
                "姓名": nm, "所属劳务公司": z["comp"], "异常类型": "逐日工时不一致",
                "我司出勤工时": round(zt, 2), "劳务公司工时": round(lt, 2),
                "差异": round(zt - lt, 2),
                "差异明细": "；".join(diff_days), "来源文件": l.get("source", ""),
            })
    _lg("  对账完成：共 %d 条异常" % len(anomalies))
    return anomalies


def _fmt(x):
    if x is None:
        return "-"
    if float(x).is_integer():
        return str(int(x))
    return str(round(x, 2))


# ---------------------------------------------------------------------------
# 5) 写出异常汇总表
# ---------------------------------------------------------------------------
COLS = ["姓名", "所属劳务公司", "异常类型", "我司出勤工时",
        "劳务公司工时", "差异", "差异明细", "来源文件"]


# ---------------------------------------------------------------------------
# 可信度评估：依据处理过程的结构化指标，判断本次生成结果是否可信
# ---------------------------------------------------------------------------
def assess_credibility(metrics):
    """
    输入 metrics（run() 收集的过程指标），输出可信度报告 dict：
      {"score": int, "level": "高/中/低", "checks": [ {项目,结论,级别,说明}, ... ] }
    级别：正常 / 提示 / 警告 / 严重。分数从 100 起扣。
    评估目的：帮助人工快速判断——数值异常是"真实差异"还是"程序/数据错误"。
    """
    checks = []
    score = 100

    def add(item, level, detail, deduct=0):
        nonlocal score
        checks.append({"项目": item, "级别": level, "说明": detail})
        score -= deduct

    # 1) 数据来源覆盖天数（考勤月通常 20+ 个有出勤的日）
    days = metrics.get("source_days", 0)
    if days == 0:
        add("数据来源覆盖天数", "严重", "未读到任何日期，数据来源可能格式异常或选错文件", 40)
    elif days < 10:
        add("数据来源覆盖天数", "警告", "仅覆盖 %d 天，明显偏少，可能只读到部分明细" % days, 20)
    elif days < 18:
        add("数据来源覆盖天数", "提示", "覆盖 %d 天，略少，请确认是否为完整月度数据" % days, 5)
    else:
        add("数据来源覆盖天数", "正常", "覆盖 %d 天，符合月度考勤预期" % days)

    # 2) 数据来源与总表名单的匹配率
    sp = metrics.get("source_people", 0)
    unmatched = metrics.get("source_unmatched", 0)
    if sp > 0:
        rate = unmatched / sp
        if rate > 0.5:
            add("数据来源→名单匹配", "警告",
                "%d/%d 人未在待对表名单中(%.0f%%)，疑似姓名不一致或选错文件"
                % (unmatched, sp, rate * 100), 20)
        elif rate > 0.2:
            add("数据来源→名单匹配", "提示",
                "%d/%d 人未在名单中(%.0f%%)，请抽查这些人的姓名写法"
                % (unmatched, sp, rate * 100), 8)
        else:
            add("数据来源→名单匹配", "正常",
                "%d/%d 人未匹配(%.0f%%)，在合理范围" % (unmatched, sp, rate * 100))
    else:
        add("数据来源→名单匹配", "严重", "数据来源未读到任何人", 30)

    # 3) 总表填写率
    zp = metrics.get("zong_people", 0)
    fp = metrics.get("filled_people", 0)
    if zp > 0:
        frate = fp / zp
        if frate < 0.2:
            add("总表填写覆盖", "警告",
                "仅 %d/%d 人被填入工时(%.0f%%)，数据来源与名单可能不匹配"
                % (fp, zp, frate * 100), 15)
        elif frate < 0.6:
            add("总表填写覆盖", "提示",
                "%d/%d 人被填入(%.0f%%)，其余无数据来源，请确认是否漏传文件"
                % (fp, zp, frate * 100), 6)
        else:
            add("总表填写覆盖", "正常", "%d/%d 人被填入工时(%.0f%%)" % (fp, zp, frate * 100))

    # 4) 各劳务文件的日列识别 + 合计列
    labor_meta = metrics.get("labor_meta", [])
    for m in labor_meta:
        f = m["file"]
        if m.get("n_candidates", 0) == 0 or m["sheet"] is None:
            add("劳务文件解析·%s" % f, "严重", "未识别到考勤子表，该文件未参与对账", 25)
            continue
        if m["day_cols"] < 28:
            add("劳务文件解析·%s" % f, "警告",
                "仅识别到 %d 个日列(通常应≥28)，可能漏读日期列" % m["day_cols"], 12)
        elif m["day_cols"] > 31:
            add("劳务文件解析·%s" % f, "提示",
                "识别到 %d 个日列(多于31)，请确认是否误纳非日期列" % m["day_cols"], 5)
        else:
            add("劳务文件解析·%s" % f, "正常",
                "识别 %d 人、%d 个日列，%s"
                % (m["people"], m["day_cols"],
                   "有合计列" if m["has_total_col"] else "无合计列(逐日求和)"))
        # 4b) 合计列 vs 逐日求和 一致性
        if m["has_total_col"] and m["people"] > 0:
            mr = m["total_sum_mismatch"] / m["people"]
            if mr > 0.3:
                add("合计列校验·%s" % f, "警告",
                    "%d/%d 人表内合计与逐日求和不符(%.0f%%)，合计列可能识别错误"
                    % (m["total_sum_mismatch"], m["people"], mr * 100), 12)
            elif m["total_sum_mismatch"] > 0:
                add("合计列校验·%s" % f, "提示",
                    "%d 人表内合计与逐日求和有差异，属对方原表口径差异或加班另计"
                    % m["total_sum_mismatch"], 3)

    # 5) 姓名重复（多文件合并时后者覆盖）
    dup = metrics.get("labor_duplicate_names", 0)
    if dup > 0:
        add("劳务文件姓名重复", "提示",
            "%d 个姓名在多个劳务文件中重复，已按后读取的为准，请确认无同名不同人" % dup, 5)

    # 6) 异常占比——系统性异常往往意味着程序/对齐错误，而非真实差异
    matched = metrics.get("matched_pairs", 0)
    diff_people = metrics.get("diff_people", 0)
    if matched > 0:
        drate = diff_people / matched
        if drate > 0.9:
            add("异常占比", "警告",
                "%d/%d 双方都有的人中 %.0f%% 存在工时差异，比例过高，"
                "更可能是填写/对齐系统性错误而非真实差异，请重点核对"
                % (diff_people, matched, drate * 100), 20)
        elif drate > 0.5:
            add("异常占比", "提示",
                "%.0f%% 的人存在工时差异，偏高，建议抽样核对若干人的原始明细"
                % (drate * 100), 8)
        else:
            add("异常占比", "正常",
                "%d/%d 人存在差异(%.0f%%)，属正常对账范围" % (diff_people, matched, drate * 100))
    else:
        add("异常占比", "警告", "待对表与劳务公司名单无任何交集，无法逐人对账，请检查是否选错文件", 25)

    # 7) 仅单方有 的规模
    only_us = metrics.get("only_us", 0)
    only_labor = metrics.get("only_labor", 0)
    total_names = matched + only_us + only_labor
    if total_names > 0 and (only_us + only_labor) / total_names > 0.5:
        add("名单交集", "提示",
            "仅一方有的人数较多(我司独有%d、劳务独有%d)，可能是姓名写法不一致或名单范围不同"
            % (only_us, only_labor), 6)

    score = max(0, min(100, score))
    level = "高" if score >= 85 else ("中" if score >= 60 else "低")
    return {"score": score, "level": level, "checks": checks}


def write_summary(anomalies, out_path, credibility=None, log_text=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "对账异常汇总"

    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="305496")
    head_font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=10)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    # 标题
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLS))
    tcell = ws.cell(1, 1, "对账异常汇总表  （生成时间：%s）"
                    % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    tcell.font = Font(name="微软雅黑", bold=True, size=13)
    tcell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # 表头
    for c, name in enumerate(COLS, 1):
        cell = ws.cell(2, c, name)
        cell.fill = head_fill
        cell.font = head_font
        cell.alignment = center
        cell.border = border

    # 内容
    type_fill = {
        "总工时不一致": PatternFill("solid", fgColor="FCE4D6"),
        "逐日工时不一致": PatternFill("solid", fgColor="FFF2CC"),
        "仅我司名单有": PatternFill("solid", fgColor="E2EFDA"),
        "仅劳务公司有": PatternFill("solid", fgColor="DDEBF7"),
    }
    r = 3
    for a in anomalies:
        for c, key in enumerate(COLS, 1):
            cell = ws.cell(r, c, a.get(key, ""))
            cell.border = border
            cell.alignment = left if key in ("差异明细", "来源文件") else center
            cell.font = Font(name="微软雅黑", size=10)
        fill = type_fill.get(a.get("异常类型"))
        if fill:
            ws.cell(r, 3).fill = fill
        r += 1

    if not anomalies:
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(COLS))
        ws.cell(3, 1, "未发现异常，全部一致 ✔").alignment = Alignment(
            horizontal="center", vertical="center")

    # 列宽
    widths = [10, 14, 14, 12, 12, 10, 46, 26]
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w
    ws.freeze_panes = "A3"

    if credibility is not None:
        _write_credibility_sheet(wb, credibility, log_text)

    wb.save(out_path)
    return out_path


def _write_credibility_sheet(wb, cred, log_text=None):
    """在工作簿最前面插入"可信度报告"sheet。"""
    ws = wb.create_sheet("可信度报告", 0)
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    level = cred["level"]
    score = cred["score"]
    level_color = {"高": "C6EFCE", "中": "FFEB9C", "低": "FFC7CE"}.get(level, "FFFFFF")
    level_font = {"高": "006100", "中": "9C6500", "低": "9C0006"}.get(level, "000000")

    ws.merge_cells("A1:C1")
    t = ws.cell(1, 1, "对账结果可信度报告")
    t.font = Font(name="微软雅黑", bold=True, size=14)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:C2")
    verdict = {"高": "结果可信度高，可放心使用，仅需按异常清单核对个别差异。",
               "中": "结果可信度中等，建议先看下方“提示/警告”项，再核对异常清单。",
               "低": "结果可信度低，很可能存在程序识别或文件选择问题，请先排查下方警告项，勿直接采用！"}
    v = ws.cell(2, 1, "综合结论：可信度【%s】  评分 %d/100 —— %s"
                % (level, score, verdict.get(level, "")))
    v.font = Font(name="微软雅黑", bold=True, size=11, color=level_font)
    v.fill = PatternFill("solid", fgColor=level_color)
    v.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 40

    heads = ["检查项目", "结论级别", "说明"]
    for c, h in enumerate(heads, 1):
        cell = ws.cell(4, c, h)
        cell.fill = PatternFill("solid", fgColor="305496")
        cell.font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=10)
        cell.alignment = center
        cell.border = border

    lvl_fill = {"正常": "E2EFDA", "提示": "FFF2CC", "警告": "FCE4D6", "严重": "FFC7CE"}
    r = 5
    for ck in cred["checks"]:
        ws.cell(r, 1, ck["项目"]).border = border
        lc = ws.cell(r, 2, ck["级别"])
        lc.border = border
        lc.alignment = center
        lc.fill = PatternFill("solid", fgColor=lvl_fill.get(ck["级别"], "FFFFFF"))
        lc.font = Font(name="微软雅黑", size=10, bold=(ck["级别"] in ("警告", "严重")))
        dc = ws.cell(r, 3, ck["说明"])
        dc.border = border
        dc.alignment = left
        ws.cell(r, 1).alignment = left
        ws.cell(r, 1).font = Font(name="微软雅黑", size=10)
        dc.font = Font(name="微软雅黑", size=10)
        r += 1

    # 运行日志（便于人工追溯每一步）
    r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    lh = ws.cell(r, 1, "运行日志（供追溯）")
    lh.font = Font(name="微软雅黑", bold=True, size=10)
    r += 1
    if log_text:
        for line in log_text.split("\n"):
            ws.cell(r, 1, line).font = Font(name="Consolas", size=9)
            r += 1

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 70
    ws.freeze_panes = "A5"
    return ws


# ---------------------------------------------------------------------------
# 人工确认：只读预分析(不写文件),供复核对话框展示识别结果与姓名匹配
# ---------------------------------------------------------------------------
def analyze(target_path, source_paths, labor_paths, opts=None):
    """只读地跑一遍识别,返回供人工确认的 plan(不落盘、不改动任何文件)。

    plan = {
      "target": {file, sheet, sheets:[可选工作表], name_col, comp_col, work_col,
                 check_col, day_cols, header/ data_start, names:[总表姓名]},
      "sources": [{file, sheet, people}],           # 各数据来源识别概况
      "labor":   [{file, sheet, people, names:[]}],  # 各对账单识别概况
      "labor_names": [...],                          # 对账单合并后的全部姓名
      "only_labor": [...],   # 仅对账单有(待配对到我司)
      "only_zong":  [...],   # 仅我司总表有(可作为配对目标)
    }
    """
    opts = opts or cc.DEFAULTS
    if isinstance(source_paths, str):
        source_paths = [source_paths]

    # —— 待对表结构 ——
    want_zong = opts.resolve_sheet(target_path)
    wb = openpyxl.load_workbook(target_path, read_only=True, data_only=True)
    try:
        sheetnames = list(wb.sheetnames)
        if want_zong and want_zong in sheetnames:
            ws = wb[want_zong]; used_sheet = want_zong
        elif "总表" in sheetnames:
            ws = wb["总表"]; used_sheet = "总表"
        else:
            ws = wb.worksheets[0]; used_sheet = ws.title
        lay = _locate_zong(ws, opts=opts, path=target_path)
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

    # —— 数据来源概况(仅统计,不参与匹配) ——
    sources_info = []
    for p in source_paths:
        one, _ = load_source([p], log=None, opts=opts)
        sources_info.append({"file": os.path.basename(p), "people": len(one)})

    # —— 对账单结构 + 姓名 ——
    labor_info = []
    labor_names = set()
    for p in labor_paths:
        meta = []
        one = load_labor(p, log=None, meta=meta, opts=opts)
        m = meta[0] if meta else {}
        labor_names |= set(one.keys())
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
def run(target_path, source_paths, labor_paths, out_dir=None, log=None, opts=None,
        choices=None, progress=None):
    """
    target_path  : 待对表(我司)
    source_paths : 数据来源，单个路径或路径列表（多文件、多子表自动识别）
    labor_paths  : 待对数据(劳务公司) 文件列表
    opts         : common_core.Options（高级选项：容差、重复策略、指定工作表等）
    choices      : 人工确认结果 dict 或 None。
                   {"target_sheet":名, "target_roles":{"name/comp/work":列1based},
                    "aliases":{劳务姓名: 我司姓名}}。None=全自动,行为与旧版一致。
    progress     : 可选进度回调(0~100)；Worker 按 run 是否有此形参自动注入。
                   进度按 ①–⑥ 六个阶段的相对耗时加权推进。
    返回 dict: {filled_path, summary_path, stats, anomalies, credibility}
    """
    # 六阶段权重(相对耗时经验值):读来源/填总表/读劳务/对账 为大头,评估/汇总较轻。
    _prog = cc.Progress(progress, stages=[
        ("read_src", 18), ("fill", 27), ("read_labor", 18),
        ("compare", 27), ("assess", 3), ("summary", 7)])
    opts = opts or cc.DEFAULTS
    log_lines = []

    def _lg(m):
        log_lines.append(str(m))
        if log:
            log(m)

    # —— 应用人工确认:待对表结构覆盖写入 opts.columns(核心已认这套 per-file 映射) ——
    aliases = {}
    if choices:
        aliases = dict(choices.get("aliases") or {})
        tsheet = choices.get("target_sheet")
        troles = choices.get("target_roles") or {}
        if tsheet or troles:
            import copy
            opts = copy.deepcopy(opts)          # 不改动调用方传入的 opts
            base = os.path.basename(target_path)
            fm = dict(opts.columns.get(base) or {})
            if tsheet:
                fm["sheet"] = tsheet
            if troles:
                roles0 = dict(fm.get("roles") or {})
                for k, col1 in troles.items():   # 对话框给 1-based,存 0-based
                    if col1:
                        roles0[k] = int(col1) - 1
                fm["roles"] = roles0
            opts.columns[base] = fm
            _lg("采用人工确认的待对表结构：" +
                ("工作表=%s " % tsheet if tsheet else "") +
                ("列映射 %d 项" % len(troles) if troles else ""))
        if aliases:
            _lg("采用人工姓名配对 %d 组(比对时视为同一人)" % len(aliases))

    if out_dir is None:
        out_dir = _unified_out_dir("reconcile", src=target_path) or cc.make_out_dir(target_path)
    else:
        os.makedirs(out_dir, exist_ok=True)
    ts = cc.timestamp()          # 填好的待对表 与 汇总表 共用一个时间戳
    _lg("采用选项：" + opts.summary())
    _lg("输出文件夹：%s" % out_dir)

    _prog.stage("read_src")
    _lg("① 读取数据来源 ...")
    # 读工时来源表前先探测"公式未刷新(读出 None)",命中则醒目提示,避免静默漏算
    for _sp in ([source_paths] if isinstance(source_paths, str) else source_paths):
        cc.warn_if_uncached(_sp, _lg, what="工时")
    src_data, days_seen = load_source(source_paths, log=_lg, opts=opts)
    _lg("   共 %d 人、覆盖 %d 天" % (len(src_data), len(days_seen)))

    _prog.stage("fill")
    _lg("② 填写待对表·总表 ...")
    want_zong = opts.resolve_sheet(target_path)   # per-file/全局 手动指定总表所在工作表
    wb = openpyxl.load_workbook(target_path)
    if want_zong:
        if want_zong not in wb.sheetnames:
            wb.close()
            raise ValueError("待对表中找不到工作表 '%s'" % want_zong)
        ws = wb[want_zong]
    else:
        ws = wb["总表"] if "总表" in wb.sheetnames else wb.worksheets[0]
    stats = fill_zong(ws, src_data, log=_lg, opts=opts, path=target_path)

    # data_only 副本:既用于解析"所属劳务公司"缓存值,也作对账时公式列的取值回退。
    # 保持打开到对账结束,最后统一 close(见 finally)。
    comp_map = {}
    wb_v = None
    ws_v = None
    try:
        wb_v = cc.load_data_only(target_path)   # 跳过内嵌透视缓存解析,只取单元格值
        if want_zong:
            ws_v = wb_v[want_zong]
        else:
            ws_v = wb_v["总表"] if "总表" in wb_v.sheetnames else wb_v.worksheets[0]
        lay = stats["layout"]
        for r in range(lay["data_start"], ws_v.max_row + 1):
            nm = _norm_name(ws_v.cell(r, lay["name_col"]).value)
            if not nm:
                continue
            v = ws_v.cell(r, lay["comp_col"]).value if lay["comp_col"] else None
            if v is not None and not (isinstance(v, str) and v.startswith("=")):
                comp_map[nm] = str(v).strip()
    except Exception as e:
        # 不再静默吞掉:告知失败原因,对账仍可继续(comp/公式列退回可写簿的原始值)
        _lg("   ⚠ 读取总表缓存值失败(所属劳务公司/公式列将退回原始值)：%s" % e)

    base = os.path.splitext(os.path.basename(target_path))[0]
    filled_path = cc.out_path(out_dir, base, "_已填写", ".xlsx", ts=ts)
    wb.save(filled_path)
    _lg("   已保存：%s" % os.path.basename(filled_path))

    _prog.stage("read_labor")
    _lg("③ 读取待对数据(劳务公司) ...")
    labor = {}
    labor_meta = []
    dup_count = 0
    for p in labor_paths:
        cc.warn_if_uncached(p, _lg, what="工时")   # 劳务对账单工时列公式未刷新→静默丢数,先提示
        one = load_labor(p, log=_lg, meta=labor_meta, opts=opts)
        src_name = os.path.basename(p)
        for nm, info in one.items():
            info["source"] = src_name
            if nm in labor:
                dup_count += 1
                if opts.conflict == "first":
                    _lg("   ⚠ 姓名重复：%s 已存在，按【先者优先】保留先读取的" % nm)
                    continue
                elif opts.conflict == "warn":
                    _lg("   ⚠ 姓名重复：%s 出现在多个劳务文件，按【不覆盖仅提示】保留先者" % nm)
                    continue
                _lg("   ⚠ 姓名重复：%s 同时出现在多个劳务公司文件，后者覆盖" % nm)
            labor[nm] = info
    _lg("   劳务公司合计 %d 人" % len(labor))

    # —— 人工姓名配对:把劳务姓名改写成我司姓名,使两侧对上(仅本次运行) ——
    if aliases:
        applied = 0
        for lab_nm, our_nm in aliases.items():
            lab_nm = _norm_name(lab_nm); our_nm = _norm_name(our_nm)
            if not lab_nm or not our_nm or lab_nm == our_nm:
                continue
            if lab_nm in labor and our_nm not in labor:
                labor[our_nm] = labor.pop(lab_nm)
                applied += 1
                _lg("   ↔ 姓名配对：劳务「%s」= 我司「%s」" % (lab_nm, our_nm))
        if applied:
            _lg("   已应用 %d 组姓名配对" % applied)

    _prog.stage("compare")
    _lg("④ 对账比较 ...")
    try:
        # 传入 data_only 副本 ws_v:公式列(出勤工时等)在可写簿读到公式串时取缓存值
        anomalies = reconcile(ws, stats["layout"], labor, comp_map=comp_map,
                              log=_lg, tol=opts.tolerance, skip=opts.skip_set(),
                              ws_v=ws_v)
        # ---- 汇总过程指标，评估可信度 ----
        zong_names = _zong_names(ws, stats["layout"])
    finally:
        # 成功/异常路径都关闭两个工作簿,避免句柄泄漏
        try:
            wb.close()
        except Exception:
            pass
        if wb_v is not None:
            try:
                wb_v.close()
            except Exception:
                pass
    labor_names = set(labor.keys())
    matched_pairs = len(zong_names & labor_names)
    only_us = len(zong_names - labor_names)
    only_labor = len(labor_names - zong_names)
    diff_people = len(set(
        a["姓名"] for a in anomalies
        if a["异常类型"] in ("总工时不一致", "逐日工时不一致")))
    metrics = {
        "source_people": len(src_data),
        "source_days": len(days_seen),
        "source_unmatched": len(set(src_data) - zong_names),
        "zong_people": len(zong_names),
        "filled_people": stats.get("filled_people", 0),
        "labor_meta": labor_meta,
        "labor_duplicate_names": dup_count,
        "labor_people": len(labor),
        "matched_pairs": matched_pairs,
        "only_us": only_us,
        "only_labor": only_labor,
        "diff_people": diff_people,
        "anomaly_count": len(anomalies),
    }
    _prog.stage("assess")
    credibility = assess_credibility(metrics)
    _lg("⑤ 可信度评估：【%s】 %d/100" % (credibility["level"], credibility["score"]))
    for ck in credibility["checks"]:
        if ck["级别"] in ("警告", "严重"):
            _lg("   [%s] %s：%s" % (ck["级别"], ck["项目"], ck["说明"]))

    _prog.stage("summary")
    _lg("⑥ 生成异常汇总表（含可信度报告）...")
    summary_path = os.path.join(out_dir, "对账异常汇总_%s.xlsx" % ts)
    write_summary(anomalies, summary_path, credibility=credibility,
                  log_text="\n".join(log_lines))
    _lg("   已保存：%s" % os.path.basename(summary_path))
    _prog.done()

    return {"filled_path": filled_path, "summary_path": summary_path,
            "stats": stats, "anomalies": anomalies,
            "credibility": credibility, "metrics": metrics}


def _unified_out_dir(feature, src=None):
    """通过统一 paths/settings 解析输出目录；导入失败则回退(返回 None)。
    src: beside 模式下用于定位源文件目录。"""
    try:
        from . import paths as _paths
        from . import settings as _settings
        st = _settings.get_settings()
        kw = st.output_kwargs()
        if src and not kw.get("src_path"):
            kw["src_path"] = src
        return _paths.resolve_output_dir(feature, **kw)
    except Exception:
        return None
