# -*- coding: utf-8 -*-
"""主数据档案：供应商编码与材料主数据的持久化台账。

档案文件默认位于应用数据目录，Web 端通过 FYT_CATALOG_PATH 指向服务端数据根；
读改写统一走 storage_lock.file_lock + 临时文件原子替换，跨进程安全。
采购计划导入运行时自动学习模板供应商映射与批次材料信息，
模板缺失供应商代码时可用档案补全，不再必须中断。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from collections.abc import Callable, Iterable, Mapping, MutableMapping

from . import paths, storage_lock


MATERIAL_FIELDS = ("name", "spec", "unit", "supplier")
FIELD_LABELS = {
    "name": "材料名称",
    "spec": "规格",
    "unit": "单位",
    "supplier": "供应商",
    "supplier_code": "供应商编码",
}


def _text(value: object) -> str:
    """把主数据键值转换为去除首尾空白的文本。"""
    if value is None:
        return ""
    return str(value).strip()


def _is_blank(value: object) -> bool:
    """判断值是否可被主数据库补全；零等非空值不视为空缺。"""
    return value is None or not str(value).strip()


def _normalized_text(value: object, *, remove_spaces: bool = False) -> str:
    """生成仅用于匹配的 Unicode 标准文本，不改变正式库展示值。

    NFKC 会统一全角字母数字，随后移除零宽字符和 BOM。供应商名称保留单个词间空格并
    忽略大小写；编码别名可选择移除全部空格，以兼容 Excel 常见格式差异。
    """
    text = unicodedata.normalize("NFKC", _text(value))
    text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
    if remove_spaces:
        return re.sub(r"\s+", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _code_alias(value: object) -> str:
    """生成仅供查找的编码别名，不改变正式库中已有编码的展示写法。

    纯数字编码从 Excel 读取后常变成 ``123.0``，别名会恢复为 ``123``；包含真实小数
    或字母的编码不会被截断。
    """
    text = _normalized_text(value, remove_spaces=True)
    match = re.fullmatch(r"([+-]?\d+)\.0+", text)
    return match.group(1) if match else text


def _add_counts(counts: MutableMapping[str, int] | None, fields: Iterable[str]) -> None:
    """累加本次业务运行实际由主数据库补入的字段数量。"""
    if counts is None:
        return
    for field in fields:
        counts[field] = int(counts.get(field, 0)) + 1


def log_fill_summary(log, feature: str, counts: Mapping[str, int] | None) -> None:
    """统一记录业务运行中由主数据库补全的字段数量。

    只输出大于零的字段，既便于审计主数据参与程度，也避免日志充斥没有发生补全的零值。
    """
    if not log or not counts:
        return
    parts = [
        "%s %d 项" % (FIELD_LABELS.get(field, field), int(count))
        for field, count in counts.items() if int(count) > 0
    ]
    if parts:
        log("主数据库已为%s补全：%s。" % (feature, "、".join(parts)))


class CatalogResolver:
    """一次性主数据库快照解析器，供单次业务运行重复查找。

    精确编码优先；仅在别名唯一时兼容 ``123`` 与 ``123.0``、全角字符等
    Excel 常见表现。若多个正式编码折叠成同一别名，则放弃模糊命中，避免错补。
    """

    def __init__(self, data: object | None = None):
        """加载并索引一次主数据快照，构建精确和唯一别名查找表。

        同一业务运行应复用解析器，避免每行重新读取 JSON。若两个正式键经标准化后得到
        同一别名，该别名会被标记为歧义并从模糊索引移除，后续只能精确匹配，防止错补。
        ``signature`` 是快照内容摘要，可用于缓存和结果投影判断主数据版本。
        """
        self.data = _normalize(load() if data is None else data)
        self._materials_exact: dict[str, tuple[str, dict[str, str]]] = {}
        self._materials_alias: dict[str, tuple[str, dict[str, str]]] = {}
        self._ambiguous_material_aliases: set[str] = set()
        materials = self.data.get("materials", {})
        if isinstance(materials, dict):
            for raw_code, raw_item in materials.items():
                code = _text(raw_code)
                item = dict(raw_item) if isinstance(raw_item, dict) else {}
                self._materials_exact[code] = (code, item)
                alias = _code_alias(code)
                existing = self._materials_alias.get(alias)
                if existing is not None and existing[0] != code:
                    # 例如正式库同时存在 123 与 123.0 时，模糊查找必须失效而不是任选一条。
                    self._ambiguous_material_aliases.add(alias)
                    self._materials_alias.pop(alias, None)
                elif alias not in self._ambiguous_material_aliases:
                    self._materials_alias[alias] = (code, item)

        self._suppliers_exact: dict[str, str] = {}
        self._suppliers_alias: dict[str, tuple[str, str]] = {}
        self._ambiguous_supplier_aliases: set[str] = set()
        suppliers = self.data.get("suppliers", {})
        if isinstance(suppliers, dict):
            for raw_name, raw_code in suppliers.items():
                name = _text(raw_name)
                code = _text(raw_code)
                self._suppliers_exact[name] = code
                alias = _normalized_text(name)
                existing = self._suppliers_alias.get(alias)
                if existing is not None and existing[1] != code:
                    # 名称标准化后相同但编码不同属于歧义，不允许静默补入任一编码。
                    self._ambiguous_supplier_aliases.add(alias)
                    self._suppliers_alias.pop(alias, None)
                elif alias not in self._ambiguous_supplier_aliases:
                    self._suppliers_alias[alias] = (name, code)

        # 更新时间不代表业务内容，签名只覆盖供应商和材料映射，减少无意义的缓存失效。
        signature_data = {
            "suppliers": self.data.get("suppliers", {}),
            "materials": self.data.get("materials", {}),
        }
        payload = json.dumps(signature_data, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        self.signature = hashlib.sha256(payload).hexdigest()

    def material_key(self, code: object) -> str:
        """返回正式材料编码键；精确匹配优先，歧义别名拒绝命中。"""
        exact = self._materials_exact.get(_text(code))
        if exact is not None:
            return exact[0]
        alias = _code_alias(code)
        if alias in self._ambiguous_material_aliases:
            return ""
        matched = self._materials_alias.get(alias)
        return matched[0] if matched is not None else ""

    def resolve_material(self, code: object) -> dict[str, str]:
        """返回材料字段副本，未找到或别名歧义时返回空字典。"""
        key = self.material_key(code)
        if not key:
            return {}
        return dict(self._materials_exact[key][1])  # 返回副本，调用方不能意外修改解析器快照。

    def has_material(self, code: object) -> bool:
        """判断材料编码能否安全解析到唯一正式记录。"""
        return bool(self.material_key(code))

    def material_alias_is_ambiguous(self, code: object) -> bool:
        """判断材料编码的标准化别名是否对应多个正式键。"""
        return _code_alias(code) in self._ambiguous_material_aliases

    def resolve_supplier_code(self, name: object) -> str:
        """按供应商名称查找编码，精确值优先且拒绝歧义别名。"""
        exact = self._suppliers_exact.get(_text(name))
        if exact is not None:
            return exact
        alias = _normalized_text(name)
        if alias in self._ambiguous_supplier_aliases:
            return ""
        matched = self._suppliers_alias.get(alias)
        return matched[1] if matched is not None else ""

    def supplier_name_key(self, name: object) -> str:
        """返回供应商在正式库中的原始名称键，供更新时保留展示写法。"""
        exact_name = _text(name)
        if exact_name in self._suppliers_exact:
            return exact_name
        alias = _normalized_text(name)
        if alias in self._ambiguous_supplier_aliases:
            return ""
        matched = self._suppliers_alias.get(alias)
        return matched[0] if matched is not None else ""

    def has_supplier(self, name: object) -> bool:
        """判断供应商名称能否安全解析到非空编码。"""
        return bool(self.resolve_supplier_code(name))

    def supplier_alias_is_ambiguous(self, name: object) -> bool:
        """判断标准化供应商名称是否对应多个不同编码。"""
        return _normalized_text(name) in self._ambiguous_supplier_aliases

    def complete_material(
        self,
        code: object,
        current: Mapping[str, object] | None = None,
        *,
        fields: Iterable[str] = MATERIAL_FIELDS,
        counts: MutableMapping[str, int] | None = None,
    ) -> dict[str, str]:
        """返回主库可补入的空字段；从不覆盖 ``current`` 中已有值。

        ``fields`` 限制当前业务允许补哪些字段，未知字段会被忽略。只有源记录为空且主库
        对应值非空时才返回补充值，并同步记录补全计数。
        """
        item = self.resolve_material(code)
        if not item:
            return {}
        current = current or {}
        additions = {
            field: _text(item.get(field))
            for field in fields
            # 双重白名单既保护材料结构，也避免调用方拼错字段后写入任意键。
            if field in MATERIAL_FIELDS and _is_blank(current.get(field))
            and _text(item.get(field))
        }
        _add_counts(counts, additions)
        return additions

    def fill_mapping(
        self,
        row: MutableMapping[str, object],
        *,
        code_key: str = "code",
        field_keys: Mapping[str, str] | None = None,
        fields: Iterable[str] = MATERIAL_FIELDS,
        counts: MutableMapping[str, int] | None = None,
    ) -> dict[str, str]:
        """按字段映射就地补空，返回本行实际补入的主数据字段。

        不同业务行的字段名可能是 ``material_name``、``name`` 等，通过 ``field_keys``
        映射到统一主数据字段。写入只应用 :meth:`complete_material` 返回的空缺项。
        """
        field_keys = field_keys or {field: field for field in MATERIAL_FIELDS}
        current = {
            field: row.get(target_key)
            for field, target_key in field_keys.items()
        }
        additions = self.complete_material(
            row.get(code_key), current, fields=fields, counts=counts)
        for field, value in additions.items():
            target_key = field_keys.get(field)
            if target_key:
                row[target_key] = value
        return additions

    def complete_supplier_code(
        self,
        supplier_name: object,
        current_code: object = None,
        *,
        counts: MutableMapping[str, int] | None = None,
    ) -> str:
        """仅在当前编码为空时按供应商名称补全编码，并记录补全次数。"""
        if not _is_blank(current_code):
            # 源表已有编码具有最高优先级，即使主库中存在不同值也不得被动覆盖。
            return _text(current_code)
        code = self.resolve_supplier_code(supplier_name)
        if code:
            _add_counts(counts, ("supplier_code",))
        return code


class CatalogConflictError(ValueError):
    """正式主数据在复核后发生变化，当前合并需要重新确认。

    异常携带每条关系的期望旧值、当前值和拟写值，导入批次层据此只重开真正受影响的
    冲突，而不丢弃其他已经确认的决策。
    """

    def __init__(self, conflicts: list[dict[str, str]]):
        """构造冲突异常并保存结构化冲突列表。"""
        super().__init__("正式主数据已发生变化，请重新复核冲突")
        self.conflicts = conflicts


def catalog_path() -> str:
    """返回正式主数据 JSON 路径，允许 Web 服务端重定向到数据根。"""
    override = os.environ.get("FYT_CATALOG_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(paths.app_data_dir(), "主数据.json")


def _now_iso() -> str:
    """生成正式主数据最后更新时间的秒级 ISO 文本。"""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _empty() -> dict[str, object]:
    """返回字段齐全且相互独立的空主数据结构。"""
    return {"suppliers": {}, "materials": {}, "updated_at": ""}


def _normalize(data: object, *, strict: bool = False) -> dict[str, object]:
    """校验并清洗从 JSON 读取的主数据结构。

    只保留已支持的材料字段和非空供应商映射，阻止历史脏键扩散到业务模块。严格模式
    用于写操作，文件损坏时拒绝覆盖；宽松模式用于首次启动或只读解析，可回退空结构。
    """
    if not isinstance(data, dict):
        if strict:
            raise ValueError("主数据档案格式无效")
        return _empty()
    suppliers = data.get("suppliers")
    materials = data.get("materials")
    if not isinstance(suppliers, dict) or not isinstance(materials, dict):
        if strict:
            raise ValueError("主数据档案缺少供应商或材料数据")
        return _empty()
    return {
        "suppliers": {
            str(key).strip(): str(value).strip()
            for key, value in suppliers.items()
            if str(key).strip() and str(value).strip()
        },
        "materials": {
            str(key).strip(): {
                str(field): str(value).strip()
                for field, value in (item.items() if isinstance(item, dict) else {})
                if str(field) in {"name", "spec", "unit", "supplier"} and str(value).strip()
            }
            for key, item in materials.items()
            if str(key).strip()
        },
        "updated_at": str(data.get("updated_at") or ""),
    }


def _read_unlocked(path: str, *, strict: bool = False) -> dict[str, object]:
    """在调用方已决定锁策略的前提下读取并规范化主数据文件。"""
    if not os.path.isfile(path):
        return _empty()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        if strict:
            raise ValueError("主数据档案损坏或无法读取") from exc
        return _empty()
    return _normalize(data, strict=strict)


def load() -> dict[str, object]:
    """读取当前主数据快照。

    写入采用原子替换，因此普通只读无需持有跨进程锁；读者只会看到完整旧文件或完整
    新文件。损坏文件在此宽松回退，管理写操作则使用严格读取避免覆盖损坏现场。
    """
    return _read_unlocked(catalog_path())


def _write_unlocked(path: str, data: dict[str, object]) -> None:
    """更新时间戳并通过同目录临时文件原子写入主数据。

    调用方必须已持有主数据文件锁。临时文件完成写入后再替换目标，避免进程中断产生
    半份 JSON；清理异常不会掩盖原始写入错误。
    """
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    data["updated_at"] = _now_iso()
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    descriptor, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
        os.replace(temp_path, path)  # 同目录替换保证目标始终是一个完整 JSON 文件。
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                # 临时文件残留不影响正式库读取，保留真正异常给调用方处理。
                pass


def _update(mutator: Callable[[dict[str, object]], object]) -> object:
    """在同一跨进程锁内完成读取、修改与原子替换。

    严格读取是关键保护：若现有文件损坏，写操作必须失败而不是从空库重新保存并抹掉
    可恢复数据。回调只负责修改内存对象，持久化协议集中在此处。
    """
    path = catalog_path()
    with storage_lock.file_lock(path):
        data = _read_unlocked(path, strict=True)
        result = mutator(data)
        _write_unlocked(path, data)
        return result


def _apply_supplier_learning_item(suppliers, resolver, learned_aliases, name, code):
    """在锁内学习一条供应商映射，返回冲突名称或 ``"added"``。"""
    alias = _normalized_text(name)
    learned = learned_aliases.get(alias)
    if learned is not None:
        return name if learned[1] != code else None
    supplier_key = resolver.supplier_name_key(name)
    if not supplier_key and resolver.supplier_alias_is_ambiguous(name):
        return name
    current = _text(suppliers.get(supplier_key)) if supplier_key else ""
    if not current:
        suppliers[name] = code
        learned_aliases[alias] = (name, code)
        return "added"
    return name if current != code else None


def learn_suppliers(mapping: dict[str, str], log=None) -> int:
    """被动学习供应商映射，仅填空缺，不覆盖管理员确认值。

    单次业务文件内相同标准名称给出多个编码时记为冲突并跳过；正式库已有不同编码时也
    只记录提示。返回值只统计真正新增的供应商映射。
    """
    normalized = {
        str(name).strip(): str(code).strip()
        for name, code in mapping.items()
        if str(name).strip() and str(code).strip()
    }
    if not normalized:
        return 0

    def mutate(data: dict[str, object]) -> int:
        """在锁内补充缺失供应商映射并收集被保留的冲突项。"""
        suppliers = data["suppliers"]
        added = 0
        conflicts = []
        resolver = CatalogResolver(data)
        # 解析器只反映修改前快照，learned_aliases 用于检测本次循环中新加入名称的重复。
        learned_aliases: dict[str, tuple[str, str]] = {}
        for name, code in normalized.items():
            outcome = _apply_supplier_learning_item(
                suppliers, resolver, learned_aliases, name, code,
            )
            if outcome == "added":
                added += 1
            elif outcome:
                conflicts.append(outcome)
        if log and conflicts:
            log("主数据库已有 %d 条不同的供应商编码，已保留管理员确认值：%s%s。"
                % (len(conflicts), "、".join(conflicts[:8]),
                   " 等" if len(conflicts) > 8 else ""))
        return added

    return int(_update(mutate))


def _apply_material_learning_item(materials, resolver, learned_keys, item):
    """在锁内学习一条材料记录，返回 ``(是否新增, 冲突字段列表)``。"""
    source_code = item["code"]
    alias = _code_alias(source_code)
    code = resolver.material_key(source_code) or learned_keys.get(alias)
    if not code and resolver.material_alias_is_ambiguous(source_code):
        return False, ["%s/编码歧义" % source_code]
    code = code or source_code
    current = materials.get(code)
    added = False
    if current is None:
        added = True
        current = {}
        if alias:
            learned_keys[alias] = code
    conflicts = []
    for field in ("name", "spec", "unit", "supplier"):
        if field not in item:
            continue
        existing = _text(current.get(field))
        if not existing:
            # 被动学习只填空字段，这是管理员维护值不被业务文件覆盖的核心约束。
            current[field] = item[field]
        elif existing != item[field]:
            conflicts.append("%s/%s" % (code, FIELD_LABELS[field]))
    materials[code] = current
    return added, conflicts


def learn_materials(items: list[dict[str, object]], log=None) -> int:
    """被动学习材料信息，仅填空缺，不覆盖管理员确认值。

    同一材料的名称、规格、单位和供应商逐字段补空，已确认字段即使与源表不同也保留。
    返回新增材料编码数量，不把既有材料补充字段的次数误计为新增材料数。
    """
    normalized: list[dict[str, str]] = []
    for item in items:
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        current = {"code": code}
        for field in ("name", "spec", "unit", "supplier"):
            value = item.get(field)
            if value is not None and str(value).strip():
                current[field] = str(value).strip()
        normalized.append(current)
    if not normalized:
        return 0

    def mutate(data: dict[str, object]) -> int:
        """在锁内逐材料补空，并统计新增编码与字段冲突。"""
        materials = data["materials"]
        added = 0
        conflicts: set[str] = set()
        resolver = CatalogResolver(data)
        # 本轮新增编码还不在 resolver 快照内，通过别名表让后续同义编码落到同一记录。
        learned_keys: dict[str, str] = {}
        for item in normalized:
            added_item, item_conflicts = _apply_material_learning_item(
                materials, resolver, learned_keys, item,
            )
            if added_item:
                added += 1
            conflicts.update(item_conflicts)
        if log and conflicts:
            values = sorted(conflicts)
            log("主数据库已有 %d 项不同的材料字段，已保留管理员确认值：%s%s。"
                % (len(values), "、".join(values[:8]),
                   " 等" if len(values) > 8 else ""))
        return added

    return int(_update(mutate))


def resolve_supplier_code(name: str) -> str:
    """按供应商名称查档案编码，未收录或别名歧义时返回空串。"""
    return CatalogResolver().resolve_supplier_code(name)


def list_all() -> dict[str, object]:
    """返回当前正式主数据快照，供管理界面展示。"""
    return load()


def upsert_supplier(name: str, code: str) -> None:
    """由管理员新增或覆盖供应商编码。"""
    name = str(name).strip()
    code = str(code).strip()
    if not name or not code:
        raise ValueError("供应商名称与编码不能为空")
    _update(lambda data: data["suppliers"].__setitem__(name, code))


def delete_supplier(name: str) -> None:
    """按正式名称删除供应商；空名称视为无操作。"""
    key = str(name).strip()
    if not key:
        return
    _update(lambda data: data["suppliers"].pop(key, None))


def upsert_material(code: str, name: str, spec: str = "", unit: str = "", supplier: str = "") -> None:
    """由管理员新增材料或覆盖其非空字段。

    传入空字段不会清除既有值；需要清除或更精细维护时应由专门管理协议显式表达，避免
    普通表单缺省值造成数据丢失。
    """
    code = str(code).strip()
    if not code:
        raise ValueError("材料编号不能为空")
    values = {
        field: str(value).strip()
        for field, value in {
            "name": name, "spec": spec, "unit": unit, "supplier": supplier,
        }.items()
        if str(value).strip()
    }

    def mutate(data: dict[str, object]) -> None:
        """在锁内合并管理员提交的非空字段。"""
        item = data["materials"].get(code, {})
        item.update(values)
        data["materials"][code] = item

    _update(mutate)


def delete_material(code: str) -> None:
    """按正式材料编码删除记录；空编码视为无操作。"""
    key = str(code).strip()
    if not key:
        return
    _update(lambda data: data["materials"].pop(key, None))


_MATERIAL_RELATION_FIELDS = {
    "material_name": "name",
    "material_spec": "spec",
    "material_unit": "unit",
    "material_supplier": "supplier",
}


def relation_value(data: dict[str, object], relation_type: str, key: str) -> str:
    """读取导入协议中的统一关系类型所对应的正式主数据值。

    供应商和材料关系都通过 ``CatalogResolver`` 处理唯一别名，保证冲突分析与最终写入
    使用相同匹配规则；未知关系类型立即拒绝。
    """
    normalized_key = str(key).strip()
    if relation_type == "supplier_code":
        return CatalogResolver(data).resolve_supplier_code(normalized_key)
    field = _MATERIAL_RELATION_FIELDS.get(relation_type)
    if not field:
        raise ValueError("不支持的主数据关系类型")
    resolver = CatalogResolver(data)
    material_key = resolver.material_key(normalized_key)
    item = data.get("materials", {}).get(material_key, {})
    return str(item.get(field, "")) if isinstance(item, dict) else ""


def _normalized_relations(
    relations: Iterable[dict[str, object]],
) -> list[tuple[str, str, str, str]]:
    """清洗管理员确认关系，并提前拒绝未知关系类型。"""
    normalized: list[tuple[str, str, str, str]] = []
    for relation in relations:
        relation_type = _text(relation.get("relation_type"))
        key = _text(relation.get("key"))
        value = _text(relation.get("value"))
        expected_current = _text(relation.get("expected_current"))
        if not relation_type or not key or not value:
            continue  # 未填写完整的管理界面草稿不参与正式合并。
        relation_value(_empty(), relation_type, key)  # 复用正式读取入口验证类型，避免第二套白名单漂移。
        normalized.append((relation_type, key, value, expected_current))
    return normalized


def _relation_conflicts(
    data: dict[str, object], relations: list[tuple[str, str, str, str]],
) -> list[dict[str, str]]:
    """返回乐观并发校验失败的关系；目标值已存在视为幂等成功。"""
    conflicts: list[dict[str, str]] = []
    for relation_type, key, value, expected_current in relations:
        current = relation_value(data, relation_type, key)
        if current in {value, expected_current}:
            continue
        conflicts.append({
            "relation_type": relation_type,
            "key": key,
            "value": value,
            "expected_current": expected_current,
            "current_value": current,
        })
    return conflicts


def _backup_catalog_snapshot(path: str, backup_dir: str | None) -> str:
    """在正式写入前保存主数据恢复点；库不存在时保存结构化空库。"""
    if not backup_dir:
        return ""
    target_dir = os.path.abspath(backup_dir)
    os.makedirs(target_dir, exist_ok=True)
    backup_path = os.path.join(
        target_dir, "主数据-%s.json" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
    )
    if os.path.isfile(path):
        shutil.copy2(path, backup_path)
    else:
        # 首次建库也留下可读取的空库快照，使管理员每次合并都有明确恢复起点。
        with open(backup_path, "w", encoding="utf-8", newline="") as handle:
            json.dump(_empty(), handle, ensure_ascii=False, indent=1)
    return backup_path


def _apply_supplier_relation(data: dict[str, object], key: str, value: str) -> None:
    """更新供应商编码，并尽量保留正式库已有的供应商展示名称。"""
    resolver = CatalogResolver(data)
    supplier_key = resolver.supplier_name_key(key) or key
    data["suppliers"][supplier_key] = value


def _apply_material_relation(
    data: dict[str, object], relation_type: str, key: str, value: str,
) -> str:
    """更新材料字段并返回实际采用的正式材料编码键。"""
    resolver = CatalogResolver(data)
    # 先复用正式别名；新增材料再采用规范化编码，避免把纯数字 ``123.0`` 建成新正式键。
    material_key = resolver.material_key(key) or _code_alias(key) or key
    item = data["materials"].get(material_key, {})
    item[_MATERIAL_RELATION_FIELDS[relation_type]] = value
    data["materials"][material_key] = item
    return material_key


def _apply_relation_changes(
    data: dict[str, object], relations: list[tuple[str, str, str, str]],
) -> tuple[int, int, set[str]]:
    """在内存快照中应用非幂等关系，并返回变更分类计数。"""
    changed = 0
    suppliers_changed = 0
    material_codes: set[str] = set()
    for relation_type, key, value, _expected_current in relations:
        if relation_value(data, relation_type, key) == value:
            continue  # 重复确认不计数，也不触发无意义写盘。
        if relation_type == "supplier_code":
            _apply_supplier_relation(data, key, value)
            suppliers_changed += 1
        else:
            material_codes.add(_apply_material_relation(data, relation_type, key, value))
        changed += 1
    return changed, suppliers_changed, material_codes


def apply_relations(
    relations: Iterable[dict[str, object]], *, backup_dir: str | None = None,
) -> dict[str, int | str]:
    """原子应用已复核关系，可选在写入前保存正式主数据快照。

    每条关系携带管理员确认时看到的 ``expected_current``。锁内再次读取正式库后，只有
    当前值仍等于期望旧值或已经等于目标值才允许继续；否则整体拒绝并返回结构化冲突，
    防止两个批次互相覆盖。所有校验通过后先备份，再在内存中应用并一次原子写入。
    """
    normalized = _normalized_relations(relations)
    if not normalized:
        return {"changed": 0, "suppliers": 0, "materials": 0, "backup_path": ""}

    path = catalog_path()
    # 冲突校验、备份和写入位于同一锁内，避免校验后到提交前正式库发生变化。
    with storage_lock.file_lock(path):
        data = _read_unlocked(path, strict=True)
        conflicts = _relation_conflicts(data, normalized)
        if conflicts:
            raise CatalogConflictError(conflicts)
        backup_path = _backup_catalog_snapshot(path, backup_dir)
        changed, suppliers_changed, material_codes = _apply_relation_changes(data, normalized)
        if changed:
            _write_unlocked(path, data)  # 全批关系在内存中成功应用后一次原子提交，不暴露半批次状态。
        return {
            "changed": changed,
            "suppliers": suppliers_changed,
            "materials": len(material_codes),
            "backup_path": backup_path,
        }
