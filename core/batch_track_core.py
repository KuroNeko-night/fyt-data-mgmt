# -*- coding: utf-8 -*-
"""批次跟踪：按批次号聚合本机任务历史与输出文件，形成单批次全流程视图。

本模块只读取 ``core.task_history`` 记录和输出目录第一层普通文件，不写入历史、不
移动或删除任何文件。搜索范围覆盖任务标题、输出目录名和目录内文件名；目录无法访问
或已被清理时按无文件处理，让历史记录仍可展示。桌面任务历史与 Web 持久化任务是
两套隔离数据，本模块只服务前者。
"""
from __future__ import annotations

import os

from . import task_history


def _task_output_files(out_dir: str) -> list[str]:
    """返回输出目录第一层普通文件名；目录不存在或不可读时返回空列表。"""
    if not out_dir or not os.path.isdir(out_dir):
        return []
    try:
        # 只枚举第一层普通文件；历史目录中不存在需要递归的嵌套输出。
        return sorted(
            name for name in os.listdir(out_dir)
            if os.path.isfile(os.path.join(out_dir, name))
        )
    except OSError:
        # 目录可能已被用户清理或权限变化；保留任务行并继续，不伪造文件数。
        return []


def _task_matches(keyword: str, title: str, out_dir: str, files: list[str]) -> bool:
    """判断任务标题、输出目录名或产物文件名是否命中批次关键词。"""
    if keyword in title.lower():
        return True
    if keyword in out_dir.lower():
        return True
    return any(keyword in name.lower() for name in files)


def search(keyword: str, limit: int = 300, db_path: str | None = None) -> dict[str, object]:
    """按批次号（如 ``26036-02``）搜索任务历史，返回匹配任务及输出文件。

    参数：
        keyword: 搜索词；空词直接返回空结果，不读取数据库。
        limit: 传递给任务历史层的最大读取条数，具体钳制由 ``task_history.list_recent``
            负责（1～1000）。
        db_path: 测试隔离用显式历史库路径；缺省使用本机默认路径。
    返回：
        ``{"keyword": 原始词, "items": [...]}``。每条结果包含任务展示字段、输出目录
        及目录第一层普通文件名（按名称升序）。
    副作用与异常：
        只读数据库与文件系统；目录无法访问时该任务文件列表置空，不抛出，也不影响
        其他任务匹配。数据库读取失败由 ``task_history`` 降级为空列表。
    """
    kw = str(keyword or "").strip().lower()
    if not kw:
        # 空查询没有业务含义，直接短路可避免无谓加载最近任务。
        return {"keyword": "", "items": []}
    items = task_history.list_recent(limit, db_path=db_path)
    results = []
    for task in items:
        title = str(task.get("title") or "")
        out_dir = str(task.get("output_dir") or "")
        files = _task_output_files(out_dir)
        if not _task_matches(kw, title, out_dir, files):
            continue
        results.append({
            "feature": str(task.get("feature") or ""),
            "title": title,
            "status": str(task.get("status") or ""),
            "started_at": str(task.get("started_at") or ""),
            "message": str(task.get("message") or ""),
            "out_dir": out_dir,
            "files": files,
        })
    return {"keyword": str(keyword).strip(), "items": results}
