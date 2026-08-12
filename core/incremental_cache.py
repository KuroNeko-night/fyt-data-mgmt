# -*- coding: utf-8 -*-
"""
业务结果增量缓存
================
根据功能名称、输入文件内容、可调参数和业务引擎版本生成稳定缓存键。再次处理完全
相同的输入时，可直接返回此前结构化结果和输出文件，减少大型 Excel 的重复计算。

索引只保存可 JSON 序列化的结果元数据和输出绝对路径，不复制、不移动业务文件。
命中时必须确认所有产物仍存在；用户删除任何输出后，该条记录会立即从索引移除并
回退完整处理。文件指纹使用内容 SHA-256，路径变化不影响命中，但文件名仍作为诊断
元数据进入键，因此同内容不同文件名当前会视为不同输入。

索引读改写通过跨进程文件锁和临时文件原子替换保护，适配多个 Web 任务子进程；最多
保留最近 200 条。清理缓存只删除索引，绝不删除业务输出文件。
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
    """返回缓存索引对应的跨进程文件锁上下文。

    锁路径由正式缓存路径派生，默认最多等待十秒；调用方用 ``with`` 覆盖完整的
    读改写事务，避免多个任务分别读取旧版本后互相覆盖新记录。
    """
    return file_lock(_cache_path(path), timeout=timeout)


def _cache_path(path=None):
    """按显式参数、环境变量、应用默认值的优先级解析缓存索引绝对路径。"""
    if path:
        return os.path.abspath(path)
    override = os.environ.get("FYT_INCREMENTAL_CACHE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return paths.incremental_cache_path()


def _empty():
    """创建符合当前 schema 的空缓存仓库。"""
    return {"version": SCHEMA_VERSION, "entries": []}


def _read_all(path=None):
    """宽容读取缓存索引，缺失、损坏或版本不符时返回空仓库。

    缓存只是性能优化，任何索引问题都不能阻断业务完整处理；正式写入会按当前 schema
    重建。此函数不自行加锁，读改写调用方必须在外层持锁。
    """
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
    """将完整缓存索引刷新到临时文件并原子替换正式文件。

    临时文件与目标位于同一目录，``fsync`` 后使用 ``os.replace``，即使进程在替换前
    中断也不会留下半截 JSON。调用方负责持有缓存锁。
    """
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
                # 正常替换后临时路径已消失；这里只清理异常写入的残留文件。
                os.remove(temp_path)
        except OSError:
            pass


def _normalize(value):
    """递归规范化任务参数，使等价结构得到稳定 JSON 表示。

    字典键先各自规范化并序列化为文本，再按文本排序；列表/元组保留顺序，集合按
    ``repr`` 排序，PathLike 转文件系统文本。基础 JSON 类型原样保留，其他对象退回
    ``repr``。该函数不判断业务等价性，调用方应避免把临时对象地址放入参数。
    """
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            # JSON 要求对象键可序列化为字符串，这里也借此建立跨进程稳定排序键。
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
    """流式计算文件 SHA-256，并附带文件名和字节数。

    每次读取 1 MiB，避免把大型工作簿整体载入内存。内容哈希提供可靠变更检测；文件名
    和大小保留在键载荷中，便于诊断并区分同内容但业务命名不同的输入。
    """
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
    """为一次业务调用生成完整的 SHA-256 缓存键。

    单个路径自动提升为列表；输入顺序保留，因此角色不同或用户调整文件优先顺序时会
    产生新键。``engine_version`` 应在算法或输出口径变化时更新，防止新代码复用旧结果。
    参数先经 ``_normalize``，最终 JSON 固定排序与分隔符以保证跨进程一致。
    """
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
    """仅当产物列表非空且每个路径仍存在时返回真。"""
    paths_to_check = [str(item) for item in (artifacts or []) if item]
    return bool(paths_to_check) and all(os.path.exists(item) for item in paths_to_check)


def get(cache_key, path=None):
    """查找有效缓存，更新命中统计后返回结果副本。

    整个查找、产物校验、失效删除或命中计数写回都处于同一文件锁内。命中结果追加
    ``cache_hit`` 和创建时间，不修改索引中保存的原结果。产物缺失时立即移除记录，
    让调用方执行完整任务。
    """
    with _locked(path):
        data = _read_all(path)
        for entry in list(data["entries"]):
            if not isinstance(entry, dict) or entry.get("key") != cache_key:
                continue
            if not _artifacts_exist(entry.get("artifacts")):
                # 缓存不拥有输出文件，文件被用户清理后只删除元数据引用。
                data["entries"].remove(entry)
                _write_all(data, path)
                return None
            entry["hits"] = int(entry.get("hits", 0)) + 1
            # 使用带时区 ISO 时间，桌面与服务器日志能够明确解释命中时间。
            entry["last_hit_at"] = datetime.datetime.now().astimezone().isoformat(
                timespec="seconds")
            _write_all(data, path)
            result = dict(entry.get("result") or {})
            result["cache_hit"] = True
            result["cache_created_at"] = entry.get("created_at", "")
            return result
    return None


def put(cache_key, feature, result, artifacts, path=None):
    """缓存一份拥有现存产物的成功结果，同键记录会被替换。

    空键、非字典结果、空产物或产物缺失均拒绝缓存。结果通过 JSON 往返转换为可持久化
    的独立副本，非标准对象使用字符串表示；产物统一保存绝对路径。新记录置顶并截断
    到 ``MAX_ENTRIES``，写入成功返回 ``True``。
    """
    if not cache_key or not isinstance(result, dict) or not _artifacts_exist(artifacts):
        return False
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with _locked(path):
        # 锁覆盖同键过滤、插入和截断，防止并发任务丢失彼此的新记录。
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
    """返回当前条目数、累计命中次数和索引文件字节数。

    统计是只读快照，不持有文件锁；并发写入时结果可能稍有滞后，但不会影响缓存正确性。
    """
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
    """在文件锁内清空全部缓存元数据并返回原条目数。

    业务产物不属于缓存索引所有权，绝不在此删除；索引本来为空时避免无意义写盘。
    """
    with _locked(path):
        data = _read_all(path)
        count = len(data["entries"])
        if count:
            _write_all(_empty(), path)
    return count
