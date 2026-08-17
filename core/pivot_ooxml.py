# -*- coding: utf-8 -*-
"""原生 Excel 透视缓存与 OOXML 部件注入。

普通透视业务负责识别、清洗和聚合；本模块只处理工作簿 ZIP 内的缓存定义、缓存记录、
透视表关系和 Content Types。写入先生成完整临时归档再原子替换，注入失败不会留下半份
xlsx。该底层实现可独立测试，也避免高风险 XML 细节淹没主业务流程。
"""

from __future__ import annotations

import os
import re
import zipfile

from . import common_core


# 规范化七字段中的固定索引。这里不依赖 pivot_core，避免主业务入口与 OOXML 层循环导入。
F_CODE = 1


def _is_blank(value):
    """判断缓存字段是否为空或只包含空白。"""
    return value is None or str(value).strip() == ""


def _code_order_key(code):
    """生成材料编号排序键，使无字母前缀编码始终排在字母前缀编码之前。

    静态聚合和透视 items/rowItems 必须使用同一规则，否则 Excel 刷新后动态列与右侧
    人工维护列会发生行错位。
    """
    text = "" if code is None else str(code)
    has_letter_prefix = bool(text) and text[0].isascii() and text[0].isalpha()
    return (1 if has_letter_prefix else 0, text)


def _esc(s):
    """转义写入 HTML 报告的文本。"""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def _num(v):
    """解析可求和数值，明确排除布尔值并清洗中文数字格式。"""
    # bool 是 int 子类, float(True)=1.0 会把 TRUE/FALSE 当 1/0 求和, 先排除
    if isinstance(v, bool):
        return None
    # 文本先清洗(全角数字/句点→半角、去千分位逗号与零宽), 再转数
    if isinstance(v, str):
        v = common_core._num_str(v)
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
    """为七个透视缓存字段建立共享项、类型标记和数值范围。

    行字段必须建立稳定的 ``sharedItems`` 与值到缓存索引映射；普通字段记录空值、数字、
    字符串及最小最大值。最终采购数量混入非数字文本时按空处理，不能把整个度量字段标成
    字符串，否则 Excel 刷新后的求和会归零。
    """
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
                    n = _num(v)  # 前一判断已经确认可解析；此处取得规范化后的实际数值。
                    info["vmin"] = n if info["vmin"] is None else min(info["vmin"], n)
                    info["vmax"] = n if info["vmax"] is None else max(info["vmax"], n)
                elif fi == DATA_FIELD:
                    # 度量列(最终采购数量)混入的非数字文本(如"见附表")按空处理:
                    # aggregate 也把它当 0 求和; 若因此把整个度量字段标成字符串,
                    # Excel 透视刷新后该字段求和会归零, 与静态总计背离。故不置 has_str。
                    info["has_blank"] = True
                else:
                    info["has_str"] = True
        meta.append(info)
    return meta


def _cache_group_field_xml(m):
    """生成分组字段的 cacheField：sharedItems 逐个声明值或空项。"""
    name = _esc(FIELD_LABELS[m["idx"]])
    items = ["<m/>" if s == "" else '<s v="%s"/>' % _esc(s) for s in m["shared"]]
    # 含空项(<m/>)时必须声明 containsBlank="1", 否则 Excel 判定
    # sharedItems 与实际内容不符 -> 打开报"内容有问题"并自动修复。
    blank_attr = ' containsBlank="1"' if m["has_blank"] else ''
    return ('<cacheField name="%s" numFmtId="0">'
            '<sharedItems%s count="%d">%s</sharedItems>'
            '</cacheField>' % (name, blank_attr, len(items), "".join(items)))


def _cache_has_integer_values(m):
    """判断普通字段的数值上下界是否都是整数值。"""
    return (
        m["vmin"] is not None
        and float(m["vmin"]) == int(m["vmin"])
        and m["vmax"] is not None
        and float(m["vmax"]) == int(m["vmax"])
    )


