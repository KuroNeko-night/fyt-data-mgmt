# -*- coding: utf-8 -*-
"""
字段映射中心 —— 模板指纹与人工确认映射的持久化
================================================
用 JSON 保存用户确认过的工作表、表头行和角色列映射；核心层不依赖 Qt。
指纹只取文件结构信息（工作表名、表头文本），不绑定绝对路径，文件移动后仍可复用。

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
    override = os.environ.get("FYT_MAPPING_STORE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(paths.app_data_dir(), "字段映射.json")


def _read_all(path=None):
    p = path or _store_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            return {"version": SCHEMA_VERSION, "mappings": []}
        mappings = data.get("mappings")
        return {"version": SCHEMA_VERSION,
                "mappings": mappings if isinstance(mappings, list) else []}
    except (OSError, ValueError, TypeError):
        return {"version": SCHEMA_VERSION, "mappings": []}


def _write_all(data, path=None):
    p = path or _store_path()
    parent = os.path.dirname(os.path.abspath(p))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    fd, tmp = tempfile.mkstemp(prefix="mapping_", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _header_tokens(row):
    tokens = []
    for value in list(row or [])[:80]:
        text = unicodedata.normalize("NFKC", str(value or ""))
        tokens.append(re.sub(r"\s+", "", text).lower())
    while tokens and not tokens[-1]:
        tokens.pop()
    return tokens


def fingerprint(sheet_name, rows, role_kind="", header_row=1):
    """根据功能类型、工作表与规范化表头生成稳定指纹，不包含业务数据。"""
    row_index = max(1, int(header_row or 1)) - 1
    header = _header_tokens(rows[row_index] if row_index < len(rows or []) else [])
    payload = {"sheet": sheet_name or "", "header": header,
               "role_kind": role_kind or ""}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def save_mapping(name, role_kind, sheet_name, header_row, roles, rows=None,
                 fingerprint_value=None, path=None):
    """新增或覆盖一条映射，返回完整记录。roles 使用 0-based 列号。"""
    role_kind = role_kind or "custom"
    fp = fingerprint_value or fingerprint(
        sheet_name, rows or [], role_kind, header_row=header_row)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "id": fp,
        "name": name or (sheet_name or "未命名模板"),
        "role_kind": role_kind,
        "fingerprint": fp,
        "sheet": sheet_name or "",
        "header": int(header_row or 1),
        "roles": {str(k): int(v) for k, v in (roles or {}).items()},
        "headers": _header_tokens(
            (rows or [])[max(1, int(header_row or 1)) - 1]
            if len(rows or []) >= max(1, int(header_row or 1)) else []),
        "updated_at": now,
    }
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        mappings = [m for m in data["mappings"]
                    if not isinstance(m, dict) or m.get("id") != fp]
        mappings.insert(0, record)
        data["mappings"] = mappings[:200]
        _write_all(data, path)
    return record


def list_mappings(role_kind=None, path=None):
    """按最近更新时间倒序返回映射记录副本。"""
    rows = _read_all(path)["mappings"]
    if role_kind:
        rows = [m for m in rows if m.get("role_kind") == role_kind]
    return [dict(m) for m in rows if isinstance(m, dict)]


def find_mapping(fingerprint_value, role_kind=None, path=None):
    """按指纹找映射，不匹配时返回 None。"""
    for row in list_mappings(role_kind=role_kind, path=path):
        if row.get("fingerprint") == fingerprint_value:
            return row
    return None


def find_for_rows(sheet_name, rows, role_kind="", path=None):
    """扫描预览行匹配已保存表头；表头上下移动仍可命中。"""
    for row_index in range(1, len(rows or []) + 1):
        fp = fingerprint(sheet_name, rows, role_kind, header_row=row_index)
        found = find_mapping(fp, role_kind=role_kind, path=path)
        if found:
            found["header"] = row_index
            found["sheet"] = sheet_name or found.get("sheet", "")
            return found
    return None


def delete_mapping(mapping_id, path=None):
    """删除一条映射，返回是否删除。"""
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        before = len(data["mappings"])
        data["mappings"] = [m for m in data["mappings"]
                             if not isinstance(m, dict) or m.get("id") != mapping_id]
        if len(data["mappings"]) == before:
            return False
        _write_all(data, path)
        return True


def clear_mappings(path=None):
    """清除全部映射，返回清除数量。"""
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        count = len(data["mappings"])
        if count:
            data["mappings"] = []
            _write_all(data, path)
        return count
