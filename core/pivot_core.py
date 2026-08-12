# -*- coding: utf-8 -*-
"""销售采购表的识别、清洗、人工复核、聚合与原生透视表生成。

处理采用严格的两阶段协议：``analyze_workbooks`` 只读源文件并收集页签选择、疑似被删
行、单位冲突和规格归并等决策点；``apply_plan`` 根据最终选择生成清洗数据、静态汇总和
Excel 原生 OOXML 透视对象。结构化可信度分析随结果返回双端前端，不再依赖单独报告。

本模块是透视业务算法的唯一事实源，不依赖界面。它还负责公式缓存提示、主数据补空、
增量缓存和 Web 任务产物隔离，但不会覆盖源文件。
"""
import os
import re
import sys
import glob
import json
import datetime
import zipfile
from collections import defaultdict, OrderedDict

import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, Side, Alignment, Font, PatternFill
from openpyxl.styles.colors import Color
from openpyxl.utils import get_column_letter

from . import paths as _paths
from . import settings as _settings
from . import common_core                    # Progress 进度上报辅助
from . import incremental_cache
from . import material_catalog
from . import pivot_reporting
from .common_core import warn_if_uncached   # 公式未刷新检测(读关键表前告警)
from .pivot_ooxml import (
    DATA_FIELD,
    FIELD_LABELS,
    ROW_FIELDS,
    _code_order_key,
    _is_blank,
    _num,
    build_fields_meta,
    cache_definition_xml,
    cache_records_xml,
    inject_pivots,
    meta_by_idx,
    pivot_table_xml,
)

# 可信度评分与兼容文本报告位于独立渲染层；保留原名称兼容旧调用。
assess_confidence = pivot_reporting.assess_confidence
write_confidence_report = pivot_reporting.write_confidence_report

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
FINAL_ALIASES = ("最终采购数量", "需求数量", "采购数量", "需求数", "采购数", "需求量",
                 "计划数量", "计划采购数量")
UNIT_ALIASES  = ("使用单位", "计量单位", "单位")
VER_ALIASES   = ("版本序号", "版本")
QTY_EXACT     = ("数量", "单套数量", "单车数量")

def _match_anchor(t, aliases):
    """判断短表头是否可作为字段锚点。

    完全相等最可靠；包含别名时限制额外长度，兼容“材料编号编码”等轻微扩展，同时避免
    在长说明文本中偶然出现“编码”便误判整行是表头。
    """
    for a in aliases:
        if t == a or (a in t and len(t) <= len(a) + 8):
            return True
    return False

def _contains_any(t, aliases):
    """判断文本是否命中任一字段别名。"""
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
    """判断文本中是否包含常用中文字符。"""
    for ch in str(s):
        if '一' <= ch <= '鿿':
            return True
    return False

def _is_zero(v):
    """判断非空单元格能否解析为数值零。"""
    if _is_blank(v):
        return False
    try:
        return float(v) == 0
    except (ValueError, TypeError):
        return False

def _norm(v):
    """去换行/空格/制表符/全角空格/零宽字符, 便于表头匹配。
    全角空格(　U+3000)与零宽字符(U+200B-D/FEFF/00AD/2060)常混进导出表头,
    不清掉会让 '计划　数量' 这类含全角空格的表头匹配不上代码锚点(见变体压测)。"""
    if v is None:
        return ""
    s = str(v)
    for ch in ["\r\n", "\n", "\r", "\t", " ", "　",
               "​", "‌", "‍", "﻿", "­", "⁠"]:
        s = s.replace(ch, "")
    return s.strip()


def _cell(ws, r, c):
    """按行列坐标读取工作表单元格值。"""
    return ws.cell(row=r, column=c).value


class _PreviewCell:
    """只承载 value 的轻量单元格，供表头快照适配现有识别函数。"""
    __slots__ = ("value",)

    def __init__(self, value):
        """保存单个预览值，提供与 openpyxl Cell 一致的最小读取属性。"""
        self.value = value


