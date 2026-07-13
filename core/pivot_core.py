# -*- coding: utf-8 -*-
"""
透视表制作核心逻辑（从 arrival_table_app.pyw 抽出，与 GUI 解耦）
================================================================
复刻 PurchaseProc.bas：定位表头、清洗数据、统一单位/规格、按
材料编号/名称/规格/单位 分组汇总最终采购数量，并生成 Excel 原生
数据透视表（OOXML）。两阶段：analyze_workbooks(收集决策点) →
apply_plan(应用选择、写出结果 + 可信度报告)。

改动点（相对原程序）：
· 输出目录改由统一 paths 系统解析（见 run）；
· 与到料明细共用同一套输出/命名规范；
· 纯逻辑，无 tkinter 依赖。

兼容 Windows 7 + Python 3.8。
"""
import os
import re
import sys
import glob
import json
import datetime
import zipfile
import copy
from collections import defaultdict, OrderedDict

import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, Side, Alignment, Font, PatternFill
from openpyxl.styles.colors import Color
from openpyxl.utils import get_column_letter

from . import paths as _paths
from . import settings as _settings

L_VER   = "版本序号"
L_CODE  = "材料编号"
L_NAME  = "材料名称"
L_SPEC  = "规格"
L_UNIT  = "单位"
L_FINAL = "最终采购数量"
L_QTY   = "数量"
KEEP_TOKEN = "原厂"            # 名称含此token的行, 步骤2不删

# 表头别名: 不同表格用词不一, 识别时任一匹配即可
CODE_ALIASES  = ("材料编号", "材料号", "物料编号", "物料号", "料号", "物料编码", "编码")
NAME_ALIASES  = ("材料名称", "物料名称", "品名", "名称")
SPEC_ALIASES  = ("规格尺寸", "规格型号", "规格", "尺寸")
FINAL_ALIASES = ("最终采购数量", "需求数量", "采购数量", "需求数", "采购数", "需求量")
UNIT_ALIASES  = ("使用单位", "计量单位", "单位")
VER_ALIASES   = ("版本序号", "版本")
QTY_EXACT     = ("数量", "单套数量", "单车数量")

def _match_anchor(t, aliases):
    """锚点匹配: 相等, 或包含别名且长度接近(避免误抓长文本)"""
    for a in aliases:
        if t == a or (a in t and len(t) <= len(a) + 8):
            return True
    return False

def _contains_any(t, aliases):
    return any(a in t for a in aliases)
PIVOT_BASE = "数据透视表"
SUM_PREFIX = "求和项:"
L_SUPPLIER = "供应商"
L_SUMMARY  = "汇总"
L_DIFF     = "差异"
L_RECEIVED = "实收"
L_DATE     = "日期"

HEADER_SCAN_ROWS = 30
MAX_BLOCKS = 12

# ---- helpers ----
def _has_chinese(s):
    for ch in str(s):
        if '一' <= ch <= '鿿':
            return True
    return False

def _is_blank(v):
    if v is None:
        return True
    return str(v).strip() == ""

def _is_zero(v):
    if _is_blank(v):
        return False
    try:
        return float(v) == 0
    except (ValueError, TypeError):
        return False

def _norm(v):
    """去换行/空格/制表符, 便于表头匹配"""
    if v is None:
        return ""
    s = str(v)
    for ch in ["\r\n", "\n", "\r", "\t", " "]:
        s = s.replace(ch, "")
    return s.strip()


def _cell(ws, r, c):
    return ws.cell(row=r, column=c).value

def _last_col(ws, r):
    """该行最后一个非空列(模拟 End(xlToLeft))"""
    last = 1
    for c in range(1, ws.max_column + 1):
        if not _is_blank(_cell(ws, r, c)):
            last = c
    return last

def find_all_blocks(ws):
    """
    找出表内所有数据块(支持并排). 每块锚定于'材料编号'表头单元格,
    向右解析 7 个字段列. 返回 [{'hdr':行, 'cols':[ver,code,name,spec,qty,unit,final]}]
    cols 中 0 表示该字段缺失.
    """
    blocks = []
    scan = min(HEADER_SCAN_ROWS, ws.max_row or 1)
    for r in range(1, scan + 1):
        lc = _last_col(ws, r)
        for c in range(1, lc + 1):
            t = _norm(_cell(ws, r, c))
            # 锚点: 匹配任一"材料编号"别名
            if t != "" and _match_anchor(t, CODE_ALIASES):
                cVer=0; cCode=c; cName=0; cSpec=0; cUnit=0; cFinal=0; cQty=0
                if c - 1 >= 1 and _contains_any(_norm(_cell(ws, r, c - 1)), VER_ALIASES):
                    cVer = c - 1
                for cc in range(c, lc + 1):
                    tt = _norm(_cell(ws, r, cc))
                    if tt == "":
                        continue
                    if cName == 0 and _contains_any(tt, NAME_ALIASES): cName = cc; continue
                    if cSpec == 0 and _contains_any(tt, SPEC_ALIASES): cSpec = cc; continue
                    if cFinal == 0 and _contains_any(tt, FINAL_ALIASES): cFinal = cc; continue
                    if cQty == 0 and tt in QTY_EXACT: cQty = cc; continue
                    if cUnit == 0 and _contains_any(tt, UNIT_ALIASES): cUnit = cc; continue
                if cCode > 0 and cFinal > 0:
                    blocks.append({'hdr': r,
                        'cols': [cVer, cCode, cName, cSpec, cQty, cUnit, cFinal]})
                    if len(blocks) >= MAX_BLOCKS:
                        return blocks
    return blocks

def _looks_like_pivot_output(ws):
    """判断该表是否本身就是"透视结果表"(避免把已生成的透视表当源数据重复统计)。
       特征: 表头出现"求和项:"前缀, 或存在"(全部)"页字段筛选行。"""
    scan = min(HEADER_SCAN_ROWS, ws.max_row or 1)
    for r in range(1, scan + 1):
        lc = _last_col(ws, r)
        for c in range(1, lc + 1):
            t = _norm(_cell(ws, r, c))
            if t == "":
                continue
            if SUM_PREFIX.replace(" ", "") in t or t == "(全部)":
                return True
    return False

# 客户供货件(客供件)不是采购物料, 标准透视表不纳入, 按表名排除
EXCLUDE_SHEET_TOKENS = ("客供", "客户供", "客户提供")

def _is_excluded_sheet(ws):
    name = ""
    try:
        name = str(ws.title)
    except Exception:
        name = ""
    name = name.replace(" ", "")
    return any(tok in name for tok in EXCLUDE_SHEET_TOKENS)

def is_data_sheet(ws):
    if _is_excluded_sheet(ws):
        return False
    if _looks_like_pivot_output(ws):
        return False
    return len(find_all_blocks(ws)) > 0


# ==================== 表类型分类层(泛用性识别 + 可信度依据) ====================
# 在结构探测之上叠加"这张表到底是什么"的判定, 输出识别依据与置信度,
# 供可信度报告使用。判定顺序: 排除类 -> 组托辅材 -> 包装方案汇总 -> 通用数据表。
FIELD_CN = ["版本序号", "材料编号", "材料名称", "规格", "数量", "单位", "最终采购数量"]
KEY_FIELDS = [1, 6]                       # 编码、最终采购数量为关键字段(缺失严重)
INFO_FIELDS = [2, 3, 5]                   # 名称/规格/单位为信息字段(缺失影响分组)

# 各类源表的表名关键词
NAME_PACKAGING = ("包装方案汇总", "包材用量计算", "PFEP及采购", "采购量核算")
NAME_ZUTUO     = ("组托辅材", "组托PFEP", "组托")
# 明确排除的表(参考/中间/已汇总/已透视), 不作为透视源
NAME_EXCLUDE   = ("客供", "客户供", "客户提供", "货物清单", "变更记录",
                  "非定额", "辅材汇总", "订单辅材", "采购明细",
                  "CASE组托数据", "组托数据")

def _sheet_name(ws):
    try:
        return str(ws.title).replace(" ", "")
    except Exception:
        return ""

def _has_token(name, tokens):
    return any(t.replace(" ", "") in name for t in tokens)