def _cache_value_field_attrs(m):
    """生成普通字段 sharedItems 的属性列表。"""
    attrs = []
    if m["has_str"]:
        attrs.append('containsString="1"')
    else:
        attrs.append('containsString="0"')
    if m["has_blank"]:
        attrs.append('containsBlank="1"')
    if m["has_num"] and not m["has_str"]:
        attrs.append('containsNumber="1"')
        if _cache_has_integer_values(m):
            attrs.append('containsInteger="1"')
        attrs.append('minValue="%s"' % m["vmin"])
        attrs.append('maxValue="%s"' % m["vmax"])
    return attrs


def _cache_value_field_xml(m):
    """生成普通字段的 cacheField。"""
    name = _esc(FIELD_LABELS[m["idx"]])
    attrs = _cache_value_field_attrs(m)
    return ('<cacheField name="%s" numFmtId="0">'
            '<sharedItems %s/>'
            '</cacheField>' % (name, " ".join(attrs)))


def cache_definition_xml(meta, record_count, rid_records):
    """pivotCacheDefinition: 声明字段与 sharedItems。
       注意: 不设 refreshOnLoad。它会让 Excel 打开即重建并按自身排序重排行,
       覆盖我们写入的 rowItems 顺序(无字母前缀置顶等), 且重排后 A-E 与静态列
       F-J(汇总/差异…)错位、末行 G/H 落空。46A 标准透视表同样不带 refreshOnLoad——
       透视渲染值已由 openpyxl 写入表格单元格, Excel 打开时直接显示该缓存状态即可。"""
    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    parts.append('<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                 'r:id="%s" refreshedBy="prog" refreshedDate="0" '
                 'createdVersion="3" refreshedVersion="3" minRefreshableVersion="3" '
                 'recordCount="%d">' % (rid_records, record_count))
    parts.append('<cacheSource type="worksheet"><worksheetSource ref="__SRC_REF__" sheet="__SRC_SHEET__"/></cacheSource>')
    parts.append('<cacheFields count="7">')
    for m in meta:
        if m["group"]:
            parts.append(_cache_group_field_xml(m))
        else:
            parts.append(_cache_value_field_xml(m))
    parts.append('</cacheFields>')
    parts.append('</pivotCacheDefinition>')
    return "".join(parts)


def cache_records_xml(rows, meta):
    """生成逐行七字段的 ``pivotCacheRecords`` XML。

    分组字段用 ``x`` 引用 sharedItems 缓存索引；普通数字、文本和空值分别使用 ``n``、
    ``s`` 和 ``m``。编码方式必须与 :func:`build_fields_meta` 的类型声明一致，否则 Excel
    会修复文件或把度量错误地当作文本。
    """
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
                n = _num(v)
                if _is_blank(v):
                    cells.append("<m/>")
                elif n is not None and not m["has_str"]:
                    cells.append('<n v="%s"/>' % n)
                elif m["idx"] == DATA_FIELD:
                    # 度量列的非数字文本按空(<m/>)缓存,与 has_str 不提升、
                    # 与 aggregate 的"文本计 0"保持一致,避免刷新后求和归零。
                    cells.append("<m/>")
                else:
                    cells.append('<s v="%s"/>' % _esc(v))
        parts.append("<r>%s</r>" % "".join(cells))
    parts.append('</pivotCacheRecords>')
    return "".join(parts)


