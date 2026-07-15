# -*- coding: utf-8 -*-
"""
送货计划表制作 —— 核心逻辑
==========================
以"物料清单"为主表逐行生成送货计划，按物料号从"物料明细表(含供应商)"查供应商
代码与名称，其余到货/收货/CASE/班组/备注等列留空，供后续人工跟单填写。

输入两份（顺序任意，程序自动辨识）：
  · 物料清单：含 物料号 + 数量（可再含中/英文描述）——决定输出的行与需求数；
  · 供应商明细：含 零部件代码 + 供应商代码 + 供应商名称——供按编码查供应商。

输出 16 列送货计划，表头样式与客户样本一致。表头行与列位置自动识别，不写死列号。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import paths as _paths
from . import settings as settings_mod

# 表头关键词 -> 角色。识别时先精确匹配，再包含匹配；每列只归一个角色。
HEADER_KEYS = {
    "code":  ["物料号", "物料编码", "零部件代码", "物料编号", "零件号", "编码", "料号"],
    "cname": ["物料中文描述", "物料名称", "零部件名称", "中文描述", "名称", "品名"],
    "ename": ["物料英文描述", "英文描述", "英文名称"],
    "qty":   ["需求数", "数量", "需求数量", "计划数量"],
    "sup_code": ["供应商代码", "供应商编码", "供方代码"],
    "sup_name": ["供应商名称", "供应商信息", "供方名称", "供应商"],
    "attr":  ["属性", "KD/SUB", "KD/SUB属性"],
}

# 输出固定 16 列（顺序即样本顺序）
OUT_HEADERS = ["序号", "物料编码", "物料名称", "供应商代码", "供应商信息", "KD/SUB",
               "需求数", "计划到货日期", "实际收货数", "实际收货日期", "第二次到货日期",
               "剩余未收数", "CASE", "CASE托数", "班组", "备注"]


def norm_code(v):
    """物料号归一：转字符串去空格。数值型编码去掉尾随的 .0。"""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def cell_text(v):
    """单元格文本化：None->''，浮点整数去 .0，其余原样 str。"""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


# ---------------------------------------------------------------------------
# 表头/列自动识别
# ---------------------------------------------------------------------------
def detect_layout(ws, scan_rows=12):
    """在前若干行里找表头行并映射列。返回 (header_row, {角色:列号})。

    选"能命中最多角色"的行为表头行；要求至少含 code 列，否则视为未识别(返回 None,{})。
    """
    best_row, best_map = None, {}
    for r in range(1, min(scan_rows, ws.max_row) + 1):
        col_map = {}
        used = set()
        for pass_exact in (True, False):     # 先精确后包含，避免"编码"抢占"供应商编码"
            for c in range(1, ws.max_column + 1):
                if c in used:
                    continue
                cell = ws.cell(r, c).value
                if cell is None:
                    continue
                text = str(cell).strip()
                for role, keys in HEADER_KEYS.items():
                    if role in col_map:
                        continue
                    hit = (text in keys) if pass_exact else any(k in text for k in keys)
                    if hit:
                        col_map[role] = c
                        used.add(c)
                        break
        if "code" in col_map and len(col_map) > len(best_map):
            best_map = col_map
            best_row = r
    return best_row, best_map


def load_sheet(path, sheet=None):
    """读取一张表：自动识别表头与列。返回 (rows, layout)。

    rows: [{r, code, cname, ename, qty, sup_code, sup_name, attr}]，按角色缺省为 None。
    已过滤空编码行与合计/小计行。
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    header_row, col = detect_layout(ws)
    if not header_row:
        raise ValueError("未能在 %s / %s 中识别表头（需含“物料号/编码”列）"
                         % (os.path.basename(path), ws.title))
    rows = []
    for r in range(header_row + 1, ws.max_row + 1):
        code = ws.cell(r, col["code"]).value
        if code is None or norm_code(code) == "":
            continue
        cn = ws.cell(r, col["cname"]).value if "cname" in col else None
        if isinstance(cn, str) and ("合计" in cn or "小计" in cn or "总计" in cn):
            continue
        rows.append({
            "r": r, "code": code, "cname": cn,
            "ename": ws.cell(r, col["ename"]).value if "ename" in col else None,
            "qty": ws.cell(r, col["qty"]).value if "qty" in col else None,
            "sup_code": ws.cell(r, col["sup_code"]).value if "sup_code" in col else None,
            "sup_name": ws.cell(r, col["sup_name"]).value if "sup_name" in col else None,
            "attr": ws.cell(r, col["attr"]).value if "attr" in col else None,
        })
    return rows, {"sheet": ws.title, "header_row": header_row, "col": col}


def _has_supplier(layout):
    """该表是否带供应商信息（可作供应商来源）。"""
    return "sup_code" in layout["col"] or "sup_name" in layout["col"]