# 归一化后字段索引: 0版本 1编码 2名称 3规格 4数量 5单位 6最终采购数量
F_VER, F_CODE, F_NAME, F_SPEC, F_QTY, F_UNIT, F_FINAL = 0, 1, 2, 3, 4, 5, 6


def classify_sheet(ws):
    """判定一张表的类型与可信度依据。返回 dict:
       {name, use(bool), kind, reason, confidence(0-100), cols, missing[], blocks}
       kind ∈ 包装方案汇总 / 组托辅材 / 组托辅材(PFEP) / 通用数据表 / 排除:xxx"""
    name = _sheet_name(ws)
    blocks = find_all_blocks(ws)
    info = {"name": name, "use": False, "kind": "", "reason": "",
            "confidence": 0, "cols": None, "missing": [], "blocks": len(blocks)}

    # 1) 排除类: 表名命中排除词 / 客供 / 已是透视输出
    if _has_token(name, NAME_EXCLUDE):
        hit = next((t for t in NAME_EXCLUDE if t.replace(" ", "") in name), "")
        info.update(kind="排除:参考或已汇总表", reason="表名含'%s', 非采购透视源" % hit)
        return info
    if _looks_like_pivot_output(ws):
        info.update(kind="排除:疑似已生成透视表",
                    reason="表内出现'求和项:'或'(全部)'页字段, 判为已有透视结果")
        return info
    if not blocks:
        info.update(kind="排除:无数据区",
                    reason="未找到'材料编号+最终采购数量'数据区")
        return info

    # 有数据区: 取首个块的字段映射, 判定具体类型
    cols = blocks[0]["cols"]     # [ver,code,name,spec,qty,unit,final]
    info["cols"] = cols
    missing = [FIELD_CN[i] for i in (KEY_FIELDS + INFO_FIELDS) if cols[i] == 0]
    info["missing"] = missing
    return _classify_by_name_and_cols(ws, name, cols, blocks, info)


def _classify_by_name_and_cols(ws, name, cols, blocks, info):
    """在确认有数据区后, 结合表名与字段映射给出类型与置信度。"""
    has_ver = cols[F_VER] != 0
    has_final = cols[F_FINAL] != 0
    # 组托辅材类
    if _has_token(name, NAME_ZUTUO):
        if has_ver or "PFEP" in name.upper():
            kind = "组托辅材(PFEP)"
            reason = "表名含'组托'且为PFEP结构(有版本序号列), 取'最终采购数量'汇总"
        else:
            kind = "组托辅材"
            reason = "表名含'组托辅材', 简单式(材料号/需求数量/使用单位)"
        conf = 92 if not info["missing"] else 80
        info.update(use=True, kind=kind, reason=reason, confidence=conf)
        return info
    # 包装方案汇总类
    if _has_token(name, NAME_PACKAGING):
        conf = 95 if not info["missing"] else 82
        info.update(use=True, kind="包装方案汇总",
                    reason="表名含包装方案/包材用量/PFEP采购关键词, 结构匹配",
                    confidence=conf)
        return info
    # 表名不含关键词, 但结构像采购数据表 -> 通用数据表(降置信)
    if has_final:
        conf = 70 if not info["missing"] else 55
        info.update(use=True, kind="通用数据表",
                    reason="表名无已知关键词, 但含'材料编号+最终采购数量'结构, 按通用源纳入",
                    confidence=conf)
        return info
    info.update(kind="排除:结构不完整", reason="缺少最终采购数量列", confidence=0)
    return info

def normalize_rows(ws):
    """把所有块的数据行读入统一的 7 字段列表(合并并排块)"""
    blocks = find_all_blocks(ws)
    if not blocks:
        return []
    last = ws.max_row or 1
    rows = []
    for b in blocks:
        cols = b['cols']
        for r in range(b['hdr'] + 1, last + 1):
            rec = []
            for i in range(7):
                sc = cols[i]
                rec.append(_cell(ws, r, sc) if sc > 0 else None)
            # 跳过整行全空
            if all(_is_blank(x) for x in rec):
                continue
            rows.append(rec)
    return rows

def clean_rows(rows):
    """步骤1: 删版本序号 空/0/含中文(仅当存在版本列时); 步骤2: 删最终采购数=0/空(名称含原厂保留)"""
    d1 = d2 = 0
    # 若整列版本序号都为空, 说明该表无版本列(如辅材表), 跳过步骤1避免全删
    has_ver = any(not _is_blank(rec[F_VER]) for rec in rows)
    out = []
    for rec in rows:
        if has_ver:
            v = rec[F_VER]
            if _is_blank(v) or _is_zero(v) or _has_chinese(str(v)):
                d1 += 1
                continue
        out.append(rec)
    kept = []
    for rec in out:
        g = rec[F_FINAL]; nm = rec[F_NAME]
        if _is_zero(g) or _is_blank(g):
            if KEEP_TOKEN not in str(nm if nm is not None else ""):
                d2 += 1
                continue
        kept.append(rec)
    return kept, d1, d2


def _is_valid_code(code):
    """真实物料编码: 非空、且不是中文表头(如 '材料编号')。"""
    if _is_blank(code):
        return False
    return not _has_chinese(str(code))


def _final_has_qty(rec):
    """该行最终采购数量是否为"有效非零数值"。"""
    g = rec[F_FINAL]
    if _is_zero(g) or _is_blank(g):
        return False
    try:
        return float(g) != 0
    except (TypeError, ValueError):
        return False


def clean_rows_ex(rows):
    """清洗并区分结果, 供人工复核:
       kept  : 系统默认保留的行(与 clean_rows 一致)
       held  : 被任一清洗规则删除、但"最终采购数量≠0"的行 —— 只要有采购量就视为疑似真实数据,
               交人工二次确认。每条附带删除原因:
                 版本序号为空 / 版本序号为0 / 版本序号含文字 / (备用)采购量规则
               默认不纳入(与现有行为一致)。为便于人工判断, 另附 has_code(是否有有效编码)。
       d1/d2 : 步骤1/步骤2 删除计数(保持与旧统计口径一致)。
       返回 (kept, held, d1, d2); held 元素为 {"rec","reason","has_code"}。"""
    d1 = d2 = 0
    held = []
    has_ver = any(not _is_blank(rec[F_VER]) for rec in rows)
    out = []
    for rec in rows:
        if has_ver:
            v = rec[F_VER]
            reason = None
            if _is_blank(v):
                reason = "版本序号为空"
            elif _is_zero(v):
                reason = "版本序号为0"
            elif _has_chinese(str(v)):
                reason = "版本序号含文字(%s)" % str(v).strip()
            if reason is not None:
                d1 += 1
                # 只要有采购量就疑似真实数据, 挑出交人工确认(不再要求编码有效)
                if _final_has_qty(rec):
                    held.append({"rec": rec, "reason": reason,
                                 "has_code": _is_valid_code(rec[F_CODE])})
                continue
        out.append(rec)
    kept = []
    for rec in out:
        g = rec[F_FINAL]; nm = rec[F_NAME]
        if _is_zero(g) or _is_blank(g):
            if KEEP_TOKEN not in str(nm if nm is not None else ""):
                d2 += 1
                # 采购量为0/空的行本不该有量; 理论到不了这里, 保留兜底不误报。
                continue
        kept.append(rec)
    return kept, held, d1, d2


# ==================== 聚类归一化(提高跨表泛用性) ====================
# 目标: 同一物料在不同表里因"排版差异"(空格/全角半角/分隔符写法)被拆成多组的问题。
# 原则: 只用"归一化键"做聚类判断, 显示值仍取原始最常见写法, 不改变对齐 46A 的结果。
_FULL2HALF = {ord('　'): ' ', 0xA0: ' ', 0x3000: ' ',
              ord('（'): '(', ord('）'): ')', ord('，'): ',',
              ord('　'): ' '}
# 全角数字/字母 -> 半角
for _i in range(10):
    _FULL2HALF[ord('０') + _i] = chr(ord('0') + _i)
for _i in range(26):
    _FULL2HALF[ord('Ａ') + _i] = chr(ord('A') + _i)
    _FULL2HALF[ord('ａ') + _i] = chr(ord('a') + _i)

