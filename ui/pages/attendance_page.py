# -*- coding: utf-8 -*-
"""考勤数据填报页。系统数据(来源) + 待填考勤表(目标) -> 填好的表。"""
import os

from PySide2.QtWidgets import QHBoxLayout, QPushButton

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import attendance_core, common_core


class AttendancePage(BasePage):
    def __init__(self, main):
        self.opts = common_core.Options() if hasattr(common_core, "Options") else None
        super(AttendancePage, self).__init__(
            main, "考勤数据填报",
            "读取打卡系统数据，自动填入待填考勤表并计算工时。支持多文件、拖拽。")

    def build_body(self, layout):
        self.z_src = FileZone(1, "系统数据（打卡来源）",
                              "考勤机/系统导出的原始打卡表，可多选。",
                              multi=True, library_cats=["att_source"],
                              detail="这些是数据来源：程序从中读取每人每天的打卡时间。")
        self.z_tgt = FileZone(2, "待填考勤表（目标）",
                              "需要被填写的考勤表模板，可多选。",
                              multi=True, library_cats=["att_target"],
                              detail="程序会把打卡与工时写入这些表，另存为“_已填写”。")
        self.z_src.changed.connect(self._refresh)
        self.z_tgt.changed.connect(self._refresh)
        layout.addWidget(self.z_src)
        layout.addWidget(self.z_tgt)

        self.panel = RunPanel("开始填报")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_link = self.panel.add_action('把结果送去"工时对账"', self._send)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        layout.addWidget(self.panel)
        self._out_files = []
        self._out_dir = ""
        self._refresh()

    def refresh_view(self):
        self.z_src.refresh_lib_count()
        self.z_tgt.refresh_lib_count()

    def _refresh(self, *_):
        ok = bool(self.z_src.get()) and bool(self.z_tgt.get())
        self.panel.run_btn.setEnabled(ok)
        if ok:
            self.panel.set_status("ready", "准备就绪（来源 %d / 目标 %d）"
                                  % (len(self.z_src.get()), len(self.z_tgt.get())))
        else:
            need = []
            if not self.z_src.get():
                need.append("系统数据")
            if not self.z_tgt.get():
                need.append("待填表")
            self.panel.set_status("idle", "还需选择：" + "、".join(need))

    def _run(self):
        # 生成前在右侧面板确认计算口径（不再弹窗打断）
        from ..panel_widgets.attendance_form import AttendanceFormWidget
        form = AttendanceFormWidget(self.opts)
        form.accepted.connect(self._do_run)
        form.cancelled.connect(self.main.close_panel)
        self.main.open_panel(form, "确认口径 · 考勤填报")

    def _do_run(self, opts):
        self.main.close_panel()
        self.panel.clear_log()
        targets = self.z_tgt.get()
        sources = self.z_src.get()
        self.launch(lambda log: attendance_core.run(targets, sources, opts=opts, log=log),
                    self.panel, self._done)

    def _done(self, res):
        self._out_files = res.get("out_files", [])
        self._out_dir = res.get("out_dir", "")
        self.panel.set_status("ok", "完成！生成 %d 个文件" % len(self._out_files))
        self.btn_link.setEnabled(bool(self._out_files))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.notify_done(self._out_dir, "填报完成",
                  "已生成 %d 个已填写考勤表。\n输出：%s" % (len(self._out_files), self._out_dir))

    def _send(self):
        if self._out_files:
            self.main.send_to_reconcile(self._out_files)
            self.info("已送达", '结果已放入"工时对账"的数据来源，请再补充①待对表与③对账单。')

    def _open(self):
        self.open_folder(self._out_dir)
