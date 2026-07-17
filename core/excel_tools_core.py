# -*- coding: utf-8 -*-
"""
Excel 工具箱核心 —— 合并 / 拆分 / 转换 / 纵向合并
==================================================
基于现有 openpyxl(xlsx 读写)+ xlrd 1.2(老 .xls 只读),零新依赖。
四种操作,均接受 log 回调、输出写入统一 paths 目录:

  merge_books   多个工作簿 → 一个工作簿(每个源 sheet 一个新 sheet)
  split_sheets  一个工作簿 → 每个 sheet 拆成单独文件
  convert       .xls → .xlsx;或 Excel ↔ CSV
  stack_tables  多个"同结构"表纵向拼成一张大表(按表头对齐)

格式保留:.xlsx/.xlsm 的拆分/合并会保留字体、填充、边框、对齐、数字格式、
列宽、行高、合并单元格、冻结窗格(拆分还完整保留图表/图片)。老 .xls 与 CSV
本身不含或无法带出这些格式,相关操作退回"仅数据"。纯数据读取走 _read_sheets()。
兼容 Windows 7 + Python 3.8。
"""
import os
import csv
import copy as _copy

import openpyxl

from . import paths as _paths

try:
    import xlrd                          # 仅用于读老 .xls
    _HAS_XLRD = True
except Exception:
    _HAS_XLRD = False


class ExcelToolError(Exception):
    """面向用户的业务异常。"""


def _safe_sheet_title(name, used):
    """Excel sheet 名限长 31 且不能含 []:*?/\\ ,去重。"""
    bad = set('[]:*?/\\')
    t = "".join("_" if c in bad else c for c in (name or "Sheet"))[:31] or "Sheet"
    base = t
    i = 1
    while t.lower() in used:
        suffix = "_%d" % i
        t = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(t.lower())
    return t