def _norm_key(s):
    """归一化聚类键: 统一大小写/全角半角/分隔符/空白, 仅用于分组判断, 不用于显示。
       尺寸分隔符 × ＊ * X 统一为小写 x; 折叠连续空白; 去首尾空白。"""
    if s is None:
        return ""
    t = str(s).translate(_FULL2HALF)
    t = t.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    for ch in ("×", "＊", "*", "X"):
        t = t.replace(ch, "x")
    while "  " in t:
        t = t.replace("  ", " ")
    return t.strip().lower()

_COMPOUND_SEP = "/／\\、,，·"

def _is_compound_unit(u):
    """复合/含糊单位(如 '个/套')判定: 含分隔符即视为复合, 聚类时降权。"""
    return any(ch in u for ch in _COMPOUND_SEP)


def _spec_base(sp):
    """去掉规格尾部的"包装数量注释"(如 ，250/包 / ，1000根/包)后的基准规格,
       用于判断两条规格是否本质相同。仅剥离末段含"包"且含数字者;
       末段若无"包"(如 110g/m²)则视为真实规格保留; 剥离后括号需平衡, 否则不剥。"""
    import re
    if sp is None:
        return ""
    s0 = str(sp).strip()
    if s0 == "":
        return ""
    parts = re.split(r"[，,]", s0)
    if len(parts) >= 2:
        last = parts[-1].strip()
        if ("包" in last) and any(ch.isdigit() for ch in last):
            base = "，".join(p.strip() for p in parts[:-1]).strip()
            if base and base.count("（") == base.count("）") \
               and base.count("(") == base.count(")"):
                return base
    return s0


def _spec_keyof(rec):
    code = str(rec[F_CODE]).strip() if rec[F_CODE] is not None else ""
    nm = str(rec[F_NAME]).strip() if rec[F_NAME] is not None else ""
    sp = str(rec[F_SPEC]).strip() if rec[F_SPEC] is not None else ""
    return code, nm, sp

def _spec_gkey(code, nm, sp):
    # 归一化分组键: 编码/名称/规格基准全部走 _norm_key
    return (_norm_key(code), _norm_key(nm), _norm_key(_spec_base(sp)))

def compute_spec_canon(rows):
    """计算规格归并: 返回 (canon, variants)。
       canon[gk]    = 系统默认采用的规格写法
       variants[gk] = OrderedDict(写法->出现次数), 供复核展示与人工改选。"""
    from collections import defaultdict, OrderedDict
    groups = defaultdict(lambda: OrderedDict())
    sample = {}
    for rec in rows:
        code, nm, sp = _spec_keyof(rec)
        if code == "" and nm == "":
            continue
        gk = _spec_gkey(code, nm, sp)
        groups[gk][sp] = groups[gk].get(sp, 0) + 1
        sample.setdefault(gk, (code, nm))
    canon = {}
    for k, spm in groups.items():
        pos = {sp: i for i, sp in enumerate(spm.keys())}
        canon[k] = min(spm.keys(), key=lambda sp: (-spm[sp], len(sp), pos[sp]))
    return canon, groups, sample


def unify_specs(rows, overrides=None):
    """同 编码+名称 下, 把"仅差包装数量注释"或"仅差排版写法"的规格合并为同一规格。
       overrides: {gk: 指定规格写法} 人工覆盖; 缺省时行为与自动一致(不影响 46A)。"""
    canon, _groups, _sample = compute_spec_canon(rows)
    if overrides:
        canon = dict(canon); canon.update(overrides)
    for rec in rows:
        code, nm, sp = _spec_keyof(rec)
        if code == "" and nm == "":
            continue
        gk = _spec_gkey(code, nm, sp)
        if gk in canon:
            rec[F_SPEC] = canon[gk]
    return rows


def _unit_simplicity(u):
    """单位"简单度"排序键, 越小越优先:
       空单位最不优先; 含分隔符(如 个/套)次之; 其余按字符长度, 短的更简单。"""
    if u == "":
        return (2, 0)
    has_sep = 1 if any(ch in u for ch in "/／\\、,，.·-") else 0
    return (has_sep, len(u))


def _name_unit_prior(rows):
    """名称级单位先验: 统计每个(归一化)名称在全部数据里最常用的"干净"单位。
       仅统计非空、非复合(不含 个/套 这类分隔符)的单位; 平票取最简单。
       用于在某组单位平票时提供一致性倾向(如'多层板'整体多为'张')。"""
    from collections import defaultdict, OrderedDict
    tally = defaultdict(lambda: OrderedDict())
    for rec in rows:
        nm = _norm_key(rec[F_NAME])
        u = str(rec[F_UNIT]).strip() if rec[F_UNIT] is not None else ""
        if not nm or not u or _is_compound_unit(u):
            continue
        tally[nm][u] = tally[nm].get(u, 0) + 1
    prior = {}
    for nm, umap in tally.items():
        pos = {u: i for i, u in enumerate(umap.keys())}
        prior[nm] = min(umap.keys(),
                        key=lambda u: (-umap[u], _unit_simplicity(u), pos[u]))
    return prior


def _unit_gkey(rec):
    code = _norm_key(rec[F_CODE]); nm = _norm_key(rec[F_NAME]); sp = _norm_key(rec[F_SPEC])
    if code == "" and nm == "" and sp == "":
        return None
    return (code, nm, sp)

def compute_unit_best(rows):
    """计算每个 编码+名称+规格 组的单位选择。返回 (best, counts, sample)。
       best[k]   = 系统默认单位
       counts[k] = OrderedDict(单位->次数), 供复核展示
       sample[k] = (code, name, spec) 原始展示值"""
    from collections import defaultdict, OrderedDict
    prior = _name_unit_prior(rows)
    counts = defaultdict(lambda: OrderedDict())
    sample = {}
    for rec in rows:
        k = _unit_gkey(rec)
        if k is None:
            continue
        u = str(rec[F_UNIT]).strip() if rec[F_UNIT] is not None else ""
        counts[k][u] = counts[k].get(u, 0) + 1
        if k not in sample:
            sample[k] = (("" if rec[F_CODE] is None else str(rec[F_CODE]).strip()),
                         ("" if rec[F_NAME] is None else str(rec[F_NAME]).strip()),
                         ("" if rec[F_SPEC] is None else str(rec[F_SPEC]).strip()))
    best = {}
    for k, umap in counts.items():
        clean = {u: c for u, c in umap.items() if u != ""}
        if not clean:
            best[k] = ""; continue
        noncomp = {u: c for u, c in clean.items() if not _is_compound_unit(u)}
        pool = noncomp if noncomp else clean
        pos = {u: i for i, u in enumerate(umap.keys())}
        mx = max(pool.values())
        tie = [u for u, c in pool.items() if c == mx]
        if len(tie) == 1:
            best[k] = tie[0]                       # 严格多数, 用本组数据
        else:
            np = prior.get(k[1], "")               # 平票: 用名称级先验
            if np in tie:
                best[k] = np
            elif np:
                best[k] = np                       # 先验单位(即使本组未出现)以求整体一致
            else:
                best[k] = min(tie, key=lambda u: (_unit_simplicity(u), pos[u]))
    return best, counts, sample


def unify_units(rows, overrides=None):
    """同 编码+名称+规格 的组统一单位。规则(按泛用性优化):
       1) 优先在"非空、非复合"单位中选; 若该组只有复合单位(如 个/套)才退而用之。
       2) 组内有唯一多数(严格胜出)-> 用它(尊重本组自身数据, 保证与标准表逐行一致)。
       3) 平票时 -> 采用该名称的"单位先验"打破平局, 先验缺失才退回"最简单单位"。
       overrides: {gk: 指定单位} 人工覆盖; 缺省时行为与自动一致(不影响 46A)。"""
    best, _counts, _sample = compute_unit_best(rows)
    if overrides:
        best = dict(best); best.update(overrides)
    for rec in rows:
        k = _unit_gkey(rec)
        if k is not None and k in best:
            rec[F_UNIT] = best[k]
    return rows


