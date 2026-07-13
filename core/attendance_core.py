# -*- coding: utf-8 -*-
"""
考勤填表核心逻辑（不依赖GUI，便于测试与复用）。
- 从“每日统计表”读取：姓名、日期、上班1打卡时间、下班1打卡时间（支持 .xlsx/.xlsm/.xls）
- 按 姓名 + 日期 匹配，填入考勤表的：上班时间（系统）、下班时间（系统）
- 实际工作时间 = 下班时间（实际） - 上班时间（实际） - 休息时间
- 加班 = 实际工时 - 标准工时（可在高级选项调整；不足记0）
公共解析/常量/选项/输出路径统一来自 common_core。保留目标文件原有格式。
"""
import os
import openpyxl

from . import common_core as cc
from .common_core import Options, norm_name, norm_date, parse_time, to_hours, parse_rest

# 向后兼容：仍暴露该常量名
STANDARD_WORKDAY_HOURS = cc.STANDARD_WORKDAY_HOURS


# ---------- 读取源表（每日统计表） ----------
def _detect_source_header(rows, opts, path=""):
    """在一个 sheet 里定位 姓名/日期/上班1打卡/下班1打卡 表头。
    返回 (hdr_idx0, cols) 或 None。
    手动列映射(opts.resolve_roles)优先；其次按 header_row 限定行；否则自动识别。"""
    roles = opts.resolve_roles(path)
    header = opts.resolve_header(path)
    if roles and all(k in roles for k in ("name", "date", "on", "off")):
        hdr0 = (header - 1) if header else 0
        return hdr0, {k: roles[k] for k in ("name", "date", "on", "off")}
    cand = [header - 1] if header else range(min(6, len(rows)))
    for i in cand:
        if i < 0 or i >= len(rows):
            continue
        row = rows[i]
        joined = [norm_name(x) for x in row]
        if "姓名" not in joined or not any("上班1打卡" in x for x in joined):
            continue
        cols = {}
        for c, val in enumerate(joined):
            if val == "姓名": cols["name"] = c
            elif val == "日期": cols["date"] = c
            elif "上班1打卡" in val: cols["on"] = c
            elif "下班1打卡" in val: cols["off"] = c
        if all(k in cols for k in ("name", "date", "on", "off")):
            return i, cols
    return None


def load_source(path, opts=None):
    """读取单个每日统计表 -> {(姓名,(y,m,d)):(上班打卡,下班打卡)}。支持多子表，取首个命中表头的子表。"""
    opts = opts or cc.DEFAULTS
    sheets = cc.read_sheets(path)
    want_sheet = opts.resolve_sheet(path)
    if want_sheet:
        sheets = [(n, r) for (n, r) in sheets if n == want_sheet]
        if not sheets:
            raise ValueError("文件 %s 中找不到工作表 '%s'" % (os.path.basename(path), want_sheet))
    ds_override = opts.resolve_data_start(path)
    for sname, rows in sheets:
        det = _detect_source_header(rows, opts, path)
        if det is None:
            continue
        hdr, cols = det
        data = {}
        start = (ds_override - 1) if ds_override else (hdr + 1)
        for r in range(start, len(rows)):
            row = rows[r]
            def g(c):
                return row[c] if c < len(row) else None
            name = norm_name(g(cols["name"]))
            d = norm_date(g(cols["date"]))
            if not name or d is None:
                continue
            on = g(cols["on"]); off = g(cols["off"])
            on_s = "" if on is None else str(on).strip()
            off_s = "" if off is None else str(off).strip()
            data[(name, d)] = (on_s, off_s)
        return data
    raise ValueError("源表 %s 未找到表头（需含 '姓名' 和 '上班1打卡时间'）。" % os.path.basename(path))


