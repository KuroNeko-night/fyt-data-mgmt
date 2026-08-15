# -*- coding: utf-8 -*-
"""
公共任务报表中心
================
接收桌面或 Web 服务已经完成权限过滤的统一任务记录，按业务模块和状态汇总任务数、
完成数、失败/中断数与成功率，并生成“汇总 + 明细”Excel 报告。核心层只负责报表
投影，不直接读取用户数据库，避免绕过服务端的数据归属和管理员权限检查。

状态 ``ok``/``completed`` 计为完成，``failed``/``interrupted`` 计为失败；等待、运行中
和取消只进入任务总数，不计成功或失败。模块标题和状态标题通过显式字典翻译，未知值
保留原文本，便于新增功能在映射尚未更新时仍可导出。

时间范围起点辅助函数支持 7 天、30 天、当月以及历史兼容别名；实际筛选应由持有任务
数据的调用层完成，``build_report`` 假定传入列表已经符合用户选择范围。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from . import common_core

FEATURE_TITLES = {
    # 报表中的客户可读模块名；未知 feature 会回退原值而不是丢弃记录。
    "attendance": "考勤填报", "reconcile": "工时对账", "arrival": "到料明细",
    "pivot": "销售透视", "purchase": "采购对账", "shipping_review": "发运评审对比",
    "delivery": "送货计划",
    "supplier_batch": "供应商批次表", "purchase_plan": "采购计划导入",
    "invoice": "发票统计", "rename": "批量重命名", "text": "文本工具",
    "pdf": "PDF 工具", "excel": "Excel 工具", "compare": "表格比对",
    "currency": "金额大写", "library": "数据库", "mappings": "字段映射",
    "templates": "模板中心", "settings": "设置",
}

STATUS_TITLES = {
    # 同时兼容桌面历史的 ok 和 Web 任务的 completed 状态。
    "ok": "完成", "running": "处理中", "queued": "等待", "failed": "失败",
    "interrupted": "中断", "cancelled": "取消", "completed": "完成",
}
DONE_STATUSES = {"ok", "completed"}
FAILED_STATUSES = {"failed", "interrupted"}


def _text(value) -> str:
    """把任务字段转换为去首尾空白的展示文本，空值统一为空串。"""
    return "" if value is None else str(value).strip()


def range_start(range_key: str) -> datetime:
    """把预设范围键转换为本地时间的查询起点。

    ``7d`` 与历史别名 ``week`` 都表示向前七天；``month`` 与 ``monthly`` 都表示本月
    首日零点；``30d`` 表示滚动三十天。未知键回退到 2000-01-01，作为“全部历史”
    的兼容下界。函数不负责时区转换，调用层应与任务记录的时间口径保持一致。
    """
    now = datetime.now()
    if range_key == "7d":
        return now - timedelta(days=7)
    if range_key == "30d":
        return now - timedelta(days=30)
    if range_key == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if range_key == "week":
        return now - timedelta(days=7)
    if range_key == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return datetime(2000, 1, 1)


def _parse_time(text: str) -> datetime | None:
    """尽力解析 ISO 时间文本为无时区 datetime，失败返回 ``None``。

    结尾 ``Z`` 先换成 UTC 偏移形式，再按第一个正偏移符号截去时区部分，保持现有
    本地筛选协议。该辅助函数不应替代需要严格时区换算的服务端业务日期逻辑。
    """
    try:
        parsed = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        # 统一剥离时区并返回 naive 时间；兼容负偏移（如 -05:00），避免与 naive 时间比较时抛 TypeError。
        parsed = parsed.replace(tzinfo=None)
    return parsed


def build_report(items: list[dict[str, object]], out_path: str, range_label: str) -> int:
    """把已筛选任务列表汇总为两页 Excel，并返回写入的明细行数。

    每条任务提取开始时间、模块、标题、状态和结果文件数；按原始 feature 统计总量、
    完成和失败。汇总页展示总体指标及模块分布，明细页逐条保留客户可读名称。函数
    不创建父目录，也不执行权限或日期筛选，调用方必须先完成这些工作。
    """
    from collections import Counter
    feature_stats: dict[str, Counter] = {}
    details: list[dict[str, object]] = []
    for item in items:
        feature = _text(item.get("feature")) or "其他"
        status = _text(item.get("status"))
        stats = feature_stats.setdefault(feature, Counter())
        # Counter 缺失键自动为零，适合逐状态累加并保持输出字段简洁。
        stats["total"] += 1
        if status in DONE_STATUSES:
            stats["done"] += 1
        elif status in FAILED_STATUSES:
            stats["failed"] += 1
        details.append({
            "started_at": _text(item.get("started_at")),
            "feature": FEATURE_TITLES.get(feature, feature),
            "title": _text(item.get("title")),
            "status": STATUS_TITLES.get(status, status or "未知"),
            "files": int(item.get("files") or 0),
        })
    total = len(details)
    # 未完成、取消和运行中只进入 total，因此成功率分母反映范围内全部任务。
    done = sum(stats["done"] for stats in feature_stats.values())
    failed = sum(stats["failed"] for stats in feature_stats.values())

    workbook = openpyxl.Workbook()
    # 删除默认空页，确保报告只有明确命名的“汇总”和“明细”。
    workbook.remove(workbook.active)
    # 两个页签复用样式对象，减少重复样式记录并保持视觉一致。
    thin = Side(style="thin", color="9AA5B1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="EAF1FF")
    title_font = Font(name="宋体", size=14, bold=True)
    head_font = Font(name="宋体", size=10, bold=True)
    cell_font = Font(name="宋体", size=10)

    def style_header(worksheet, row_index: int, count: int) -> None:
        """为指定行前若干列统一应用报表表头样式。"""
        for column in range(1, count + 1):
            cell = worksheet.cell(row_index, column)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

    # 汇总页顶部给管理者总体指标，下部再按模块拆分，打开文件即可先看结论。
    summary = workbook.create_sheet("汇总")
    summary.column_dimensions["A"].width = 22
    summary.column_dimensions["B"].width = 14
    summary.column_dimensions["C"].width = 14
    summary.column_dimensions["D"].width = 14
    summary.cell(1, 1, "峰运通业务报表").font = title_font
    summary.cell(2, 1, "统计范围：%s" % range_label).font = cell_font
    summary.cell(3, 1, "生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M")).font = cell_font
    summary.cell(5, 1, "任务总数").font = head_font
    summary.cell(5, 2, total)
    summary.cell(6, 1, "已完成").font = head_font
    summary.cell(6, 2, done)
    summary.cell(7, 1, "失败/中断").font = head_font
    summary.cell(7, 2, failed)
    summary.cell(8, 1, "成功率").font = head_font
    # total 为零时显示 0%，避免空范围触发除零错误。
    summary.cell(8, 2, "%.1f%%" % (done / total * 100 if total else 0))
    for row in range(5, 9):
        for column in (1, 2):
            summary.cell(row, column).border = border
    summary.cell(10, 1, "模块分布").font = head_font
    header_row = 11
    for column, name in enumerate(("模块", "任务数", "完成", "失败", "成功率"), start=1):
        summary.cell(header_row, column, name)
    style_header(summary, header_row, 5)
    row_index = header_row + 1
    for feature, stats in sorted(feature_stats.items()):
        # 按内部 feature 排序可保持重复导出顺序稳定，展示时再翻译为中文名称。
        feature_total = stats["total"]
        feature_done = stats["done"]
        feature_failed = stats["failed"]
        values = [
            FEATURE_TITLES.get(feature, feature), feature_total, feature_done,
            feature_failed, "%.1f%%" % (feature_done / feature_total * 100 if feature_total else 0),
        ]
        for column, value in enumerate(values, start=1):
            cell = summary.cell(row_index, column, value)
            cell.font = cell_font
            cell.border = border
        row_index += 1

    # 明细页不输出内部任务 ID、绝对路径等实现信息，只保留客户可理解字段。
    detail = workbook.create_sheet("明细")
    widths = {"A": 19, "B": 14, "C": 40, "D": 10, "E": 10}
    for column, width in widths.items():
        detail.column_dimensions[column].width = width
    for column, name in enumerate(("开始时间", "模块", "任务", "状态", "结果文件"), start=1):
        detail.cell(1, column, name)
    style_header(detail, 1, 5)
    for index, row in enumerate(details, start=2):
        values = [row["started_at"], row["feature"], row["title"], row["status"], row["files"]]
        for column, value in enumerate(values, start=1):
            cell = detail.cell(index, column, value)
            cell.font = cell_font
            cell.border = border
    workbook.save(out_path)
    return total


def unique_report_path(out_dir: str, range_label: str) -> str:
    """生成带范围标签和秒级时间戳的唯一报表路径。

    ``range_label`` 应由调用层提供客户可读且已校验的短文本；最终仍使用公共唯一路径
    规则避免同秒重复导出覆盖旧报告。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "业务报表_%s_%s.xlsx" % (range_label, stamp)
    return common_core.unique_path(os.path.join(out_dir, filename))
