"""峰运通数据管理系统局域网 Web 服务端组合入口。

运行于 Python 3.13，使用标准库 HTTP 服务托管同源 React 前端和 API。业务服务、路由、
数据库初始化与生命周期已拆分到 ``web_backend/``；本文件保留全局配置、依赖装配、
独立 Core 桥接进程和历史公开入口，避免部署脚本与测试在拆分期间失效。

所有业务任务按用户 ID 隔离上传、输出、缓存和运行目录。HTTP 线程不直接执行耗时 Excel
逻辑，而是通过标准流协议启动 ``core.tauri_bridge`` 子进程，以便取消、记录进度并隔离
第三方库异常。绝对文件路径只在服务端持久化，对浏览器响应会转换为受控下载 URL。
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
import urllib.request

# core 是纯业务事实源；入口只导入配置、解析器和库操作，不复制任何业务算法。
from core.version import VERSION
from core import arrival_core
from core import daily_report_core
from core import daily_production_plan_core
from core import daily_safety_check_core
from core import library as core_library
from core import material_catalog
from core import master_data_import_core
from core import report_center_core
from core import storage_lock as core_storage_lock
from core import workshop_issue_core

# web_backend 承载 HTTP、数据库、领域服务与任务运行器；本文件仅做装配和兼容导出。
from web_backend import config as server_config
from web_backend import presenters
from web_backend import server_runtime
from web_backend.database import DB_LOCK as _DB_LOCK
from web_backend.database import ManagedConnection as _ManagedConnection
from web_backend.database import db as _db
from web_backend.database.initializer import initialize as initialize_database
from web_backend.errors import ApiError as _ApiError
from web_backend.http import context as request_context
from web_backend.http import static_files
from web_backend.http.handler import ApiHandler, HandlerBindings
from web_backend.serializers import json_list as _json_list_from_backend
from web_backend.serializers import json_object as _json_object_from_backend
from web_backend.serializers import json_value as _json_value_from_backend
from web_backend.passwords import hash_password, password_policy_error, verify_password
from web_backend.services import auth as auth_service
from web_backend.services import maintenance as maintenance_service
from web_backend.services import daily_report as daily_report_service
from web_backend.services import admin_accounts as admin_account_service
from web_backend.services import notifications as notification_service
from web_backend.services import library as library_service
from web_backend.services import workshop as workshop_service
from web_backend.services import jobs as jobs_service
from web_backend.services import daily_management as daily_management_service
from web_backend.services import backups as backup_service
from web_backend.services import admin_data as admin_data_service
from web_backend.services import trash as trash_service
from web_backend.services import master_data as master_data_service
from web_backend.services import reports as report_service
from web_backend.services import dashboard as dashboard_service
from web_backend.services import uploads as upload_service
from web_backend.tasks import actions as task_actions
from web_backend.tasks import bridge as task_bridge
from web_backend.tasks import results as task_results
from web_backend.tasks import runner as task_runner


# Web 配置的唯一事实源是 web_backend/config.py；此处只兼容导出旧名称，避免部署脚本与测试失效。
ROOT = server_config.ROOT
WEB_ROOT = server_config.WEB_ROOT
STATIC_ROOT = server_config.STATIC_ROOT

# 运行路径、监听地址和会话安全上限均由配置模块集中管理；入口层只读全局值。
DATA_ROOT = server_config.DATA_ROOT
DB_PATH = server_config.DB_PATH
HOST = server_config.HOST
PORT = server_config.PORT
SESSION_DAYS = server_config.SESSION_DAYS
SESSION_TOUCH_INTERVAL_SECONDS = server_config.SESSION_TOUCH_INTERVAL_SECONDS
MAX_UPLOAD_BYTES = server_config.MAX_UPLOAD_BYTES
MAX_MASTER_DATA_UPLOAD_BYTES = server_config.MAX_MASTER_DATA_UPLOAD_BYTES
MAX_JSON_BODY_BYTES = server_config.MAX_JSON_BODY_BYTES
MAX_WORKSHOP_IMAGE_BYTES = server_config.MAX_WORKSHOP_IMAGE_BYTES
MAX_WORKSHOP_IMAGES = server_config.MAX_WORKSHOP_IMAGES
MAX_WORKSHOP_EXPORT_DAYS = server_config.MAX_WORKSHOP_EXPORT_DAYS
WORKSHOP_DRAFT_RETENTION_HOURS = server_config.WORKSHOP_DRAFT_RETENTION_HOURS
LIBRARY_USER_QUOTA_BYTES = server_config.LIBRARY_USER_QUOTA_BYTES
LOGIN_FAILURE_LIMIT = server_config.LOGIN_FAILURE_LIMIT
LOGIN_WINDOW_SECONDS = server_config.LOGIN_WINDOW_SECONDS
LOGIN_LOCK_SECONDS = server_config.LOGIN_LOCK_SECONDS
OUTPUT_RETENTION_COUNT = server_config.OUTPUT_RETENTION_COUNT
TRASH_RETENTION_DAYS = server_config.TRASH_RETENTION_DAYS
BUSINESS_TZ = server_config.BUSINESS_TZ
MAINTENANCE_INTERVAL_SECONDS = server_config.MAINTENANCE_INTERVAL_SECONDS
BACKUP_ROOT = server_config.BACKUP_ROOT
TRASH_ROOT = server_config.TRASH_ROOT
AUTO_BACKUP_KEEP = server_config.AUTO_BACKUP_KEEP
NOTIFY_WEBHOOK_URL = server_config.NOTIFY_WEBHOOK_URL

# 角色矩阵：业务成员/班组长/管理员及其中文文案、可访问能力全部由配置模块定义。
# 前端隐藏导航不能替代后端鉴权，入口只导出稳定英文键给 HTTP 层使用。
ROLE_LABELS = server_config.ROLE_LABELS
ROLE_CHOICES = server_config.ROLE_CHOICES
LIBRARY_ROLES = server_config.LIBRARY_ROLES
DAILY_PERSON_TYPES = server_config.DAILY_PERSON_TYPES
DAILY_BRIEF_CATEGORIES = server_config.DAILY_BRIEF_CATEGORIES
DAILY_BRIEF_STATUSES = server_config.DAILY_BRIEF_STATUSES
WORKSHOP_ISSUE_CATEGORIES = server_config.WORKSHOP_ISSUE_CATEGORIES
WORKSHOP_ISSUE_SEVERITIES = server_config.WORKSHOP_ISSUE_SEVERITIES
WORKSHOP_ISSUE_TEMPLATE_FIELDS = server_config.WORKSHOP_ISSUE_TEMPLATE_FIELDS


def role_label(role: object) -> str:
    """兼容旧调用名，转由配置模块返回中文角色名称。

    入口层不保存角色映射副本，避免角色键、中文文案与权限矩阵出现第二份事实源。
    """
    return server_config.role_label(role)


def notify_webhook(title: str, content: str) -> None:
    """异步向企业微信/钉钉兼容的 text webhook 推送消息。

    通知是辅助功能，网络超时或第三方响应异常不能改变业务任务结果，因此独立守护线程
    最多等待五秒并吞掉异常。消息内容不包含密码、会话令牌或文件绝对路径。
    """
    url = NOTIFY_WEBHOOK_URL
    if not url:
        return

    def send() -> None:
        """在守护线程中发送一次 webhook，并把所有外部网络失败降级为静默失败。

        该闭包只捕获已经清理过的标题、正文和固定地址，不接触数据库事务。读取响应体可
        促使连接正常结束，但第三方返回内容不参与业务判断。
        """
        try:
            # 脱敏错误信息里可能出现的服务端绝对路径，避免向外部 webhook 泄露部署目录结构。
            safe_content = str(content)
            for base in (str(DATA_ROOT), str(ROOT)):
                if base:
                    safe_content = safe_content.replace(base, "<数据目录>")
            payload = json.dumps(
                {"msgtype": "text", "text": {"content": f"{title}\n{safe_content}"}},
                ensure_ascii=False,
            ).encode("utf-8")
            request = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read()
        except Exception:
            pass  # 外部通知失败不回滚已经完成的本地业务事务。

    threading.Thread(target=send, daemon=True).start()  # 守护线程不会阻止服务进程退出。


# 数据库锁保护同一进程内的 SQLite 复合操作；其余锁分别隔离任务进程表、文件事务和
# 需要临时改写环境变量的主数据 Core。拆开锁域可避免大型文件操作阻塞普通登录查询。
DB_LOCK = _DB_LOCK
JOB_LOCK = threading.RLock()
STORAGE_LOCK = threading.RLock()
MASTER_DATA_LOCK = threading.RLock()
JOB_PROCESSES: dict[str, subprocess.Popen[str]] = {}
ManagedConnection = _ManagedConnection
ApiError = _ApiError


def db() -> sqlite3.Connection:
    """使用当前服务数据路径创建连接，保留测试和部署时的路径注入能力。"""
    return _db(DATA_ROOT, DB_PATH)


def master_data_import_root() -> Path:
    """返回 Web 服务共享的主数据导入元数据目录。

    该目录用于保存待合并批次和导入过程文件，不直接暴露给浏览器；调用 Core 前必须通过
    ``web_master_data_environment`` 注入环境变量。
    """
    return DATA_ROOT / "master-data-imports"


@contextlib.contextmanager
def web_master_data_environment():
    """为直接调用 Core 的管理员接口临时设置 Web 主数据路径。

    Core 通过环境变量定位主数据文件，进程内环境变量又是全局状态，因此必须在专用锁内
    保存旧值、设置 Web 路径并在 ``finally`` 中恢复。这样测试、桌面端嵌入调用或异常
    中断都不会把随后任务永久指向错误的数据目录。
    """
    catalog_key = "FYT_CATALOG_PATH"
    import_key = "FYT_MASTER_DATA_IMPORT_ROOT"
    with MASTER_DATA_LOCK:
        old_catalog = os.environ.get(catalog_key)
        old_import = os.environ.get(import_key)
        os.environ[catalog_key] = str(DATA_ROOT / "catalog.json")
        os.environ[import_key] = str(master_data_import_root())
        try:
            yield
        finally:
            # 区分“原来不存在”和“原来为空字符串”，精确恢复调用前的进程环境。
            if old_catalog is None:
                os.environ.pop(catalog_key, None)
            else:
                os.environ[catalog_key] = old_catalog
            if old_import is None:
                os.environ.pop(import_key, None)
            else:
                os.environ[import_key] = old_import

# Web 动作白名单与两阶段人工复核动作；新动作必须同时评估桥接白名单、路径校验和复核协议。
WEB_ACTIONS = server_config.WEB_ACTIONS
REVIEW_ACTIONS = server_config.REVIEW_ACTIONS


def feature_key_for_action(action: object) -> str:
    """兼容旧调用名，转由配置模块解析业务功能键。"""
    return server_config.feature_key_for_action(action)


def is_review_pending(row: sqlite3.Row) -> bool:
    """兼容旧调用名，转由配置模块判断是否等待人工复核。"""
    return server_config.is_review_pending(row)

FEATURES = server_config.FEATURES
"""前端工作台功能目录。"""


def now_iso() -> str:
    """返回秒精度 UTC ISO 时间，作为数据库排序和并发版本的统一格式。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def business_today() -> date:
    """业务时区下的今天。用于按「哪一天」分桶的统计。"""
    return datetime.now(BUSINESS_TZ).date()