def pivot_table_xml(meta, agg, cache_id, name="数据透视表"):
    """
    pivotTable 定义. 行字段 编码/名称/规格/单位, 度量=求和最终采购数量.
    agg: [[code,name,spec,unit,sum], ...] 已排序. 单元格数值另由 openpyxl 渲染.
    布局采用表格式、无分类汇总并重复标签。引用范围覆盖 A1 到 E 的表头、数据和总计行。

    最易出错的边界是 ``rowItems`` 中 ``x`` 的值代表 ``items`` 排序后的位置，而不是缓存
    sharedItems 索引。函数先建立缓存索引到显示位置的映射，再用同一排序生成两处 XML，
    保证 Excel/WPS 打开时不修复文件，也不打乱静态业务列。
    """
    n = len(agg)
    last_row = 1 + n + 1                       # 表头+数据+总计
    ref = "A1:E%d" % last_row

    # 各行字段的 值->共享索引 映射
    mp = {fi: meta_by_idx(meta, fi)["map"] for fi in ROW_FIELDS}

    # 关键: rowItems 里 <x v="N"/> 的 N 是"该字段 <items> 排序列表中的位置",
    # 不是缓存共享索引(cache shared index)。<items> 按 shared 值升序排列(见下方
    # pivotFields), 若这里误写缓存索引, Excel 会判定引用越界/错乱 ->
    # 打开报"内容有问题"并自动修复, 修复后 A-E 行序被打乱, 与静态列 F-J 错位。
    # 故先按与 <items> 完全一致的排序, 建 缓存索引->位置 映射。
    orders = {}       # fi -> [cache_idx,...] 按 <items> 顺序
    pos_map = {}      # fi -> {cache_idx: 位置}
    for fi in ROW_FIELDS:
        m = meta_by_idx(meta, fi)
        # 材料编号(F_CODE)用 _code_order_key: 无字母前缀编码排最前, 与 aggregate 一致;
        # 其余字段按 shared 值字符串升序。
        if fi == F_CODE:
            keyf = lambda i: _code_order_key(m["shared"][i])
        else:
            keyf = lambda i: m["shared"][i]
        od = sorted(range(len(m["shared"])), key=keyf)
        orders[fi] = od
        pos_map[fi] = {ci: p for p, ci in enumerate(od)}

    # rowItems: 每个数据行一个 <i>, 末尾一个 grand total <i t="grand">
    ritems = []
    prev = [None, None, None, None]
    for grp in agg:
        vals = [grp[0], grp[1], grp[2], grp[3]]   # code,name,spec,unit
        rcommon = 0
        while rcommon < 4 and prev[rcommon] == vals[rcommon]:
            rcommon += 1
        xs = "".join(
            '<x v="%d"/>' % pos_map[ROW_FIELDS[k]][
                mp[ROW_FIELDS[k]][("" if _is_blank(vals[k]) else str(vals[k]).strip())]]
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
            # 复用上面 rowItems 用的同一排序(orders[fi]), 保证 <items> 顺序
            # 与 pos_map 位置一一对应, 二者绝不能各自 sort 以免错位。
            items = "".join('<item x="%d"/>' % i for i in orders[fi])
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
    """按透视字段索引查找对应的缓存元数据。"""
    for m in meta:
        if m["idx"] == fi:
            return m
    return None


def _attr(tag, name):
    """从单个 XML 标签文本中读取指定属性值。"""
    m = re.search(r'\b' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else None

def _sheet_target_for(zin_names, data):
    """从 workbook.xml + rels 找到 sheet 名 -> 归档内 worksheet 路径(如 xl/worksheets/sheet3.xml).
    兼容 XML 属性任意顺序与绝对、相对 Target。``zin_names`` 保留在接口中用于归档上下文，
    实际映射依据已经读取的 workbook XML 和关系文件。
    """
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
        arc = re.sub(r'/[^/]+/\.\./', '/', arc)  # 规范化关系目标中的单层父目录跳转。
        out[nm] = arc
    return out


_PIVOT_CACHE_RECORDS_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotCacheRecords"
)
_PIVOT_CACHE_DEFINITION_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotCacheDefinition"
)
_PIVOT_TABLE_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotTable"
)


def _read_xlsx_parts(xlsx_path):
    """完整读取 xlsx ZIP 的全部部件，避免在原归档上边读边写造成损坏。"""
    with zipfile.ZipFile(xlsx_path, "r") as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    return names, data


def _next_relationship_id(rels_xml):
    """返回关系 XML 中可用的下一个 ``rId`` 编号。"""
    used = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels_xml)]
    return max(used) + 1 if used else 1