def load_source_multi(paths, opts=None, log=None):
    """读取并合并多个每日统计表。重复(姓名+日期)按 opts.conflict 处理。
    返回 (data, stat)：stat={"files","records","conflicts"}"""
    opts = opts or cc.DEFAULTS
    log = log or (lambda *a, **k: None)
    if isinstance(paths, str):
        paths = [paths]
    merged = {}; conflicts = 0
    for p in paths:
        try:
            one = load_source(p, opts)
        except Exception as e:
            log("  · [跳过] %s（读取失败：%s）" % (os.path.basename(p), e)); continue
        log("  · [读取] %s：%d 条打卡记录" % (os.path.basename(p), len(one)))
        for key, (new_on, new_off) in one.items():
            if key not in merged:
                merged[key] = (new_on, new_off); continue
            conflicts += 1
            old_on, old_off = merged[key]
            if opts.conflict == "first":
                pass                                  # 保留先者
            elif opts.conflict == "warn":
                log("    ! 重复且不覆盖：%s %s" % (key[0], "-".join(map(str, key[1]))))
            else:                                     # last：非空才覆盖
                use_on = new_on if (new_on and new_on not in ("-", "—")) else old_on
                use_off = new_off if (new_off and new_off not in ("-", "—")) else old_off
                merged[key] = (use_on, use_off)
    if conflicts:
        cn = {"last": "后者覆盖", "first": "先者优先", "warn": "不覆盖仅提示"}
        log("  注意：%d 条(姓名+日期)重复，按【%s】处理。" % (conflicts, cn.get(opts.conflict)))
    return merged, {"files": len(paths), "records": len(merged), "conflicts": conflicts}


# ---------- 填写目标表（保留原格式，用 openpyxl 写回） ----------
def find_target_columns(ws, opts=None, path=""):
    """在目标表定位所需列，返回 (header_row, cols)。
    手动列映射(opts.resolve_roles)优先；其次 header_row 指定行；否则第1行自动识别。
    cols 内的列号统一为 1-based（openpyxl）；手动映射存的是 0-based，取用时 +1。"""
    opts = opts or cc.DEFAULTS
    hr = opts.resolve_header(path) or 1
    header = {norm_name(ws.cell(hr, c).value).replace("\n", ""): c
              for c in range(1, ws.max_column + 1)}
    def col(*keys):
        for k in keys:
            if k in header:
                return header[k]
        return None
    cols = {
        "name": col("姓名"), "date": col("日期"),
        "sys_on": col("上班时间（系统）"), "act_on": col("上班时间（实际）"),
        "sys_off": col("下班时间（系统）"), "act_off": col("下班时间（实际）"),
        "rest": col("休息时间"), "work": col("实际工作时间"), "ot": col("加班"),
    }
    roles = opts.resolve_roles(path)     # 手动映射覆盖对应角色（0-based -> 1-based）
    for k, c0 in roles.items():
        if k in cols:
            cols[k] = c0 + 1
    return hr, cols


def fill_workbook(target_path, source_data, out_path, opts=None, log=None):
    """把 source_data 填入目标表所有工作表（或指定表），算工时/加班，另存 out_path。返回统计 dict。"""
    opts = opts or cc.DEFAULTS
    log = log or (lambda *a, **k: None)
    wb = openpyxl.load_workbook(target_path)   # 不用 data_only，保留格式
    stats = {"sheets": [], "matched": 0, "filled_time": 0, "computed_work": 0, "unmatched": 0}
    sheets = wb.worksheets
    want_sheet = opts.resolve_sheet(target_path)
    if want_sheet:
        sheets = [w for w in sheets if w.title == want_sheet]
        if not sheets:
            wb.close()
            raise ValueError("目标表中找不到工作表 '%s'" % want_sheet)
    ds_override = opts.resolve_data_start(target_path)
    for ws in sheets:
        hr, cols = find_target_columns(ws, opts, target_path)
        if not cols["name"] or not cols["date"]:
            log("跳过工作表 '%s'（未找到姓名/日期列）" % ws.title); continue
        s_matched = s_filled = s_work = s_unmatched = 0
        start = ds_override if ds_override else (hr + 1)
        for r in range(start, ws.max_row + 1):
            name = norm_name(ws.cell(r, cols["name"]).value)
            d = norm_date(ws.cell(r, cols["date"]).value)
            if not name or d is None:
                continue
            key = (name, d)
            if key in source_data:
                on_s, off_s = source_data[key]; s_matched += 1
                if cols["sys_on"] and on_s and on_s not in ("-", "—"):
                    ws.cell(r, cols["sys_on"]).value = on_s; s_filled += 1
                if cols["sys_off"] and off_s and off_s not in ("-", "—"):
                    ws.cell(r, cols["sys_off"]).value = off_s
            else:
                s_unmatched += 1
            # 实际工作时间 = 下班(实际) - 上班(实际) - 休息
            if cols["work"] and cols["act_on"] and cols["act_off"]:
                a_on = parse_time(ws.cell(r, cols["act_on"]).value)
                a_off = parse_time(ws.cell(r, cols["act_off"]).value)
                if a_on is not None and a_off is not None:
                    rest = parse_rest(ws.cell(r, cols["rest"]).value) if cols["rest"] else 0.0
                    hours = to_hours(a_off) - to_hours(a_on) - rest
                    if hours < 0:                # 下班早于上班：按 cross_day 策略处理
                        if opts.cross_day == "wrap":
                            hours += 24           # 跨夜班
                        elif opts.cross_day == "zero":
                            hours = 0.0
                        else:                     # flag：保留负值并提示，供人工核对
                            log("    ! 负工时：%s 第%d行 实际工时=%.2f（下班早于上班，请核对）"
                                % (ws.title, r, hours))
                    hours = round(hours, 2)
                    ws.cell(r, cols["work"]).value = hours; s_work += 1
                    if opts.overtime and cols["ot"]:
                        ot = round(hours - opts.workday_hours, 2)
                        ws.cell(r, cols["ot"]).value = ot if ot > 0 else 0
        stats["sheets"].append((ws.title, s_matched, s_filled, s_work, s_unmatched))
        for k, v in (("matched", s_matched), ("filled_time", s_filled),
                     ("computed_work", s_work), ("unmatched", s_unmatched)):
            stats[k] += v
        log("工作表 '%s'：匹配 %d 行，填打卡 %d 处，算工时 %d 行" %
            (ws.title, s_matched, s_filled, s_work))
    wb.save(out_path)
    return stats


