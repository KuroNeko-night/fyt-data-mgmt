# -*- coding: utf-8 -*-
"""表格比对页。A 表 + B 表 -> 按关键列配对,找出差异 / 只在单边的行。

用途:核对"程序输出 vs 手工结果"、两版数据、交接复核。
选好两个文件后,自动列出两表公共列供选"关键列"(如物料编码);
比对结果弹窗展示(差异红、单边黄),同时导出一份带高亮的 Excel 报告。
读表在子线程(core.compare_core),不卡界面。
"""
import os

from PySide2.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel

from ..animations import AnimatedComboBox as QComboBox
from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from ..dialogs.compare_review import CompareReviewDialog
from core import compare_core as cc

_XL_FILTER = "Excel 文件 (*.xlsx *.xlsm);;所有文件 (*.*)"
_XL_EXTS = [".xlsx", ".xlsm"]


class ComparePage(BasePage):
    def __init__(self, main):
        super(ComparePage, self).__init__(
            main, "表格比对",
            "两份 Excel 按“关键列”配对核对,找出值差异与只在单边的行。"
            "适合核对程序输出与手工结果、两版数据、交接复核。")

    def build_body(self, layout):
        self.z_a = FileZone(1, "A 表(单个)", "拖入或选择 .xlsx/.xlsm,选 1 个。",
                            multi=False, exts=_XL_EXTS, file_filter=_XL_FILTER,
                            detail="作为比对的“A 侧”,通常放程序输出或新版。")
        self.z_b = FileZone(2, "B 表(单个)", "拖入或选择 .xlsx/.xlsm,选 1 个。",
                            multi=False, exts=_XL_EXTS, file_filter=_XL_FILTER,
                            detail="作为比对的“B 侧”,通常放手工结果或旧版。")
        for z in (self.z_a, self.z_b):
            z.changed.connect(self._refresh)
            layout.addWidget(z)

        layout.addWidget(self._key_card())

        self.panel = RunPanel("开始比对")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        self.btn_report = self.panel.add_action("打开报告", self._open_report)
        layout.addWidget(self.panel)
        layout.addStretch(1)
        self._out_dir = ""
        self._report = ""
        self._common = []
        self._refresh()

    def _key_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 12, 16, 12); v.setSpacing(8)
        t = QLabel("关键列"); t.setObjectName("SecTitle"); v.addWidget(t)
        row = QHBoxLayout(); row.setSpacing(10)
        row.addWidget(QLabel("按此列配对两表"))
        self.cmb_key = QComboBox(); self.cmb_key.setMinimumWidth(200)
        row.addWidget(self.cmb_key); row.addStretch(1)
        v.addLayout(row)
        self.tip = QLabel(""); self.tip.setObjectName("Hint"); self.tip.setWordWrap(True)
        v.addWidget(self.tip)
        return card

    def _refresh(self, *_):
        fa = self.z_a.get(); fb = self.z_b.get()
        cur = self.cmb_key.currentText()
        self._common = []
        if fa and fb:
            try:
                ha = cc.read_headers(fa[0]); hb = cc.read_headers(fb[0])
                self._common = cc.common_columns(ha, hb)
            except Exception as e:
                self.tip.setText("读取表头失败:%s" % e)
        self.cmb_key.blockSignals(True)
        self.cmb_key.clear()
        for name in self._common:
            self.cmb_key.addItem(name)
        if cur in self._common:                    # 尽量保留用户已选
            self.cmb_key.setCurrentText(cur)
        self.cmb_key.blockSignals(False)
        self._update_run(fa, fb)

    def _update_run(self, fa, fb):
        if not (fa and fb):
            self.panel.run_btn.setEnabled(False)
            self.panel.set_status("idle", "请选择 A、B 两个文件")
            self.tip.setText("")
            return
        if not self._common:
            self.panel.run_btn.setEnabled(False)
            self.panel.set_status("idle", "两表没有同名列,无法配对(请确认表头)")
            return
        self.panel.run_btn.setEnabled(True)
        self.panel.set_status("ready", "准备比对(关键列可选 %d 个)" % len(self._common))
        self.tip.setText("公共列:%s" % "、".join(self._common[:12])
                         + ("…" if len(self._common) > 12 else ""))

    def _run(self):
        self.panel.clear_log()
        fa = self.z_a.get()[0]; fb = self.z_b.get()[0]
        key = self.cmb_key.currentText()
        if not key:
            self.panel.set_status("idle", "请先选择关键列"); return

        def job(log):
            return cc.run(fa, fb, key=key, log=log)

        self.launch(job, self.panel, self._done)

    def _done(self, res):
        self._result = res
        self._out_dir = res.get("out_dir", "")
        self._report = res.get("report_path", "")
        cn = res["counts"]
        self.panel.set_status(
            "ok", "完成:差异 %d 处,只在A %d,只在B %d"
            % (cn["diffs"], cn["only_a"], cn["only_b"]))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.btn_report.setEnabled(bool(self._report))
        # 弹窗展示明细
        try:
            CompareReviewDialog(res, self).exec_()
        except Exception as e:
            self.panel.log_line("结果弹窗打开失败(报告已生成):%s" % e)
        self.notify_done(self._out_dir, "比对完成",
                         "差异 %d 处。\n报告:%s" % (cn["diffs"], self._report))

    def _open(self):
        self.open_folder(self._out_dir)

    def _open_report(self):
        try:
            if self._report and os.path.isfile(self._report):
                os.startfile(self._report)          # 直接打开报告文件
        except Exception:
            pass
