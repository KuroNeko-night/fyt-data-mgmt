# -*- coding: utf-8 -*-
"""表格比对引擎:两份 Excel 按"关键列"配对,找出差异 / 只在单边的行。

用途:核对"程序输出 vs 手工结果"、两版数据、交接复核等。
设计:
 - 表头自动识别(取前若干行里非空单元格最多的一行当表头);
 - 按用户选定的关键列(如物料编码)配对两表的行,行顺序不同也能对上;
 - 值比较做归一化:数字与其文本形态("10"==10)、去首尾空白、浮点容差,
   避免"程序输出 vs 手工"因格式差异误报;
 - 输出结构化结果 + 可导出带高亮的 Excel 报告。
纯逻辑、可测试,不依赖 UI。
"""
import os
import numbers

import openpyxl
from openpyxl.styles import PatternFill, Font

from . import paths as _paths
from . import settings as settings_mod

FONT_NAME = "微软雅黑"
FILL_DIFF = PatternFill("solid", fgColor="FFC7CE")     # 红:值不同
FILL_ONLY = PatternFill("solid", fgColor="FFEB9C")     # 黄:只在单边
FILL_HEAD = PatternFill("solid", fgColor="D9E1F2")     # 表头浅蓝
FLOAT_TOL = 1e-9


def _norm_cell(v):
    """归一化单元格值用于比较:None->'';数字规整;字符串去首尾空白。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, numbers.Number):
        return float(v)
    s = str(v).strip()
    # 纯数字文本按数字比:"10"==10、"10.0"==10、" 10 "==10
    try:
        return float(s.replace(",", "")) if s != "" else ""
    except ValueError:
        return s


def _eq(a, b):
    """两个已归一化值是否相等(浮点容差)。"""
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= FLOAT_TOL
    return a == b


def _open_ws(path, sheet=None):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    return wb, ws


def _detect_header_row(ws, scan_rows=15):
    """取前 scan_rows 行里"非空单元格最多"的一行作表头行(1-based)。
    通用启发式:不依赖具体字段名,适配任意表。空表返回 None。"""
    best_row, best_cnt = None, 0
    for r in range(1, min(scan_rows, ws.max_row) + 1):
        cnt = sum(1 for c in range(1, ws.max_column + 1)
                  if _norm_cell(ws.cell(r, c).value) != "")
        if cnt > best_cnt:
            best_cnt, best_row = cnt, r
    return best_row


def read_table(path, sheet=None, scan_rows=15):
    """读一张表 -> (headers, rows)。
    headers: [列名...](按列序,去重时后者加后缀);rows: [{列名: 值}...]。
    表头行之后的每一行为一条记录;整行全空则跳过。"""
    wb, ws = _open_ws(path, sheet)
    try:
        hr = _detect_header_row(ws, scan_rows)
        if hr is None:
            return [], []
        headers, seen = [], {}
        for c in range(1, ws.max_column + 1):
            name = str(ws.cell(hr, c).value).strip() if ws.cell(hr, c).value is not None else ""
            if name == "":
                name = "列%d" % c
            if name in seen:                    # 重名列加后缀,保证键唯一
                seen[name] += 1
                name = "%s(%d)" % (name, seen[name])
            else:
                seen[name] = 1
            headers.append(name)
        rows = []
        for r in range(hr + 1, ws.max_row + 1):
            vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            if all(_norm_cell(v) == "" for v in vals):
                continue
            rows.append({headers[i]: vals[i] for i in range(len(headers))})
        return headers, rows
    finally:
        wb.close()


def read_headers(path, sheet=None, scan_rows=15):
    """只读表头行,轻量(read_only)。供 UI 快速填"关键列"下拉,不读数据行。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        rows = []                                   # read_only 下顺序取前若干行
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= scan_rows:
                break
            rows.append(row)
        if not rows:
            return []
        best = max(rows, key=lambda rw: sum(1 for v in rw if _norm_cell(v) != ""))
        headers, seen = [], {}
        for c, v in enumerate(best, 1):
            name = str(v).strip() if v is not None else ""
            if name == "":
                name = "列%d" % c
            if name in seen:
                seen[name] += 1
                name = "%s(%d)" % (name, seen[name])
            else:
                seen[name] = 1
            headers.append(name)
        return headers
    finally:
        wb.close()


def common_columns(headers_a, headers_b):
    """两表都存在的列(按 A 的顺序),供选关键列/比较列。"""
    setb = set(headers_b)
    return [h for h in headers_a if h in setb]


def _index_by_key(rows, key):
    """按关键列建索引 {键: [行...]}。键归一化为字符串,空键行单独收集。"""
    idx, blank = {}, []
    for row in rows:
        k = row.get(key)
        ks = "" if k is None else str(k).strip()
        if ks == "":
            blank.append(row)
            continue
        idx.setdefault(ks, []).append(row)
    return idx, blank


