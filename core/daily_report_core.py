# -*- coding: utf-8 -*-
"""日清报告业务入口。

稳定快照聚合与 Excel 写入已经拆分，避免单文件同时维护统计规则和近十张工作表格式。
公开入口 build_snapshot 与 run 保持不变，Web、Tauri 和测试继续复用同一 Core。
"""

from .daily_report_excel import run
from .daily_report_snapshot import build_snapshot


__all__ = ["build_snapshot", "run"]
