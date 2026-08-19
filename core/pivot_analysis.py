# -*- coding: utf-8 -*-
"""采购汇总的结构识别、字段提取、清洗与人工复核计划。

本模块只读源工作簿，产出第一阶段复核计划：哪些页签默认纳入、哪些被清洗规则删除的
疑似真实行需要人工勾选、哪些规格和单位存在冲突。真正的归并与写出由
:mod:`core.pivot_core` 在第二阶段执行。源表中的多个横向子表会按各自边界直接提取为同一
六字段记录流，不再模拟“先并排复制、再二次拼接”的人工过程。本模块不依赖
``pivot_core``，避免主业务入口与底层实现循环导入。
"""
import os
from collections import defaultdict, OrderedDict

from . import common_core
from . import material_catalog
from .pivot_clustering import (
    F_VER, F_CODE, F_NAME, F_SPEC, F_UNIT, F_FINAL,
    _compute_unit_best, _is_blank,
    compute_spec_canon,
)

L_VER   = "版本序号"
L_CODE  = "材料编号"
L_NAME  = "材料名称"
L_SPEC  = "规格"
L_UNIT  = "单位"
L_FINAL = "最终采购数量"
KEEP_TOKEN = "原厂"            # 名称含此 token 的行, 步骤2不删

# 表头别名: 不同表格用词不一, 识别时任一匹配即可
CODE_ALIASES  = ("材料编号", "材料号", "物料编号", "物料号", "料号", "物料编码", "编码")
NAME_ALIASES  = ("材料名称", "物料名称", "品名", "名称")
SPEC_ALIASES  = ("规格尺寸", "规格型号", "规格", "尺寸")
FINAL_ALIASES = ("最终采购数量", "需求数量", "采购数量", "需求数", "采购数", "需求量",
                 "计划数量", "计划采购数量")
UNIT_ALIASES  = ("使用单位", "计量单位", "单位")
VER_ALIASES   = ("版本序号", "版本")

SUM_PREFIX = "求和项:"
HEADER_SCAN_ROWS = 30
MAX_BLOCKS = 12


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

    全角空格(``　`` U+3000)与零宽字符(U+200B-D/FEFF/00AD/2060)常混进导出表头，
    不清掉会让 ``计划　数量`` 这类含全角空格的表头匹配不上代码锚点(见变体压测)。
    """
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

    这里只识别最终结果真正需要的名称、规格、单位和最终采购数量；旧流程为了构造透视
    缓存读取的普通“数量”列并不参与清洗或聚合，现已从数据模型移除。每个字段只接受
    首次命中，避免备注区或后续重复标题覆盖靠近编码锚点的列。
    """
    if not text:
        return
    if columns["name"] == 0 and _contains_any(text, NAME_ALIASES):
        columns["name"] = column
        return
    if columns["spec"] == 0 and _contains_any(text, SPEC_ALIASES):
        columns["spec"] = column
        return
    if columns["final"] == 0 and _contains_any(text, FINAL_ALIASES):
        columns["final"] = column
        return
    if columns["unit"] == 0 and _contains_any(text, UNIT_ALIASES):
        columns["unit"] = column


def _block_from_anchor(ws, row, anchor, block_end):
    """从一个材料编码锚点解析字段列；缺少最终采购数量时返回 ``None``。"""
    columns = {
        "version": 0,
        "code": anchor,
        "name": 0,
        "spec": 0,
        "unit": 0,
        "final": 0,
    }
    if anchor > 1:
        previous = _norm(_cell(ws, row, anchor - 1))
        if _contains_any(previous, VER_ALIASES):
            columns["version"] = anchor - 1

    # 每个横向子表只扫描到下一个材料编码锚点之前，防止前一块缺列时误借用后一块字段。
    for column in range(anchor, block_end + 1):
        _assign_block_column(columns, _norm(_cell(ws, row, column)), column)
    if columns["final"] == 0:
        return None
    return {
        "hdr": row,
        "cols": [
            columns["version"], columns["code"], columns["name"],
            columns["spec"], columns["unit"], columns["final"],
        ],
    }