class _SheetPreview:
    """只保留工作表前若干行值，避免大文件识别阶段随机扫描只读工作表。"""
    __slots__ = ("title", "_rows", "max_row", "max_column")

    def __init__(self, title, rows):
        """根据顺序读取的前若干行构造轻量工作表接口。"""
        self.title = title
        self._rows = rows
        self.max_row = len(rows)
        self.max_column = max((len(row) for row in rows), default=1)

    def cell(self, row, column):
        """按 openpyxl 的一基坐标读取预览值，越界时返回空轻量单元格。"""
        if row < 1 or column < 1 or row > len(self._rows):
            return _PreviewCell(None)
        values = self._rows[row - 1]
        value = values[column - 1] if column <= len(values) else None
        return _PreviewCell(value)


def _preview_sheet(ws, max_rows=HEADER_SCAN_ROWS):
    """顺序读取工作表前若干行，生成只供结构识别使用的轻量快照。"""
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(tuple(row))
        if len(rows) >= max_rows:
            break
    return _SheetPreview(ws.title, rows)

def _last_col(ws, r):
    """该行最后一个非空列(模拟 End(xlToLeft))"""
    last = 1
    for c in range(1, ws.max_column + 1):
        if not _is_blank(_cell(ws, r, c)):
            last = c
    return last


def _header_anchor_columns(ws, row, last_col):
    """返回表头行中所有材料编码锚点列，供并排区块逐一解析。"""
    anchors = []
    for column in range(1, last_col + 1):
        text = _norm(_cell(ws, row, column))
        if text and _match_anchor(text, CODE_ALIASES):
            anchors.append(column)
    return anchors


def _assign_block_column(columns, text, column):
    """按业务优先级把一个表头单元格分配给区块字段。

    “最终采购数量”同时包含“数量”，因此必须先判断最终数量，再判断普通数量；名称、
    规格和单位同样只接受首次命中，避免备注区或后续重复标题覆盖靠近编码锚点的列。
    """
    if not text:
        return
    if columns["name"] == 0 and _contains_any(text, NAME_ALIASES):
        columns["name"] = column
    elif columns["spec"] == 0 and _contains_any(text, SPEC_ALIASES):
        columns["spec"] = column
    elif columns["final"] == 0 and _contains_any(text, FINAL_ALIASES):
        columns["final"] = column
    elif columns["qty"] == 0 and (text in QTY_EXACT or "数量" in text):
        # 放宽的“含数量”匹配兼容“二级包装规格\n数量”等合并导出表头。
        columns["qty"] = column
    elif columns["unit"] == 0 and _contains_any(text, UNIT_ALIASES):
        columns["unit"] = column


def _block_from_anchor(ws, row, anchor, last_col):
    """从一个材料编码锚点解析字段列；缺少最终采购数量时返回 ``None``。"""
    columns = {
        "version": 0,
        "code": anchor,
        "name": 0,
        "spec": 0,
        "qty": 0,
        "unit": 0,
        "final": 0,
    }
    if anchor > 1:
        previous = _norm(_cell(ws, row, anchor - 1))
        if _contains_any(previous, VER_ALIASES):
            columns["version"] = anchor - 1

    # 与旧逻辑一致扫描到本行末尾；字段仅记录首次命中，因此并排模板仍由各自锚点解析。
    for column in range(anchor, last_col + 1):
        _assign_block_column(columns, _norm(_cell(ws, row, column)), column)
    if columns["final"] == 0:
        return None
    return {
        "hdr": row,
        "cols": [
            columns["version"], columns["code"], columns["name"],
            columns["spec"], columns["qty"], columns["unit"], columns["final"],
        ],
    }


def find_all_blocks(ws):
    """识别工作表中所有可能并排的数据区块。

    每个区块以材料编码表头为锚点，从该列向右解析版本、编码、名称、规格、数量、单位和
    最终采购数量七个字段。返回项包含表头行和列号数组，列号零表示可选字段缺失。只有
    编码与最终采购数量同时存在才构成有效区块，并限制最多十二块防止异常表头组合爆炸。
    """
    blocks = []
    scan = min(HEADER_SCAN_ROWS, ws.max_row or 1)
    for row in range(1, scan + 1):
        last_col = _last_col(ws, row)
        for anchor in _header_anchor_columns(ws, row, last_col):
            block = _block_from_anchor(ws, row, anchor, last_col)
            if block is None:
                continue
            blocks.append(block)
            if len(blocks) >= MAX_BLOCKS:
                return blocks
    return blocks

