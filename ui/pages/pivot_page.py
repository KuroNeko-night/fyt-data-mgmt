# -*- coding: utf-8 -*-
"""透视表制作页。采购数据表 -> 分组汇总 + 原生数据透视表 + 可信度报告。"""
import os

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import pivot_core


class PivotPage(BasePage):
    def __init__(self, main):
        super(PivotPage, self).__init__(
            main, "透视表制作",
            "自动定位表头、清洗数据、统一单位/规格，按编码/名称/规格/单位分组汇总，"
            "生成 Excel 原生数据透视表并评估可信度。")

    def build_body(self, layout):
        self.zone = FileZone(1, "采购数据表",
                             "包装方案/采购量核算表、组托辅材等，可多选/拖拽。",
                             multi=True, library_cats=["pivot_src"],
                             detail="程序会自动跳过“客供/已生成透视表”类工作表，只处理数据表。")
        self.zone.changed.connect(self._refresh)
        layout.addWidget(self.zone)

        self.panel = RunPanel("生成透视表")
        self.panel.run_btn.clicked.connect(self._run_auto)
        self.btn_review = self.panel.add_action("人工复核后生成…", self._run_review)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        self.btn_report = self.panel.add_action("查看可信度报告", self._open_report)
        layout.addWidget(self.panel)
        self._out_dir = ""
        self._report = ""
        self._refresh()

    def add_source_files(self, paths):
        self.zone.add_paths(paths)
        self._refresh()

    def refresh_view(self):
        self.zone.refresh_lib_count()

    def _refresh(self, *_):
        ok = bool(self.zone.get())
        self.panel.run_btn.setEnabled(ok)
        self.btn_review.setEnabled(ok)
        self.panel.set_status("ready" if ok else "idle",
                              "准备就绪（%d 个文件）" % len(self.zone.get()) if ok
                              else "请添加采购数据表")

    def _run_auto(self):
        self.panel.clear_log()
        files = self.zone.get()
        self.launch(lambda log: pivot_core.run(files, log=log), self.panel, self._done)

    def _run_review(self):
        """先分析，弹出复核对话框收集选择，再应用。"""
        from ..dialogs.pivot_review import PivotReviewDialog
        files = self.zone.get()
        self.panel.clear_log()
        self.panel.log_line("正在分析文件以供复核…")
        try:
            plan = pivot_core.analyze(files)
        except Exception as e:
            self.warn("分析失败", str(e))
            return
        dlg = PivotReviewDialog(plan, self)
        if not dlg.exec_():
            self.panel.log_line("已取消复核。")
            return
        choices = dlg.choices()
        self.launch(lambda log: pivot_core.run(files, choices=choices, log=log),
                    self.panel, self._done)

    def _done(self, res):
        self._out_dir = os.path.dirname(res.get("out", ""))
        self._report = res.get("report", "")
        level = res.get("level", "?")
        score = res.get("score", 0)
        kind = "ok" if level == "可信" else ("warn" if level == "需复核" else "err")
        self.panel.set_status(kind, "完成 · 分组 %d · 合计 %s · 可信度【%s】%d/100"
                              % (res.get("groups", 0), pivot_core._fmt_num(res.get("total", 0)),
                                 level, score))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.btn_report.setEnabled(bool(self._report))
        self.notify_done(self._out_dir, "生成完成",
                  "分组：%d 项\n合计：%s\n可信度：【%s】 %d/100\n输出：%s"
                  % (res.get("groups", 0), pivot_core._fmt_num(res.get("total", 0)),
                     level, score, res.get("out", "")))

    def _open(self):
        self.open_folder(self._out_dir)

    def _open_report(self):
        try:
            if self._report and os.path.exists(self._report):
                os.startfile(self._report)
        except Exception:
            pass