def aggregate(rows):
    """按 编码/名称/规格/单位 分组, 对最终采购数量求和. 返回有序分组列表"""
    from collections import OrderedDict
    groups = OrderedDict()
    for rec in rows:
        code = "" if rec[F_CODE] is None else str(rec[F_CODE]).strip()
        nm   = "" if rec[F_NAME] is None else str(rec[F_NAME]).strip()
        sp   = "" if rec[F_SPEC] is None else str(rec[F_SPEC]).strip()
        un   = "" if rec[F_UNIT] is None else str(rec[F_UNIT]).strip()
        try:
            q = float(rec[F_FINAL]) if not _is_blank(rec[F_FINAL]) else 0.0
        except (ValueError, TypeError):
            q = 0.0
        key = (code, nm, sp, un)
        groups[key] = groups.get(key, 0.0) + q
    # 排序: 按 编码/名称/规格/单位 纯字符串升序
    # (与 Excel 透视表文本字段的默认升序一致, 对齐 46A 标准透视表)
    items = sorted(groups.items(),
                   key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3]))
    result = []
    for (code, nm, sp, un), s in items:
        # 整数化显示
        if s == int(s):
            s = int(s)
        result.append([code, nm, sp, un, s])
    return result

# ---- 输出样式(与主程序一致: 微软雅黑, 蓝底表头, 细边框) ----
_FONT_NAME = "微软雅黑"
_thin = Side(style='thin')
_BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
_FONT = Font(name=_FONT_NAME, size=11)
_FONT_B = Font(name=_FONT_NAME, size=11, bold=True)
_BLUE = PatternFill(patternType='solid', fgColor=Color(theme=4, tint=0.3999755851924192))

def _st(cell, bold=False, fill=False):
    cell.border = _BORDER
    cell.alignment = _CENTER
    cell.font = _FONT_B if bold else _FONT
    if fill:
        cell.fill = _BLUE

def write_clean_sheet(ws, rows):
    """把清洗+统一单位后的数据写回源表(原样式清空): 行1空, 行2表头, 行3起数据, 列A-G.
       无任何主题样式(默认字体/无填充/无边框), 与样例一致."""
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
    """在 wb 里新建透视结果表(无样式, 与样例一致). 列: 编码/名称/规格/单位/
       求和项:最终采购数量 + 供应商/汇总/差异(公式)/实收/日期; 末尾总计行."""
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
        ws.cell(row=r, column=7, value=s)            # 汇总 = 数量
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


# ==================== 动态透视表(原生OOXML, 兼容Excel/WPS) ====================
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def _is_blank(v):
    return v is None or str(v).strip() == ""

def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return None

# 归一化字段: 0版本 1编码 2名称 3规格 4数量 5单位 6最终采购数量
FIELD_LABELS = ["版本序号", "材料编号", "材料名称", "规格", "数量", "单位", "最终采购数量"]
# 行字段(进透视): 编码(1) 名称(2) 规格(3) 单位(5); 度量: 最终采购数量(6)
ROW_FIELDS = [1, 2, 3, 5]
DATA_FIELD = 6

def build_fields_meta(rows):
    """对7个字段, 分组字段建 sharedItems 及 值->索引 映射; 度量算min/max"""
    meta = []
    for fi in range(7):
        col = [r[fi] for r in rows]
        is_group = fi in ROW_FIELDS
        info = {"idx": fi, "group": is_group, "shared": [], "map": {},
                "has_blank": False, "has_num": False, "has_str": False,
                "vmin": None, "vmax": None}
        if is_group:
            seen = {}
            for v in col:
                key = "" if _is_blank(v) else str(v).strip()
                if key not in seen:
                    seen[key] = len(info["shared"])
                    info["shared"].append(key)
            info["map"] = seen
            info["has_blank"] = "" in seen
        else:
            for v in col:
                if _is_blank(v):
                    info["has_blank"] = True
                elif _num(v) is not None:
                    info["has_num"] = True
                    n = _num(v)
                    info["vmin"] = n if info["vmin"] is None else min(info["vmin"], n)
                    info["vmax"] = n if info["vmax"] is None else max(info["vmax"], n)
                else:
                    info["has_str"] = True
        meta.append(info)
    return meta


def cache_definition_xml(meta, record_count, rid_records):
    """pivotCacheDefinition: 声明字段与 sharedItems; refreshOnLoad 让 Excel/WPS 打开即刷新"""
    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    parts.append('<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                 'r:id="%s" refreshOnLoad="1" refreshedBy="prog" refreshedDate="0" '
                 'createdVersion="3" refreshedVersion="3" minRefreshableVersion="3" '
                 'recordCount="%d">' % (rid_records, record_count))
    parts.append('<cacheSource type="worksheet"><worksheetSource ref="__SRC_REF__" sheet="__SRC_SHEET__"/></cacheSource>')
    parts.append('<cacheFields count="7">')
    for m in meta:
        name = _esc(FIELD_LABELS[m["idx"]])
        if m["group"]:
            items = []
            for s in m["shared"]:
                items.append("<m/>" if s == "" else '<s v="%s"/>' % _esc(s))
            parts.append('<cacheField name="%s" numFmtId="0">' % name)
            parts.append('<sharedItems count="%d">%s</sharedItems>' % (len(items), "".join(items)))
            parts.append('</cacheField>')
        else:
            attrs = []
            if m["has_str"]:
                attrs.append('containsString="1"')
            else:
                attrs.append('containsString="0"')
            if m["has_blank"]:
                attrs.append('containsBlank="1"')
            if m["has_num"] and not m["has_str"]:
                attrs.append('containsNumber="1"')
                if m["vmin"] is not None and float(m["vmin"]) == int(m["vmin"]) and \
                   m["vmax"] is not None and float(m["vmax"]) == int(m["vmax"]):
                    attrs.append('containsInteger="1"')
                attrs.append('minValue="%s"' % m["vmin"])
                attrs.append('maxValue="%s"' % m["vmax"])
            parts.append('<cacheField name="%s" numFmtId="0">' % name)
            parts.append('<sharedItems %s/>' % " ".join(attrs))
            parts.append('</cacheField>')
    parts.append('</cacheFields>')
    parts.append('</pivotCacheDefinition>')
    return "".join(parts)