def _read_sheets(path):
    """把一个 Excel 文件读成 [(sheet名, [row,...])],row 为值列表。

    .xlsx/.xlsm 用 openpyxl(只读值);.xls 用 xlrd。其它扩展名报错。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        out = []
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            out.append((ws.title, rows))
        wb.close()
        return out
    if ext == ".xls":
        if not _HAS_XLRD:
            raise ExcelToolError("未安装 xlrd,无法读取老式 .xls 文件")
        book = xlrd.open_workbook(path)
        out = []
        for sh in book.sheets():
            rows = []
            for r in range(sh.nrows):
                # 逐格判类型:日期格(XL_CELL_DATE)按 xldate 还原为 datetime,
                # 否则原样取值——避免日期被写成 Excel 序列号(float)静默变数字
                cells = []
                for c in range(sh.ncols):
                    cell = sh.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            cells.append(xlrd.xldate.xldate_as_datetime(
                                cell.value, book.datemode))
                        except Exception:
                            cells.append(cell.value)   # 还原失败退回原值
                    else:
                        cells.append(cell.value)
                rows.append(cells)
            out.append((sh.name, rows))
        return out
    raise ExcelToolError("不支持的文件类型:%s" % ext)


def _write_rows(ws, rows):
    """把行列表写入 openpyxl worksheet(仅值,无格式)。"""
    for r in rows:
        ws.append(list(r) if r is not None else [])


def _copy_sheet(src, dst):
    """把源工作表 src 的内容与格式复制到目标工作表 dst(同一/跨工作簿均可)。

    复制:单元格值 + 字体/填充/边框/对齐/数字格式、列宽、行高与隐藏、
    合并单元格、冻结窗格、网格线显示。样式对象跨工作簿需 deepcopy 脱离原簿。
    注:图片/图表等绘图对象 openpyxl 无法跨簿搬运,合并时会丢失(拆分则保留)。"""
    for row in src.iter_rows():
        for c in row:
            d = dst.cell(row=c.row, column=c.column, value=c.value)
            if c.has_style:
                d.font = _copy.copy(c.font)
                d.fill = _copy.copy(c.fill)
                d.border = _copy.copy(c.border)
                d.alignment = _copy.copy(c.alignment)
                d.protection = _copy.copy(c.protection)
                d.number_format = c.number_format
    # 列宽 / 列隐藏
    for key, dim in src.column_dimensions.items():
        nd = dst.column_dimensions[key]
        nd.width = dim.width
        nd.hidden = dim.hidden
        if dim.width is None and dim.hidden:
            nd.width = 8.43
    # 行高 / 行隐藏
    for idx, dim in src.row_dimensions.items():
        nd = dst.row_dimensions[idx]
        nd.height = dim.height
        nd.hidden = dim.hidden
    # 合并单元格
    for rng in list(src.merged_cells.ranges):
        dst.merge_cells(str(rng))
    # 冻结窗格 & 视图
    dst.freeze_panes = src.freeze_panes
    dst.sheet_view.showGridLines = src.sheet_view.showGridLines


def merge_books(files, out_dir=None, out_name="合并工作簿.xlsx",
                keep_formula=False, log=None):
    """多个工作簿合并为一个:每个源 sheet 成为结果里的一个 sheet。

    keep_formula=False(默认):公式转为计算后的值,数值稳妥、不会引用错乱。
    keep_formula=True:保留公式原文;但因工作表被重命名为「文件名-原表名」,
        跨表公式(如 =表二!A1)会指向旧表名而失效,仅表内公式安全。
    sheet 名用「文件名-原sheet名」并去重、限长。返回 {out_file, out_dir}。"""
    log = log or (lambda *_: None)
    if len(files) < 2:
        raise ExcelToolError("合并至少需要 2 个 Excel 文件")
    out_dir = out_dir or _paths.resolve_output_dir("excel_tools")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    used = set()
    total = 0
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        ext = os.path.splitext(f)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            # 带格式复制:逐个源工作表 → 新工作表
            # data_only=False 时 cell.value 返回公式原文,由 _copy_sheet 原样搬运
            src_wb = openpyxl.load_workbook(f, data_only=not keep_formula)
            for sn in src_wb.sheetnames:
                title = _safe_sheet_title("%s-%s" % (stem, sn), used)
                ws = wb.create_sheet(title=title)
                _copy_sheet(src_wb[sn], ws)
                total += 1
            log("并入 %s(%d 个表,含格式%s)"
                % (os.path.basename(f), len(src_wb.sheetnames),
                   "、保留公式" if keep_formula else ""))
            src_wb.close()
        else:
            # .xls/.csv 无法带格式,退回仅值
            sheets = _read_sheets(f)
            for name, rows in sheets:
                title = _safe_sheet_title("%s-%s" % (stem, name), used)
                _write_rows(wb.create_sheet(title=title), rows)
                total += 1
            log("并入 %s(%d 个表,仅数据)" % (os.path.basename(f), len(sheets)))
    out_file = os.path.join(out_dir, out_name)
    wb.save(out_file)
    log("已合并 %d 个文件、共 %d 个工作表 → %s" % (len(files), total, out_file))
    return {"out_file": out_file, "out_dir": out_dir, "out_files": [out_file]}


def split_sheets(file, out_dir=None, log=None):
    """把一个工作簿的每个 sheet 拆成单独 .xlsx 文件,保留原格式。

    .xlsx/.xlsm:整簿载入后只留目标表再另存,列宽/合并/字体/图表/图片全保留;
    .xls:openpyxl 不能读,退回仅数据。返回 {out_files, out_dir}。"""
    log = log or (lambda *_: None)
    out_dir = out_dir or _paths.resolve_output_dir("excel_tools")
    stem = os.path.splitext(os.path.basename(file))[0]
    ext = os.path.splitext(file)[1].lower()

    def _safe(name):
        return "".join("_" if c in '\\/:*?"<>|' else c for c in name)

    outs = []
    if ext in (".xlsx", ".xlsm"):
        # 只载入一次整簿(保留全部格式/绘图),之后每个目标表用 deepcopy 复用,避免 O(N²) 反复读盘
        full = openpyxl.load_workbook(file)
        names = list(full.sheetnames)
        if len(names) < 2:
            full.close()
            raise ExcelToolError("该工作簿只有 1 个工作表,无需拆分")
        for target in names:
            wb = _copy.deepcopy(full)      # 深拷贝脱离原簿,删掉其余表再存
            for sn in list(wb.sheetnames):
                if sn != target:
                    del wb[sn]
            wb[target].sheet_state = "visible"
            wb.active = 0
            of = os.path.join(out_dir, "%s_%s.xlsx" % (stem, _safe(target)))
            wb.save(of)
            wb.close()
            outs.append(of)
            log("导出工作表「%s」(含格式)→ %s" % (target, os.path.basename(of)))
        full.close()
    else:
        sheets = _read_sheets(file)
        if len(sheets) < 2:
            raise ExcelToolError("该工作簿只有 1 个工作表,无需拆分")
        for name, rows in sheets:
            of = os.path.join(out_dir, "%s_%s.xlsx" % (stem, _safe(name)))
            wb = openpyxl.Workbook()
            _write_rows(wb.active, rows)
            wb.active.title = _safe_sheet_title(name, set())
            wb.save(of)
            outs.append(of)
            log("导出工作表「%s」(仅数据,老 .xls 无格式)→ %s"
                % (name, os.path.basename(of)))
    log("已按工作表拆分为 %d 个文件" % len(outs))
    return {"out_files": outs, "out_dir": out_dir, "out_file": outs[0] if outs else ""}


def _read_csv(path, log=None):
    """读 CSV → [row,...]。尝试 utf-8-sig,失败退回 gbk。

    gbk 几乎能"解码"任意字节,异编码会静默乱码,故解码成功后再抽样校验:
    若出现替换符/大量不可见控制字符,log 提示编码可能不对,请人工核对。"""
    log = log or (lambda *_: None)
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                rows = [row for row in csv.reader(f)]
        except (UnicodeDecodeError, UnicodeError):
            continue
        # 抽样前若干单元格,统计替换符�与异常控制字符占比
        sample = "".join(str(c) for r in rows[:50] for c in r)[:5000]
        if sample:
            bad = sum(1 for ch in sample
                      if ch == "�" or (ord(ch) < 32 and ch not in "\t\n\r"))
            if bad and bad / float(len(sample)) > 0.02:
                log("警告:%s 以 %s 解码后疑似乱码,编码可能不是 utf-8/gbk,请核对"
                    % (os.path.basename(path), enc))
        return rows
    raise ExcelToolError("无法识别 CSV 编码:%s" % os.path.basename(path))


def convert(files, target, out_dir=None, log=None):
    """格式转换。target in {'xlsx','csv'}。

    · target='xlsx': 每个 .xls/.csv → 一个 .xlsx(多 sheet 的 xls 全部并入)
    · target='csv' : 每个 Excel 的每个 sheet → 一个 .csv(utf-8-sig,Excel 友好)
    返回 {out_files, out_dir}。"""
    log = log or (lambda *_: None)
    if not files:
        raise ExcelToolError("请先选择文件")
    out_dir = out_dir or _paths.resolve_output_dir("excel_tools")
    outs = []
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        stem = os.path.splitext(os.path.basename(f))[0]
        if target == "xlsx":
            wb = openpyxl.Workbook(); wb.remove(wb.active); used = set()
            if ext == ".csv":
                ws = wb.create_sheet(_safe_sheet_title(stem, used))
                _write_rows(ws, _read_csv(f, log))   # 传 log,乱码兜底可提示
            else:
                for name, rows in _read_sheets(f):
                    _write_rows(wb.create_sheet(_safe_sheet_title(name, used)), rows)
            of = os.path.join(out_dir, stem + ".xlsx")
            wb.save(of); outs.append(of)
            log("%s → %s" % (os.path.basename(f), os.path.basename(of)))
        else:  # csv
            if ext == ".csv":
                continue                # 已是 csv,跳过
            sheets = _read_sheets(f)
            for name, rows in sheets:
                suffix = ("_" + name) if len(sheets) > 1 else ""
                of = os.path.join(out_dir, "%s%s.csv" % (stem, suffix))
                with open(of, "w", encoding="utf-8-sig", newline="") as fh:
                    w = csv.writer(fh)
                    for r in rows:
                        w.writerow(["" if c is None else c for c in r])
                outs.append(of)
                log("%s[%s] → %s" % (os.path.basename(f), name, os.path.basename(of)))
    if not outs:
        raise ExcelToolError("没有可转换的文件(目标格式与源相同?)")
    return {"out_files": outs, "out_dir": out_dir, "out_file": outs[0]}


def stack_tables(files, has_header=True, out_dir=None,
                 out_name="纵向合并.xlsx", log=None):
    """多个同结构表纵向拼接成一张大表(取每个文件的第一个 sheet)。

    has_header=True 时保留第一个文件的表头,其余文件跳过首行;并新增
    「来源文件」列便于追溯。返回 {out_file, out_dir}。"""
    log = log or (lambda *_: None)
    if len(files) < 2:
        raise ExcelToolError("纵向合并至少需要 2 个文件")
    out_dir = out_dir or _paths.resolve_output_dir("excel_tools")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "合并"
    header_written = False
    total_rows = 0
    base_cols = None            # 首个非空表的列数,后续按它校验,防止结构不一致时静默错位
    for f in files:
        sheets = _read_sheets(f)
        if not sheets:
            continue
        rows = sheets[0][1]
        if not rows:
            log("跳过空表 %s" % os.path.basename(f)); continue
        start = 0
        if has_header:
            if not header_written:
                ws.append(list(rows[0]) + ["来源文件"])
                header_written = True
                base_cols = len(rows[0])
            start = 1
        elif base_cols is None:
            base_cols = len(rows[0])
        for r in rows[start:]:
            row = list(r)
            # 列数与首表不一致→告警(不静默),并补齐/截断到基准列数保持对齐
            if base_cols is not None and len(row) != base_cols:
                log("警告:%s 某行列数为 %d,与首表 %d 列不一致,已补齐/截断对齐"
                    % (os.path.basename(f), len(row), base_cols))
                if len(row) < base_cols:
                    row = row + [None] * (base_cols - len(row))
                else:
                    row = row[:base_cols]
            ws.append(row + [os.path.basename(f)])
            total_rows += 1
        log("追加 %s:%d 行" % (os.path.basename(f), len(rows) - start))
    out_file = os.path.join(out_dir, out_name)
    wb.save(out_file)
    log("已纵向合并 %d 个文件、共 %d 行数据 → %s" % (len(files), total_rows, out_file))
    return {"out_file": out_file, "out_dir": out_dir, "out_files": [out_file]}
