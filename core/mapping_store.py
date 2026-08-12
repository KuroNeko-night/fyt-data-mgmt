# -*- coding: utf-8 -*-
"""
人工字段映射持久化中心
======================
保存用户确认过的页签、表头行和业务角色列映射，使同结构模板再次上传时可直接复用，
无需在桌面或 Web 界面重复选择。记录存为有版本号的 JSON，核心层不依赖任何界面。

映射指纹只包含功能类型、页签名和规范化表头，不包含绝对路径或正文业务数据，因此
文件移动、重命名后仍可复用，也不会把敏感明细写入索引。列角色统一使用 0 基编号，
与公共映射协议一致；具体 openpyxl 业务模块在使用时再转换为 1 基列号。

所有读改写通过 ``storage_lock.file_lock`` 串行化，并使用同目录临时文件原子替换；
映射最多保留最近 200 条，避免长期学习导致索引无限增长。环境变量允许 Web 用户或
测试把存储路径隔离到各自运行目录。
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
    """返回字段映射 JSON 路径，并允许环境变量完整覆盖默认位置。"""
    override = os.environ.get("FYT_MAPPING_STORE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(paths.app_data_dir(), "字段映射.json")


def _read_all(path=None):
    """读取并校验映射存储根结构，缺失或损坏时返回当前版本空仓库。

    此函数只做宽容读取，不负责加锁；读改写调用方必须在外层持有文件锁。旧 schema
    不尝试猜测迁移，避免错误解释列号协议。
    """
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
        # 单纯查询映射不应因可选缓存损坏阻断业务，后续保存会重建合法文件。
        return {"version": SCHEMA_VERSION, "mappings": []}


def _write_all(data, path=None):
    """将完整映射仓库写入同目录临时文件并原子替换正式文件。

    调用方负责持有文件锁。``mkstemp`` 先安全占用唯一临时文件名，``fsync`` 尽力把
    内容落盘，``os.replace`` 在同一文件系统内原子切换；任何残留临时文件都会清理。
    """
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
                # replace 成功后临时路径已不存在；异常路径才需要清理。
                os.remove(tmp)
        except OSError:
            pass


def _header_tokens(row):
    """把一行表头转换为最多 80 个稳定比较令牌，并删除尾部空列。

    NFKC 统一全半角兼容字符，所有空白删除并转小写；只清理尾部空列，保留中间空列
    的相对位置，因为插入空列同样属于模板结构变化。
    """
    tokens = []
    for value in list(row or [])[:80]:
        text = unicodedata.normalize("NFKC", str(value or ""))
        tokens.append(re.sub(r"\s+", "", text).lower())
    while tokens and not tokens[-1]:
        tokens.pop()
    return tokens


def fingerprint(sheet_name, rows, role_kind="", header_row=1):
    """根据功能类型、页签名和指定表头生成 24 位稳定结构指纹。

    ``header_row`` 是面向界面的 1 基行号，越界时使用空表头。JSON 固定键排序和紧凑
    分隔符保证跨进程序列化一致；SHA-256 截断值只作为本地索引键，不承担密码学认证。
    """
    row_index = max(1, int(header_row or 1)) - 1
    header = _header_tokens(rows[row_index] if row_index < len(rows or []) else [])
    payload = {"sheet": sheet_name or "", "header": header,
               "role_kind": role_kind or ""}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def save_mapping(name, role_kind, sheet_name, header_row, roles, rows=None,
                 fingerprint_value=None, path=None):
    """新增或覆盖一条人工确认映射，并返回保存记录。

    ``roles`` 的列号为 0 基。调用方可直接提供预先计算的指纹；否则根据预览行生成。
    相同指纹视为同一结构，旧记录会被替换并移动到列表首部；不同指纹形成新记录。
    仓库截取最近 200 条，防止历史模板无限增长。
    """
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
        # 保存规范化表头既便于诊断，也避免后续查看记录时需要重新访问原文件。
        "headers": _header_tokens(
            (rows or [])[max(1, int(header_row or 1)) - 1]
            if len(rows or []) >= max(1, int(header_row or 1)) else []),
        "updated_at": now,
    }
    target = path or _store_path()
    with file_lock(target):
        # 锁覆盖完整的“读、过滤、插入、写”事务，避免并发保存互相覆盖。
        data = _read_all(path)
        mappings = [m for m in data["mappings"]
                    if not isinstance(m, dict) or m.get("id") != fp]
        mappings.insert(0, record)
        data["mappings"] = mappings[:200]
        _write_all(data, path)
    return record


def list_mappings(role_kind=None, path=None):
    """按存储顺序返回映射的浅副本，可按功能类型过滤。

    保存时最新记录置顶，因此正常情况下即为最近更新顺序。返回副本可防止调用方直接
    修改内存中的读取结果，但嵌套字段仍应视为只读。
    """
    rows = _read_all(path)["mappings"]
    if role_kind:
        rows = [m for m in rows if m.get("role_kind") == role_kind]
    return [dict(m) for m in rows if isinstance(m, dict)]


def find_mapping(fingerprint_value, role_kind=None, path=None):
    """在可选功能类型范围内查找结构指纹，未命中返回 ``None``。"""
    for row in list_mappings(role_kind=role_kind, path=path):
        if row.get("fingerprint") == fingerprint_value:
            return row
    return None


def find_for_rows(sheet_name, rows, role_kind="", path=None):
    """逐行尝试结构指纹，使表头上下移动后仍能复用已保存映射。

    指纹本身包含表头内容但不含表头行号，因此每个候选行都能与历史结构比较。命中后
    用本次实际行号和页签名覆盖返回副本，不修改持久化记录。
    """
    for row_index in range(1, len(rows or []) + 1):
        fp = fingerprint(sheet_name, rows, role_kind, header_row=row_index)
        found = find_mapping(fp, role_kind=role_kind, path=path)
        if found:
            found["header"] = row_index
            found["sheet"] = sheet_name or found.get("sheet", "")
            return found
    return None


def delete_mapping(mapping_id, path=None):
    """在文件锁内删除指定映射，返回是否确实找到并写回。"""
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
    """清空映射列表并返回原记录数；本来为空时不执行无意义写盘。"""
    target = path or _store_path()
    with file_lock(target):
        data = _read_all(path)
        count = len(data["mappings"])
        if count:
            data["mappings"] = []
            _write_all(data, path)
        return count