def business_date(value: str) -> str:
    """把库里的 UTC 时间戳转成业务时区的日期字符串（YYYY-MM-DD）。

    直接对时间戳做 value[:10] 取到的是 UTC 日期，与前端按本地时区渲染出的
    日期不一致——本地 00:00-07:59 的任务会掉进前一天，导致「今天 0 件」。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(BUSINESS_TZ).date().isoformat()


def business_day_bounds(value: date) -> tuple[str, str]:
    """返回业务日期对应的 UTC 左闭右开时间范围。

    数据库存 UTC，管理看板按业务时区分日；把本地午夜转换为 UTC 后查询 ``[start, end)``
    能正确处理跨日边界，并避免相邻日期同时包含恰好午夜的记录。
    """
    start = datetime.combine(value, datetime.min.time(), tzinfo=BUSINESS_TZ)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def path_is_within(root: Path, target: Path) -> bool:
    """判断目标路径是否位于指定目录内，避免字符串前缀和符号链接误判。"""
    try:
        root_resolved = root.resolve()
        target_resolved = target.resolve()
    except OSError:
        return False
    return target_resolved == root_resolved or root_resolved in target_resolved.parents


def write_audit(actor_id: int, action: str) -> None:
    """写入一条管理审计记录，供管理页“管理记录”查询。

    审计写入使用独立数据库锁并立即提交，不参与业务事务回滚；动作文本截断到 200 字符，
    防止异常输入撑大审计页。
    """
    with DB_LOCK, db() as connection:
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor_id, action[:200], now_iso()),
        )


REPORT_RANGE_LABELS = report_service.REPORT_RANGE_LABELS


def build_web_report_file(range_key: str, user_id: int | None, scope_all: bool) -> Path:
    """保留原公开入口，委托报表服务生成业务报表。"""
    return report_service.build_web_report_file(
        _report_dependencies(), range_key, user_id, scope_all,
    )


def auto_weekly_report_if_due() -> str:
    """保留原公开入口，执行每周业务报表任务。"""
    return report_service.auto_weekly_report_if_due(_report_dependencies())


def auto_monthly_report_if_due() -> str:
    """保留原公开入口，执行每月业务报表任务。"""
    return report_service.auto_monthly_report_if_due(_report_dependencies())


def _daily_management_dependencies() -> daily_management_service.DailyManagementDependencies:
    """组装日清维护、成品资料上传、快照和报告导出服务依赖。

    这里把业务时区、上传上限、Core 解析器、统一投影和存储锁集中注入领域服务。日清
    服务因此无需反向导入入口全局变量，测试可替换日期、数据目录和表格解析器，也能保证
    到料、安全检查与生产计划始终复用 Core 的唯一业务规则。
    """
    return daily_management_service.DailyManagementDependencies(
        db_lock=DB_LOCK,
        db=db,
        storage_lock=STORAGE_LOCK,
        data_root=DATA_ROOT,
        request_max_upload_bytes=MAX_UPLOAD_BYTES,
        max_upload_bytes=MAX_MASTER_DATA_UPLOAD_BYTES,
        person_types=DAILY_PERSON_TYPES,
        brief_categories=DAILY_BRIEF_CATEGORIES,
        brief_statuses=DAILY_BRIEF_STATUSES,
        now_iso=now_iso,
        business_today=business_today,
        report_date=daily_report_date,
        safe_name=safe_name,
        daily_person_public=daily_person_public,
        production_group_public=daily_production_group_public,
        daily_attendance_public=daily_attendance_public,
        production_attendance_public=daily_production_attendance_public,
        daily_brief_public=daily_brief_public,
        production_plan_public=production_plan_public,
        source_upload_public=daily_source_upload_public,
        production_plan_core=daily_production_plan_core,
        arrival_core=arrival_core,
        safety_check_core=daily_safety_check_core,
        daily_report_core=daily_report_core,
        build_daily_report_snapshot=build_daily_report_snapshot,
        tree_size=_tree_size,
        write_audit=write_audit,
    )


def _request_context_dependencies() -> request_context.RequestContextDependencies:
    """组装会话读取、账号识别和角色权限服务依赖。

    会话 Cookie 校验、设备管理和角色判定都在请求上下文模块中完成；入口只注入锁、数据库
    工厂和统一时间函数，不在此复制任何权限矩阵。
    """
    return request_context.RequestContextDependencies(
        db_lock=DB_LOCK,
        db=db,
        now_iso=now_iso,
        touch_interval_seconds=SESSION_TOUCH_INTERVAL_SECONDS,
        role_label=role_label,
    )


def _static_file_dependencies() -> static_files.StaticFileDependencies:
    """组装前端静态资源服务依赖。

    静态目录来自配置模块并由 HTTP 层做路径包含校验，本函数只传递值，不解析用户请求路径。
    """
    return static_files.StaticFileDependencies(static_root=STATIC_ROOT)


def _dashboard_dependencies() -> dashboard_service.DashboardDependencies:
    """组装工作台概览与个人看板聚合服务依赖。

    看板只读聚合当前用户可见数据；角色可访问功能和业务日期边界由注入函数统一提供。
    """
    return dashboard_service.DashboardDependencies(
        db_lock=DB_LOCK,
        db=db,
        now_iso=now_iso,
        business_today=business_today,
        business_date=business_date,
        is_review_pending=is_review_pending,
        feature_key_for_action=feature_key_for_action,
        features=FEATURES,
        json_list=_json_list,
        user_public=user_public,
        notification_public=notification_public,
    )


def _upload_dependencies() -> upload_service.UploadDependencies:
    """组装临时业务上传与上传句柄解析服务依赖。

    上传目录按用户隔离，``safe_name`` 与大小上限在服务端执行；浏览器提交的路径不会直接
    用于文件读写。
    """
    return upload_service.UploadDependencies(
        db_lock=DB_LOCK,
        db=db,
        data_root=DATA_ROOT,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        now_iso=now_iso,
        safe_name=safe_name,
    )


def _bridge_dependencies() -> task_bridge.BridgeDependencies:
    """组装 Core 子进程执行依赖，并保留测试动态替换数据根的能力。

    这里不缓存依赖对象，因为测试、部署启动器和备份恢复流程会在运行期替换
    ``DATA_ROOT``。每次调用读取当前全局值，才能保证任务仍写入当前账号的数据目录。
    """
    return task_bridge.BridgeDependencies(
        root=ROOT,
        data_root=DATA_ROOT,
        job_lock=JOB_LOCK,
        job_processes=JOB_PROCESSES,
        append_job_log=append_job_log,
        update_job=update_job,
    )


def _result_dependencies() -> task_results.ResultDependencies:
    """组装任务结果投影、版本查询和受控下载路径依赖。

    返回浏览器的结构会隐藏绝对路径；后续下载、预览和分享链接仍需经过所属关系校验。
    """
    return task_results.ResultDependencies(
        data_root=DATA_ROOT,
        db_lock=DB_LOCK,
        db=db,
        json_list=_json_list,
        json_value=_json_value,
        is_review_pending=is_review_pending,
    )


def _runner_dependencies() -> task_runner.RunnerDependencies:
    """组装后台任务状态机依赖，辅助维护失败不影响业务完成状态。"""
    return task_runner.RunnerDependencies(
        db_lock=DB_LOCK,
        db=db,
        now_iso=now_iso,
        update_job=update_job,
        execute_action=execute_action,
        collect_result_files=collect_result_files,
        public_result=public_result,
        enforce_output_retention=enforce_output_retention,
        notify_webhook=notify_webhook,
        review_actions=REVIEW_ACTIONS,
    )


def _job_dependencies() -> jobs_service.JobDependencies:
    """组装任务、人工复核和分享服务依赖。

    人工复核遵循“只读分析 -> 返回计划 -> 用户选择 -> 最终执行”的两阶段协议；任务公开
    投影隐藏服务端绝对路径。
    """
    return jobs_service.JobDependencies(
        db_lock=DB_LOCK,
        db=db,
        job_lock=JOB_LOCK,
        job_processes=JOB_PROCESSES,
        web_actions=WEB_ACTIONS,
        review_actions=REVIEW_ACTIONS,
        now_iso=now_iso,
        resolve_uploads=resolve_uploads,
        run_web_job=run_web_job,
        job_public=job_public,
        json_list=_json_list,
        json_object=_json_object,
        owned_result_path=_owned_result_path,
        write_audit=write_audit,
    )


def _workshop_dependencies() -> workshop_service.WorkshopDependencies:
    """组装现场问题模板、图片存储、权限投影和导出服务依赖。

    五类模板字段和图片限制来自统一配置，编辑、闭环、删除权限及公开投影由集中函数
    注入。领域服务只使用这些显式能力，不读取入口内部状态，便于合成测试覆盖账号隔离、
    目录穿越防护和模板导出规则。
    """
    return workshop_service.WorkshopDependencies(
        db_lock=DB_LOCK,
        db=db,
        storage_lock=STORAGE_LOCK,
        data_root=DATA_ROOT,
        max_image_bytes=MAX_WORKSHOP_IMAGE_BYTES,
        max_images=MAX_WORKSHOP_IMAGES,
        categories=WORKSHOP_ISSUE_CATEGORIES,
        template_fields=WORKSHOP_ISSUE_TEMPLATE_FIELDS,
        now_iso=now_iso,
        safe_name=safe_name,
        issue_date=workshop_issue_date,
        export_range=workshop_issue_export_range,
        issue_dir=workshop_issue_dir,
        resolve_image_path=resolve_workshop_image_path,
        can_edit=workshop_issue_can_edit,
        can_resolve=workshop_issue_can_resolve,
        can_delete=workshop_issue_can_delete,
        issue_public=workshop_issue_public,
        tree_size=_tree_size,
        write_audit=write_audit,
        workshop_core=workshop_issue_core,
    )


def _library_dependencies() -> library_service.LibraryDependencies:
    """组装共享文件数据库服务依赖。

    允许角色、用户配额和分类注册表均在此注入；文件路径在服务层重新解析到所属账号目录。
    """
    return library_service.LibraryDependencies(
        db_lock=DB_LOCK,
        db=db,
        data_root=DATA_ROOT,
        storage_lock=STORAGE_LOCK,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        user_quota_bytes=LIBRARY_USER_QUOTA_BYTES,
        allowed_roles=LIBRARY_ROLES,
        now_iso=now_iso,
        safe_name=safe_name,
        library_scope=library_scope,
        library_category=library_category,
        library_category_catalog=library_category_catalog,
        classify_library_file=classify_library_file,
        library_file_public=library_file_public,
        resolve_library_path=resolve_library_path,
        write_audit=write_audit,
        unknown_category=core_library.UNKNOWN,
    )


def _notification_dependencies() -> notification_service.NotificationDependencies:
    """组装消息和公告服务依赖。

    消息中心只返回当前账号可见内容，公告展示不包含服务端路径或令牌。
    """
    return notification_service.NotificationDependencies(
        db_lock=DB_LOCK,
        db=db,
        now_iso=now_iso,
        announcement_public=announcement_public,
        notification_public=notification_public,
    )


def _admin_account_dependencies() -> admin_account_service.AdminAccountDependencies:
    """组装管理员账号服务依赖，保留当前数据路径和任务进程状态。

    管理员密码策略、会话失效和备份创建都由领域服务执行；本入口不直接处理明文密码。
    """
    return admin_account_service.AdminAccountDependencies(
        db_lock=DB_LOCK,
        db=db,
        now_iso=now_iso,
        role_choices=ROLE_CHOICES,
        user_public=user_public,
        password_policy_error=password_policy_error,
        hash_password=hash_password,
        create_web_backup=create_web_backup,
        job_lock=JOB_LOCK,
        job_processes=JOB_PROCESSES,
        data_root=DATA_ROOT,
    )


def _backup_dependencies() -> backup_service.BackupDependencies:
    """组装备份创建、校验和恢复服务依赖。

    备份与恢复需要暂停任务进程并持有数据库锁，因此同时注入 ``JOB_LOCK`` 与
    ``JOB_PROCESSES``，防止备份期间新任务写入文件或数据库。
    """
    return backup_service.BackupDependencies(
        db_lock=DB_LOCK,
        db=db,
        data_root=DATA_ROOT,
        db_path=DB_PATH,
        job_lock=JOB_LOCK,
        job_processes=JOB_PROCESSES,
        auto_backup_keep=AUTO_BACKUP_KEEP,
        version=VERSION,
        now_iso=now_iso,
        master_data_import_root=master_data_import_root,
        catalog_file_lock=core_storage_lock.file_lock,
        init_db=init_db,
        write_audit=write_audit,
    )


def _admin_data_dependencies() -> admin_data_service.AdminDataDependencies:
    """组装管理员数据总览、审计和资料维护服务依赖。"""
    return admin_data_service.AdminDataDependencies(
        db_lock=DB_LOCK,
        db=db,
        storage_lock=STORAGE_LOCK,
        data_root=DATA_ROOT,
        job_lock=JOB_LOCK,
        job_processes=JOB_PROCESSES,
        now_iso=now_iso,
        user_public=user_public,
        json_list=_json_list,
        move_job_to_trash=move_job_to_trash,
    )


def _trash_dependencies() -> trash_service.TrashDependencies:
    """组装回收站分类恢复服务依赖。

    回收站按文件类别恢复，分类枚举来自 core 事实源，恢复前仍需重新校验所属账号目录。
    """
    return trash_service.TrashDependencies(
        db_lock=DB_LOCK,
        db=db,
        storage_lock=STORAGE_LOCK,
        data_root=DATA_ROOT,
        now_iso=now_iso,
        json_value=_json_value,
        json_list=_json_list,
        library_categories=tuple(core_library.CATEGORIES),
        library_unknown=core_library.UNKNOWN,
        workshop_template_fields=tuple(WORKSHOP_ISSUE_TEMPLATE_FIELDS),
        workshop_core=workshop_issue_core,
    )


def _master_data_dependencies() -> master_data_service.MasterDataDependencies:
    """组装主数据正式档案与表格学习服务依赖。

    通过环境上下文把 Core 主数据路径指向 Web 账号隔离目录；正式档案只补空值，管理员确认
    值不会被被动学习覆盖。
    """
    return master_data_service.MasterDataDependencies(
        db_lock=DB_LOCK,
        db=db,
        data_root=DATA_ROOT,
        max_upload_bytes=MAX_MASTER_DATA_UPLOAD_BYTES,
        now_iso=now_iso,
        safe_name=safe_name,
        environment=web_master_data_environment,
        import_core=master_data_import_core,
        catalog_core=material_catalog,
    )


def _report_dependencies() -> report_service.ReportDependencies:
    """组装报表中心、批次跟踪与周期报表服务依赖。

    报表文件路径由 ``path_is_within`` 校验，防止越权读取任务输出目录之外的报告。
    """
    return report_service.ReportDependencies(
        db_lock=DB_LOCK,
        db=db,
        data_root=DATA_ROOT,
        now_iso=now_iso,
        json_value=_json_value,
        collect_result_files=collect_result_files,
        feature_key_for_action=feature_key_for_action,
        path_is_within=path_is_within,
        report_core=report_center_core,
    )


def _auth_dependencies() -> auth_service.AuthDependencies:
    """按当前 Web 运行配置组装认证服务依赖，支持测试注入临时数据库。"""
    return auth_service.AuthDependencies(
        db=db,
        db_lock=DB_LOCK,
        now_iso=now_iso,
        hash_password=hash_password,
        verify_password=verify_password,
        password_policy_error=password_policy_error,
        user_public=user_public,
        session_days=SESSION_DAYS,
        touch_interval_seconds=SESSION_TOUCH_INTERVAL_SECONDS,
        login_failure_limit=LOGIN_FAILURE_LIMIT,
        login_window_seconds=LOGIN_WINDOW_SECONDS,
        login_lock_seconds=LOGIN_LOCK_SECONDS,
    )


def _tree_size(path: Path) -> int:
    """统计文件或目录树中普通文件的字节数，供配额和回收站展示使用。"""
    if path.is_file():
        return path.stat().st_size
    if not path.is_dir():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())  # 目录本身元数据不计入用户可理解的文件容量。


def create_web_backup(created_by: int | None = None, auto: bool = False) -> dict[str, object]:
    """保留原公开入口：先同步旧全局备份根，再委托备份服务创建可校验快照。"""
    global BACKUP_ROOT
    BACKUP_ROOT = DATA_ROOT / "backups"
    return backup_service.create_web_backup(_backup_dependencies(), created_by, auto)


def auto_backup_if_due() -> str:
    """保留原公开入口：先同步旧全局备份根，再执行每日备份与滚动清理。"""
    global BACKUP_ROOT
    BACKUP_ROOT = DATA_ROOT / "backups"
    return backup_service.auto_backup_if_due(_backup_dependencies())


def verify_web_backup(path: Path) -> dict[str, object]:
    """保留原公开入口，委托备份服务完成完整性校验。

    校验只读备份文件，不修改生产数据库或任务进程。
    """
    return backup_service.verify_web_backup(path)


def init_db() -> None:
    """初始化当前配置指向的 Web 数据库，保留旧入口兼容测试和部署脚本。

    建库事务、表结构和幂等迁移由 ``web_backend.database.initializer`` 统一编排；本函数
    只负责注入数据库锁、时间与密码摘要能力。
    """
    initialize_database(
        db_lock=DB_LOCK,
        db_factory=db,
        now_iso=now_iso,
        hash_password=hash_password,
        password_policy_error=password_policy_error,
        workshop_issue_template_fields=WORKSHOP_ISSUE_TEMPLATE_FIELDS,
    )


def _maintenance_dependencies() -> maintenance_service.MaintenanceDependencies:
    """组装输出保留、回收站、草稿和主数据自动维护的运行时依赖。

    数据库锁、存储锁、保留周期和路径函数在此统一交给维护服务；主数据合并额外包裹 Web
    环境上下文。维护模块因此既不依赖启动入口，也能在测试中注入固定时间和临时目录。
    """
    def merge_ready_batches(limit: int) -> dict[str, object]:
        """在 Web 主数据隔离环境中自动合并已确认且仍无冲突的批次。

        周期维护只传入处理上限，真正的状态复核和原子合并仍由 Core 完成。环境上下文
        确保自动任务不会读取桌面端的本地主数据目录。
        """
        with web_master_data_environment():
            return master_data_import_core.merge_ready_batches(limit=limit)

    return maintenance_service.MaintenanceDependencies(
        db_lock=DB_LOCK,
        db=db,
        data_root=DATA_ROOT,
        storage_lock=STORAGE_LOCK,
        output_retention_count=OUTPUT_RETENTION_COUNT,
        trash_retention_days=TRASH_RETENTION_DAYS,
        workshop_draft_retention_hours=WORKSHOP_DRAFT_RETENTION_HOURS,
        tree_size=_tree_size,
        is_review_pending=is_review_pending,
        workshop_issue_dir=workshop_issue_dir,
        now_iso=now_iso,
        merge_ready_batches=merge_ready_batches,
        merge_environment=web_master_data_environment,
    )


def move_job_to_trash(
    job_id: str,
    deleted_by: int | None = None,
    audit_action: str | None = None,
) -> str | None:
    """把任务记录及所属输出目录原子移入回收站。"""
    return maintenance_service.move_job_to_trash(
        _maintenance_dependencies(), job_id, deleted_by, audit_action,
    )


def enforce_output_retention(limit: int = OUTPUT_RETENTION_COUNT) -> int:
    """每个账号仅保留最近若干个包含输出文件的已完成任务。"""
    return maintenance_service.enforce_output_retention(
        _maintenance_dependencies(), limit, move_job_to_trash,
    )


def purge_expired_trash(
    retention_days: int = TRASH_RETENTION_DAYS,
    current_time: datetime | None = None,
) -> tuple[int, int]:
    """彻底删除超过保留期的回收站数据，失败项目留待下次重试。"""
    return maintenance_service.purge_expired_trash(
        _maintenance_dependencies(), retention_days, current_time,
    )


def cleanup_stale_workshop_drafts(
    retention_hours: int = WORKSHOP_DRAFT_RETENTION_HOURS,
    current_time: datetime | None = None,
) -> int:
    """删除长期未发布的车间问题草稿及其临时图片。"""
    return maintenance_service.cleanup_stale_workshop_drafts(
        _maintenance_dependencies(), retention_hours, current_time,
    )


def merge_confirmed_master_data(limit: int = 5) -> dict[str, int]:
    """定期合并管理员已确认的主数据批次，并记录系统审计。"""
    return maintenance_service.merge_confirmed_master_data(_maintenance_dependencies(), limit)


def run_storage_maintenance(
    output_limit: int = OUTPUT_RETENTION_COUNT,
    trash_retention_days: int = TRASH_RETENTION_DAYS,
    current_time: datetime | None = None,
) -> dict[str, int]:
    """执行一次输出保留和回收站清理维护。"""
    deps = _maintenance_dependencies()
    return maintenance_service.run_storage_maintenance(
        deps, output_limit, trash_retention_days, current_time,
    )


# 统一投影层：所有“公开模型”只输出浏览器可看字段并隐藏服务端路径，入口保留旧名称供 HTTP 层复用。
user_public = presenters.user_public
daily_person_public = presenters.daily_person_public
daily_attendance_public = presenters.daily_attendance_public
daily_production_shift_public = presenters.daily_production_shift_public
daily_production_group_public = presenters.daily_production_group_public
daily_production_attendance_public = presenters.daily_production_attendance_public
daily_brief_public = presenters.daily_brief_public
production_plan_public = presenters.production_plan_public
daily_source_upload_public = presenters.daily_source_upload_public
notification_public = presenters.notification_public
announcement_public = presenters.announcement_public


def safe_name(value: str) -> str:
    """把浏览器文件名收敛为服务端可安全保存的单层名称。

    先同时按 Windows 与 URL 风格分隔符取 basename，再移除 Windows 禁止字符和控制字符；
    结果限制 180 字符，为后续 UUID 目录、临时后缀和压缩包名称留出路径长度空间。
    """
    name = Path(value.replace("\\", "/")).name.strip().strip(".")  # ``C:\\a`` 在 Linux 也按 Windows 路径剥离目录。
    name = "".join(char for char in name if char not in '<>:"/\\|?*' and ord(char) >= 32)
    return name[:180] or "未命名文件"


def library_scope(value: object) -> str:
    """校验共享文件的可见范围。

    只允许 ``team``/``private`` 两个稳定英文键；无效值直接拒绝，防止未登记范围写入库。
    """
    scope = str(value or "team").strip().lower()
    if scope not in {"team", "private"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件可见范围无效")
    return scope


def library_category_catalog() -> list[dict[str, str]]:
    """从 core 分类注册表生成 Web 可用分类，新增业务模块无需重复维护。"""
    keys = [*core_library.CATEGORIES, core_library.UNKNOWN]
    return [{"key": key, "title": core_library.CATEGORY_TITLES.get(key, key)} for key in keys]


def library_category(value: object) -> str:
    """校验分类键，避免客户端提交未注册分类污染索引。

    合法集合来自 core 分类注册表；空值回退到“未知”而不是拒绝，便于旧文件补录。
    """
    category = str(value or core_library.UNKNOWN).strip()
    valid = {item["key"] for item in library_category_catalog()}
    if category not in valid:
        raise ApiError(HTTPStatus.BAD_REQUEST, "数据库文件分类无效")
    return category


def classify_library_file(path: Path, log=None) -> dict[str, object]:
    """调用桌面端同一分类器，并整理为可持久化的 Web 元数据。

    分类属于辅助信息，失败时文件仍可进入数据库并标记为未知，管理员之后可以手动维护。
    所有列表、分值和工作表名称都在这里限制类型与长度，不能把 Core 的任意对象直接写入
    JSON 或返回给浏览器。
    """
    try:
        info = core_library.classify(str(path), log=log)
    except Exception as exc:  # 分类失败不应让已写入的文件变成孤儿文件
        if log:
            log(f"分类暂未完成：{type(exc).__name__}")
        info = {
            "category": core_library.UNKNOWN,
            "confidence": 0,
            "categories": [],
            "signals": ["自动识别失败"],
            "sheet": "",
            "sheets": {},
        }
    category = library_category(info.get("category", core_library.UNKNOWN))
    categories = [
        value for value in info.get("categories", [])
        if isinstance(value, str) and value in {item["key"] for item in library_category_catalog()}
    ]
    if not categories:
        categories = [category]
    signals = info.get("signals", [])
    if not isinstance(signals, list):
        signals = []
    sheets = info.get("sheets", {})
    if not isinstance(sheets, dict):
        sheets = {}
    return {
        "category": category,
        "categories": list(dict.fromkeys(categories)),  # 保持识别优先顺序并去重。
        "confidence": max(0, min(100, int(info.get("confidence", 0) or 0))),
        "signals": [str(value) for value in signals[:30]],
        "sheet": str(info.get("sheet", "") or "")[:200],
        "category_sheets": {str(key): str(value) for key, value in sheets.items() if isinstance(key, str)},
    }


def _json_list(value: object, fallback: list[object] | None = None) -> list[object]:
    """兼容旧调用名，转由 ``web_backend.serializers`` 处理。"""
    return _json_list_from_backend(value, fallback)


def _json_value(value: object, fallback: object = None) -> object:
    """兼容旧调用名，转由 ``web_backend.serializers`` 处理。"""
    return _json_value_from_backend(value, fallback)


def _json_object(value: object, fallback: dict[str, object] | None = None) -> dict[str, object]:
    """兼容旧调用名，转由 ``web_backend.serializers`` 处理。"""
    return _json_object_from_backend(value, fallback)


# 共享文件投影同样复用统一投影层；路径转换在 resolve_library_path 中完成。
library_file_public = presenters.library_file_public


def resolve_library_path(row: sqlite3.Row) -> Path:
    """把数据库路径限制在所属账号的共享文件目录内。

    使用 ``resolve()`` 后再做父目录判断，既防 ``..`` 穿越也防符号链接逃逸；路径必须解析
    为账号目录的真实子路径，否则按无效路径拒绝。
    """
    target = Path(row["path"]).resolve()
    root = (DATA_ROOT / "users" / str(row["owner_id"]) / "library").resolve()
    if root not in target.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "数据库文件路径无效")
    return target


def workshop_issue_date(value: object) -> str:
    """校验问题日期并拒绝未来日期。"""
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "问题日期无效") from exc
    if parsed > business_today():
        raise ApiError(HTTPStatus.BAD_REQUEST, "问题日期不能晚于今天")
    return parsed.isoformat()


def workshop_issue_export_range(query: dict[str, list[str]]) -> tuple[str, str]:
    """读取现场问题导出日期范围，并兼容旧版单日 date 参数。"""
    default_date = business_today().isoformat()
    legacy_date = query.get("date", [default_date])[0]
    start_date = workshop_issue_date(query.get("start_date", [legacy_date])[0])
    end_date = workshop_issue_date(query.get("end_date", [start_date])[0])
    parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if parsed_start > parsed_end:
        raise ApiError(HTTPStatus.BAD_REQUEST, "开始日期不能晚于结束日期")
    if (parsed_end - parsed_start).days + 1 > MAX_WORKSHOP_EXPORT_DAYS:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"单次最多导出 {MAX_WORKSHOP_EXPORT_DAYS} 天的问题报表")
    return start_date, end_date


def daily_report_date(value: object) -> str:
    """校验日清报告日期，按业务时区拒绝未来日期。"""
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清报告日期无效") from exc
    if parsed > business_today():
        raise ApiError(HTTPStatus.BAD_REQUEST, "日清报告日期不能晚于今天")
    return parsed.isoformat()


def _daily_report_dependencies() -> daily_report_service.DailyReportDependencies:
    """组装日清快照查询依赖，避免服务模块反向导入启动入口。"""
    return daily_report_service.DailyReportDependencies(
        db_lock=DB_LOCK,
        db=db,
        business_day_bounds=business_day_bounds,
        workshop_issue_select=workshop_service.workshop_issue_select,
        attendance_rows=daily_management_service.attendance_rows,
        production_attendance_rows=daily_management_service.production_attendance_rows,
        daily_attendance_public=daily_attendance_public,
        daily_production_attendance_public=daily_production_attendance_public,
        daily_brief_public=daily_brief_public,
        production_plan_public=production_plan_public,
        daily_source_upload_public=daily_source_upload_public,
        workshop_issue_public=workshop_issue_public,
        build_snapshot=daily_report_core.build_snapshot,
        now_iso=now_iso,
    )


def build_daily_report_snapshot(report_date: str, user: sqlite3.Row) -> dict[str, object]:
    """查询全账号到料与现场问题，生成管理层日清快照。"""
    return daily_report_service.build_daily_report_snapshot(
        report_date, user, _daily_report_dependencies(),
    )


def workshop_issue_dir(user_id: int, issue_id: str) -> Path:
    """返回指定账号和现场问题的隔离图片目录。"""
    return DATA_ROOT / "users" / str(user_id) / "workshop-issues" / issue_id


def resolve_workshop_image_path(row: sqlite3.Row) -> Path:
    """把现场图片限制在问题上传者的隔离目录内。

    数据库中的路径可能来自旧版本或备份恢复，使用前必须重新解析父目录；只比较字符串
    前缀会把 ``user/1-old`` 错判为 ``user/1`` 的子目录。
    """
    target = Path(row["path"]).resolve()
    root = workshop_issue_dir(int(row["user_id"]), str(row["issue_id"])).resolve()
    if root not in target.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "现场图片路径无效")
    return target


# 现场问题角色矩阵：成员仅维护自己的草稿，班组长可编辑/闭环/删除自己发布的，管理员可维护全部。
workshop_issue_can_edit = presenters.workshop_issue_can_edit
workshop_issue_can_resolve = presenters.workshop_issue_can_resolve
workshop_issue_can_delete = presenters.workshop_issue_can_delete
workshop_issue_public = presenters.workshop_issue_public


# update_job 可更新的任务列白名单：键只来自服务端内部状态机，任何新列必须先在此登记，
# 防止未来调用方传入未清洗的键参与列名拼接（值仍使用参数化 SQL，不参与拼接）。
_JOB_UPDATE_COLUMNS = frozenset({
    "status", "progress", "result", "error", "files", "logs",
    "cancelled", "assignee_id", "payload",
})


def update_job(job_id: str, **values: object) -> None:
    """更新 Web 任务的一组受控字段，并统一刷新版本时间。

    调用方传入的键必须命中 ``_JOB_UPDATE_COLUMNS`` 白名单，不接受 HTTP 字段；值仍使用
    参数化 SQL。一次语句更新全部字段，避免进度、状态和错误信息出现可观察的中间组合。
    """
    if not values:
        return
    unknown = set(values) - _JOB_UPDATE_COLUMNS
    if unknown:
        raise ValueError("不允许更新这些任务字段：%s" % "、".join(sorted(unknown)))
    values["updated_at"] = now_iso()
    columns = ", ".join(f"{key} = ?" for key in values)  # 键已通过白名单校验，业务值不参与 SQL 拼接。
    with DB_LOCK, db() as connection:
        connection.execute(
            f"UPDATE web_jobs SET {columns} WHERE id = ?",
            (*values.values(), job_id),
        )


def append_job_log(job_id: str, message: str) -> None:
    """追加任务日志并仅保留最近 500 条，避免任务记录无限增长。"""
    with DB_LOCK, db() as connection:
        row = connection.execute("SELECT logs FROM web_jobs WHERE id = ?", (job_id,)).fetchone()
        logs = _json_list(row["logs"] if row else "[]")
        logs.append(str(message))
        connection.execute(
            "UPDATE web_jobs SET logs = ?, updated_at = ? WHERE id = ?",
            (json.dumps(logs[-500:], ensure_ascii=False), now_iso(), job_id),  # 从尾部截取以保留最接近失败现场的日志。
        )


def _owned_upload_path(path_value: str | Path, user_id: int) -> Path:
    """保留原调用名，校验路径属于当前账号上传目录。"""
    return upload_service.owned_upload_path(
        _upload_dependencies(), path_value, user_id,
    )


def resolve_uploads(value: object, user_id: int) -> object:
    """保留原调用名，递归解析当前账号的上传句柄。"""
    return upload_service.resolve_uploads(
        _upload_dependencies(), value, user_id,
    )


def run_bridge(job_id: str, user_id: int, action: str, payload: dict[str, object]) -> object:
    """通过独立 Core 子进程执行任务，并转发结构化日志与进度。

    具体的环境隔离、标准流消费和进程清理位于任务桥接模块。本包装保留历史公开名称，
    也确保测试在动态替换数据根后能够取得一份新的依赖快照。
    """
    return task_bridge.run_bridge(
        job_id, user_id, action, payload, _bridge_dependencies(),
    )


def execute_action(job_id: str, user_id: int, action: str, payload: dict[str, object]) -> object:
    """执行 Web 特殊两阶段动作，普通动作直接进入统一 Core 桥接层。

    两阶段动作的只读分析、计划返回和最终执行都由任务动作模块实现；本入口只负责把任务
    推进统一桥接。
    """
    return task_actions.execute_action(job_id, user_id, action, payload, run_bridge)


def collect_result_files(value: object) -> list[dict[str, object]]:
    """发现任务结果文件；目录遍历达到两百项后立即停止。"""
    return task_results.collect_result_files(value)


def public_result(value: object) -> object:
    """隐藏结果中的服务端绝对路径，保留业务数据和文件名。"""
    return task_results.public_result(value)


def job_public(row: sqlite3.Row) -> dict[str, object]:
    """把任务、历史版本和统一业务展示模型投影为浏览器公开结构。"""
    return task_results.job_public(row, _result_dependencies())


def _bridge_command() -> list[str]:
    """保留部署工具使用的桥接命令入口。"""
    return task_bridge.bridge_command()


def run_web_job(job_id: str, user_id: int, action: str, payload: dict[str, object]) -> None:
    """运行后台任务状态机并持久化结果、版本、取消和失败状态。"""
    task_runner.run_web_job(
        job_id, user_id, action, payload, _runner_dependencies(),
    )


def _owned_result_path(path_value: object, user_id: int, job_id: str) -> Path:
    """校验结果路径属于当前账号上传区或当前任务输出区。"""
    return task_results.owned_result_path(
        path_value, user_id, job_id, _result_dependencies(),
    )
def _handler_bindings() -> HandlerBindings:
    """组装 HTTP 处理器依赖，领域工厂在每次请求时读取当前运行路径。

    测试会动态替换数据根和静态目录，因此这里只固定工厂函数，不提前构造包含路径的
    依赖对象。三个轻量包装也保留对入口全局函数的运行期查找能力。
    """
    return HandlerBindings(
        version=VERSION,
        max_json_body_bytes=MAX_JSON_BODY_BYTES,
        now_iso=lambda: now_iso(),
        user_public=lambda row: user_public(row),
        resolve_uploads=lambda value, user_id: resolve_uploads(value, user_id),
        request_context_dependencies=_request_context_dependencies,
        static_file_dependencies=_static_file_dependencies,
        dashboard_dependencies=_dashboard_dependencies,
        upload_dependencies=_upload_dependencies,
        library_dependencies=_library_dependencies,
        workshop_dependencies=_workshop_dependencies,
        job_dependencies=_job_dependencies,
        daily_management_dependencies=_daily_management_dependencies,
        auth_dependencies=_auth_dependencies,
        admin_account_dependencies=_admin_account_dependencies,
        backup_dependencies=_backup_dependencies,
        master_data_dependencies=_master_data_dependencies,
        admin_data_dependencies=_admin_data_dependencies,
        trash_dependencies=_trash_dependencies,
        report_dependencies=_report_dependencies,
        notification_dependencies=_notification_dependencies,
    )


class Handler(ApiHandler):
    """装配当前应用依赖的 HTTP Handler；协议实现位于独立 HTTP 模块。

    类属性只在导入时求值一次，运行期动态替换依赖由各工厂函数负责。
    """

    bindings = _handler_bindings()
# 保留历史导入名；实际服务生命周期实现位于 ``web_backend.server_runtime``。
ThreadingHTTPServer = server_runtime.ThreadingHTTPServer
MaintenanceHTTPServer = server_runtime.MaintenanceHTTPServer


def _server_runtime_dependencies() -> server_runtime.ServerRuntimeDependencies:
    """组装 HTTP 服务生命周期与周期维护依赖。

    运行时只接收回调，不反向导入本入口，从而可在测试中替换端口、维护任务和初始化过程。
    """
    return server_runtime.ServerRuntimeDependencies(
        host=HOST,
        port=PORT,
        handler_class=Handler,
        maintenance_interval=MAINTENANCE_INTERVAL_SECONDS,
        output_retention_count=OUTPUT_RETENTION_COUNT,
        trash_retention_days=TRASH_RETENTION_DAYS,
        init_db=init_db,
        run_storage_maintenance=run_storage_maintenance,
        auto_backup_if_due=auto_backup_if_due,
        auto_weekly_report_if_due=auto_weekly_report_if_due,
        auto_monthly_report_if_due=auto_monthly_report_if_due,
    )


def _reset_admin_password_from_env() -> None:
    """从环境变量读取新密码并重置内置 admin 账号密码。

    密码只允许通过 ``FYT_NEW_ADMIN_PASSWORD``/``FYT_ADMIN_PASSWORD`` 环境变量传入，
    不进入命令行参数、日志或配置文件。本入口供冻结后的 Windows 部署包在停止服务后
    调用（``web_server.exe --reset-admin-password``），也兼容源码部署的同一用法。
    """
    password = os.environ.get("FYT_NEW_ADMIN_PASSWORD") or os.environ.get("FYT_ADMIN_PASSWORD")
    if not password:
        print("未提供新密码：请通过 FYT_NEW_ADMIN_PASSWORD 环境变量传入。", file=sys.stderr)
        raise SystemExit(2)
    policy_error = password_policy_error(password)
    if policy_error:
        print(f"密码不符合要求：{policy_error}", file=sys.stderr)
        raise SystemExit(2)
    salt, digest = hash_password(password)
    init_db()
    connection = db()
    try:
        # 参数绑定与 Windows PowerShell 重置脚本保持同一 SQL 形状，避免双份实现漂移。
        connection.execute(
            "UPDATE users SET salt = ?, password_hash = ? WHERE username = ?",
            (salt, digest, "admin"),
        )
        connection.commit()
    finally:
        connection.close()
    print("[完成] 管理员密码已更新。")


def main() -> None:
    """按命令行参数选择密码重置入口或正常 Web 服务启动。"""
    if "--reset-admin-password" in sys.argv:
        _reset_admin_password_from_env()
        return
    server_runtime.run_server(_server_runtime_dependencies())


if __name__ == "__main__":
    main()