def cache_records_xml(rows, meta):
    """pivotCacheRecords: 每行7字段. 分组字段用<x v=索引/>, 其他数值<n>/文本<s>/空<m>"""
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    parts.append('<pivotCacheRecords xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                 'count="%d">' % len(rows))
    for r in rows:
        cells = []
        for m in meta:
            v = r[m["idx"]]
            if m["group"]:
                key = "" if _is_blank(v) else str(v).strip()
                cells.append('<x v="%d"/>' % m["map"][key])
            else:
                if _is_blank(v):
                    cells.append("<m/>")
                else:
                    n = _num(v)
                    if n is not None and not m["has_str"]:
                        cells.append('<n v="%s"/>' % n)
                    else:
                        cells.append('<s v="%s"/>' % _esc(v))
        parts.append("<r>%s</r>" % "".join(cells))
    parts.append('</pivotCacheRecords>')
    return "".join(parts)


def pivot_table_xml(meta, agg, cache_id, name="数据透视表"):
    """
    pivotTable 定义. 行字段 编码/名称/规格/单位, 度量=求和最终采购数量.
    agg: [[code,name,spec,unit,sum], ...] 已排序. 单元格数值另由 openpyxl 渲染.
    布局: 表格式(outline=0), 无分类汇总, 重复所有标签(fillDownLabels).
    ref 覆盖 A1 到 E(行数+2)(表头1行 + 数据N行 + 总计1行).
    """
    n = len(agg)
    last_row = 1 + n + 1                       # 表头+数据+总计
    ref = "A1:E%d" % last_row

    # 各行字段的 值->共享索引 映射
    mp = {fi: meta_by_idx(meta, fi)["map"] for fi in ROW_FIELDS}

    # rowItems: 每个数据行一个 <i>, 末尾一个 grand total <i t="grand">
    ritems = []
    prev = [None, None, None, None]
    for grp in agg:
        vals = [grp[0], grp[1], grp[2], grp[3]]   # code,name,spec,unit
        rcommon = 0
        while rcommon < 4 and prev[rcommon] == vals[rcommon]:
            rcommon += 1
        xs = "".join('<x v="%d"/>' % mp[ROW_FIELDS[k]][("" if _is_blank(vals[k]) else str(vals[k]).strip())]
                     for k in range(rcommon, 4))
        if rcommon == 0:
            ritems.append("<i>%s</i>" % xs)
        else:
            ritems.append('<i r="%d">%s</i>' % (rcommon, xs))
        prev = vals
    ritems.append('<i t="grand"><x/></i>')

    # pivotFields: 7个字段, 行字段标 axis="axisRow" 并列出其 items
    pf = []
    for m in meta:
        fi = m["idx"]
        if fi in ROW_FIELDS:
            cnt = len(m["shared"])
            # 按共享值字符串升序排列 item 顺序 -> Excel 刷新后按升序显示(匹配标准)
            order = sorted(range(cnt), key=lambda i: m["shared"][i])
            items = "".join('<item x="%d"/>' % i for i in order)
            pf.append('<pivotField axis="axisRow" showAll="0" outline="0" compact="0" '
                      'subtotalTop="0" defaultSubtotal="0">'
                      '<items count="%d">%s</items></pivotField>' % (cnt, items))
        elif fi == DATA_FIELD:
            pf.append('<pivotField dataField="1" showAll="0"/>')
        else:
            pf.append('<pivotField showAll="0"/>')

    rowfields = "".join('<field x="%d"/>' % fi for fi in ROW_FIELDS)

    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    parts.append('<pivotTableDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                 'name="%s" cacheId="%d" applyNumberFormats="0" applyBorderFormats="0" '
                 'applyFontFormats="0" applyPatternFormats="0" applyAlignmentFormats="0" '
                 'applyWidthHeightFormats="1" dataCaption="值" '
                 'updatedVersion="3" minRefreshableVersion="3" createdVersion="3" '
                 'indent="0" outline="0" outlineData="0" compactData="0" multipleFieldFilters="0" '
                 'rowGrandTotals="1" colGrandTotals="0">' % (_esc(name), cache_id))
    parts.append('<location ref="%s" firstHeaderRow="1" firstDataRow="1" firstDataCol="4"/>' % ref)
    parts.append('<pivotFields count="7">%s</pivotFields>' % "".join(pf))
    parts.append('<rowFields count="%d">%s</rowFields>' % (len(ROW_FIELDS), rowfields))
    parts.append('<rowItems count="%d">%s</rowItems>' % (len(ritems), "".join(ritems)))
    parts.append('<colItems count="1"><i/></colItems>')
    parts.append('<dataFields count="1">'
                 '<dataField name="求和项:最终采购数量" fld="%d" baseField="0" baseItem="0"/>'
                 '</dataFields>' % DATA_FIELD)
    parts.append('<pivotTableStyleInfo name="PivotStyleLight16" showRowHeaders="1" '
                 'showColHeaders="1" showRowStripes="0" showColStripes="0" showLastColumn="1"/>')
    parts.append('</pivotTableDefinition>')
    return "".join(parts)


def meta_by_idx(meta, fi):
    for m in meta:
        if m["idx"] == fi:
            return m
    return None


def _attr(tag, name):
    m = re.search(r'\b' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else None

def _sheet_target_for(zin_names, data):
    """从 workbook.xml + rels 找到 sheet 名 -> 归档内 worksheet 路径(如 xl/worksheets/sheet3.xml).
       兼容属性任意顺序与绝对/相对 Target."""
    wb = data["xl/workbook.xml"].decode("utf-8")
    rels = data["xl/_rels/workbook.xml.rels"].decode("utf-8")
    # sheet name -> r:id (属性顺序无关)
    name2rid = {}
    for m in re.finditer(r'<sheet\b[^>]*/?>', wb):
        tag = m.group(0)
        nm = _attr(tag, "name"); rid = _attr(tag, "r:id")
        if nm and rid:
            name2rid[nm] = rid
    # r:id -> target (属性顺序无关)
    rid2t = {}
    for m in re.finditer(r'<Relationship\b[^>]*/?>', rels):
        tag = m.group(0)
        rid = _attr(tag, "Id"); tgt = _attr(tag, "Target")
        if rid and tgt:
            rid2t[rid] = tgt
    out = {}
    for nm, rid in name2rid.items():
        t = rid2t.get(rid, "")
        if not t:
            continue
        if t.startswith("/"):
            arc = t.lstrip("/")               # 绝对: /xl/worksheets/sheet3.xml
        else:
            arc = "xl/" + t                   # 相对于 xl/
        arc = re.sub(r'/[^/]+/\.\./', '/', arc)
        out[nm] = arc
    return out


def inject_pivots(xlsx_path, pivots):
    """
    pivots: [{'sheet':透视sheet名, 'src_sheet':源sheet名, 'src_ref':'A2:G100',
              'rows':清洗行, 'agg':聚合, 'name':透视表名}]
    就地把动态透视表部件写入 xlsx.
    """
    with zipfile.ZipFile(xlsx_path, "r") as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}

    sheet_target = _sheet_target_for(names, data)
    new_parts = {}
    ct_overrides = []
    wb_caches = []          # (cacheId, rId) for workbook.xml
    wb_rels_add = []        # workbook.xml.rels 新增

    # 现有 workbook rels 里最大 rId
    wb_rels = data["xl/_rels/workbook.xml.rels"].decode("utf-8")
    used = [int(x) for x in re.findall(r'Id="rId(\d+)"', wb_rels)]
    next_rid = max(used) + 1 if used else 1

    for i, pv in enumerate(pivots, start=1):
        cache_id = 1000 + i
        cdef = "xl/pivotCache/pivotCacheDefinition%d.xml" % i
        crec = "xl/pivotCache/pivotCacheRecords%d.xml" % i
        ptbl = "xl/pivotTables/pivotTable%d.xml" % i

        meta = build_fields_meta(pv["rows"])
        # cacheDefinition (rid 指向 records, 局部 rId1)
        cdx = cache_definition_xml(meta, len(pv["rows"]), "rId1")
        cdx = cdx.replace("__SRC_REF__", _esc(pv["src_ref"])).replace("__SRC_SHEET__", _esc(pv["src_sheet"]))
        new_parts[cdef] = cdx.encode("utf-8")
        new_parts[crec] = cache_records_xml(pv["rows"], meta).encode("utf-8")
        new_parts["xl/pivotCache/_rels/pivotCacheDefinition%d.xml.rels" % i] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/pivotCacheRecords" Target="pivotCacheRecords%d.xml"/></Relationships>' % i
        ).encode("utf-8")

        new_parts[ptbl] = pivot_table_xml(meta, pv["agg"], cache_id, pv["name"]).encode("utf-8")
        new_parts["xl/pivotTables/_rels/pivotTable%d.xml.rels" % i] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/pivotCacheDefinition" Target="../pivotCache/pivotCacheDefinition%d.xml"/>'
            '</Relationships>' % i
        ).encode("utf-8")

        ct_overrides.append('<Override PartName="/%s" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.pivotCacheDefinition+xml"/>' % cdef)
        ct_overrides.append('<Override PartName="/%s" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.pivotCacheRecords+xml"/>' % crec)
        ct_overrides.append('<Override PartName="/%s" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.pivotTable+xml"/>' % ptbl)

        rid = "rId%d" % next_rid; next_rid += 1
        wb_caches.append((cache_id, rid))
        wb_rels_add.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/pivotCacheDefinition" '
            'Target="pivotCache/pivotCacheDefinition%d.xml"/>' % (rid, i))

        # sheet rels: 透视 sheet -> pivotTable
        st = sheet_target.get(pv["sheet"])
        if st:
            base = os.path.basename(st)
            relpath = os.path.dirname(st) + "/_rels/" + base + ".rels"
            if relpath in data:
                sr = data[relpath].decode("utf-8")
                sused = [int(x) for x in re.findall(r'Id="rId(\d+)"', sr)]
                srid = "rId%d" % ((max(sused)+1) if sused else 1)
                add = ('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/'
                       '2006/relationships/pivotTable" Target="../pivotTables/pivotTable%d.xml"/>' % (srid, i))
                data[relpath] = sr.replace("</Relationships>", add + "</Relationships>").encode("utf-8")
            else:
                data[relpath] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    'relationships/pivotTable" Target="../pivotTables/pivotTable%d.xml"/></Relationships>' % i
                    ).encode("utf-8")

    # [Content_Types].xml
    ct = data["[Content_Types].xml"].decode("utf-8")
    data["[Content_Types].xml"] = ct.replace("</Types>", "".join(ct_overrides) + "</Types>").encode("utf-8")

    # workbook.xml.rels
    data["xl/_rels/workbook.xml.rels"] = wb_rels.replace(
        "</Relationships>", "".join(wb_rels_add) + "</Relationships>").encode("utf-8")

    # workbook.xml: 插入 <pivotCaches>; 确保根元素声明 xmlns:r
    wbx = data["xl/workbook.xml"].decode("utf-8")
    if "xmlns:r=" not in wbx[:wbx.find(">")+1]:
        wbx = wbx.replace("<workbook ",
            '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    caches_xml = '<pivotCaches>' + "".join(
        '<pivotCache cacheId="%d" r:id="%s"/>' % (cid, rid) for cid, rid in wb_caches) + '</pivotCaches>'
    # OOXML schema 要求 pivotCaches 必须在 calcPr 之后(顺序: sheets, definedNames,
    # calcPr, ..., pivotCaches, extLst). 顺序错会导致 Excel 报"文件损坏".
    m = re.search(r'<calcPr\b[^>]*/>', wbx)
    if m:
        wbx = wbx[:m.end()] + caches_xml + wbx[m.end():]
    else:
        m2 = re.search(r'</calcPr>', wbx)
        if m2:
            wbx = wbx[:m2.end()] + caches_xml + wbx[m2.end():]
        elif "<extLst" in wbx:
            wbx = wbx.replace("<extLst", caches_xml + "<extLst", 1)
        else:
            wbx = wbx.replace("</workbook>", caches_xml + "</workbook>", 1)
    data["xl/workbook.xml"] = wbx.encode("utf-8")

    for p, b in new_parts.items():
        data[p] = b

    tmp = xlsx_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    os.replace(tmp, xlsx_path)