def find_all_blocks(ws):
    """识别工作表中所有可能并排的数据区块。

    每个区块以材料编码表头为锚点，只在当前锚点与下一个锚点之间解析版本、编码、名称、
    规格、单位和最终采购数量六个字段。这样同一页的两个子表会直接形成两段记录流，不会
    先复制成中间并排表，也不会跨子表误配字段。只有编码与最终采购数量同时存在才构成
    有效区块，并限制最多十二块防止异常表头组合爆炸。
    """
    blocks = []
    scan = min(HEADER_SCAN_ROWS, ws.max_row or 1)
    for row in range(1, scan + 1):
        last_col = _last_col(ws, row)
        anchors = _header_anchor_columns(ws, row, last_col)
        for index, anchor in enumerate(anchors):
            block_end = anchors[index + 1] - 1 if index + 1 < len(anchors) else last_col
            block = _block_from_anchor(ws, row, anchor, block_end)
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
FIELD_CN = ["版本序号", "材料编号", "材料名称", "规格", "单位", "最终采购数量"]
KEY_FIELDS = [F_CODE, F_FINAL]             # 编码、最终采购数量为关键字段（缺失严重）。
INFO_FIELDS = [F_NAME, F_SPEC, F_UNIT]     # 名称、规格、单位缺失会影响最终聚合。

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
        info.update(kind="排除:疑似已生成汇总表",
                    reason="表内出现'求和项:'或'(全部)'页字段, 判为历史透视输出")
        return info
    if not blocks:
        info.update(kind="排除:无数据区",
                    reason="未找到'材料编号+最终采购数量'数据区")
        return info

    # 同一页的并排区块共享模板结构，分类依据取首个区块，实际读取仍处理全部区块。
    cols = blocks[0]["cols"]     # [version, code, name, spec, unit, final]
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
    """把普通工作表中的全部横向子表直接读成统一六字段列表。

    缺失可选列填 ``None``，整条六字段均为空的行跳过。区块按表头扫描顺序、行按工作表
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
            for i in range(6):
                sc = cols[i]
                rec.append(_cell(ws, r, sc) if sc > 0 else None)
            # 跳过整行全空
            if all(_is_blank(x) for x in rec):
                continue
            rows.append(rec)
    return rows


def normalize_stream_rows(ws, blocks):
    """从只读工作表按已识别区块流式提取六个业务字段。

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
    """该行最终采购数量是否为“有效非零数值”。"""
    g = rec[F_FINAL]
    if _is_zero(g) or _is_blank(g):
        return False
    try:
        return float(g) != 0
    except (TypeError, ValueError):
        return False


def _version_delete_reason(rec, has_ver):
    """返回版本列触发的删除原因；未启用版本规则或该行可保留时返回 ``None``。"""
    if not has_ver:
        return None
    version = rec[F_VER]
    if _is_blank(version):
        return "版本序号为空"
    if _is_zero(version):
        return "版本序号为0"
    if _has_chinese(str(version)):
        return "版本序号含文字(%s)" % str(version).strip()
    return None


def _final_should_drop(rec):
    """判断最终采购数量规则是否要求删除该行。"""
    final_value = rec[F_FINAL]
    if _is_zero(final_value) or _is_blank(final_value):
        name = rec[F_NAME]
        return KEEP_TOKEN not in str(name if name is not None else "")
    return False


def clean_rows_ex(rows):
    """清洗并区分结果, 供人工复核。

    ``kept`` 为系统默认保留的行(与 :func:`clean_rows` 一致)；``held`` 为被任一清洗
    规则删除、但“最终采购数量≠0”的行——只要有采购量就视为疑似真实数据，交人工二次
    确认。每条附带删除原因: 版本序号为空 / 版本序号为0 / 版本序号含文字 / (备用)采购
    量规则；默认不纳入(与现有行为一致)。为便于人工判断，另附 ``has_code``。

    返回 ``(kept, held, d1, d2)``；``held`` 元素为 ``{"rec","reason","has_code"}``。
    ``held`` 默认仍不纳入，保持自动处理口径不变；它只把有采购量或疑似公式未刷新的
    被删行暴露给人工选择，禁止通过隐藏入口绕过复核直接加入。
    """
    d1 = d2 = 0
    held = []
    has_ver = any(not _is_blank(rec[F_VER]) for rec in rows)
    out = []
    for rec in rows:
        reason = _version_delete_reason(rec, has_ver)
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
        if _final_should_drop(rec):
            d2 += 1
            # 区分“公式未刷新”与“真实空/0”: 最终采购数量为 None(非 0/非空串)且本行
            # 有有效编码, 极可能是公式未刷新读出 None, 不当真实空行静默删, 挑入 held。
            if rec[F_FINAL] is None and _is_valid_code(rec[F_CODE]):
                held.append({"rec": rec,
                             "reason": "最终采购数量为空(疑似公式未刷新)",
                             "has_code": True})
            continue
        kept.append(rec)
    return kept, held, d1, d2


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


