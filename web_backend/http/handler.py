"""Web HTTP 请求处理器与领域端点绑定。

本模块只负责 HTTP 协议适配、路由分发和同步轻量扫描。账号、任务、日清、资料等领域
行为仍位于 ``web_backend.services``，业务表格识别仍调用 ``core``。入口通过
``HandlerBindings`` 注入当前数据库、路径和限制，避免本模块反向导入 ``web_server``。

大量端点过去只是三行左右的重复方法。这里使用按领域分组的显式绑定表生成这些薄方法：
方法名仍真实存在于 Handler 类上，路由协议保持不变；每组依赖工厂也清楚标出，新增接口
时只需在对应领域登记一次，不再复制容易漏改的样板代码。
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core import arrival_core, reconcile_statement_core
from web_backend.errors import ApiError
from web_backend.http import context as request_context
from web_backend.http import responses as http_responses
from web_backend.http.routes import (
    delete_routes,
    dispatch_path,
    get_routes,
    patch_routes,
    post_routes,
    post_upload_routes,
)
from web_backend.http import static_files
from web_backend.services import admin_accounts as admin_account_service
from web_backend.services import admin_data as admin_data_service
from web_backend.services import auth as auth_service
from web_backend.services import backups as backup_service
from web_backend.services import daily_management as daily_management_service
from web_backend.services import dashboard as dashboard_service
from web_backend.services import jobs as jobs_service
from web_backend.services import library as library_service
from web_backend.services import master_data as master_data_service
from web_backend.services import notifications as notification_service
from web_backend.services import reports as report_service
from web_backend.services import trash as trash_service
from web_backend.services import uploads as upload_service
from web_backend.services import workshop as workshop_service


DependencyFactory = Callable[[], Any]


@dataclass(frozen=True)
class HandlerBindings:
    """请求处理器需要的运行配置、展示函数和各领域依赖工厂。

    字段保存的是“工厂”而不是已经构造好的依赖对象。每次请求再调用工厂，可继续支持
    测试动态替换 ``DATA_ROOT``、``DB_PATH`` 和静态资源目录，也避免恢复备份后沿用旧路径。
    """

    version: str
    max_json_body_bytes: int
    now_iso: Callable[[], str]
    user_public: Callable[[sqlite3.Row], dict[str, object]]
    resolve_uploads: Callable[[object, int], object]
    request_context_dependencies: DependencyFactory
    static_file_dependencies: DependencyFactory
    dashboard_dependencies: DependencyFactory
    upload_dependencies: DependencyFactory
    library_dependencies: DependencyFactory
    workshop_dependencies: DependencyFactory
    job_dependencies: DependencyFactory
    daily_management_dependencies: DependencyFactory
    auth_dependencies: DependencyFactory
    admin_account_dependencies: DependencyFactory
    backup_dependencies: DependencyFactory
    master_data_dependencies: DependencyFactory
    admin_data_dependencies: DependencyFactory
    trash_dependencies: DependencyFactory
    report_dependencies: DependencyFactory
    notification_dependencies: DependencyFactory


class ApiHandler(BaseHTTPRequestHandler):
    """峰运通 Web API 与静态前端的同源请求处理器。"""

    server_version = "FYTWeb/1.0"
    # 单个请求的套接字超时；长任务在后台线程运行，不在 HTTP 请求线程中等待。
    timeout = 60
    bindings: HandlerBindings

    @property
    def _bindings(self) -> HandlerBindings:
        """取得子类装配的依赖；缺少装配属于启动配置错误而非客户端错误。"""
        try:
            return type(self).bindings
        except AttributeError as exc:  # pragma: no cover - 只有错误集成才会触发。
            raise RuntimeError("HTTP Handler 尚未装配运行依赖") from exc

    def log_message(self, fmt: str, *args: object) -> None:
        """以统一时间格式输出访问日志，兼容图形控制台捕获标准输出。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        sys.stdout.write(f"[{timestamp}] {self.address_string()} {fmt % args}\n")

    def send_json(
        self, payload: object, status: int = HTTPStatus.OK, cookie: str = "",
    ) -> None:
        """发送统一 UTF-8 JSON 响应。"""
        http_responses.send_json(self, payload, status, cookie)

    def send_file(
        self,
        path: str | Path,
        *,
        content_type: str | None = None,
        file_name: str | None = None,
        disposition: str | None = "attachment",
        cache_control: str = "no-store",
    ) -> None:
        """按流式响应发送文件，并统一下载名、缓存和内容类型。"""
        http_responses.send_file(
            self,
            path,
            content_type=content_type,
            file_name=file_name,
            disposition=disposition,
            cache_control=cache_control,
        )

    def read_json(self) -> dict[str, object]:
        """读取受大小限制的 JSON 对象，拒绝超限或非对象请求体。"""
        return http_responses.read_json(self, self._bindings.max_json_body_bytes)

    def current_user(self) -> sqlite3.Row | None:
        """返回当前有效会话账号；匿名请求返回 ``None``。"""
        return request_context.current_user(
            self, self._bindings.request_context_dependencies(),
        )

    def require_user(self, admin: bool = False) -> sqlite3.Row:
        """要求已登录；``admin`` 为真时进一步要求管理员角色。"""
        return request_context.require_user(
            self, self._bindings.request_context_dependencies(), admin,
        )

    def require_role(self, *roles: str) -> sqlite3.Row:
        """要求当前账号属于指定角色之一，服务端鉴权不依赖前端隐藏入口。"""
        return request_context.require_role(
            self, self._bindings.request_context_dependencies(), *roles,
        )

    def _run_request(self, action: Callable[[], None]) -> None:
        """执行一次请求并把领域异常转换为一致的 JSON 错误响应。"""
        http_responses.run_request(self, action)

    def _dispatch_path(
        self,
        path: str,
        exact_routes: dict[str, Callable[[], None]],
        pattern_routes: Sequence[
            tuple[str, str, str | tuple[str, ...], Callable[[str], None]]
        ] = (),
    ) -> bool:
        """按精确路径和受限模式路由请求，返回是否成功匹配。"""
        return dispatch_path(path, exact_routes, pattern_routes)

    def _health(self) -> None:
        """返回无需登录的服务版本和当前服务器时间。"""
        self.send_json({
            "status": "ok",
            "app": "峰运通数据管理系统",
            "version": self._bindings.version,
            "server_time": self._bindings.now_iso(),
        })

    def _auth_me(self) -> None:
        """返回当前会话账号的公开字段，不包含密码摘要或内部状态。"""
        user = self.current_user()
        if user is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "未登录")
        self.send_json({"user": self._bindings.user_public(user)})

    def _overview(self) -> None:
        """生成当前账号可见的工作台总览。"""
        dashboard_service.overview(self, self._bindings.dashboard_dependencies())

    def _list_admin_users(self) -> None:
        """返回管理员账号维护列表。"""
        admin_account_service.list_users(
            self, self._bindings.admin_account_dependencies(),
        )

    def _list_admin_announcements(self) -> None:
        """返回管理员公告维护列表。"""
        notification_service.list_admin_announcements(
            self, self._bindings.notification_dependencies(),
        )

    def _handle_post_request(self) -> None:
        """优先分流二进制上传，再读取普通 POST 的 JSON 请求体。"""
        path = urlparse(self.path).path
        upload_routes, upload_patterns = post_upload_routes(self)
        if self._dispatch_path(path, upload_routes, upload_patterns):
            return
        body = self.read_json()
        exact_routes, pattern_routes = post_routes(self, body)
        if not self._dispatch_path(path, exact_routes, pattern_routes):
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")

    def _handle_get_request(self) -> None:
        """分发 GET；未知 API 返回 JSON 404，页面路径才回落到 SPA。"""
        path = urlparse(self.path).path
        exact_routes, pattern_routes = get_routes(self)
        if self._dispatch_path(path, exact_routes, pattern_routes):
            return
        if path.startswith("/api/"):
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
        self.serve_static(path)

    def _handle_patch_request(self) -> None:
        """读取 JSON 后分发局部更新请求。"""
        path = urlparse(self.path).path
        exact_routes, pattern_routes = patch_routes(self, self.read_json())
        if not self._dispatch_path(path, exact_routes, pattern_routes):
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")

    def _handle_delete_request(self) -> None:
        """分发删除、撤销和回收站请求。"""
        path = urlparse(self.path).path
        exact_routes, pattern_routes = delete_routes(self)
        if not self._dispatch_path(path, exact_routes, pattern_routes):
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")

    def do_POST(self) -> None:
        """处理 POST 请求。"""
        self._run_request(self._handle_post_request)

    def do_GET(self) -> None:
        """处理 GET 请求。"""
        self._run_request(self._handle_get_request)

    def do_PATCH(self) -> None:
        """处理 PATCH 请求。"""
        self._run_request(self._handle_patch_request)

    def do_DELETE(self) -> None:
        """处理 DELETE 请求。"""
        self._run_request(self._handle_delete_request)

    def scan_reconcile(self, body: dict[str, object]) -> None:
        """同步扫描对账单批次；这里只分析，不生成最终业务输出。"""
        user = self.require_user()
        resolved = self._bindings.resolve_uploads(body, int(user["id"]))
        result = reconcile_statement_core.scan(resolved.get("paths") or [])
        self.send_json(result)

    def scan_arrival(self, body: dict[str, object]) -> None:
        """扫描送货计划并返回可人工调整的总类数、批次和未到料摘要。"""
        user = self.require_user()
        handles = body.get("paths")
        if not isinstance(handles, list) or not handles:
            raise ApiError(HTTPStatus.BAD_REQUEST, "请至少上传一个送货计划")
        resolved = self._bindings.resolve_uploads(
            {"paths": handles}, int(user["id"]),
        )
        paths = resolved.get("paths") or []
        if len(paths) != len(handles):
            raise ApiError(HTTPStatus.BAD_REQUEST, "送货计划资料不完整，请重新上传")

        rows: list[dict[str, object]] = []
        for handle, path_value in zip(handles, paths):
            # 识别只读取当前账号已经解析过的真实路径；响应继续返回不透明上传句柄，
            # 正式任务会再次校验所属关系，扫描接口不能成为越权路径旁路。
            path = os.path.abspath(str(path_value))
            inspection = arrival_core.inspect_plan(path)
            total = int(inspection.get("total", 0) or 0)
            rows.append({
                "path": str(handle),
                "name": os.path.basename(path),
                "batch_no": arrival_core.detect_batch(path),
                "total": total,
                "auto_total": total,
                "missing_count": len(inspection.get("materials", [])),
                "remark": "",
                "include": True,
            })
        self.send_json({"rows": rows})

    def admin_catalog(self, body: dict[str, object] | None = None) -> None:
        """查询或维护正式主数据目录。

        GET 路由不传请求体，POST 路由传入维护对象，因此这里必须显式保留 ``None`` 默认值；
        该不对称签名不进入通用端点生成器，避免把依赖对象误当成请求体。
        """
        master_data_service.admin_catalog(
            self, body, self._bindings.master_data_dependencies(),
        )

    def serve_static(self, path: str) -> None:
        """发送静态资源并执行路径穿越校验和 SPA 页面回退。"""
        static_files.serve_static(
            self, path, self._bindings.static_file_dependencies(),
        )


