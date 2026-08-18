"""Web API 路由匹配和各 HTTP 方法的路由表。

路由表只负责把 URL 映射到 Handler 的已有方法，不包含业务逻辑。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence


# 动态路由依次描述：固定前缀、固定后缀、必须包含的片段、实际处理函数。
PatternRoute = tuple[str, str, str | tuple[str, ...], Callable[[str], None]]


def dispatch_path(
    path: str,
    exact_routes: dict[str, Callable[[], None]],
    pattern_routes: Sequence[PatternRoute] = (),
) -> bool:
    """先匹配精确路由，再匹配前缀、后缀和包含片段组成的动态路由。"""
    handler = exact_routes.get(path)  # 精确路由优先，防止 /api/jobs 被更宽泛的 /api/jobs/<id> 规则吞掉。
    if handler is not None:
        handler()
        return True
    for prefix, suffix, contains, route_handler in pattern_routes:
        contains_match = (
            all(fragment in path for fragment in contains)
            if isinstance(contains, tuple)
            else (not contains or contains in path)
        )  # 元组用于版本文件等需要同时出现多个路径片段的情况，空字符串表示不附加限制。
        if path.startswith(prefix) and path.endswith(suffix) and contains_match:
            route_handler(path)
            return True
    return False


def post_upload_routes(handler) -> tuple[dict[str, Callable[[], None]], tuple[PatternRoute, ...]]:
    """返回需要在读取 JSON 请求体之前处理的上传路由。"""
    # 上传接口直接消费二进制请求流；若先按 JSON 读取，文件内容会被提前耗尽且触发解析错误。
    return (
        {
            "/api/files/upload": handler.upload_file,
            "/api/library/files": handler.upload_library_file,
            "/api/admin/master-data/imports": handler.upload_master_data_import,
            "/api/admin/daily-production-plans": handler.upload_daily_production_plan,
            "/api/admin/daily-source-uploads": handler.upload_daily_source,
        },
        (
            ("/api/library/files/", "/content", "", handler.replace_library_file),
            ("/api/workshop/issues/", "/images", "", handler.upload_workshop_issue_image),
        ),
    )


def post_routes(handler, body: dict[str, object]) -> tuple[dict[str, Callable[[], None]], tuple[PatternRoute, ...]]:
    """返回 POST JSON 精确路由和动态动作路由。

    请求体通过闭包绑定到本次请求，路由层不解析业务字段。创建、发布、复核、恢复和账号
    动作都只映射到 Handler 的白名单方法；动态规则同时约束前缀与后缀，具体编号仍由
    领域服务再次校验。
    """
    # lambda 只延迟调用并绑定本次请求体，业务校验仍全部位于对应服务模块。
    return (
        {
            "/api/auth/register": lambda: handler.register(body),
            "/api/auth/login": lambda: handler.login(body),
            "/api/auth/logout": handler.logout,
            "/api/auth/password": lambda: handler.change_password(body),
            "/api/jobs": lambda: handler.create_job(body),
            "/api/shares": lambda: handler.create_share(body),
            "/api/jobs/preflight": lambda: handler.preflight_job(body),
            "/api/workshop/issues": lambda: handler.create_workshop_issue(body),
            "/api/admin/backups": handler.create_backup,
            "/api/admin/messages": lambda: handler.publish_message(body),
            "/api/admin/announcements": lambda: handler.publish_announcement(body),
            "/api/admin/catalog": lambda: handler.admin_catalog(body),
            "/api/admin/daily-people": lambda: handler.create_daily_person(body),
            "/api/admin/daily-production-groups": lambda: handler.create_daily_production_group(body),
            "/api/admin/daily-attendance": lambda: handler.save_daily_attendance(body),
            "/api/admin/daily-brief-items": lambda: handler.create_daily_brief_item(body),
            "/api/templates": lambda: handler.create_template(body),
            "/api/reconcile/scan": lambda: handler.scan_reconcile(body),
            "/api/arrival/scan": lambda: handler.scan_arrival(body),
            "/api/notifications/read-all": handler.mark_all_notifications_read,
        },
        (
            ("/api/jobs/", "/assign", "", lambda value: handler.assign_job(value, body)),
            ("/api/workshop/issues/", "/publish", "", handler.publish_workshop_issue),
            ("/api/workshop/issues/", "/resolve", "", lambda value: handler.resolve_workshop_issue(value, body)),
            ("/api/workshop/issues/", "/reopen", "", lambda value: handler.reopen_workshop_issue(value, body)),
            ("/api/jobs/", "/retry", "", handler.retry_job),
            ("/api/jobs/", "/review", "", lambda value: handler.submit_review(value, body)),
            ("/api/jobs/", "/cancel", "", handler.cancel_job),
            ("/api/admin/users/", "/approve", "", lambda value: handler.review_user(value, "approved")),
            ("/api/admin/users/", "/reject", "", lambda value: handler.review_user(value, "rejected")),
            ("/api/admin/users/", "/role", "", lambda value: handler.update_user_role(value, body)),
            ("/api/admin/users/", "/access", "", lambda value: handler.update_user_access(value, body)),
            ("/api/admin/users/", "/sessions/revoke", "", handler.revoke_user_sessions),
            ("/api/admin/users/", "/password", "", lambda value: handler.reset_user_password(value, body)),
            ("/api/admin/trash/", "/restore", "", handler.restore_trash),
            ("/api/admin/backups/", "/restore", "", lambda value: handler.restore_backup(value, body)),
            ("/api/admin/master-data/imports/", "/resolve", "", lambda value: handler.resolve_master_data_conflict(value, body)),
            ("/api/admin/master-data/imports/", "/confirm", "", handler.confirm_master_data_import),
            ("/api/admin/master-data/imports/", "/merge", "", handler.merge_master_data_import),
            ("/api/admin/master-data/imports/", "/reject", "", handler.reject_master_data_import),
            ("/api/notifications/", "/read", "", handler.mark_notification_read),
        ),
    )


def get_routes(handler) -> tuple[dict[str, Callable[[], None]], tuple[PatternRoute, ...]]:
    """返回 GET 数据接口、动态资源接口和文件下载路由。

    动态规则按从具体到宽泛的顺序声明，版本文件、预览和普通文件必须先于任务详情匹配；
    每个下载处理器仍负责账号归属与真实路径校验。未匹配的 API 由 Handler 返回接口不
    存在，只有非 API GET 才进入前端静态资源回退。
    """
    # 更具体的下载/预览规则必须排在通用任务详情规则之前，dispatch_path 会按声明顺序匹配。
    return (
        {
            "/api/health": handler._health,
            "/api/auth/me": handler._auth_me,
            "/api/auth/sessions": handler.list_sessions,
            "/api/overview": handler._overview,
            "/api/dashboard": handler.dashboard,
            "/api/daily-report/export": handler.export_daily_report,
            "/api/daily-report": handler.daily_report,
            "/api/batch-track": handler.batch_track,
            "/api/reports/list": handler.list_report_files,
            "/api/reports": handler.build_report_endpoint,
            "/api/reports/download": handler.download_report_file,
            "/api/notifications": handler.notifications,
            "/api/templates": handler.list_templates,
            "/api/library/files": handler.list_library_files,
            "/api/workshop/issues/export": handler.export_workshop_issues,
            "/api/workshop/issues": handler.list_workshop_issues,
            "/api/search": handler.search,
            "/api/admin/users": handler._list_admin_users,
            "/api/admin/data": handler.admin_data,
            "/api/admin/audit": handler.admin_audit,
            "/api/admin/announcements": handler._list_admin_announcements,
            "/api/admin/backups": handler.list_backups,
            "/api/admin/catalog": handler.admin_catalog,
            "/api/admin/daily-people": handler.list_daily_people,
            "/api/admin/daily-production-groups": handler.list_daily_production_groups,
            "/api/admin/daily-attendance": handler.list_daily_attendance,
            "/api/admin/daily-brief-items": handler.list_daily_brief_items,
            "/api/admin/daily-production-plans": handler.list_daily_production_plans,
            "/api/admin/daily-source-uploads": handler.list_daily_sources,
            "/api/admin/master-data/imports": handler.list_master_data_imports,
            "/api/admin/master-data/export": handler.export_master_data_catalog,
            "/api/admin/trash": handler.list_trash,
            "/api/jobs": handler.list_jobs,
        },
        (
            ("/api/shares/", "", "", handler.download_shared_file),
            ("/api/library/files/", "/download", "", handler.download_library_file),
            ("/api/workshop/issues/", "", "/images/", handler.download_workshop_issue_image),
            ("/api/admin/daily-production-plans/", "/download", "", handler.download_daily_production_plan),
            ("/api/admin/daily-source-uploads/", "", "/images/", handler.download_daily_source_image),
            ("/api/admin/daily-source-uploads/", "/download", "", handler.download_daily_source),
            ("/api/admin/master-data/imports/", "", "", handler.get_master_data_import),
            ("/api/admin/backups/", "/download", "", handler.download_backup),
            ("/api/jobs/", "/preview", "/files/", handler.preview_job_file),
            ("/api/jobs/", "", ("/files/", "/versions/"), handler.download_job_version_file),
            ("/api/jobs/", "", "/files/", handler.download_job_file),
            ("/api/jobs/", "", "", handler.get_job),
        ),
    )


def patch_routes(handler, body: dict[str, object]) -> tuple[dict[str, Callable[[], None]], tuple[PatternRoute, ...]]:
    """返回 PATCH 路由。"""
    return (
        {},
        # PATCH 一律先读 JSON 再路由；具体编号由领域服务二次校验，路由只固定前缀。
        (
            ("/api/admin/users/", "", "", lambda value: handler.update_user(value, body)),
            ("/api/admin/daily-people/", "", "", lambda value: handler.update_daily_person(value, body)),
            ("/api/admin/daily-production-groups/", "", "", lambda value: handler.update_daily_production_group(value, body)),
            ("/api/admin/daily-brief-items/", "", "", lambda value: handler.update_daily_brief_item(value, body)),
            ("/api/admin/announcements/", "", "", lambda value: handler.update_announcement(value, body)),
            ("/api/templates/", "", "", lambda value: handler.update_template(value, body)),
            ("/api/library/files/", "", "", lambda value: handler.update_library_file(value, body)),
            ("/api/workshop/issues/", "", "", lambda value: handler.update_workshop_issue(value, body)),
        ),
    )


def delete_routes(handler) -> tuple[dict[str, Callable[[], None]], tuple[PatternRoute, ...]]:
    """返回 DELETE 路由。"""
    return (
        {},
        (
            ("/api/auth/sessions/", "", "", handler.delete_session),
            ("/api/shares/", "", "", handler.revoke_share),
            ("/api/admin/backups/", "", "", handler.delete_backup),
            ("/api/admin/trash/", "", "", handler.delete_trash),
            ("/api/admin/users/", "", "", handler.delete_user),
            ("/api/admin/daily-people/", "", "", handler.delete_daily_person),
            ("/api/admin/daily-production-groups/", "", "", handler.delete_daily_production_group),
            ("/api/admin/daily-brief-items/", "", "", handler.delete_daily_brief_item),
            ("/api/admin/daily-production-plans/", "", "", handler.delete_daily_production_plan),
            ("/api/admin/daily-source-uploads/", "", "", handler.delete_daily_source),
            ("/api/admin/jobs/", "", "", handler.delete_job),
            ("/api/admin/uploads/", "", "", handler.delete_upload),
            ("/api/admin/announcements/", "", "", handler.delete_announcement),
            ("/api/templates/", "", "", handler.delete_template),
            ("/api/library/files/", "", "", handler.delete_library_file),
            # 图片删除规则必须先于通用问题删除，否则带 /images/ 的路径会被更宽泛的问题规则抢先匹配。
            ("/api/workshop/issues/", "", "/images/", handler.delete_workshop_issue_image),
            ("/api/workshop/issues/", "", "", handler.delete_workshop_issue),
        ),
    )