# ---------- 统一入口：与对账功能同构 ----------
def run(targets, sources, opts=None, log=None, out_dir=None):
    """考勤填报统一入口（输出方式与工时对账一致）。
    targets : 待填考勤表路径列表（或单个）
    sources : 系统数据表路径列表（打卡来源）
    out_dir : 输出目录；不传则用统一 paths 系统（文档下统一文件夹）。
    输出：out_dir 下生成 名字_已填写_时间戳.xlsx（同批次共用一个时间戳）
    返回 {"out_files":[...], "out_dir":..., "source_stat":..., "results":[(target,out,stats)]}
    """
    opts = opts or cc.DEFAULTS
    log = log or (lambda *a, **k: None)
    if isinstance(targets, str):
        targets = [targets]
    if isinstance(sources, str):
        sources = [sources]
    ts = cc.timestamp()          # 同一批次共用一个时间戳
    if out_dir is None:
        out_dir = _unified_out_dir("attendance", ts, src=targets[0]) or cc.make_out_dir(targets[0])
    log("采用选项：" + opts.summary())
    log("① 读取并合并系统数据（%d 个文件）..." % len(sources))
    data, sstat = load_source_multi(sources, opts=opts, log=log)
    log("   合并后共 %d 条打卡记录。" % sstat["records"])

    out_files, results = [], []
    for i, tgt in enumerate(targets, 1):
        log("\n② 填写第 %d/%d 个待填表：%s" % (i, len(targets), os.path.basename(tgt)))
        base = os.path.splitext(os.path.basename(tgt))[0]
        op = cc.out_path(out_dir, base, "_已填写", ".xlsx", ts=ts)
        stats = fill_workbook(tgt, data, op, opts=opts, log=log)
        log("   匹配 %d 行、填打卡 %d 处、算工时 %d 行、未匹配 %d 行"
            % (stats["matched"], stats["filled_time"], stats["computed_work"], stats["unmatched"]))
        log("   已保存：%s" % op)
        out_files.append(op); results.append((tgt, op, stats))
    return {"out_files": out_files, "out_dir": out_dir,
            "source_stat": sstat, "results": results}


def _unified_out_dir(feature, ts=None, src=None):
    """通过统一 paths/settings 解析输出目录；导入失败则回退到原逻辑。
    src: beside 模式下用于定位源文件目录。"""
    try:
        from . import paths as _paths
        from . import settings as _settings
        st = _settings.get_settings()
        kw = st.output_kwargs()
        if src and not kw.get("src_path"):
            kw["src_path"] = src
        return _paths.resolve_output_dir(feature, ts=ts, **kw)
    except Exception:
        return None
