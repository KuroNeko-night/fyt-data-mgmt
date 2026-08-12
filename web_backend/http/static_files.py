"""Web 前端静态资源托管与浏览器缓存策略。"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from web_backend.errors import ApiError


@dataclass(frozen=True)
class StaticFileDependencies:
    """静态资源服务所需的运行时路径。"""

    static_root: Path


def _cache_control(relative: str, candidate: Path) -> str:
    """按入口页、哈希资源和固定名称资源返回缓存策略。"""
    if candidate.name == "index.html":
        # 入口页引用带哈希资源，缓存旧 HTML 会造成部署后白屏。no-transform 同时禁止
        # Cloudflare 等中间代理改写 HTML 并注入 Bot 检测脚本；系统不依赖这类脚本，
        # 避免其 deprecated API 警告污染客户浏览器的开发者工具。
        return "no-store, must-revalidate, no-transform"
    if relative.startswith("assets/"):
        return "public, max-age=31536000, immutable"  # Vite 文件名含内容哈希，可安全永久缓存。
    return "public, max-age=604800"


def serve_static(handler: Any, path: str, deps: StaticFileDependencies) -> None:
    """托管 Vite 构建产物，并为前端路由提供入口页回退。"""
    if not deps.static_root.exists():
        handler.send_json(
            {"error": "前端尚未构建，请运行 web-app\\npm run build"},
            HTTPStatus.NOT_FOUND,
        )
        return
    root = deps.static_root.resolve()  # 先固定真实根路径，后续不能只依赖字符串前缀判断目录边界。
    relative = path.lstrip("/") or "index.html"
    candidate = (root / relative).resolve()  # resolve 会展开 ..，便于下一行统一拦截路径穿越。
    if candidate != root and root not in candidate.parents:
        raise ApiError(HTTPStatus.NOT_FOUND, "资源不存在")
    if not candidate.is_file():
        candidate = root / "index.html"  # 未命中静态文件时交给 React Router 处理客户端路由。
    handler.send_file(
        candidate,
        content_type=mimetypes.guess_type(candidate.name)[0],
        disposition=None,
        cache_control=_cache_control(relative, candidate),
    )