def _relationship_element(rid, relationship_type, target):
    """生成单个 OPC 关系元素。"""
    return '<Relationship Id="%s" Type="%s" Target="%s"/>' % (rid, relationship_type, target)


def _relationship_part(relationship_type, target):
    """生成以 ``rId1`` 为唯一关系的独立 .rels 部件。"""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + _relationship_element("rId1", relationship_type, target)
        + '</Relationships>'
    )


def _content_type_override(part_name, content_suffix):
    """生成 Content Types 中单个部件覆盖声明。"""
    return ('<Override PartName="/%s" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.%s+xml"/>' % (part_name, content_suffix))


def _pivot_part_paths(i):
    """返回第 ``i`` 个透视的缓存定义、缓存记录和透视表部件路径。"""
    return (
        "xl/pivotCache/pivotCacheDefinition%d.xml" % i,
        "xl/pivotCache/pivotCacheRecords%d.xml" % i,
        "xl/pivotTables/pivotTable%d.xml" % i,
    )


def _build_pivot_parts(pv, i, next_rid):
    """生成单个透视的缓存 XML、透视表 XML 及其关系注册。

    返回 ``(新部件, Content Types 覆盖项, workbook 缓存声明, workbook 关系元素)``。
    """
    cache_id = 1000 + i  # 使用独立高位缓存编号，避免与工作簿潜在既有编号碰撞。
    cdef, crec, ptbl = _pivot_part_paths(i)

    meta = build_fields_meta(pv["rows"])
    # cacheDefinition (rid 指向 records, 局部 rId1)
    cdx = cache_definition_xml(meta, len(pv["rows"]), "rId1")
    cdx = cdx.replace("__SRC_REF__", _esc(pv["src_ref"])).replace("__SRC_SHEET__", _esc(pv["src_sheet"]))
    new_parts = {cdef: cdx.encode("utf-8")}
    new_parts[crec] = cache_records_xml(pv["rows"], meta).encode("utf-8")
    new_parts["xl/pivotCache/_rels/pivotCacheDefinition%d.xml.rels" % i] = _relationship_part(
        _PIVOT_CACHE_RECORDS_REL, "pivotCacheRecords%d.xml" % i
    ).encode("utf-8")

    new_parts[ptbl] = pivot_table_xml(meta, pv["agg"], cache_id, pv["name"]).encode("utf-8")
    new_parts["xl/pivotTables/_rels/pivotTable%d.xml.rels" % i] = _relationship_part(
        _PIVOT_CACHE_DEFINITION_REL, "../pivotCache/pivotCacheDefinition%d.xml" % i
    ).encode("utf-8")

    ct_overrides = [
        _content_type_override(cdef, "pivotCacheDefinition"),
        _content_type_override(crec, "pivotCacheRecords"),
        _content_type_override(ptbl, "pivotTable"),
    ]
    rid = "rId%d" % next_rid
    wb_cache = (cache_id, rid)
    wb_rel_add = _relationship_element(
        rid, _PIVOT_CACHE_DEFINITION_REL, "pivotCache/pivotCacheDefinition%d.xml" % i
    )
    return new_parts, ct_overrides, wb_cache, wb_rel_add


def _append_sheet_pivot_relationship(data, sheet_name, sheet_target, pivot_index):
    """把透视 sheet 到 pivotTable 的关系写入对应 worksheet rels。"""
    st = sheet_target.get(sheet_name)
    if not st:
        return
    base = os.path.basename(st)
    relpath = os.path.dirname(st) + "/_rels/" + base + ".rels"
    if relpath in data:
        sr = data[relpath].decode("utf-8")
        sused = [int(x) for x in re.findall(r'Id="rId(\d+)"', sr)]
        srid = "rId%d" % ((max(sused) + 1) if sused else 1)
        add = _relationship_element(
            srid, _PIVOT_TABLE_REL, "../pivotTables/pivotTable%d.xml" % pivot_index
        )
        data[relpath] = sr.replace("</Relationships>", add + "</Relationships>").encode("utf-8")
    else:
        data[relpath] = _relationship_part(
            _PIVOT_TABLE_REL, "../pivotTables/pivotTable%d.xml" % pivot_index
        ).encode("utf-8")


