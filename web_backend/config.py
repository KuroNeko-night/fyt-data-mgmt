"""Web 服务端运行配置、路径和接口能力目录。"""

from __future__ import annotations

import mimetypes
import os
import sys
from datetime import timedelta, timezone
from pathlib import Path

from core import workshop_issue_core
from core.version import VERSION


# 源码运行时以仓库根目录为基准；冻结后会在下面改为可执行文件所在部署目录。
ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web-app"
STATIC_ROOT = WEB_ROOT / "dist"
if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent  # PyInstaller 下 __file__ 位于临时解包目录，不能用于定位持久资源。
    if (exe_dir.parent / "web-app" / "dist").is_dir():
        ROOT = exe_dir.parent  # Windows 整合包把服务端放在“服务端”子目录，静态资源位于其父目录。
    else:
        ROOT = exe_dir  # 兼容可执行文件与 web-app 同级的精简部署结构。
    WEB_ROOT = ROOT / "web-app"
    STATIC_ROOT = WEB_ROOT / "dist"

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

DATA_ROOT = Path(os.environ.get("FYT_WEB_DATA", ROOT / "web-data"))  # 环境变量允许 Linux 把代码与可写数据彻底分离。
DB_PATH = DATA_ROOT / "accounts.sqlite3"
HOST = os.environ.get("FYT_WEB_HOST", "0.0.0.0")  # 默认监听局域网地址；反向代理部署可改成 127.0.0.1。
PORT = int(os.environ.get("FYT_WEB_PORT", "8787"))
SESSION_DAYS = 7
SESSION_TOUCH_INTERVAL_SECONDS = max(10, int(os.environ.get("FYT_SESSION_TOUCH_INTERVAL_SECONDS", "60")))  # 限制会话活跃时间的写库频率。
PBKDF2_ROUNDS = 240_000
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_MASTER_DATA_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_JSON_BODY_BYTES = 4 * 1024 * 1024
MAX_WORKSHOP_IMAGE_BYTES = 15 * 1024 * 1024
MAX_WORKSHOP_IMAGES = 8
MAX_WORKSHOP_EXPORT_DAYS = 366
WORKSHOP_DRAFT_RETENTION_HOURS = 24
LIBRARY_USER_QUOTA_BYTES = max(
    MAX_UPLOAD_BYTES,
    int(os.environ.get("FYT_LIBRARY_USER_QUOTA_BYTES", str(2 * 1024 * 1024 * 1024))),
)  # 配额不得小于单文件上限，否则一个合法上传也可能永远无法完成。
LOGIN_FAILURE_LIMIT = max(3, int(os.environ.get("FYT_LOGIN_FAILURE_LIMIT", "5")))
LOGIN_WINDOW_SECONDS = max(60, int(os.environ.get("FYT_LOGIN_WINDOW_SECONDS", str(15 * 60))))
LOGIN_LOCK_SECONDS = max(60, int(os.environ.get("FYT_LOGIN_LOCK_SECONDS", str(15 * 60))))
OUTPUT_RETENTION_COUNT = max(1, int(os.environ.get("FYT_OUTPUT_RETENTION_COUNT", "20")))
TRASH_RETENTION_DAYS = max(1, int(os.environ.get("FYT_TRASH_RETENTION_DAYS", "30")))
BUSINESS_TZ = timezone(timedelta(hours=float(os.environ.get("FYT_BUSINESS_TZ_OFFSET", "8"))))  # 日清统计按业务时区分日，而不是按服务器 UTC 日期。
MAINTENANCE_INTERVAL_SECONDS = max(
    60, int(os.environ.get("FYT_MAINTENANCE_INTERVAL_SECONDS", str(6 * 60 * 60)))
)
BACKUP_ROOT = DATA_ROOT / "backups"
TRASH_ROOT = DATA_ROOT / "trash"
AUTO_BACKUP_KEEP = max(1, int(os.environ.get("FYT_AUTO_BACKUP_KEEP", "7")))
NOTIFY_WEBHOOK_URL = os.environ.get("FYT_NOTIFY_WEBHOOK_URL", "").strip()

ROLE_LABELS = {
    "admin": "系统管理员",
    "team_leader": "班组长",
    "user": "业务成员",
}
ROLE_CHOICES = frozenset(ROLE_LABELS)
LIBRARY_ROLES = frozenset({"admin", "team_leader"})

DAILY_PERSON_TYPES = {"participant"}
DAILY_BRIEF_CATEGORIES = {"escalation", "notice", "meeting_todo", "past_todo", "process"}
DAILY_BRIEF_STATUSES = {"open", "in_progress", "done", "cancelled"}
WORKSHOP_ISSUE_CATEGORIES = set(workshop_issue_core.WORKSHOP_ISSUE_CATEGORY_ORDER)
WORKSHOP_ISSUE_SEVERITIES = {"normal", "important", "critical"}
WORKSHOP_ISSUE_TEMPLATE_FIELDS = {
    field: ("TEXT NOT NULL DEFAULT ''", limit, label)
    for field, (limit, label) in workshop_issue_core.WORKSHOP_ISSUE_TEMPLATE_FIELDS.items()
}  # Core 只维护业务字段；Web 在此补充 SQLite 列定义，避免两处重复维护名称和长度。