def _analyze_one_file(in_path, fname, sid, sheets, resolver, fill_counts):
    """分析单个文件并追加页签记录，返回下一个可用页签 id。

    文件无法打开时仍生成一条可见审计记录，其他文件继续分析；工作簿用后立即关闭。
    """
    try:
        # 只读模式不创建整本工作簿的 Cell 对象；公共入口会先修复错误 dimension，
        # 避免部分业务导出表被静默截成一行。
        wb = common_core.load_data_only_stream(in_path)
    except Exception:
        sheets.append({"id": sid, "file": os.path.basename(in_path), "sheet": "(整个文件)",
                       "use": False, "openable": False, "kind": "排除:无法打开",
                       "confidence": 0, "reason": "openpyxl 打开失败, 可能非法xlsx或被占用",
                       "cols": None, "missing": [], "kept": [], "held": [], "d1": 0, "d2": 0})
        return sid + 1
    try:
        for sn in list(wb.sheetnames):
            sheets.append(_analyze_stream_sheet(
                wb[sn], fname, sid, resolver=resolver, fill_counts=fill_counts))
            sid += 1
    finally:
        wb.close()
    return sid


def analyze_workbooks(in_paths, on_file=None, resolver=None, fill_counts=None):
    """第一阶段: 只读文件、分类、清洗, 收集所有“待人工复核的决策点”, 不写任何文件。

    ``on_file(done, total)`` 为可选回调, 每处理完一个文件调用一次, 供进度条使用。
    返回 ``plan``:

    - ``sheets``: 每张候选表 ``{id,file,sheet,use(默认),kind,confidence,reason,
      cols,missing,kept[行],held[行],d1,d2}``
    - ``held_index``: 扁平化的疑似被删行 ``[{sid,ridx,rec,file,sheet}]``
    - ``unit_conflicts``: 单位冲突组 ``[{gk,code,name,spec,dist,default}]``
    - ``spec_merges``: 规格归并组 ``[{gk,code,name,variants,default}]``

    默认选择等于自动分类结果，所有 ``held`` 行默认不纳入。分析阶段不创建输出文件，
    也不修改源工作簿；调用方必须把计划展示给人工后再进入 ``apply_plan``。
    """
    if isinstance(in_paths, str):
        in_paths = [in_paths]  # 入口统一归一化，避免单字符串路径被逐字符遍历。
    resolver = resolver or material_catalog.CatalogResolver()
    sheets = []
    sid = 0
    _total = len(in_paths)
    for _fi, in_path in enumerate(in_paths):
        fname = os.path.splitext(os.path.basename(in_path))[0]
        sid = _analyze_one_file(in_path, fname, sid, sheets, resolver, fill_counts)
        if on_file:
            on_file(_fi + 1, _total)          # 每读完一个文件上报一次进度

    # 扁平化“疑似真实但被删”的行, 给每行稳定 id, 供弹窗逐行勾选
    held_index = []
    for s in sheets:
        for ridx, hd in enumerate(s["held"]):
            held_index.append({"sid": s["id"], "ridx": ridx, "rec": hd["rec"],
                               "reason": hd["reason"], "has_code": hd["has_code"],
                               "file": s["file"], "sheet": s["sheet"]})

    # 冲突收集: 在默认纳入行上建立可重放迭代视图，不复制也不修改复核计划原始行。
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