def _insert_pivot_caches_xml(wbx, wb_caches):
    """向 workbook.xml 插入 ``pivotCaches``，并确保根元素声明 ``xmlns:r``。"""
    if "xmlns:r=" not in wbx[:wbx.find(">") + 1]:
        wbx = wbx.replace("<workbook ",
            '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    caches_xml = '<pivotCaches>' + "".join(
        '<pivotCache cacheId="%d" r:id="%s"/>' % (cid, rid) for cid, rid in wb_caches) + '</pivotCaches>'
    # OOXML schema 要求 pivotCaches 必须在 calcPr 之后(顺序: sheets, definedNames,
    # calcPr, ..., pivotCaches, extLst). 顺序错会导致 Excel 报"文件损坏".
    m = re.search(r'<calcPr\b[^>]*/>', wbx)
    if m:
        return wbx[:m.end()] + caches_xml + wbx[m.end():]
    m2 = re.search(r'</calcPr>', wbx)
    if m2:
        return wbx[:m2.end()] + caches_xml + wbx[m2.end():]
    if "<extLst" in wbx:
        return wbx.replace("<extLst", caches_xml + "<extLst", 1)
    return wbx.replace("</workbook>", caches_xml + "</workbook>", 1)


def _write_xlsx_parts(xlsx_path, data):
    """把内存部件写为临时归档后原子替换原 xlsx。"""
    tmp = xlsx_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    os.replace(tmp, xlsx_path)  # 完整新归档写成后再替换，避免留下半份 xlsx。


def inject_pivots(xlsx_path, pivots):
    """把原生透视缓存、透视表和关系部件注入现有 xlsx。

    ``pivots`` 每项声明透视页、源数据页、源范围、清洗行、聚合值和透视名称。函数先完整
    读取 ZIP 包，在内存中补齐 Content Types、工作簿缓存关系、工作表关系和三类透视 XML，
    最后写临时归档并原子替换。任一异常会保留原静态工作簿，由调用方记录注入失败。
    """
    names, data = _read_xlsx_parts(xlsx_path)
    sheet_target = _sheet_target_for(names, data)
    new_parts = {}
    ct_overrides = []
    wb_caches = []          # (cacheId, rId) for workbook.xml
    wb_rels_add = []        # workbook.xml.rels 新增

    # 现有 workbook rels 里最大 rId
    wb_rels = data["xl/_rels/workbook.xml.rels"].decode("utf-8")
    next_rid = _next_relationship_id(wb_rels)

    for i, pv in enumerate(pivots, start=1):
        parts, overrides, wb_cache, wb_rel_add = _build_pivot_parts(pv, i, next_rid)
        new_parts.update(parts)
        ct_overrides.extend(overrides)
        wb_caches.append(wb_cache)
        wb_rels_add.append(wb_rel_add)
        next_rid += 1
        # sheet rels: 透视 sheet -> pivotTable
        _append_sheet_pivot_relationship(data, pv["sheet"], sheet_target, i)

    # [Content_Types].xml
    ct = data["[Content_Types].xml"].decode("utf-8")
    data["[Content_Types].xml"] = ct.replace("</Types>", "".join(ct_overrides) + "</Types>").encode("utf-8")

    # workbook.xml.rels
    data["xl/_rels/workbook.xml.rels"] = wb_rels.replace(
        "</Relationships>", "".join(wb_rels_add) + "</Relationships>").encode("utf-8")

    # workbook.xml: 插入 <pivotCaches>; 确保根元素声明 xmlns:r
    wbx = _insert_pivot_caches_xml(data["xl/workbook.xml"].decode("utf-8"), wb_caches)
    data["xl/workbook.xml"] = wbx.encode("utf-8")

    for p, b in new_parts.items():
        data[p] = b

    _write_xlsx_parts(xlsx_path, data)
