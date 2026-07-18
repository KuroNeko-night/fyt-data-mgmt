# -*- coding: utf-8 -*-
"""通用表头/列识别引擎。

原本 delivery_core / purchase_core 各写了一套几乎逐行相同的 detect_layout,
差异只在:(1) 角色→关键词表 HEADER_KEYS;(2) 判定"这行是表头"的必需角色;
(3) 某些角色在"包含匹配"时要排除的干扰子串(如"委外供应商属性"含"供应商"
但不是供应商列)。此处抽成一个引擎,各 core 传自己的常量做薄封装,
使"先精确后包含""排除干扰列"等修复只维护一处,并自动惠及所有调用方。
"""


def detect_layout(ws, header_keys, require, scan_rows=12, exclude_contains=None,
                  log=None):
    """在前若干行里找表头行并映射列。返回 (header_row, {角色:列号}) 或 (None, {})。

    - header_keys: dict 角色->关键词列表(dict 顺序即角色优先级,先到先占列)。
    - require:     必需角色列表;某行须命中其中全部角色才算候选表头。
    - scan_rows:   最多扫描前多少行找表头。
    - exclude_contains: dict 角色->子串列表;仅在"包含匹配"阶段,若单元格文本
                   含该角色的任一排除子串,则该列不得当作此角色(精确匹配不受影响)。
                   例:{"sup_name": ["属性"]} 让"委外供应商属性"不被当供应商名称。
    - log:         可选回调;识别成功后上报"哪些列没被任何角色认领",
                   让"表里有列但缺别名"这类问题第一时间暴露(而非静默漏读)。

    选"能命中最多角色"的行作表头(命中数相同则取更靠前的行)。
    """
    exclude_contains = exclude_contains or {}
    best_row, best_map = None, {}
    # 空表/只读表未迭代时 max_row 可能为 None,or 0 兜底避免 min() 抛 TypeError
    for r in range(1, min(scan_rows, ws.max_row or 0) + 1):
        col_map = {}
        used = set()
        # 先精确后包含:避免"编码"抢占"供应商编码"、"编号"抢占"材料编号"等。
        for pass_exact in (True, False):
            for c in range(1, ws.max_column + 1):
                if c in used:
                    continue
                cell = ws.cell(r, c).value
                if cell is None:
                    continue
                text = str(cell).strip()
                for role, keys in header_keys.items():
                    if role in col_map:
                        continue
                    hit = (text in keys) if pass_exact else any(k in text for k in keys)
                    # 包含匹配阶段:排除该角色的干扰子串列(精确匹配不受影响)。
                    if hit and not pass_exact:
                        if any(sub in text for sub in exclude_contains.get(role, ())):
                            hit = False
                    if hit:
                        col_map[role] = c
                        used.add(c)
                        break
        if all(req in col_map for req in require) and len(col_map) > len(best_map):
            best_map = col_map
            best_row = r
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