def compare(headers_a, rows_a, headers_b, rows_b, key, columns=None, log=None):
    """按关键列配对两表,返回差异结构。

    - key:      关键列名(须同时存在于两表)。
    - columns:  要比较的列(默认两表公共列去掉 key);仅比这些列的值。
    返回 dict:
      diffs:    [{key, column, a, b}]        值不同的单元格
      only_a:   [{key, row}]                 关键列只在 A 出现
      only_b:   [{key, row}]                 关键列只在 B 出现
      dup_a/dup_b: [键...]                    关键列在单表内重复(比对按首条,余略)
      blank_a/blank_b: 关键列为空而被跳过的行数
      columns:  实际比较的列
      counts:   概要计数
    """
    if key not in headers_a or key not in headers_b:
        raise ValueError("关键列「%s」需同时存在于两份表" % key)
    if columns is None:
        columns = [c for c in common_columns(headers_a, headers_b) if c != key]

    idx_a, blank_a = _index_by_key(rows_a, key)
    idx_b, blank_b = _index_by_key(rows_b, key)
    dup_a = sorted(k for k, v in idx_a.items() if len(v) > 1)
    dup_b = sorted(k for k, v in idx_b.items() if len(v) > 1)

    diffs, only_a, only_b = [], [], []
    for k, rows in idx_a.items():
        if k not in idx_b:
            only_a.append({"key": k, "row": rows[0]})
            continue
        ra, rb = rows[0], idx_b[k][0]           # 各取首条(重复已在 dup_* 报告)
        for col in columns:
            va, vb = ra.get(col), rb.get(col)
            if not _eq(_norm_cell(va), _norm_cell(vb)):
                diffs.append({"key": k, "column": col, "a": va, "b": vb})
    for k, rows in idx_b.items():
        if k not in idx_a:
            only_b.append({"key": k, "row": rows[0]})

    if log:
        log("· 比对完成:差异 %d 处,只在A %d 行,只在B %d 行"
            % (len(diffs), len(only_a), len(only_b)))
        if dup_a or dup_b:
            log("⚠ 关键列有重复值(A:%d B:%d),重复键只按首条比对"
                % (len(dup_a), len(dup_b)))
        if blank_a or blank_b:
            log("⚠ 关键列为空的行已跳过(A:%d B:%d)" % (len(blank_a), len(blank_b)))

    counts = {"diffs": len(diffs), "only_a": len(only_a), "only_b": len(only_b),
              "dup_a": len(dup_a), "dup_b": len(dup_b),
              "blank_a": len(blank_a), "blank_b": len(blank_b),
              "matched": len(idx_a) - len(only_a)}
    return {"diffs": diffs, "only_a": only_a, "only_b": only_b,
            "dup_a": dup_a, "dup_b": dup_b, "blank_a": len(blank_a),
            "blank_b": len(blank_b), "columns": columns, "key": key,
            "counts": counts}


def _style_header(ws, headers):
    for c, name in enumerate(headers, 1):
        cell = ws.cell(1, c, name)
        cell.font = Font(name=FONT_NAME, bold=True)
        cell.fill = FILL_HEAD


def export_report(result, out_dir=None, out_name="差异报告.xlsx", log=None):
    """把比对结果写成带高亮的 Excel:概要 / 差异明细(红) / 只在A(黄) / 只在B(黄)。"""
    out_dir = out_dir or os.getcwd()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, out_name)
    wb = openpyxl.Workbook()

    # 概要
    ws = wb.active; ws.title = "概要"
    _style_header(ws, ["项目", "数量"])
    cn = result["counts"]
    for name, val in [("关键列", result["key"]), ("比较列数", len(result["columns"])),
                      ("值差异(单元格)", cn["diffs"]), ("配对成功(行)", cn["matched"]),
                      ("只在A的行", cn["only_a"]), ("只在B的行", cn["only_b"]),
                      ("A重复键", cn["dup_a"]), ("B重复键", cn["dup_b"]),
                      ("A关键列空行", cn["blank_a"]), ("B关键列空行", cn["blank_b"])]:
        ws.append([name, val])

    # 差异明细
    ws = wb.create_sheet("差异明细")
    _style_header(ws, [result["key"], "列名", "A 值", "B 值"])
    for d in result["diffs"]:
        ws.append([d["key"], d["column"], d["a"], d["b"]])
        for c in (3, 4):
            ws.cell(ws.max_row, c).fill = FILL_DIFF

    # 只在 A / 只在 B
    for title, items in [("只在A", result["only_a"]), ("只在B", result["only_b"])]:
        ws = wb.create_sheet(title)
        cols = list(items[0]["row"].keys()) if items else [result["key"]]
        _style_header(ws, cols)
        for it in items:
            ws.append([it["row"].get(c) for c in cols])
            for c in range(1, len(cols) + 1):
                ws.cell(ws.max_row, c).fill = FILL_ONLY

    wb.save(path)
    if log:
        log("· 报告已生成:%s" % path)
    return path


def run(file_a, file_b, key, sheet_a=None, sheet_b=None, columns=None,
        out_dir=None, log=None):
    """完整流程:读两表 -> 比对 -> 导出报告。返回 result + report_path/out_dir。"""
    ha, ra = read_table(file_a, sheet_a)
    hb, rb = read_table(file_b, sheet_b)
    if log:
        log("· A《%s》%d 行,B《%s》%d 行"
            % (os.path.basename(file_a), len(ra), os.path.basename(file_b), len(rb)))
    result = compare(ha, ra, hb, rb, key, columns=columns, log=log)
    # 输出目录:未显式指定时走全程序统一约定(文档/…/表格比对/时间戳),
    # 与考勤/透视/采购等一致,尊重"设置"里的输出模式。
    if out_dir is None:
        st = settings_mod.get_settings()
        out_dir = _paths.resolve_output_dir("compare", **st.output_kwargs())
    stem = "差异报告_%s_vs_%s.xlsx" % (
        os.path.splitext(os.path.basename(file_a))[0],
        os.path.splitext(os.path.basename(file_b))[0])
    report = export_report(result, out_dir=out_dir, out_name=stem, log=log)
    result["report_path"] = report
    result["out_dir"] = os.path.dirname(report)
    return result