def process_workbook(in_path, out_path=None):
    """
    复刻 RunProcess: 打开工作簿, 对每张数据表清洗并生成一张透视结果表.
    不改动原文件(输出到 out_path, 默认在原名后加 _透视结果).
    返回 {'processed':n, 'skipped':n, 'sheets':[(源表名,透视表名,d1,d2,组数,总计)], 'out':路径}
    """
    import os
    wb = openpyxl.load_workbook(in_path, data_only=True)
    src_names = list(wb.sheetnames)   # 先快照, 避免扫到新建的透视表
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
    wb.save(out_path)
    # 3) 注入原生 OOXML 动态透视表(兼容 Excel/WPS); 失败则保留静态表
    if pivot_jobs:
        try:
            inject_pivots(out_path, pivot_jobs)
        except Exception:
            pass
    return {'processed': processed, 'skipped': skipped,
            'sheets': detail, 'out': out_path}


def _safe_sheet_name(wb, base):
    """生成 Excel 合法且唯一的工作表名(<=31字符, 去非法字符)。"""
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


def assess_confidence(res):
    """扣分制评估透视结果是否可信。返回 {level, score, issues[]}
       level ∈ 可信 / 需复核 / 存疑。100 分起扣。"""
    score = 100
    issues = []          # (等级, 说明)  等级: 严重/警告/提示
    used = [a for a in res["audit"] if a["use"]]
    kinds = [a["kind"] for a in used]

    # 1) 完全没识别到任何数据表 -> 存疑
    if res["processed"] == 0 or res["clean_rows"] == 0:
        score = 0
        issues.append(("严重", "未识别到任何有效数据表, 无法生成可信透视表"))
    # 2) 未识别到包装方案汇总(核心源)
    if not any("包装方案汇总" in k for k in kinds):
        score -= 35
        issues.append(("严重", "未识别到'包装方案汇总'类表(通常是采购量核心来源), 结果可能严重缺料"))
    # 3) 未识别到组托辅材
    if not any("组托辅材" in k for k in kinds):
        score -= 12
        issues.append(("警告", "未识别到'组托辅材'类表, 若本单本应含组托数据则会漏项"))
    # 4) 逐文件: 某文件 0 张数据表
    by_file = {}
    for a in res["audit"]:
        by_file.setdefault(a["file"], []).append(a)
    for f, arr in by_file.items():
        if not any(x["use"] for x in arr):
            score -= 15
            issues.append(("警告", "文件[%s]未识别出任何数据表, 请确认是否选错文件" % f))
    # 5) 字段缺失
    for a in used:
        if a["missing"]:
            miss = "/".join(a["missing"])
            key_miss = any(m in ("材料编号", "最终采购数量") for m in a["missing"])
            score -= (10 if key_miss else 4)
            issues.append(("严重" if key_miss else "提示",
                           "表[%s/%s]缺失字段: %s" % (a["file"], a["sheet"], miss)))
        if a["use"] and a["confidence"] and a["confidence"] < 75:
            issues.append(("提示", "表[%s/%s]为低置信识别(%d分, %s)" %
                           (a["file"], a["sheet"], a["confidence"], a["kind"])))
    # 6) 总计为 0
    if res["clean_rows"] > 0 and res["total"] == 0:
        score -= 30
        issues.append(("严重", "透视总计为 0, 数据虽有行但最终采购数量全为空/0, 请核对源列"))
    # 7) 勾稽: 透视分组数应 <= 清洗行数
    if res["groups"] > res["clean_rows"] and res["clean_rows"] > 0:
        score -= 20
        issues.append(("严重", "分组数(%d)大于清洗行数(%d), 逻辑异常" %
                       (res["groups"], res["clean_rows"])))

    score = max(0, min(100, score))
    level = "可信" if score >= 85 else ("需复核" if score >= 60 else "存疑")
    return {"level": level, "score": score, "issues": issues}


def _fmt_cols(cols):
    """把字段列映射渲染为可读文本: 编码=K列 名称=L列 ..."""
    if not cols:
        return "(无)"
    names = ["版本", "编码", "名称", "规格", "数量", "单位", "最终采购数量"]
    parts = []
    for i, c in enumerate(cols):
        if c:
            parts.append("%s=%s列" % (names[i], get_column_letter(c)))
    return "  ".join(parts) if parts else "(无)"


