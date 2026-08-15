# -*- coding: utf-8 -*-
"""本机文件库归档、删除和人工重分类所需的文件事务步骤。

本模块只提供纯文件系统步骤和索引条目构造，不负责加锁与事务编排；锁的获取顺序和
整体回滚决策由 :mod:`library` 统筹。所有清理函数都采用尽力而为语义：逻辑提交完成后
物理删除失败不应把成功操作改判为失败，因此异常被限制在单个文件上。"""

from __future__ import annotations

import os
import shutil


def safe_log(log, message: str) -> None:
    """安全调用可选日志回调，展示层异常不影响文件事务。"""

    if not log:
        return
    try:
        log(message)
    except Exception:
        pass


def prepare_import_backup(destination: str) -> tuple[bool, str]:
    """为即将覆盖的归档创建回滚备份，返回是否属于替换。"""

    backup = destination + ".bak"
    if not os.path.exists(destination):
        return False, backup
    # 同一归档只保留最近一次覆盖前的备份，旧备份不累积。
    if os.path.exists(backup):
        os.remove(backup)
    shutil.copy2(destination, backup)
    return True, backup


def without_same_primary_item(items, category: str, name: str):
    """移除同主类别同名旧条目，附加标签命中不影响其他物理归档。"""

    return [
        item for item in items
        if not (item.get("category") == category and item.get("name") == name)
    ]


def build_library_item(path: str, destination: str, info: dict, updated: str) -> dict:
    """根据已提交归档和分类结果生成完整索引记录。"""

    category = info["category"]
    return {
        "name": os.path.basename(path),
        "category": category,
        # 多标签字段由分类结果提供；旧调用方缺省时退回主类别单标签。
        "categories": info.get("categories") or [category],
        "path": destination,
        "updated": updated,
        "size": os.path.getsize(destination),
        "confidence": info["confidence"],
        "signals": info["signals"],
        "sheet": info.get("sheet", ""),
        "sheets": info.get("sheets", {}),
        "origin": os.path.abspath(path),
    }


def rollback_import(part: str, destination: str, backup: str, replaced: bool) -> None:
    """尽力撤销临时文件和正式归档替换，不掩盖原始事务错误。"""

    try:
        if os.path.exists(part):
            os.remove(part)
        if replaced and os.path.exists(backup):
            os.replace(backup, destination)
        elif os.path.exists(destination):
            # 首次导入没有旧版本，索引未提交时必须删除已经落盘的新文件。
            os.remove(destination)
    except OSError:
        pass


def partition_items(items, category: str, name: str):
    """把索引拆成保留项和待删除项，支持从任一附加标签定位条目。"""

    keep, removed = [], []
    for item in items:
        categories = item.get("categories") or [item.get("category")]
        target = category in categories and item.get("name") == name
        (removed if target else keep).append(item)
    return keep, removed


def delete_item_files(items) -> None:
    """尽力删除归档及普通覆盖备份；逻辑删除已提交后不回滚索引。"""

    # 归档与 .bak 一起清理，残留备份会在界面中表现为重复数据。
    for item in items:
        archive = item.get("path") or ""
        for candidate in (archive, archive + ".bak"):
            try:
                if candidate and os.path.exists(candidate):
                    os.remove(candidate)
            except OSError:
                pass


def matching_item(items, category: str, name: str):
    """返回指定类别可见且名称匹配的第一条索引记录。"""

    return next(
        (
            item for item in items
            if category in (item.get("categories") or [item.get("category")])
            and item.get("name") == name
        ),
        None,
    )


def _reserve_reclassify_backup(destination: str) -> str | None:
    """把目标同名文件移到不冲突的事务备份路径。"""

    if not os.path.isfile(destination):
        return None
    backup = destination + ".reclassify.bak"
    suffix = 1
    while os.path.exists(backup):
        backup = destination + ".reclassify.%d.bak" % suffix
        suffix += 1
    os.replace(destination, backup)
    return backup


def move_for_reclassification(source: str, destination: str) -> tuple[bool, str | None]:
    """执行必要的跨类别移动，返回是否移动及目标旧文件备份。"""

    if os.path.abspath(source) == os.path.abspath(destination):
        return False, None
    backup = _reserve_reclassify_backup(destination)
    try:
        shutil.move(source, destination)
    except Exception:
        # 源移动失败时立即恢复目标原文件，再把异常交给统一事务回滚。
        if backup and os.path.exists(backup):
            os.replace(backup, destination)
        raise
    return True, backup


def set_manual_category(item: dict, category: str, destination: str, updated: str) -> None:
    """把索引条目更新为管理员确认的单一类别。"""

    item.update({
        "category": category,
        "categories": [category],
        "path": destination,
        "updated": updated,
        "confidence": 100,
        "signals": ["人工指定类别"],
    })


def rollback_reclassification(
    source: str,
    destination: str,
    moved: bool,
    backup: str | None,
) -> None:
    """按“撤销新移动、恢复旧目标”的顺序回滚文件系统。"""

    if moved:
        try:
            os.replace(destination, source)
        except OSError:
            pass
    if backup and os.path.exists(backup):
        try:
            os.replace(backup, destination)
        except OSError:
            pass


def discard_reclassify_backup(backup: str | None) -> None:
    """索引提交成功后尽力清理目标旧文件备份。"""

    if not backup:
        return
    try:
        os.remove(backup)
    except OSError:
        # 备份残留不影响索引与正式文件一致性，可留给管理员检查。
        pass


__all__ = [
    "build_library_item",
    "delete_item_files",
    "discard_reclassify_backup",
    "matching_item",
    "move_for_reclassification",
    "partition_items",
    "prepare_import_backup",
    "rollback_import",
    "rollback_reclassification",
    "safe_log",
    "set_manual_category",
    "without_same_primary_item",
]
