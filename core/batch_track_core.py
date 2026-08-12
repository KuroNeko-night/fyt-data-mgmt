# -*- coding: utf-8 -*-
"""批次跟踪：按批次号聚合任务历史与结果文件，形成全流程视图。"""
from __future__ import annotations

import os

from . import task_history


def search(keyword: str, limit: int = 300, db_path: str | None = None) -> dict[str, object]:
    """按批次号（如 26036-02）搜索任务历史，返回匹配任务及输出文件。"""
    kw = str(keyword or "").strip().lower()
    if not kw:
        return {"keyword": "", "items": []}
    items = task_history.list_recent(limit, db_path=db_path)
    results = []
    for task in items:
        title = str(task.get("title") or "")
        out_dir = str(task.get("output_dir") or "")
        hit = kw in title.lower()
        files: list[str] = []
        if out_dir and os.path.isdir(out_dir):
            try:
                files = sorted(
                    name for name in os.listdir(out_dir)
                    if os.path.isfile(os.path.join(out_dir, name))
                )
            except OSError:
                files = []
            if not hit:
                hit = kw in out_dir.lower() or any(kw in name.lower() for name in files)
        if hit:
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