def write_confidence_report(out_path, in_paths, res):
    """生成独立的可信度分析报告 .txt, 与透视结果同目录。返回报告路径。"""
    import os
    base = os.path.splitext(os.path.basename(out_path))[0]
    rpt = os.path.join(os.path.dirname(out_path), base + "_可信度分析报告.txt")
    L = []
    bar = "=" * 66
    L.append(bar)
    L.append("           透视表制作 · 可信度分析报告")
    L.append(bar)
    L.append("生成时间   : %s" % (datetime.datetime.utcnow() +
             datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"))
    L.append("透视结果   : %s" % os.path.basename(out_path))
    L.append("")
    L.append("【总体结论】  可信度: %s   评分: %d/100" % (res["level"], res["score"]))
    tip = {"可信": "识别与汇总逻辑一致, 可直接使用(仍建议抽查关键料号)。",
           "需复核": "存在需关注项, 请对照下方风险清单核对后使用。",
           "存疑": "存在严重问题, 结果可能不可用, 务必人工核对源数据。"}
    L.append("            %s" % tip.get(res["level"], ""))
    L.append("")
    _write_report_body(L, in_paths, res, bar)
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return rpt


def _write_review_section(L, res, bar):
    """报告【人工复核项】: 记录空白序号行、单位/规格聚类冲突及最终采用值,
       并标注人工是否改动过默认, 便于日后快速核对。"""
    rv = res.get("review")
    if not rv:
        return
    L.append(bar)
    L.append("【人工复核项】(生成前弹窗展示; 默认=系统选择)")
    L.append(bar)
    # A. 疑似真实但被删的行(有采购量却被清洗规则删除)
    plan = rv.get("plan", {})
    held = plan.get("held_index", []) if plan else []
    L.append("● 疑似真实但被删的行 —— 有最终采购量却被清洗删除 (共 %d 条, 本次纳入 %d 条, 纳入采购量合计 %s):"
             % (rv.get("held_total_n", 0), rv.get("held_kept_n", 0),
                _fmt_num(rv.get("held_kept_total", 0))))
    if not held:
        L.append("    (无) 未发现此类行。")
    else:
        ch_held = rv.get("choices", {}).get("held", {})
        for h in held:
            r = h["rec"]; kept = ch_held.get((h["sid"], h["ridx"]), False)
            nocode = "" if h.get("has_code") else " [无有效编码]"
            L.append("    [%s] %s %s %s %s  采购量=%s  删除原因:%s%s  来源:%s"
                     % ("已纳入" if kept else "已删除", r[F_CODE], r[F_NAME],
                        r[F_SPEC], r[F_UNIT], _fmt_num(r[F_FINAL]),
                        h.get("reason", "?"), nocode, h["sheet"]))
    L.append("")
    # B. 单位聚类冲突
    uc = rv.get("unit_conflicts", [])
    ov_u = rv.get("choices", {}).get("unit_overrides", {})
    L.append("● 单位聚类冲突 (共 %d 处, 人工改动 %d 处):" % (len(uc), len(ov_u)))
    if not uc:
        L.append("    (无) 所有分组单位唯一。")
    for c in uc:
        gk = c["gk"]; final = ov_u.get(gk, c["default"])
        dist = " / ".join("%s×%d" % (u if u else "(空)", n) for u, n in c["dist"].items())
        flag = "  <-人工改" if gk in ov_u else ""
        L.append("    %s %s %s | 分布: %s | 采用: %s%s"
                 % (c["code"], c["name"], c["spec"], dist, final, flag))
    L.append("")
    # C. 规格聚类归并
    sm = rv.get("spec_merges", [])
    ov_s = rv.get("choices", {}).get("spec_overrides", {})
    L.append("● 规格聚类归并 (共 %d 处, 人工改动 %d 处):" % (len(sm), len(ov_s)))
    if not sm:
        L.append("    (无) 无同料多写法归并。")
    for c in sm:
        gk = c["gk"]; final = ov_s.get(gk, c["default"])
        variants = " / ".join("%s×%d" % (s, n) for s, n in c["variants"].items())
        flag = "  <-人工改" if gk in ov_s else ""
        L.append("    %s %s | 写法: %s | 采用: %s%s"
                 % (c["code"], c["name"], variants, final, flag))
    L.append("")


def _write_report_body(L, in_paths, res, bar):
    import os
    # 1) 风险清单
    L.append("【风险清单】")
    if res["issues"]:
        order = {"严重": 0, "警告": 1, "提示": 2}
        for lv, msg in sorted(res["issues"], key=lambda x: order.get(x[0], 3)):
            mark = {"严重": "✗", "警告": "!", "提示": "·"}.get(lv, "·")
            L.append("  [%s] %s %s" % (lv, mark, msg))
    else:
        L.append("  (无) 未发现风险项。")
    L.append("")
    # 2) 数据来源与识别依据
    L.append(bar)
    L.append("【数据来源识别明细】(共扫描 %d 个文件)" % res["files"])
    L.append(bar)
    used = [a for a in res["audit"] if a["use"]]
    skip = [a for a in res["audit"] if not a["use"]]
    L.append("● 已纳入透视的数据表 (%d 张):" % len(used))
    if not used:
        L.append("    (无)")
    for a in used:
        L.append("  ─ [%s] 工作表《%s》" % (a["file"], a["sheet"]))
        L.append("     类型: %s   置信度: %d" % (a["kind"], a["confidence"]))
        L.append("     依据: %s" % a["reason"])
        L.append("     字段: %s" % _fmt_cols(a["cols"]))
        L.append("     贡献: 保留 %d 行 (清洗删除 版本%d / 采购量%d)" %
                 (a["rows"], a["d1"], a["d2"]))
        if a["missing"]:
            L.append("     ⚠ 缺失字段: %s" % "/".join(a["missing"]))
    L.append("")
    L.append("● 已跳过的工作表 (%d 张):" % len(skip))
    if not skip:
        L.append("    (无)")
    for a in skip:
        L.append("  ─ [%s]《%s》: %s — %s" %
                 (a["file"], a["sheet"], a["kind"], a["reason"]))
    L.append("")
    # 2.5) 人工复核项(供日后快速核对)
    _write_review_section(L, res, bar)
    # 3) 汇总与勾稽
    L.append(bar)
    L.append("【汇总与勾稽校验】")
    L.append(bar)
    tot = res["total"]
    try:
        if float(tot) == int(tot):
            tot = int(tot)
    except (ValueError, TypeError):
        pass
    L.append("  清洗后合并数据行 : %d 行" % res["clean_rows"])
    L.append("  透视分组(去重后) : %d 组" % res["groups"])
    L.append("  最终采购数量总计 : %s" % tot)
    L.append("  清洗删除小计     : 版本序号 %d 行 / 最终采购量为空或0 %d 行"
             % (res["d1"], res["d2"]))
    chk = "通过" if (res["groups"] <= res["clean_rows"] and res["clean_rows"] > 0) else "异常"
    L.append("  勾稽(分组数<=行数): %s" % chk)
    L.append("")
    L.append(bar)
    L.append("说明: 本报告由程序按规则自动生成, 仅供复核参考。评分为扣分制,")
    L.append("      严重项每项重扣、警告次之、提示轻扣; >=85 可信, 60-84 需复核, <60 存疑。")
    L.append(bar)


def analyze_workbooks(in_paths):
    """第一阶段: 只读文件、分类、清洗, 收集所有"待人工复核的决策点", 不写任何文件。
       返回 plan:
         plan['sheets']         每张候选表 {id,file,sheet,use(默认),kind,confidence,
                                 reason,cols,missing,kept[行],held[行],d1,d2}
         plan['held_index']     扁平化的空白序号行 [{sid,ridx,rec,file,sheet}]
         plan['unit_conflicts'] 单位冲突组 [{gk,code,name,spec,dist,default}]
         plan['spec_merges']    规格归并组 [{gk,code,name,variants,default}]
       默认选择 = 现有系统行为(use=分类结果, held 全不纳入)。"""
    import os
    sheets = []
    sid = 0
    for in_path in in_paths:
        fname = os.path.splitext(os.path.basename(in_path))[0]
        try:
            wb = openpyxl.load_workbook(in_path, data_only=True)
        except Exception:
            sheets.append({"id": sid, "file": os.path.basename(in_path), "sheet": "(整个文件)",
                           "use": False, "openable": False, "kind": "排除:无法打开",
                           "confidence": 0, "reason": "openpyxl 打开失败, 可能非法xlsx或被占用",
                           "cols": None, "missing": [], "kept": [], "held": [], "d1": 0, "d2": 0})
            sid += 1; continue
        for sn in list(wb.sheetnames):
            ws = wb[sn]
            cls = classify_sheet(ws)
            rec = {"id": sid, "file": fname, "sheet": sn, "use": cls["use"], "openable": True,
                   "kind": cls["kind"], "confidence": cls["confidence"], "reason": cls["reason"],
                   "cols": cls["cols"], "missing": cls["missing"],
                   "kept": [], "held": [], "d1": 0, "d2": 0, "no_block": False}
            # 独立探测数据区 —— 不依赖 classify_sheet 的结论。因为表名命中排除词或被判为
            # "疑似已有透视"时, classify 会提前返回、cols 为 None, 但表里可能确有可用数据区。
            # 只要结构上找得到"材料编号+最终采购数量", 就预读好行数据; 这样人工在弹窗勾选
            # 一张被误排除的表后, 数据能真正纳入(否则勾了也是空表)。默认是否纳入仍由 cls 决定。
            blocks = find_all_blocks(ws)
            if blocks:
                if rec["cols"] is None:
                    rec["cols"] = blocks[0]["cols"]
                    rec["missing"] = [FIELD_CN[i] for i in (KEY_FIELDS + INFO_FIELDS)
                                      if blocks[0]["cols"][i] == 0]
                rows = normalize_rows(ws)
                kept, held, d1, d2 = clean_rows_ex(rows)
                rec.update(kept=kept, held=held, d1=d1, d2=d2)
                if cls["use"] and not kept and not held:
                    rec.update(use=False, kind="排除:清洗后无数据",
                               reason="识别为%s, 但清洗后无有效行(全被版本/采购量规则删除)" % cls["kind"])
            else:
                # 结构上找不到数据区(无可识别表头), 无法自动取数, 人工勾选也无从下手
                rec["no_block"] = True
            sheets.append(rec); sid += 1
        try:
            wb.close()
        except Exception:
            pass

    # 扁平化"疑似真实但被删"的行, 给每行稳定 id, 供弹窗逐行勾选
    held_index = []
    for s in sheets:
        for ridx, hd in enumerate(s["held"]):
            held_index.append({"sid": s["id"], "ridx": ridx, "rec": hd["rec"],
                               "reason": hd["reason"], "has_code": hd["has_code"],
                               "file": s["file"], "sheet": s["sheet"]})

    # 冲突收集: 在"默认纳入表的 kept 行"上计算(与现有输出口径一致)
    default_rows = []
    for s in sheets:
        if s["use"]:
            default_rows.extend([list(r) for r in s["kept"]])
    # 规格归并 (需先归并规格, 单位冲突才在同一规格下判定)
    import copy
    spec_pool = copy.deepcopy(default_rows)
    scanon, sgroups, ssample = compute_spec_canon(spec_pool)
    spec_merges = []
    for gk, variants in sgroups.items():
        if len([v for v in variants if v]) > 1:
            code, nm = ssample.get(gk, ("", ""))
            spec_merges.append({"gk": gk, "code": code, "name": nm,
                                "variants": variants, "default": scanon[gk]})
    # 应用默认规格归并后, 计算单位冲突
    unify_specs(spec_pool)  # 就地把规格统一到默认, 便于单位分组
    ubest, ucounts, usample = compute_unit_best(spec_pool)
    unit_conflicts = []
    for gk, dist in ucounts.items():
        if len([u for u in dist if u]) > 1:
            code, nm, sp = usample.get(gk, ("", "", ""))
            unit_conflicts.append({"gk": gk, "code": code, "name": nm, "spec": sp,
                                   "dist": dist, "default": ubest[gk]})

    return {"in_paths": in_paths, "files": len(in_paths), "sheets": sheets,
            "held_index": held_index, "unit_conflicts": unit_conflicts,
            "spec_merges": spec_merges}


def _default_choices(plan):
    """由 plan 生成"系统默认选择"(人工不改时即用这套, 等价于现有行为)。"""
    return {
        "sheets": {s["id"]: bool(s["use"]) for s in plan["sheets"]},
        "held":   {(h["sid"], h["ridx"]): False for h in plan["held_index"]},
        "unit_overrides": {},   # {gk: unit}
        "spec_overrides": {},   # {gk: spec}
    }


def apply_plan(plan, choices, out_path):
    """第二阶段: 按人工最终选择合并、聚类、聚合并写出透视结果与报告。
       choices 见 _default_choices。返回结果 dict(兼容旧结构 + review 明细)。"""
    import os, copy
    sheets = plan["sheets"]
    audit = []
    detail = []
    processed = 0; skipped = 0
    d1_sum = d2_sum = 0
    all_rows = []
    held_kept_total = 0.0
    held_kept_n = 0

    sel_sheets = choices.get("sheets", {})
    sel_held = choices.get("held", {})

    for s in sheets:
        use = sel_sheets.get(s["id"], s["use"])
        rec = {"file": s["file"], "sheet": s["sheet"], "use": use, "kind": s["kind"],
               "confidence": s["confidence"], "reason": s["reason"],
               "cols": s["cols"], "missing": s["missing"], "rows": 0,
               "d1": s["d1"], "d2": s["d2"], "held_kept": 0}
        if not use:
            audit.append(rec); skipped += 1; continue
        rows = [list(r) for r in s["kept"]]
        # 追加人工勾选保留的"疑似真实但被删"的行
        hk = 0
        for ridx, hd in enumerate(s["held"]):
            if sel_held.get((s["id"], ridx), False):
                hrec = hd["rec"]
                rows.append(list(hrec)); hk += 1
                try: held_kept_total += float(hrec[F_FINAL])
                except (TypeError, ValueError): pass
        held_kept_n += hk
        if not rows:
            rec.update(use=False, kind="排除:未选中任何行")
            audit.append(rec); skipped += 1; continue
        all_rows.extend(rows)
        d1_sum += s["d1"]; d2_sum += s["d2"]
        rec.update(rows=len(rows), held_kept=hk)
        audit.append(rec)
        detail.append(("%s / %s" % (s["file"], s["sheet"]), len(rows), s["d1"], s["d2"]))
        processed += 1

    out_wb = openpyxl.Workbook()
    default_ws = out_wb.active
    groups = 0; total = 0
    if all_rows:
        all_rows = unify_specs(all_rows, overrides=choices.get("spec_overrides") or None)
        all_rows = unify_units(all_rows, overrides=choices.get("unit_overrides") or None)
        agg = aggregate(all_rows)
        groups = len(agg)
        total = sum((x[4] for x in agg), 0)
        clean_name = _safe_sheet_name(out_wb, "清洗数据")
        cws = out_wb.create_sheet(title=clean_name)
        write_clean_sheet(cws, all_rows)
        pv_name = write_pivot_sheet(out_wb, PIVOT_BASE, agg)
        src_ref = "A2:G%d" % (2 + len(all_rows))
        pivot_jobs = [{"sheet": pv_name, "src_sheet": clean_name, "src_ref": src_ref,
                       "rows": all_rows, "agg": agg, "name": pv_name}]
        if len(out_wb.sheetnames) > 1 and default_ws.title in out_wb.sheetnames:
            out_wb.remove(default_ws)
    else:
        pivot_jobs = []

    out_wb.save(out_path)
    if pivot_jobs:
        try:
            inject_pivots(out_path, pivot_jobs)
        except Exception:
            pass

    result = {'processed': processed, 'skipped': skipped, 'sheets': detail,
              'out': out_path, 'files': plan["files"], 'groups': groups,
              'total': total, 'd1': d1_sum, 'd2': d2_sum, 'audit': audit,
              'clean_rows': len(all_rows),
              'review': {'plan': plan, 'choices': choices,
                         'held_kept_n': held_kept_n, 'held_kept_total': held_kept_total,
                         'held_total_n': len(plan["held_index"]),
                         'unit_conflicts': plan["unit_conflicts"],
                         'spec_merges': plan["spec_merges"]}}
    verdict = assess_confidence(result)
    result.update(verdict)
    try:
        report_path = write_confidence_report(out_path, plan["in_paths"], result)
        result['report'] = report_path
    except Exception as e:
        result['report'] = ""
        result['report_error'] = str(e)
    return result


def process_workbooks(in_paths, out_path, choices=None):
    """整合入口(向后兼容): analyze -> (默认或给定 choices) -> apply。
       不传 choices 时等价于现有全自动行为。"""
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

# ---------------- 统一入口（与其它三功能同构：接受统一 out_dir）----------------
def run(in_paths, choices=None, out_dir=None, log=None):
    """透视表制作统一入口。
    in_paths : 采购数据表路径列表。
    choices  : 人工复核选择；None=全自动默认。
    out_dir  : 输出目录；不传则用统一 paths 系统。
    返回 apply_plan 的结果 dict（含 out/report/level/score 等）。
    """
    log = log or (lambda *a, **k: None)
    st = _settings.get_settings()
    if isinstance(in_paths, str):
        in_paths = [in_paths]
    if out_dir is None:
        out_dir = _paths.resolve_output_dir("pivot", **st.output_kwargs())
    fname = "%s透视结果.xlsx" % _beijing_date()
    out_path = os.path.join(out_dir, fname)
    log("① 分析 %d 个文件..." % len(in_paths))
    plan = analyze_workbooks(in_paths)
    if choices is None:
        choices = _default_choices(plan)
    log("② 应用选择、聚合并写出...")
    res = apply_plan(plan, choices, out_path)
    log("   分组 %d 项，合计 %s；可信度【%s】%d/100"
        % (res.get("groups", 0), _fmt_num(res.get("total", 0)),
           res.get("level", "?"), res.get("score", 0)))
    log("已保存：%s" % out_path)
    return res


def analyze(in_paths):
    """仅第一阶段：分析并返回决策计划（供界面做人工复核）。"""
    return analyze_workbooks(in_paths)


def _beijing_date():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y%m%d")