def _looks_like_pivot_output(ws):
    """判断工作表是否已经是透视结果，避免把输出再次当作源数据。

    “求和项:”是 Excel 透视度量字段前缀，“(全部)”常见于页字段筛选。命中任一特征就
    排除该页，否则重复处理会把已经汇总的数量再次求和。
    """
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
    """排除说明、汇总和历史输出等非原始数据工作表。"""
    name = str(getattr(ws, "title", "") or "").replace(" ", "")
    return any(tok in name for tok in EXCLUDE_SHEET_TOKENS)

def is_data_sheet(ws):
    """判断工作表是否包含可识别的销售数据区块。"""
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
    """返回去除空格后的工作表名称。"""
    return str(getattr(ws, "title", "") or "").replace(" ", "")

def _has_token(name, tokens):
    """判断工作表名称是否包含任一规范化关键字。"""
    return any(t.replace(" ", "") in name for t in tokens)


# 归一化后字段索引: 0版本 1编码 2名称 3规格 4数量 5单位 6最终采购数量
F_VER, F_CODE, F_NAME, F_SPEC, F_QTY, F_UNIT, F_FINAL = 0, 1, 2, 3, 4, 5, 6


def _complete_rows_from_catalog(rows, resolver, fill_counts=None):
    """在聚类前用同一主数据快照补全名称、规格和单位。

    补全发生在规格和单位聚类之前，否则同一材料的空字段会形成独立组。解析器只返回源
    行空缺项，已有报表值保持最高优先级；计数用于任务日志说明主数据库参与程度。
    """
    for rec in rows:
        additions = resolver.complete_material(
            rec[F_CODE],
            {"name": rec[F_NAME], "spec": rec[F_SPEC], "unit": rec[F_UNIT]},
            fields=("name", "spec", "unit"),
            counts=fill_counts,
        )
        if "name" in additions:
            rec[F_NAME] = additions["name"]
        if "spec" in additions:
            rec[F_SPEC] = additions["spec"]
        if "unit" in additions:
            rec[F_UNIT] = additions["unit"]
    return rows


def classify_sheet(ws):
    """判定工作表类型、默认是否纳入以及识别置信度。

    返回结构包含名称、类型、理由、字段列、缺失字段、区块数和默认选择。判定顺序是明确
    排除页、已有透视输出、无数据区，再进入表名与字段结构分类；这使人工复核既能看到
    系统为何排除，也能在结构确实存在时重新勾选纳入。
    """
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

    # 同一页的并排区块共享模板结构，分类依据取首个区块，实际读取仍处理全部区块。
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
    """把普通工作表全部并排区块读成统一七字段列表。

    缺失可选列填 ``None``，整条七字段均为空的行跳过。区块按表头扫描顺序、行按工作表
    顺序追加，使后续“首次出现”平局规则具有确定性。
    """
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


def normalize_stream_rows(ws, blocks):
    """从只读工作表按已识别区块流式提取七个业务字段。

    ``values_only`` 避免创建大量 Cell 对象，列号从一基转换为元组零基索引。输出行序与
    :func:`normalize_rows` 一致，因此人工复核编号和聚类平局结果不会因读取模式改变。
    """
    rows = []
    for block in blocks:
        cols = block["cols"]
        max_col = max(cols)
        for values in ws.iter_rows(min_row=block["hdr"] + 1,
                                   max_col=max_col, values_only=True):
            rec = []
            for source_col in cols:
                if source_col > 0 and source_col <= len(values):
                    rec.append(values[source_col - 1])
                else:
                    rec.append(None)
            if all(_is_blank(value) for value in rec):
                continue
            rows.append(rec)
    return rows

