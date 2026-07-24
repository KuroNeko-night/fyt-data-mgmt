# -*- coding: utf-8 -*-
"""
增量缓存 —— 按输入文件内容和参数复用既有结果
================================================
缓存索引只保存任务结果元数据和输出路径，不复制、不移动业务文件；命中时会先
确认所有输出文件仍存在，输出被删除后自动视为失效并回退完整处理。

运行于 Windows 10/11 + Python 3.13。
"""
import datetime
import hashlib
import json
import os
import tempfile

from . import paths
from .storage_lock import file_lock


SCHEMA_VERSION = 1
MAX_ENTRIES = 200


def _locked(path=None, timeout=10.0):
    """对缓存索引的读改写加跨进程锁，避免多个 Web sidecar 相互覆盖。"""
    return file_lock(_cache_path(path), timeout=timeout)


def _cache_path(path=None):
    if path:
        return os.path.abspath(path)
    override = os.environ.get("FYT_INCREMENTAL_CACHE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return paths.incremental_cache_path()


def _empty():
    return {"version": SCHEMA_VERSION, "entries": []}


def _read_all(path=None):
    try:
        with open(_cache_path(path), "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            return _empty()
        entries = data.get("entries")
        return {"version": SCHEMA_VERSION,
                "entries": entries if isinstance(entries, list) else []}
    except (OSError, ValueError, TypeError):
        return _empty()


def _write_all(data, path=None):
    target = _cache_path(path)
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    file_id, temp_path = tempfile.mkstemp(
        prefix="incremental_cache_", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(file_id, "w", encoding="utf-8") as file_obj:
            json.dump(data, file_obj, ensure_ascii=False, indent=2)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, target)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def _normalize(value):
    """把参数递归转换为可稳定排序和序列化的结构。"""
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            key_text = json.dumps(_normalize(key), ensure_ascii=False,
                                  sort_keys=True, separators=(",", ":"))
            items.append((key_text, _normalize(item)))
        return {key: item for key, item in sorted(items)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, set):
        return sorted((_normalize(item) for item in value), key=repr)
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def file_fingerprint(file_path):
    """返回文件内容 SHA-256；路径变化但内容相同仍视为同一输入。"""
    digest = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    stat = os.stat(file_path)
    return {"name": os.path.basename(file_path), "size": stat.st_size,
            "sha256": digest.hexdigest()}


def make_key(feature, input_paths, params=None, engine_version="1"):
    """按功能、输入文件内容、参数和引擎版本生成稳定缓存键。"""
    if isinstance(input_paths, (str, os.PathLike)):
        input_paths = [input_paths]
    payload = {
        "feature": str(feature or "unknown"),
        "engine_version": str(engine_version or "1"),
        "inputs": [file_fingerprint(path) for path in (input_paths or [])],
        "params": _normalize(params or {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _artifacts_exist(artifacts):
    paths_to_check = [str(item) for item in (artifacts or []) if item]
    return bool(paths_to_check) and all(os.path.exists(item) for item in paths_to_check)


def get(cache_key, path=None):
    """返回有效缓存结果；输出已不存在时移除失效记录并返回 None。"""
    with _locked(path):
        data = _read_all(path)
        for entry in list(data["entries"]):
            if not isinstance(entry, dict) or entry.get("key") != cache_key:
                continue
            if not _artifacts_exist(entry.get("artifacts")):
                data["entries"].remove(entry)
                _write_all(data, path)
                return None
            entry["hits"] = int(entry.get("hits", 0)) + 1
            entry["last_hit_at"] = datetime.datetime.now().astimezone().isoformat(
                timespec="seconds")
            _write_all(data, path)
            result = dict(entry.get("result") or {})
            result["cache_hit"] = True
            result["cache_created_at"] = entry.get("created_at", "")
            return result
    return None


def put(cache_key, feature, result, artifacts, path=None):
    """保存成功结果；同键覆盖，索引按最近写入时间最多保留 200 条。"""
    if not cache_key or not isinstance(result, dict) or not _artifacts_exist(artifacts):
        return False
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with _locked(path):
        data = _read_all(path)
        data["entries"] = [entry for entry in data["entries"]
                           if not isinstance(entry, dict) or entry.get("key") != cache_key]
        clean_result = json.loads(json.dumps(result, ensure_ascii=False, default=str))
        data["entries"].insert(0, {
            "key": cache_key,
            "feature": str(feature or "unknown"),
            "result": clean_result,
            "artifacts": [os.path.abspath(str(item)) for item in artifacts if item],
            "created_at": now,
            "last_hit_at": "",
            "hits": 0,
        })
        data["entries"] = data["entries"][:MAX_ENTRIES]
        _write_all(data, path)
    return True


def stats(path=None):
    """返回缓存条目数、累计命中数和索引文件大小。"""
    entries = _read_all(path)["entries"]
    target = _cache_path(path)
    try:
        size = os.path.getsize(target)
    except OSError:
        size = 0
    return {"entries": len(entries),
            "hits": sum(int(item.get("hits", 0)) for item in entries
                        if isinstance(item, dict)),
            "bytes": size}


def clear(path=None):
    """清空缓存索引但保留业务输出文件，返回清除条目数。"""
    with _locked(path):
        data = _read_all(path)
        count = len(data["entries"])
        if count:
            _write_all(_empty(), path)
    return count
