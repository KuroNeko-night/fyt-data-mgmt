# -*- coding: utf-8 -*-
"""工时对账页。待对表 + 数据来源 + 对账单 -> 填好的表 + 异常汇总 + 可信度。"""
import os

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import reconcile_core, common_core


class ReconcilePage(BasePage):
    def __init__(self, main):
        self.opts = common_core.Options() if hasattr(common_core, "Options") else None
        super(ReconcilePage, self).__init__(
            main, "工时对账",
            "把数据来源与对账单核对填入待对表，输出异常汇总并给出可信度评分。")

    def build_body(self, layout):
        self.z_tgt = FileZone(1, "待对表（目标·单个）",
                              "需要被核对填写的总表，选 1 个。", multi=False,
                              library_cats=["rec_zong"],
                              detail="程序在此表上核对并标注，另存为“_已填写”。")
        self.z_src = FileZone(2, "数据来源",
                              "已填好的考勤/工时数据，可多选。可由“考勤填报”直接送来。",
                              multi=True, library_cats=["rec_source", "att_target"],
                              detail="核对的事实来源：每人每天的实际工时。")
        self.z_labor = FileZone(3, "对账单 / 工时单",
                                "需要与来源核对的对账单据，可多选。", multi=True,
                                library_cats=["rec_labor"],
                                detail="被核对的一方：与数据来源逐项比对，差异计入异常。")
        for z in (self.z_tgt, self.z_src, self.z_labor):
            z.changed.connect(self._refresh)
            layout.addWidget(z)

        self.panel = RunPanel("开始对账")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_review = self.panel.add_action("人工确认后对账…", self._run_review)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        layout.addWidget(self.panel)
        self._out_dir = ""
        self._refresh()

    def add_source_files(self, paths):
        self.z_src.add_paths(paths)
        self._refresh()

    def refresh_view(self):
        for z in (self.z_tgt, self.z_src, self.z_labor):
            z.refresh_lib_count()

    def _refresh(self, *_):
        ok = bool(self.z_tgt.get()) and bool(self.z_src.get()) and bool(self.z_labor.get())
        self.panel.run_btn.setEnabled(ok)
        self.btn_review.setEnabled(ok)
        if ok:
            self.panel.set_status("ready", "准备就绪")
        else:
            need = []
            if not self.z_tgt.get(): need.append("待对表")
            if not self.z_src.get(): need.append("数据来源")
            if not self.z_labor.get(): need.append("对账单")
            self.panel.set_status("idle", "还需选择：" + "、".join(need))

    def _run(self):
        self.panel.clear_log()
        tgt = self.z_tgt.get()[0]
        src = self.z_src.get()
        labor = self.z_labor.get()
        opts = self.opts
        self.launch(lambda log: reconcile_core.run(tgt, src, labor, opts=opts, log=log),
                    self.panel, self._done)

    def _run_review(self):
        """先只读分析，在右侧面板收集结构纠正与姓名配对，再对账（不弹窗）。"""
        from ..dialogs.reconcile_review import ReconcileReviewPanel
        tgt = self.z_tgt.get()[0]
        src = self.z_src.get()
        labor = self.z_labor.get()
        self.panel.clear_log()
        self.panel.log_line("正在分析文件以供人工确认…")
        try:
            plan = reconcile_core.analyze(tgt, src, labor, opts=self.opts)
        except Exception as e:
            self.warn("分析失败", str(e))
            self.panel.set_status("err", "分析失败")
            return
        self._review_ctx = (tgt, src, labor)
        panel = ReconcileReviewPanel(plan)
        panel.accepted.connect(self._do_review_run)
        panel.cancelled.connect(self._cancel_review)
        self.main.open_panel(panel, "人工确认 · 工时对账")

    def _cancel_review(self):
        self.main.close_panel()
        self.panel.log_line("已取消人工确认。")

    def _do_review_run(self, choices):
        self.main.close_panel()
        tgt, src, labor = self._review_ctx
        self.launch(lambda log: reconcile_core.run(tgt, src, labor, opts=self.opts,
                                                    log=log, choices=choices),
                    self.panel, self._done)

    def _done(self, res):
        cred = res.get("credibility", {}) or {}
        level = cred.get("level", "?")
        score = cred.get("score", 0)
        self._out_dir = os.path.dirname(res.get("filled_path", "") or res.get("summary_path", ""))
        n = len(res.get("anomalies", []))
        kind = "ok" if level == "可信" else ("warn" if level == "需复核" else "err")
        self.panel.set_status(kind, "完成 · 可信度【%s】%d/100 · 异常 %d 条" % (level, score, n))
        self.btn_open.setEnabled(bool(self._out_dir))
        tone = {"可信": "对账结果可信，可直接使用。",
                "需复核": "结果基本可用，但建议人工复核异常汇总。",
                "存疑": "可信度偏低，请务必核对异常汇总与列映射设置。"}.get(level, "")
        self.notify_done(self._out_dir, "对账完成",
                  "可信度：【%s】 %d/100\n异常：%d 条\n%s\n输出：%s"
                  % (level, score, n, tone, self._out_dir))

    def _open(self):
        self.open_folder(self._out_dir)
