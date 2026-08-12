# -*- coding: utf-8 -*-
"""通用表头/列识别引擎。

原本 delivery_core / purchase_core 各写了一套几乎逐行相同的 detect_layout,
差异只在:(1) 角色→关键词表 HEADER_KEYS;(2) 判定"这行是表头"的必需角色;
(3) 某些角色在"包含匹配"时要排除的干扰子串(如"委外供应商属性"含"供应商"
但不是供应商列)。此处抽成一个引擎,各 core 传自己的常量做薄封装,
使"先精确后包含""排除干扰列"等修复只维护一处,并自动惠及所有调用方。
"""

import re

# 表头文本内部空白(空格/制表/换行/全角空格)统一折叠的正则。
# Excel 表头常见手动换行("供应商\n编码")或对齐空格("物料 名称"),
# 而各 core 的关键词表都是无空格精确串——不折叠会导致精确匹配失配、
# 退化到包含匹配后被别的列抢占,识别率下降。折叠只会让真实表头多命中。
_WS = re.compile(r"\s+")


def _norm_header(cell):
    """表头单元格文本归一:转字符串、去掉内部所有空白(含全角空格 　)。
    \\s 在 Python3 str 模式下已覆盖 　,这里再显式替换一次以防万一。"""
    if cell is None:
        return ""
    return _WS.sub("", str(cell)).replace("　", "")


def _matches_role(text, keys, *, exact, excluded):
    """判断一个规范化表头是否命中角色，并应用包含匹配排除词。"""
    if exact:
        return text in keys
    # 排除词只约束模糊包含阶段；若表头与正式别名完全相同，仍应由精确阶段认领。
    return not any(word in text for word in excluded) and any(
        keyword in text for keyword in keys
    )


def _first_matching_role(text, header_keys, assigned, *, exact, exclusions):
    """按角色声明顺序返回首个尚未认领且命中的角色。"""
    for role, keys in header_keys.items():
        if role in assigned:
            continue
        if _matches_role(
            text,
            keys,
            exact=exact,
            excluded=exclusions.get(role, ()),
        ):
            return role
    return None


def _map_header_row(ws, row, header_keys, exclusions):
    """对单行执行“先精确、后包含”的列角色映射。"""
    column_map = {}
    used_columns = set()
    for exact in (True, False):
        for column in range(1, (ws.max_column or 0) + 1):
            if column in used_columns:
                continue
            text = _norm_header(ws.cell(row, column).value)
            if not text:
                continue
            role = _first_matching_role(
                text,
                header_keys,
                column_map,
                exact=exact,
                exclusions=exclusions,
            )
            if role is not None:
                column_map[role] = column
                used_columns.add(column)
    return column_map


def detect_layout(ws, header_keys, require, scan_rows=12, exclude_contains=None,
                  log=None):
    """在前若干行中选择命中角色最多的表头并返回列映射。

    ``header_keys`` 的声明顺序决定同一列的角色优先级；同一行先做精确匹配，再做包含
    匹配，避免“编码”抢占“供应商编码”。候选行必须覆盖全部 ``require`` 角色，命中数
    相同则保留更靠前的一行。``exclude_contains`` 只用于排除模糊匹配干扰列。
    """
    exclusions = exclude_contains or {}
    best_row, best_map = None, {}
    # 空表和部分只读工作表的 max_row 可能为 None，零值兜底后不会让 min 抛异常。
    last_row = min(scan_rows, ws.max_row or 0)
    for row in range(1, last_row + 1):
        column_map = _map_header_row(ws, row, header_keys, exclusions)
        has_required = all(role in column_map for role in require)
        if has_required and len(column_map) > len(best_map):
            best_row, best_map = row, column_map
    if log and best_row:
        _report_unmatched(ws, best_row, best_map, log)
    return best_row, best_map


def _report_unmatched(ws, header_row, col_map, log):
    """上报表头行里"有文字却没被任何角色认领"的列,便于发现缺失的别名。
    只报非空列,避免刷屏;纯装饰/空列忽略。"""
    used_cols = set(col_map.values())
    unmatched = []
    for c in range(1, ws.max_column + 1):
        if c in used_cols:
            continue
        v = ws.cell(header_row, c).value
        if v is None:
            continue
        t = str(v).strip()
        if t:
            unmatched.append(t)
    try:
        if unmatched:
            log("· 表头识别:已认领 %d 列;未认领列(如需纳入请补别名): %s"
                % (len(col_map), "、".join(unmatched)))
    except Exception:
        pass          # 日志失败绝不影响识别结果