def clean_rows(rows):
    """按正式口径清洗版本与采购数量，并返回两步删除计数。

    只有版本列存在有效值时才启用版本规则，避免无版本模板被整表删除。最终采购数量为空
    或零的行通常排除，但材料名称含“原厂”时保留，这是现行业务例外。该函数用于无需
    人工复核的兼容路径；两阶段流程使用 :func:`clean_rows_ex` 额外保留疑似真实行。
    """
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
       返回 (kept, held, d1, d2); held 元素为 {"rec","reason","has_code"}。

       ``held`` 默认仍不纳入，保持自动处理口径不变；它只把有采购量或疑似公式未刷新的
       被删行暴露给人工选择，禁止通过隐藏入口绕过复核直接加入。
       """
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
                # 区分"公式未刷新"与"真实空/0": 最终采购数量为 None(非 0/非空串)且本行有有效编码,
                # 极可能是公式未刷新读出 None, 不当真实空行静默删, 挑入 held 交人工确认。
                if g is None and _is_valid_code(rec[F_CODE]):
                    held.append({"rec": rec,
                                 "reason": "最终采购数量为空(疑似公式未刷新)",
                                 "has_code": True})
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
    """提取记录的材料编码、名称和规格原始键。"""
    code = str(rec[F_CODE]).strip() if rec[F_CODE] is not None else ""
    nm = str(rec[F_NAME]).strip() if rec[F_NAME] is not None else ""
    sp = str(rec[F_SPEC]).strip() if rec[F_SPEC] is not None else ""
    return code, nm, sp

def _spec_gkey(code, nm, sp):
    """生成忽略格式差异的材料规格分组键。"""
    # 归一化分组键: 编码/名称/规格基准全部走 _norm_key
    return (_norm_key(code), _norm_key(nm), _norm_key(_spec_base(sp)))

def compute_spec_canon(rows):
    """计算规格归并的默认写法、变体频次和展示样例。

    分组键使用编码、名称和去包装注释后的规格。默认值按出现次数降序、文本长度升序、
    首次出现顺序选择，既倾向主流写法，也保证同样输入产生稳定结果；原始变体完整保留
    给人工复核。
    """
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
        pos = {sp: i for i, sp in enumerate(spm.keys())}  # OrderedDict 顺序提供最终稳定平局规则。
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
    """生成单位检查使用的材料键；全空记录不参与统计。"""
    code = _norm_key(rec[F_CODE]); nm = _norm_key(rec[F_NAME]); sp = _norm_key(rec[F_SPEC])
    if code == "" and nm == "" and sp == "":
        return None
    return (code, nm, sp)


def _unit_key_sample(rec, spec_canon=None):
    """返回单位分组键与展示样例，可只读套用规格规范值而不修改原始行。"""
    code, name, spec = _spec_keyof(rec)
    if spec_canon is not None:
        spec = spec_canon.get(_spec_gkey(code, name, spec), spec)
    key = (_norm_key(code), _norm_key(name), _norm_key(spec))
    if key == ("", "", ""):
        return None, None
    return key, (code, name, spec)


def _compute_unit_best(rows_factory, spec_canon=None):
    """从可重放行迭代器计算每个材料规格组的默认单位。

    需要两遍数据：第一遍建立名称级单位先验，第二遍统计规格组分布，因此参数是每次返回
    新迭代器的工厂。优先非空非复合单位；严格多数直接胜出，平票再使用名称先验，最后
    依据单位简单度和首次出现顺序选择。规格规范值只参与键计算，不修改复核计划原始行。
    """
    from collections import defaultdict, OrderedDict
    prior = _name_unit_prior(rows_factory())
    counts = defaultdict(lambda: OrderedDict())
    sample = {}
    for rec in rows_factory():
        key, display = _unit_key_sample(rec, spec_canon=spec_canon)
        if key is None:
            continue
        unit = str(rec[F_UNIT]).strip() if rec[F_UNIT] is not None else ""
        counts[key][unit] = counts[key].get(unit, 0) + 1
        sample.setdefault(key, display)
    best = {}
    for key, unit_map in counts.items():
        clean = {unit: count for unit, count in unit_map.items() if unit != ""}
        if not clean:
            best[key] = ""
            continue
        noncompound = {unit: count for unit, count in clean.items()
                       if not _is_compound_unit(unit)}
        pool = noncompound if noncompound else clean
        positions = {unit: index for index, unit in enumerate(unit_map.keys())}
        maximum = max(pool.values())
        tied = [unit for unit, count in pool.items() if count == maximum]
        if len(tied) == 1:
            best[key] = tied[0]
        else:
            name_prior = prior.get(key[1], "")
            if name_prior in tied:
                best[key] = name_prior
            elif name_prior:
                # 即使先验未出现在当前平票集合，也用跨表名称先验统一同名材料口径。
                best[key] = name_prior
            else:
                best[key] = min(tied,
                                key=lambda unit: (_unit_simplicity(unit), positions[unit]))
    return best, counts, sample


def compute_unit_best(rows):
    """计算每个 编码+名称+规格 组的单位选择。返回 (best, counts, sample)。
       best[k]   = 系统默认单位
       counts[k] = OrderedDict(单位->次数), 供复核展示
       sample[k] = (code, name, spec) 原始展示值"""
    return _compute_unit_best(lambda: iter(rows))


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


def drop_blank_code_rows(rows):
    """剔除"材料编号为空"的行: 这类行无法归属到任何物料, 在透视里会并成一个
       无意义的 (空白) 组; 且会给行字段引入空项。返回 (保留行, 被剔除数)。
       仅按编码判空(名称/规格可空但有编码仍是有效物料)。"""
    kept = [r for r in rows if not _is_blank(r[F_CODE])]
    return kept, len(rows) - len(kept)


def aggregate(rows):
    """按编码、名称、规格和单位分组并汇总最终采购数量。

    非数字度量按零参与，与透视缓存的空值策略保持一致。排序使用统一编码规则，确保静态
    A 至 E 列、OOXML ``items`` 和 ``rowItems`` 三处行序完全对齐。
    """
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
    # 排序: 编码优先按"无字母前缀在前"分组(见 _code_order_key), 再按 名称/规格/单位
    # 字符串升序。与透视 <items>/pos_map 用同一编码键, 保证 A-E 行序与静态列对齐。
    items = sorted(groups.items(),
                   key=lambda kv: (_code_order_key(kv[0][0]), kv[0][1], kv[0][2], kv[0][3]))
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
        # 汇总列改为"同行 E(求和项:最终采购数量)"的公式而非静态值:
        # E 属于动态透视范围(A1:E…), Excel 打开刷新会按自身排序重排 A–E;
        # 若 G 写静态值, 刷新后 G 停在原顺序 -> 与重排后的 E 错位(用户所见"汇总≠最终采购数")。
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


# 原生透视缓存和 OOXML 归档注入位于 pivot_ooxml.py；本模块通过顶部导入保留原公开名。
def process_workbook(in_path, out_path=None, log=None):
    """
    复刻 RunProcess: 打开工作簿, 对每张数据表清洗并生成一张透视结果表.
    不改动原文件(输出到 out_path, 默认在原名后加 _透视结果).
    返回处理、跳过数量、逐表汇总、输出路径和动态透视注入错误。该兼容入口没有人工决策
    阶段，适用于旧调用；新双端流程应使用 ``analyze_workbooks`` 与 ``apply_plan``。
    """
    import os
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


# 可信度与兼容文本报告实现位于 pivot_reporting.py。
def _analyze_stream_sheet(ws, fname, sid, resolver=None, fill_counts=None):
    """分析一张只读工作表并生成稳定的人工复核记录。

    前若干行轻量快照只用于分类和列识别，真正数据通过流式读取。按表名提前排除的页只要
    仍存在有效数据区，也会预读行数据，使管理员重新勾选时确实可以纳入，而不是空操作。
    """
    preview = _preview_sheet(ws)
    cls = classify_sheet(preview)
    rec = {"id": sid, "file": fname, "sheet": ws.title, "use": cls["use"],
           "openable": True, "kind": cls["kind"], "confidence": cls["confidence"],
           "reason": cls["reason"], "cols": cls["cols"], "missing": cls["missing"],
           "kept": [], "held": [], "d1": 0, "d2": 0, "no_block": False}
    # 分类会按表名提前排除参考表，但人工仍可重新勾选；只要结构上存在数据区，
    # 就必须预读行数据，保证“勾选纳入”不是空操作。
    blocks = find_all_blocks(preview)
    if blocks:
        if rec["cols"] is None:
            rec["cols"] = blocks[0]["cols"]
            rec["missing"] = [FIELD_CN[index] for index in (KEY_FIELDS + INFO_FIELDS)
                              if blocks[0]["cols"][index] == 0]
        rows = normalize_stream_rows(ws, blocks)
        if resolver is not None:
            _complete_rows_from_catalog(rows, resolver, fill_counts)
        kept, held, d1, d2 = clean_rows_ex(rows)
        rec.update(kept=kept, held=held, d1=d1, d2=d2)
        if cls["use"] and not kept and not held:
            rec.update(use=False, kind="排除:清洗后无数据",
                       reason="识别为%s, 但清洗后无有效行(全被版本/采购量规则删除)" % cls["kind"])
    else:
        rec["no_block"] = True
    return rec


def analyze_workbooks(in_paths, on_file=None, resolver=None, fill_counts=None):
    """第一阶段: 只读文件、分类、清洗, 收集所有"待人工复核的决策点", 不写任何文件。

       on_file(done, total): 可选回调, 每处理完一个文件调用一次, 供进度条使用。
       返回 plan:
         plan['sheets']         每张候选表 {id,file,sheet,use(默认),kind,confidence,
                                 reason,cols,missing,kept[行],held[行],d1,d2}
         plan['held_index']     扁平化的空白序号行 [{sid,ridx,rec,file,sheet}]
         plan['unit_conflicts'] 单位冲突组 [{gk,code,name,spec,dist,default}]
         plan['spec_merges']    规格归并组 [{gk,code,name,variants,default}]
       默认选择等于自动分类结果，所有 ``held`` 行默认不纳入。分析阶段不创建输出文件，
       也不修改源工作簿；调用方必须把计划展示给人工后再进入 ``apply_plan``。
       """
    import os
    resolver = resolver or material_catalog.CatalogResolver()
    sheets = []
    sid = 0
    _total = len(in_paths)
    for _fi, in_path in enumerate(in_paths):
        fname = os.path.splitext(os.path.basename(in_path))[0]
        try:
            # 只读模式不创建整本工作簿的 Cell 对象；公共入口会先修复错误 dimension，
            # 避免部分业务导出表被静默截成一行。
            wb = common_core.load_data_only_stream(in_path)
        except Exception:
            # 整个文件打不开时仍生成一条可见审计记录，其他文件继续分析。
            sheets.append({"id": sid, "file": os.path.basename(in_path), "sheet": "(整个文件)",
                           "use": False, "openable": False, "kind": "排除:无法打开",
                           "confidence": 0, "reason": "openpyxl 打开失败, 可能非法xlsx或被占用",
                           "cols": None, "missing": [], "kept": [], "held": [], "d1": 0, "d2": 0})
            sid += 1; continue
        try:
            for sn in list(wb.sheetnames):
                sheets.append(_analyze_stream_sheet(
                    wb[sn], fname, sid, resolver=resolver, fill_counts=fill_counts))
                sid += 1
        finally:
            wb.close()
        if on_file:
            on_file(_fi + 1, _total)          # 每读完一个文件上报一次进度

    # 扁平化"疑似真实但被删"的行, 给每行稳定 id, 供弹窗逐行勾选
    held_index = []
    for s in sheets:
        for ridx, hd in enumerate(s["held"]):
            held_index.append({"sid": s["id"], "ridx": ridx, "rec": hd["rec"],
                               "reason": hd["reason"], "has_code": hd["has_code"],
                               "file": s["file"], "sheet": s["sheet"]})

    # 冲突收集:在默认纳入行上建立可重放迭代视图，不复制也不修改复核计划原始行。
    def default_rows():
        """每次调用都重新遍历系统默认纳入页的已保留行。"""
        for sheet in sheets:
            if sheet["use"]:
                yield from sheet["kept"]

    # 规格归并 (需先归并规格, 单位冲突才在同一规格下判定)
    scanon, sgroups, ssample = compute_spec_canon(default_rows())
    spec_merges = []
    for gk, variants in sgroups.items():
        if len([v for v in variants if v]) > 1:
            code, nm = ssample.get(gk, ("", ""))
            spec_merges.append({"gk": gk, "code": code, "name": nm,
                                "variants": variants, "default": scanon[gk]})
    # 单位冲突在规范规格视图上只读计算，避免复制全部行再就地改规格。
    ubest, ucounts, usample = _compute_unit_best(default_rows, spec_canon=scanon)
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

# 统一运行入口供 Tauri 与 Web 桥接调用，包含缓存、进度、主数据补空和正式两阶段执行。
def run(in_paths, choices=None, out_dir=None, log=None, progress=None):
    """执行销售表透视并返回输出、可信度和结构化复核结果。

    输入可为单路径或路径列表。增量缓存键包含文件内容、人工选择、输出作用域、主数据
    签名和算法版本；Web 命中缓存后仍会复制产物到当前用户任务目录。缓存故障只回退完整
    处理，不影响业务。未提供人工选择时使用默认选择，输出目录由统一路径系统解析。
    """
    log = log or (lambda *a, **k: None)
    st = _settings.get_settings()
    if isinstance(in_paths, str):
        in_paths = [in_paths]
    resolver = material_catalog.CatalogResolver()
    fill_counts: dict[str, int] = {}
    cache_key = ""
    web_root = os.environ.get("FYT_WEB_OUTPUT_ROOT", "").strip()
    # 输出作用域进入缓存键，避免桌面自定义目录与 Web 用户缓存互相复用绝对路径。
    cache_scope = (os.path.abspath(out_dir) if out_dir is not None else
                   "web-user-cache" if web_root else
                   {"mode": st.output_mode,
                    "custom_root": st.custom_output_root})
    if st.get("enable_incremental_cache", True):
        try:
            cache_key = incremental_cache.make_key(
                "pivot", in_paths,
                {"choices": choices, "output": cache_scope,
                 "catalog": resolver.signature},
                engine_version="pivot-v3")
            cached = incremental_cache.get(cache_key)
            if cached:
                if web_root:
                    out_dir = _paths.resolve_output_dir(
                        "pivot", **st.output_kwargs())
                    cached = _materialize_web_cache(cached, out_dir)
                log("[缓存] 输入文件和处理参数未变化，已复用现有透视结果。")
                if progress:
                    progress(100)
                return cached
        except (OSError, ValueError, TypeError) as error:
            log("[缓存] 无法读取缓存，已回退完整处理：%s" % error)
    if out_dir is None:
        out_dir = _paths.resolve_output_dir("pivot", **st.output_kwargs())
    # 读取与分类通常占主要耗时，按文件细分五成五；聚合和写盘占剩余阶段。
    prog = common_core.Progress(progress, stages=[("analyze", 55), ("apply", 45)])
    fname = "%s透视结果.xlsx" % _beijing_date()
    out_path = common_core.unique_path(os.path.join(out_dir, fname))  # 同日重跑不覆盖
    # "最终采购数量"常是公式; 未刷新时 data_only 读出 None 会被 clean_rows 当空删除,
    # 导致总计漏数且置信度检查不报警。读表前逐个文件醒目告警。
    for p in in_paths:
        warn_if_uncached(p, log, what="最终采购数量")
    log("① 分析 %d 个文件..." % len(in_paths))
    prog.stage("analyze")
    plan = analyze_workbooks(
        in_paths, on_file=prog.tick, resolver=resolver, fill_counts=fill_counts)
    material_catalog.log_fill_summary(log, "销售透视", fill_counts)
    if choices is None:
        choices = _default_choices(plan)
    log("② 应用选择、聚合并写出...")
    prog.stage("apply")
    res = apply_plan(plan, choices, out_path, log=log)
    res.setdefault("out_dir", out_dir)
    prog.done()
    log("   分组 %d 项，合计 %s；可信度【%s】%d/100"
        % (res.get("groups", 0), _fmt_num(res.get("total", 0)),
           res.get("level", "?"), res.get("score", 0)))
    log("已保存：%s" % out_path)
    if cache_key:
        artifacts = [res.get("out"), res.get("report")]
        artifacts = [path for path in artifacts if path]
        try:
            incremental_cache.put(cache_key, "pivot", _cacheable_result(res), artifacts)
        except (OSError, ValueError, TypeError) as error:
            log("[缓存] 结果索引保存失败，不影响本次输出：%s" % error)
    return res


def analyze(in_paths, log=None, progress=None):
    """仅第一阶段：分析并返回决策计划（供界面做人工复核）。

    ``log`` 与 ``progress`` 只报告状态，不改变分析结果。该入口读取全部源文件并返回
    人工复核计划，不创建输出文件。
    """
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