def _delegate_endpoint(
    method_name: str,
    service: Callable[..., None],
    dependency_name: str,
    domain_label: str,
) -> Callable[..., None]:
    """创建一个仅负责“参数透传 + 依赖装配”的领域端点方法。

    路由传入的 ``path``、``body`` 或固定状态值保持原顺序；依赖对象统一追加在最后。这样
    服务函数仍拥有清晰、可独立测试的签名，同时 Handler 不再保存近百份重复样板。
    """

    def endpoint(self: ApiHandler, *args: object) -> None:
        factory = getattr(self._bindings, dependency_name)
        service(self, *args, factory())

    endpoint.__name__ = method_name
    endpoint.__qualname__ = f"ApiHandler.{method_name}"
    endpoint.__doc__ = f"委托{domain_label}服务处理请求，Handler 仅装配当前运行依赖。"
    return endpoint


# 端点表按领域分组。名称是 routes.py 使用的稳定协议，右侧函数是唯一业务实现；
# dependency_name 明确指出每次请求构造哪组路径、数据库、权限和展示依赖。
_DELEGATE_GROUPS: tuple[
    tuple[str, str, tuple[tuple[str, Callable[..., None]], ...]], ...
] = (
    ("临时上传", "upload_dependencies", (
        ("upload_file", upload_service.upload_file),
    )),
    ("共享数据库", "library_dependencies", (
        ("upload_library_file", library_service.upload_library_file),
        ("list_library_files", library_service.list_library_files),
        ("update_library_file", library_service.update_library_file),
        ("replace_library_file", library_service.replace_library_file),
        ("download_library_file", library_service.download_library_file),
        ("delete_library_file", library_service.delete_library_file),
    )),
    ("现场问题", "workshop_dependencies", (
        ("create_workshop_issue", workshop_service.create_workshop_issue),
        ("upload_workshop_issue_image", workshop_service.upload_workshop_issue_image),
        ("update_workshop_issue", workshop_service.update_workshop_issue),
        ("publish_workshop_issue", workshop_service.publish_workshop_issue),
        ("resolve_workshop_issue", workshop_service.resolve_workshop_issue),
        ("reopen_workshop_issue", workshop_service.reopen_workshop_issue),
        ("list_workshop_issues", workshop_service.list_workshop_issues),
        ("download_workshop_issue_image", workshop_service.download_workshop_issue_image),
        ("delete_workshop_issue_image", workshop_service.delete_workshop_issue_image),
        ("export_workshop_issues", workshop_service.export_workshop_issues),
        ("delete_workshop_issue", workshop_service.delete_workshop_issue),
    )),
    ("任务与人工复核", "job_dependencies", (
        ("create_job", jobs_service.create_job),
        ("preflight_job", jobs_service.preflight_job),
        ("retry_job", jobs_service.retry_job),
        ("list_jobs", jobs_service.list_jobs),
        ("search", jobs_service.search),
        ("list_templates", jobs_service.list_templates),
        ("create_template", jobs_service.create_template),
        ("update_template", jobs_service.update_template),
        ("delete_template", jobs_service.delete_template),
        ("get_job", jobs_service.get_job),
        ("cancel_job", jobs_service.cancel_job),
        ("submit_review", jobs_service.submit_review),
        ("download_job_file", jobs_service.download_job_file),
        ("download_job_version_file", jobs_service.download_job_version_file),
        ("preview_job_file", jobs_service.preview_job_file),
        ("assign_job", jobs_service.assign_job),
        ("create_share", jobs_service.create_share),
        ("download_shared_file", jobs_service.download_shared_file),
        ("revoke_share", jobs_service.revoke_share),
    )),
    ("日清维护", "daily_management_dependencies", (
        ("list_daily_people", daily_management_service.list_daily_people),
        ("create_daily_person", daily_management_service.create_daily_person),
        ("update_daily_person", daily_management_service.update_daily_person),
        ("delete_daily_person", daily_management_service.delete_daily_person),
        ("list_daily_production_groups", daily_management_service.list_daily_production_groups),
        ("create_daily_production_group", daily_management_service.create_daily_production_group),
        ("update_daily_production_group", daily_management_service.update_daily_production_group),
        ("delete_daily_production_group", daily_management_service.delete_daily_production_group),
        ("list_daily_attendance", daily_management_service.list_daily_attendance),
        ("save_daily_attendance", daily_management_service.save_daily_attendance),
        ("list_daily_brief_items", daily_management_service.list_daily_brief_items),
        ("create_daily_brief_item", daily_management_service.create_daily_brief_item),
        ("update_daily_brief_item", daily_management_service.update_daily_brief_item),
        ("delete_daily_brief_item", daily_management_service.delete_daily_brief_item),
        ("upload_daily_production_plan", daily_management_service.upload_daily_production_plan),
        ("list_daily_production_plans", daily_management_service.list_daily_production_plans),
        ("download_daily_production_plan", daily_management_service.download_daily_production_plan),
        ("delete_daily_production_plan", daily_management_service.delete_daily_production_plan),
        ("upload_daily_source", daily_management_service.upload_daily_source),
        ("list_daily_sources", daily_management_service.list_daily_sources),
        ("download_daily_source", daily_management_service.download_daily_source),
        ("download_daily_source_image", daily_management_service.download_daily_source_image),
        ("delete_daily_source", daily_management_service.delete_daily_source),
        ("daily_report", daily_management_service.daily_report),
        ("export_daily_report", daily_management_service.export_daily_report),
    )),
    ("管理看板", "dashboard_dependencies", (
        ("dashboard", dashboard_service.dashboard),
    )),
    ("账号认证", "auth_dependencies", (
        ("register", auth_service.register),
        ("login", auth_service.login),
        ("logout", auth_service.logout),
        ("change_password", auth_service.change_password),
        ("list_sessions", auth_service.list_sessions),
        ("delete_session", auth_service.delete_session),
    )),
    ("账号管理", "admin_account_dependencies", (
        ("review_user", admin_account_service.review_user),
        ("update_user", admin_account_service.update_user),
        ("update_user_role", admin_account_service.update_user_role),
        ("update_user_access", admin_account_service.update_user_access),
        ("revoke_user_sessions", admin_account_service.revoke_user_sessions),
        ("reset_user_password", admin_account_service.reset_user_password),
        ("delete_user", admin_account_service.delete_user),
    )),
    ("备份恢复", "backup_dependencies", (
        ("create_backup", backup_service.create_backup),
        ("list_backups", backup_service.list_backups),
        ("download_backup", backup_service.download_backup),
        ("delete_backup", backup_service.delete_backup),
        ("restore_backup", backup_service.restore_backup),
    )),
    ("主数据治理", "master_data_dependencies", (
        ("upload_master_data_import", master_data_service.upload_import),
        ("list_master_data_imports", master_data_service.list_imports),
        ("get_master_data_import", master_data_service.get_import),
        ("resolve_master_data_conflict", master_data_service.resolve_conflict),
        ("confirm_master_data_import", master_data_service.confirm_import),
        ("reject_master_data_import", master_data_service.reject_import),
        ("merge_master_data_import", master_data_service.merge_import),
        ("export_master_data_catalog", master_data_service.export_catalog),
    )),
    ("管理数据", "admin_data_dependencies", (
        ("admin_data", admin_data_service.admin_data),
        ("admin_audit", admin_data_service.admin_audit),
        ("delete_job", admin_data_service.delete_job),
        ("delete_upload", admin_data_service.delete_upload),
    )),
    ("回收站", "trash_dependencies", (
        ("list_trash", trash_service.list_trash),
        ("restore_trash", trash_service.restore_trash),
        ("delete_trash", trash_service.delete_trash),
    )),
    ("报表与批次跟踪", "report_dependencies", (
        ("batch_track", report_service.batch_track),
        ("build_report_endpoint", report_service.build_report_endpoint),
        ("list_report_files", report_service.list_report_files),
        ("download_report_file", report_service.download_report_file),
    )),
    ("消息与公告", "notification_dependencies", (
        ("notifications", notification_service.notifications),
        ("mark_notification_read", notification_service.mark_notification_read),
        ("mark_all_notifications_read", notification_service.mark_all_notifications_read),
        ("publish_message", notification_service.publish_message),
        ("publish_announcement", notification_service.publish_announcement),
        ("update_announcement", notification_service.update_announcement),
        ("delete_announcement", notification_service.delete_announcement),
    )),
)


for _domain, _dependency_name, _endpoints in _DELEGATE_GROUPS:
    for _method_name, _service in _endpoints:
        # setattr 在模块导入时执行一次，生成的方法与手写方法一样参与属性查找；路由仍通过
        # handler.create_job 等稳定名称调用，不需要改变任何 URL 或前端代码。
        setattr(
            ApiHandler,
            _method_name,
            _delegate_endpoint(
                _method_name, _service, _dependency_name, _domain,
            ),
        )


del _domain, _dependency_name, _endpoints, _method_name, _service
