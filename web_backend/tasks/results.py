"""任务结果文件发现、路径隐藏、历史版本和前端公开投影。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from http import HTTPStatus
from itertools import islice
from pathlib import Path
from typing import Any, Callable

from core import business_result_core
from web_backend.errors import ApiError


@dataclass(frozen=True)
class ResultDependencies:
    """结果投影使用的数据根、数据库连接与兼容 JSON 解析能力。"""

    data_root: Path
    db_lock: Any
    db: Callable[[], Any]
    json_list: Callable[[object], list[object]]
    json_value: Callable[[object, object], object]
    is_review_pending: Callable[[Any], bool]


def _file_candidates(path: Path):
    """返回单文件或目录前两百个子文件候选，目录遍历在达到上限后立即停止。"""
    if path.is_file():
        return (path,)
    if path.is_dir():
        return islice(path.rglob("*"), 200)
    return ()


def collect_result_files(value: object) -> list[dict[str, object]]:
    """递归发现桥接结果中的绝对文件路径，并按解析后路径去重。"""
    found: dict[str, dict[str, object]] = {}

    def add(path_value: str) -> None:
        """展开一个文件或受限目录，把真实文件加入稳定索引。"""
        for item in _file_candidates(Path(path_value)):
            if not item.is_file():
                continue
            resolved = str(item.resolve())
            found[resolved] = {
                "name": item.name,
                "path": resolved,
                "size": item.stat().st_size,
            }

    def visit(item: object) -> None:
        """遍历 JSON 风格结果，普通业务文本不会被误判为文件。"""
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str) and os.path.isabs(item) and os.path.exists(item):
            add(item)

    visit(value)
    return list(found.values())


def public_result(value: object) -> object:
    """递归把服务端绝对路径替换为文件名，避免向浏览器泄漏部署结构。"""
    if isinstance(value, dict):
        return {key: public_result(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_result(item) for item in value]
    if isinstance(value, str) and os.path.isabs(value):
        return Path(value).name
    return value


def _download_files(items, url_factory):
    """把持久化文件清单投影为前端可下载结构，忽略历史损坏条目。"""
    return [{
        "name": item["name"],
        "size": item.get("size", 0),
        "url": url_factory(index),
    } for index, item in enumerate(items)
      if isinstance(item, dict) and "name" in item]


def _job_versions(job_id: str, deps: ResultDependencies):
    """读取任务不可变版本，并为每版文件生成受控下载 URL。"""
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT version, status, created_at, files FROM web_job_versions "
            "WHERE job_id = ? ORDER BY version DESC",
            (job_id,),
        ).fetchall()
    versions = []
    for row in rows:
        version = row["version"]
        files = deps.json_list(row["files"])
        versions.append({
            "version": version,
            "status": row["status"],
            "created_at": row["created_at"],
            "files": _download_files(
                files,
                lambda index, current=version: (
                    f"/api/jobs/{job_id}/versions/{current}/files/{index}"
                ),
            ),
        })
    return versions


def job_public(row: Any, deps: ResultDependencies) -> dict[str, object]:
    """把任务记录、版本和业务展示模型转换为浏览器公开结构。"""
    job_id = str(row["id"])
    files = deps.json_list(row["files"])
    result = deps.json_value(row["result"], None)
    presentation = (
        business_result_core.present(row["action"], result)
        if result is not None else None
    )
    return {
        "id": job_id,
        "action": row["action"],
        "title": row["title"],
        "status": row["status"],
        "progress": row["progress"],
        "logs": deps.json_list(row["logs"]),
        "result": result,
        "presentation": presentation,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "review_pending": deps.is_review_pending(row),
        "retry_of": row["retry_of"] if "retry_of" in row.keys() else None,
        "versions": _job_versions(job_id, deps),
        "files": _download_files(
            files, lambda index: f"/api/jobs/{job_id}/files/{index}",
        ),
    }


def owned_result_path(
    path_value: object,
    user_id: int,
    job_id: str,
    deps: ResultDependencies,
) -> Path:
    """限制任务文件只能来自当前账号上传目录或当前任务输出目录。"""
    user_root = deps.data_root / "users" / str(user_id)
    allowed_roots = [
        (user_root / "uploads").resolve(),
        (user_root / "jobs" / job_id / "outputs").resolve(),
    ]
    try:
        target = Path(str(path_value)).resolve()
    except (TypeError, OSError) as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在") from exc
    # 使用 resolve 后的路径比较，防止符号链接或 .. 绕过用户目录限制。
    if not any(target == root or root in target.parents for root in allowed_roots):
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在")
    return target

