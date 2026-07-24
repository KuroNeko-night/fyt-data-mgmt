# -*- coding: utf-8 -*-
"""
模板中心 —— 模板版本、结构差异与迁移规则
==========================================
模板族按功能类型、工作表和用户名称归档；每次表头结构变化形成新版本，
并保存相邻版本之间的差异。核心层只使用标准库，不依赖 Qt。

运行于 Windows 10/11 + Python 3.13。
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
    override = os.environ.get("FYT_TEMPLATE_STORE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(paths.app_data_dir(), "模板中心.json")


def _empty():
    return {"version": SCHEMA_VERSION, "templates": []}


def _read_all(path=None):
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
                os.remove(temp_path)
        except OSError:
            pass


def normalize_headers(headers):
    """规范化表头文本，保留列顺序并删除末尾空列。"""
    result = []
    for value in list(headers or [])[:120]:
        text = unicodedata.normalize("NFKC", str(value or ""))
        result.append(re.sub(r"\s+", "", text).lower())
    while result and not result[-1]:
        result.pop()
    return result


def header_fingerprint(headers):
    """返回只依赖表头顺序的稳定指纹。"""
    raw = json.dumps(normalize_headers(headers), ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def diff_headers(old_headers, new_headers):
    """比较两版表头，返回 added/removed/moved/changed 和摘要。"""
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
    raw = "%s|%s|%s" % (name or "未命名模板", role_kind or "custom", sheet_name or "")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def save_template(name, role_kind, sheet_name, headers, mapping_id="",
                  notes="", template_id=None, path=None):
    """保存模板当前版本；结构未变化时只更新时间，不重复创建版本。"""
    headers = normalize_headers(headers)
    tid = template_id or _template_id(name, role_kind, sheet_name)
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        record = next((item for item in data["templates"]
                       if isinstance(item, dict) and item.get("id") == tid), None)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if record is None:
            record = {"id": tid, "name": name or "未命名模板",
                      "role_kind": role_kind or "custom", "sheet": sheet_name or "",
                      "versions": [], "rules": [], "updated_at": now}
            data["templates"].insert(0, record)
        versions = record.setdefault("versions", [])
        fp = header_fingerprint(headers)
        if versions and versions[0].get("fingerprint") == fp:
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
        data["templates"] = data["templates"][:200]
        _write_all(data, path)
        return dict(record)


def list_templates(path=None):
    """按最近更新时间返回模板族副本。"""
    rows = _read_all(path)["templates"]
    return [dict(item) for item in rows if isinstance(item, dict)]


def get_template(template_id, path=None):
    for item in list_templates(path):
        if item.get("id") == template_id:
            return item
    return None


def save_migration_rule(template_id, from_version, to_version, rules, path=None):
    """保存版本迁移规则。rules 可包含 rename/drop/defaults/roles。"""
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        for item in data["templates"]:
            if isinstance(item, dict) and item.get("id") == template_id:
                row = {"from": int(from_version), "to": int(to_version),
                       "rules": dict(rules or {}),
                       "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                item.setdefault("rules", [])
                item["rules"] = [r for r in item["rules"]
                                  if not (r.get("from") == row["from"] and r.get("to") == row["to"])]
                item["rules"].insert(0, row)
                item["updated_at"] = row["updated_at"]
                _write_all(data, path)
                return row
    return None


def apply_migration(headers, rules):
    """按迁移规则得到新表头；仅处理显式 rename/drop/defaults。"""
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
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        count = len(data["templates"])
        if count:
            data["templates"] = []
            _write_all(data, path)
        return count
