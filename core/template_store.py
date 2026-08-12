# -*- coding: utf-8 -*-
"""
表格模板版本与迁移规则中心
==========================
按用户名称、功能类型和页签名组织模板族；同一模板的表头结构变化会形成递增版本，
并保存与上一版本之间的新增、移除、移动和同位置改名摘要。核心层只使用标准库，
桌面端和 Web 端通过同一 JSON 仓库查看模板历史与维护迁移规则。

模板只保存规范化表头、人工映射 ID、备注和显式迁移规则，不复制正文数据或源文件。
表头指纹保留列顺序和中间空列，因此列移动也会生成新版本；完全相同结构再次保存时
只更新映射、备注和时间，不制造重复版本。模板族最多保留最近 200 个。

所有读改写使用文件锁与同目录临时文件原子替换。迁移规则只执行管理员明确配置的
rename、drop 和 defaults，不推断业务含义，也不自动修改原工作簿。
"""
import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata

from . import paths
from .storage_lock import file_lock


SCHEMA_VERSION = 1


def _store_path():
    """返回模板中心 JSON 路径，并允许环境变量隔离 Web 用户或测试。"""
    override = os.environ.get("FYT_TEMPLATE_STORE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(paths.app_data_dir(), "模板中心.json")


def _empty():
    """创建符合当前 schema 的全新空仓库结构。"""
    return {"version": SCHEMA_VERSION, "templates": []}


def _read_all(path=None):
    """宽容读取模板仓库，版本不符或文件损坏时返回空仓库。

    查询模板属于辅助能力，存储损坏不应阻断业务表格处理；后续保存会按当前 schema
    重建文件。此函数不加锁，读改写事务由外层调用方负责。
    """
    try:
        with open(path or _store_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            return _empty()
        templates = data.get("templates")
        return {"version": SCHEMA_VERSION,
                "templates": templates if isinstance(templates, list) else []}
    except (OSError, ValueError, TypeError):
        return _empty()


def _write_all(data, path=None):
    """将完整模板仓库刷新到临时文件后原子替换正式 JSON。

    调用方必须已持有文件锁。临时文件与目标位于同一目录，确保 ``os.replace`` 可使用
    同文件系统原子语义；异常路径会尽力删除残留临时文件。
    """
    target = path or _store_path()
    parent = os.path.dirname(os.path.abspath(target))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    fd, temp_path = tempfile.mkstemp(prefix="template_", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target)
    finally:
        try:
            if os.path.exists(temp_path):
                # 正常 replace 后路径已消失，此分支主要清理写入失败留下的临时文件。
                os.remove(temp_path)
        except OSError:
            pass


def normalize_headers(headers):
    """规范化最多 120 个表头，同时保留业务列顺序和中间空列。

    NFKC 统一全半角兼容字符，删除所有空白并转小写，使纯排版变化不产生新版本；
    末尾空列不构成有效结构而被裁掉，中间空列仍保留位置以识别列移动。
    """
    result = []
    for value in list(headers or [])[:120]:
        text = unicodedata.normalize("NFKC", str(value or ""))
        result.append(re.sub(r"\s+", "", text).lower())
    while result and not result[-1]:
        result.pop()
    return result


def header_fingerprint(headers):
    """为规范化表头顺序生成 24 位 SHA-256 截断指纹。"""
    raw = json.dumps(normalize_headers(headers), ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def diff_headers(old_headers, new_headers):
    """比较两个表头版本并返回机器明细和中文摘要。

    ``added``/``removed`` 按名称集合判断，``moved`` 记录同名字段的位置变化，
    ``changed`` 记录同一位置上的不同非空名称。一个改名可能同时表现为移除、新增和
    位置修改，这是为了保留原始结构事实，不在此处猜测两个名称是否语义相同。

    模板应避免重复表头；位置字典对重复名称只保留最后位置，人工映射中心负责处理
    具体列角色，本函数仅提供结构预警。
    """
    old = normalize_headers(old_headers)
    new = normalize_headers(new_headers)
    old_pos = {value: index + 1 for index, value in enumerate(old) if value}
    new_pos = {value: index + 1 for index, value in enumerate(new) if value}
    added = [value for value in new if value and value not in old_pos]
    removed = [value for value in old if value and value not in new_pos]
    moved = [{"header": value, "from": old_pos[value], "to": new_pos[value]}
             for value in new if value in old_pos and old_pos[value] != new_pos[value]]
    changed = []
    for index in range(min(len(old), len(new))):
        if old[index] and new[index] and old[index] != new[index]:
            changed.append({"column": index + 1, "from": old[index], "to": new[index]})
    parts = []
    # 摘要只呈现数量，详细字段仍保留在返回对象中供管理界面展开查看。
    if added:
        parts.append("新增 %d 列" % len(added))
    if removed:
        parts.append("移除 %d 列" % len(removed))
    if moved:
        parts.append("调整 %d 列位置" % len(moved))
    if changed:
        parts.append("修改 %d 个列名" % len(changed))
    return {"added": added, "removed": removed, "moved": moved,
            "changed": changed, "same": not parts,
            "summary": "结构未变化" if not parts else "、".join(parts)}


def _template_id(name, role_kind, sheet_name):
    """根据模板族身份字段生成稳定的 20 位本地 ID。"""
    raw = "%s|%s|%s" % (name or "未命名模板", role_kind or "custom", sheet_name or "")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def save_template(name, role_kind, sheet_name, headers, mapping_id="",
                  notes="", template_id=None, path=None):
    """保存模板族当前结构，并按指纹决定更新现版或创建新版本。

    模板族 ID 默认由名称、功能类型和页签名共同生成，也可由调用方指定。相同最新
    指纹只更新映射 ID、备注和时间；结构变化时在版本列表首部插入新版本，版本号在
    上一版基础上递增，并保存相邻差异。整个读改写过程处于文件锁内。
    """
    headers = normalize_headers(headers)
    tid = template_id or _template_id(name, role_kind, sheet_name)
    target = path or _store_path()
    with file_lock(target):
        # 锁必须覆盖查找、版本决策和写盘，防止并发保存产生相同版本号或丢记录。
        data = _read_all(path)
        record = next((item for item in data["templates"]
                       if isinstance(item, dict) and item.get("id") == tid), None)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if record is None:
            # 新模板族从空版本列表开始，初次结构会成为版本 1。
            record = {"id": tid, "name": name or "未命名模板",
                      "role_kind": role_kind or "custom", "sheet": sheet_name or "",
                      "versions": [], "rules": [], "updated_at": now}
            data["templates"].insert(0, record)
        versions = record.setdefault("versions", [])
        fp = header_fingerprint(headers)
        if versions and versions[0].get("fingerprint") == fp:
            # 空字符串不覆盖已有人工映射或备注，允许仅“重新确认”而不清除说明。
            versions[0]["mapping_id"] = mapping_id or versions[0].get("mapping_id", "")
            versions[0]["notes"] = notes or versions[0].get("notes", "")
            versions[0]["updated_at"] = now
        else:
            previous = versions[0] if versions else None
            version = int(previous.get("version", 0)) + 1 if previous else 1
            version_diff = diff_headers(previous.get("headers", []), headers) if previous else {
                "added": [], "removed": [], "moved": [], "changed": [],
                "same": True, "summary": "初始版本"}
            versions.insert(0, {"version": version, "fingerprint": fp,
                                 "headers": headers, "mapping_id": mapping_id or "",
                                 "notes": notes or "", "diff": version_diff,
                                 "created_at": now, "updated_at": now})
        record["updated_at"] = now
        # 模板族按首次创建插入首部；截断控制仓库规模，不裁剪单个模板的版本历史。
        data["templates"] = data["templates"][:200]
        _write_all(data, path)
        return dict(record)


def list_templates(path=None):
    """返回所有合法模板族的浅副本，保持仓库存储顺序。"""
    rows = _read_all(path)["templates"]
    return [dict(item) for item in rows if isinstance(item, dict)]


def get_template(template_id, path=None):
    """按模板族 ID 查找记录，未命中返回 ``None``。"""
    for item in list_templates(path):
        if item.get("id") == template_id:
            return item
    return None


def save_migration_rule(template_id, from_version, to_version, rules, path=None):
    """新增或覆盖一个版本方向的显式迁移规则。

    ``rules`` 可保存 rename、drop、defaults、roles 等管理信息；实际表头变换函数目前
    只消费前三项，roles 留给业务映射层。相同 ``from``/``to`` 组合视为同一规则并
    被新记录替换。模板不存在时返回 ``None``，不创建悬空规则。
    """
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        for item in data["templates"]:
            if isinstance(item, dict) and item.get("id") == template_id:
                row = {"from": int(from_version), "to": int(to_version),
                       "rules": dict(rules or {}),
                       "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                item.setdefault("rules", [])
                # 先删除同方向旧规则再置顶，保证查找时最新人工确认优先。
                item["rules"] = [r for r in item["rules"]
                                  if not (r.get("from") == row["from"] and r.get("to") == row["to"])]
                item["rules"].insert(0, row)
                item["updated_at"] = row["updated_at"]
                _write_all(data, path)
                return row
    return None


def apply_migration(headers, rules):
    """在内存中按显式规则转换表头列表并返回新列表。

    顺序固定为重命名、删除、追加默认字段。默认字段只有尚不存在时才追加，避免重复；
    函数不调用 ``normalize_headers``，规则键值必须与传入表头使用相同文本口径，也不
    修改原列表或任何工作簿。
    """
    values = list(headers or [])
    rules = rules or {}
    rename = rules.get("rename") or {}
    values = [rename.get(value, value) for value in values]
    drops = set(rules.get("drop") or [])
    values = [value for value in values if value not in drops]
    defaults = rules.get("defaults") or []
    values.extend([value for value in defaults if value not in values])
    return values


def delete_template(template_id, path=None):
    """删除整个模板族及其版本和规则，返回是否实际删除。"""
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        before = len(data["templates"])
        data["templates"] = [item for item in data["templates"]
                              if not isinstance(item, dict) or item.get("id") != template_id]
        if len(data["templates"]) == before:
            return False
        _write_all(data, path)
        return True


def clear_templates(path=None):
    """清空全部模板族并返回原数量；仓库已空时不重复写盘。"""
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        count = len(data["templates"])
        if count:
            data["templates"] = []
            _write_all(data, path)
        return count
