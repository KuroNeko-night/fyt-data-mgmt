# -*- coding: utf-8 -*-
"""销售表透视页。采购数据表 -> 分组汇总 + 原生数据透视表 + 可信度报告。"""
import os

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import pivot_core


class PivotPage(BasePage):
    def __init__(self, main):
        super(PivotPage, self).__init__(
            main, "销售表透视",
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
        """先分析，在右侧面板收集复核选择，再应用（不弹窗打断）。"""
        from ..dialogs.pivot_review import PivotReviewPanel
        files = self.zone.get()
        self.panel.clear_log()
        self.panel.log_line("正在分析文件以供复核…")
        try:
            plan = pivot_core.analyze(files)
        except Exception as e:
            self.warn("分析失败", str(e))
            return
        self._review_files = files
        panel = PivotReviewPanel(plan)
        panel.accepted.connect(self._do_review_run)
        panel.cancelled.connect(self._cancel_review)
        self.main.open_panel(panel, "人工复核 · 销售表透视", key="review")

    def _cancel_review(self):
        self.main.close_panel("review")
        self.panel.log_line("已取消复核。")

    def _do_review_run(self, choices):
        self.main.close_panel("review")
        self.launch(lambda log: pivot_core.run(self._review_files, choices=choices, log=log),
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

    def guide_steps(self):
        return [
            (None, "欢迎使用销售表透视",
             "这个页面自动定位表头、清洗数据、统一单位规格,按编码/名称/规格/单位分组汇总,\n"
             "生成 Excel 原生数据透视表并评估可信度。跟着高亮走一遍即可。"),
            (self.zone, "① 放采购数据表",
             "把包装方案/采购量核算表、组托辅材等拖到这里,可多选。\n"
             "程序会自动跳过「客供/已生成透视表」类工作表,只处理数据表。"),
            (self.panel, "生成 · 复核 · 看报告",
             "直接点「生成透视表」即可;想先看分组结果再定,点「人工复核后生成…」。\n"
             "完成后状态行给出分组数、合计与可信度评分;点「打开输出文件夹」看表、\n"
             "「查看可信度报告」了解清洗与匹配是否可靠。"),
        ]