def classify(lay_a, lay_b):
    """辨识两份表哪份是物料清单(主表)、哪份是供应商明细。返回 ('a'/'b' 为主表, 供应商来源同理)。

    规则：带供应商列的那份作供应商来源；另一份作主表(物料清单)。
    两份都带供应商列时，用"含数量列且不含供应商列"优先作主表；仍无法区分则 A 主 B 供。
    """
    a_sup, b_sup = _has_supplier(lay_a), _has_supplier(lay_b)
    if a_sup and not b_sup:
        return "b", "a"          # B 无供应商 -> 主表；A 供应商来源
    if b_sup and not a_sup:
        return "a", "b"
    return "a", "b"              # 兜底：A 主表、B 供应商来源


# ---------------------------------------------------------------------------
# 输出（复刻客户样本格式）
# ---------------------------------------------------------------------------
_HEAD_FILL = PatternFill("solid", fgColor="FFBDD7EE")     # 样本表头浅蓝
_HEAD_FONT = Font(name="微软雅黑", size=11, bold=True, color="FF000000")
_DATA_FONT = Font(name="等线", size=11)
_THIN = Side(style="thin", color="FF000000")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
# 列宽复刻样本：A序号 B编码 C名称 D供代 E供信息 其余统一 13
_WIDTHS = [13, 15.83, 39.91, 13, 45.75, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13]


def build_plan_sheet(ws, master_rows, sup_map, log=None):
    """把主表行写成送货计划。sup_map: 归一编码 -> (供应商代码, 供应商名称)。

    返回 (写入行数, 未匹配供应商的编码列表)。第 1 行留空，第 2 行表头，数据自第 3 行起。
    """
    ncol = len(OUT_HEADERS)
    ws.row_dimensions[1].height = 20
    for c in range(1, ncol + 1):            # 表头(第2行)
        cell = ws.cell(2, c, OUT_HEADERS[c - 1])
        cell.font = _HEAD_FONT
        cell.fill = _HEAD_FILL
        cell.alignment = _CENTER
        cell.border = _BORDER
    ws.row_dimensions[2].height = 33

    missing = []
    r = 3
    for i, row in enumerate(master_rows, 1):
        code = norm_code(row["code"])
        sup = sup_map.get(code)
        if sup is None:
            missing.append(code)
        sc, sn = (sup if sup else (None, None))
        vals = [i, row["code"], row.get("cname"), sc, sn, None,
                row.get("qty"), None, None, None, None, None, None, None, None, None]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(r, c, v)
            cell.font = _DATA_FONT
        r += 1

    for c, w in enumerate(_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    if log and missing:
        log("有 %d 个物料在供应商明细中未找到供应商，已留空：%s%s"
            % (len(missing), "、".join(missing[:8]), " 等" if len(missing) > 8 else ""))
    return r - 3, missing


def build_supplier_map(sup_rows, log=None):
    """从供应商明细行建 归一编码 -> (供应商代码, 供应商名称) 映射。

    一码多供应商时以首见为准，并在日志里提示冲突数（避免静默择一）。
    """
    m = {}
    conflicts = 0
    for row in sup_rows:
        code = norm_code(row["code"])
        if not code:
            continue
        pair = (cell_text(row.get("sup_code")) or None,
                cell_text(row.get("sup_name")) or None)
        if code in m:
            if m[code] != pair:
                conflicts += 1
            continue
        m[code] = pair
    if log and conflicts:
        log("注意：供应商明细中有 %d 个物料存在多个不同供应商，已取首个。" % conflicts)
    return m


def run(file_a, file_b, sheet_a=None, sheet_b=None, out_dir=None, log=None):
    """送货计划表制作主流程。两份输入顺序任意，自动辨识主表/供应商来源。

    返回 dict：{plan_path, out_dir, rows, matched, missing, master_file, supplier_file}。
    """
    def _lg(msg):
        if log:
            log(msg)

    rows_a, lay_a = load_sheet(file_a, sheet_a)
    rows_b, lay_b = load_sheet(file_b, sheet_b)
    master_key, sup_key = classify(lay_a, lay_b)
    pack = {"a": (rows_a, lay_a, file_a), "b": (rows_b, lay_b, file_b)}
    master_rows, _lm, master_file = pack[master_key]
    sup_rows, _ls, sup_file = pack[sup_key]
    _lg("主表(物料清单)：%s —— %d 行" % (os.path.basename(master_file), len(master_rows)))
    _lg("供应商来源：%s —— %d 行" % (os.path.basename(sup_file), len(sup_rows)))

    sup_map = build_supplier_map(sup_rows, log=_lg)

    if out_dir is None:
        st = settings_mod.get_settings()
        out_dir = _paths.resolve_output_dir("delivery", **st.output_kwargs())
    else:
        os.makedirs(out_dir, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    n, missing = build_plan_sheet(ws, master_rows, sup_map, log=_lg)
    matched = n - len(missing)
    _lg("已生成 %d 行，供应商匹配 %d / %d。" % (n, matched, n))

    plan_path = os.path.join(out_dir, "送货计划.xlsx")
    try:
        wb.save(plan_path)
    except PermissionError:
        raise PermissionError("无法保存 %s —— 请先在 Excel 里关闭该文件后重试" % plan_path)
    _lg("已生成送货计划：%s" % plan_path)
    return {"plan_path": plan_path, "out_dir": out_dir, "rows": n,
            "matched": matched, "missing": missing,
            "master_file": master_file, "supplier_file": sup_file}