WEB_ACTIONS = {
    "attendance.run", "reconcile.run", "pivot.run", "purchase.run", "shipping_review.run",
    "delivery.run", "supplier_batch.run", "purchase_plan.run", "purchase_plan.diff", "rename.apply", "pdf.run",
    "excel.run", "currency.convert", "text.transform", "invoice_match.run", "attendance_archive.run",
    "reconcile_statement.scan", "reconcile_statement.build", "web.arrival", "web.invoice", "web.compare",
}
REVIEW_ACTIONS = {
    "web.reconcile.review": "reconcile.run",
    "web.pivot.review": "pivot.run",
    "web.invoice.review": "web.invoice",
    "web.compare.review": "web.compare",
    "web.supplier_batch.review": "supplier_batch.run",
}
WEB_ACTIONS.update(REVIEW_ACTIONS)  # 两阶段复核动作本身也必须通过任务创建白名单。

FEATURES = [
    {"key": "attendance", "title": "考勤填报", "group": "人事", "description": "上传打卡记录，自动生成考勤填报表"},
    {"key": "attendance_archive", "title": "考勤月度归档", "group": "人事", "description": "上传考勤填报表，汇总月度出勤统计"},
    {"key": "reconcile", "title": "工时对账", "group": "人事", "description": "上传工时表，自动核对多方差异并汇总"},
    {"key": "arrival", "title": "到料明细", "group": "业务", "description": "上传送货计划，自动统计到料与未收料"},
    {"key": "pivot", "title": "销售透视", "group": "业务", "description": "上传采购明细，自动清洗汇总成透视表"},
    {"key": "purchase", "title": "采购对账", "group": "业务", "description": "上传双方采购表，逐行比对数量差异"},
    {"key": "shipping_review", "title": "发运评审对比", "group": "业务", "description": "过滤作废 BOX，汇总包装数量并与发运评审表逐项核对"},
    {"key": "delivery", "title": "送货计划", "group": "业务", "description": "上传物料与供应商清单，自动生成送货计划"},
    {"key": "supplier_batch", "title": "供应商批次表", "group": "业务", "description": "上传批次清单，按供应商生成采购明细"},
    {"key": "purchase_plan", "title": "采购计划导入", "group": "业务", "description": "上传辅料清单与模板，生成批次采购计划"},
    {"key": "purchase_diff", "title": "采购差异清单", "group": "业务", "description": "上传辅料清单，提取实收差异记录"},
    {"key": "reconcile_statement", "title": "对账单制作", "group": "业务", "description": "选择批次，自动生成供应商对账单"},
    {"key": "invoice", "title": "发票统计", "group": "财务", "description": "上传 PDF 发票，自动识别并按月汇总"},
    {"key": "invoice_match", "title": "票货匹配", "group": "财务", "description": "上传发票台账与采购明细，比对供应商票货"},
    {"key": "rename", "title": "批量重命名", "group": "工具", "description": "选择文件，按规则批量改名"},
    {"key": "text", "title": "文本工具", "group": "工具", "description": "粘贴文本，去重、排序或提取内容"},
    {"key": "pdf", "title": "PDF 工具", "group": "工具", "description": "选择 PDF，合并、拆分或提取页"},
    {"key": "excel", "title": "Excel 工具", "group": "工具", "description": "选择表格，合并、拆分或转换格式"},
    {"key": "compare", "title": "表格比对", "group": "工具", "description": "选择两张表，按关键列找差异"},
    {"key": "currency", "title": "金额大写", "group": "财务", "description": "输入金额，一键转中文大写"},
]


def role_label(role: object) -> str:
    """返回面向用户的账号角色名称，未知历史值安全降级为业务成员。

    权限判断始终使用稳定的英文角色键；中文名称只用于提示，避免显示文案调整影响鉴权。
    """
    return ROLE_LABELS.get(str(role or ""), "业务成员")


def feature_key_for_action(action: object) -> str:
    """从普通或 Web 复核动作中提取看板使用的业务功能键。

    桥接动作同时存在 ``arrival.run`` 与 ``web.arrival`` 两种命名方向，统计层只关心
    ``arrival``。此处集中归一化，避免工作台、任务列表和报表各自维护一套切分规则。
    """
    parts = str(action or "").split(".")  # web.arrival 与 arrival.run 都归一成 arrival。
    if parts[0] == "web" and len(parts) > 1:
        return parts[1]
    return parts[0]


def is_review_pending(row) -> bool:
    """判断两阶段任务是否已完成分析、正在等待人工确认。

    复核动作的 ``completed`` 表示分析阶段成功，而不是最终文件已经生成；普通动作同样
    状态则是真正完成。调用方必须同时检查动作白名单，不能只按状态推断。
    """
    return row["action"] in REVIEW_ACTIONS and row["status"] == "completed"
