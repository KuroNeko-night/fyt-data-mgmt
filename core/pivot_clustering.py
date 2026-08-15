# -*- coding: utf-8 -*-
"""销售采购表的规格/单位归并与静态聚合层。

本模块集中维护七字段行 ``[版本,编码,名称,规格,数量,单位,最终采购数量]`` 的聚类与
聚合规则，供 :mod:`core.pivot_analysis` 的冲突检测和 :mod:`core.pivot_core` 的第二
阶段应用共用。模块不依赖工作表或界面，只从 :mod:`core.pivot_ooxml` 导入固定索引、
空值判断和排序键，避免与 OOXML 注入层产生循环依赖。

归并原则是“只改分组判断、不改展示优先值”：归一化键只用于判断两个写法是否同组，
最终显示值取出现次数最多、文本最短且首次出现最早的原始写法；这使 46A 等标准表
逐行结果不受影响。
"""
import re
from collections import defaultdict, OrderedDict

from .pivot_ooxml import _code_order_key, _is_blank

# 归一化后字段索引: 0版本 1编码 2名称 3规格 4数量 5单位 6最终采购数量。
F_VER, F_CODE, F_NAME, F_SPEC, F_QTY, F_UNIT, F_FINAL = 0, 1, 2, 3, 4, 5, 6

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

    尺寸分隔符 ``× ＊ * X`` 统一为小写 x；折叠连续空白；去首尾空白。
    """
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
    """去掉规格尾部的“包装数量注释”(如 ``，250/包``、``，1000根/包``)后的基准规格。

    仅剥离末段含“包”且含数字者；末段若无“包”(如 ``110g/m²``)则视为真实规格保留。
    剥离后括号必须平衡，否则宁可不剥，避免把真实规格截断。
    """
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
    """同 编码+名称 下, 把“仅差包装数量注释”或“仅差排版写法”的规格合并为同一规格。

    ``overrides`` 为 ``{gk: 指定规格写法}`` 的人工覆盖；缺省时行为与自动一致，不影响
    46A 等标准表。
    """
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
    """单位“简单度”排序键, 越小越优先。

    空单位最不优先；含分隔符(如 ``个/套``)次之；其余按字符长度，短的更简单。
    """
    if u == "":
        return (2, 0)
    has_sep = 1 if any(ch in u for ch in "/／\\、,，.·-") else 0
    return (has_sep, len(u))


def _name_unit_prior(rows):
    """名称级单位先验: 统计每个(归一化)名称在全部数据里最常用的“干净”单位。

    仅统计非空、非复合(不含 ``个/套`` 这类分隔符)的单位；平票取最简单。用于在某组
    单位平票时提供一致性倾向(如“多层板”整体多为“张”)。
    """
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
            if name_prior:
                # 先验命中平票集合或虽未命中也用它统一同名材料口径；缺失才退回最简单单位。
                best[key] = name_prior
            else:
                best[key] = min(tied,
                                key=lambda unit: (_unit_simplicity(unit), positions[unit]))
    return best, counts, sample


def compute_unit_best(rows):
    """计算每个 编码+名称+规格 组的单位选择。返回 ``(best, counts, sample)``。

    ``best[k]`` 为系统默认单位，``counts[k]`` 为 OrderedDict(单位->次数)，``sample[k]``
    为 ``(code, name, spec)`` 原始展示值。
    """
    return _compute_unit_best(lambda: iter(rows))


def unify_units(rows, overrides=None):
    """同 编码+名称+规格 的组统一单位。规则(按泛用性优化):

    1) 优先在“非空、非复合”单位中选；若该组只有复合单位(如 ``个/套``)才退而用之。
    2) 组内有唯一多数(严格胜出)-> 用它(尊重本组自身数据, 保证与标准表逐行一致)。
    3) 平票时 -> 采用该名称的“单位先验”打破平局，先验缺失才退回“最简单单位”。

    ``overrides`` 为 ``{gk: 指定单位}`` 的人工覆盖；缺省时行为与自动一致。
    """
    best, _counts, _sample = compute_unit_best(rows)
    if overrides:
        best = dict(best); best.update(overrides)
    for rec in rows:
        k = _unit_gkey(rec)
        if k is not None and k in best:
            rec[F_UNIT] = best[k]
    return rows


def drop_blank_code_rows(rows):
    """剔除“材料编号为空”的行。

    这类行无法归属到任何物料，在透视里会并成一个无意义的 ``(空白)`` 组，且会给行
    字段引入空项。返回 ``(保留行, 被剔除数)``；仅按编码判空，名称/规格可空但仍有
    编码的物料视为有效。
    """
    kept = [r for r in rows if not _is_blank(r[F_CODE])]
    return kept, len(rows) - len(kept)


def aggregate(rows):
    """按编码、名称、规格和单位分组并汇总最终采购数量。

    非数字度量按零参与，与透视缓存的空值策略保持一致。排序使用统一编码规则，确保静态
    A 至 E 列、OOXML ``items`` 和 ``rowItems`` 三处行序完全对齐。
    """
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
    # 排序: 编码优先按“无字母前缀在前”分组(见 _code_order_key), 再按 名称/规格/单位
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
