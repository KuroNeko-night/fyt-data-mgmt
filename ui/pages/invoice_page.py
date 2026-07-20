# -*- coding: utf-8 -*-
"""增值税发票统计页。

选资料文件夹 → 扫描识别专用发票 → 人工复核 → 生成月度汇总表，
并把所有专用发票原始 PDF 复制到复核文件夹（含存疑清单）供二次核对。
两阶段：扫描在后台线程；复核确认后再生成。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog)

from .base_page import BasePage
from ..widgets.run_panel import RunPanel
from core import invoice_core


class InvoicePage(BasePage):
    def __init__(self, main):
        super(InvoicePage, self).__init__(
            main, "增值税发票统计",
            "选一个资料文件夹，自动识别其中的增值税专用发票并汇总成月度台账；"
            "生成前可逐张人工复核。同时把专用发票单独归档，供二次核对。")

    def build_body(self, layout):
        self._fc = self._folder_card()
        layout.addWidget(self._fc)
        self.panel = RunPanel("扫描识别发票")
        self.panel.run_btn.clicked.connect(self._scan)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        layout.addWidget(self.panel)
        self._result = None
        self._out = {}
        self._refresh()

    # ---------- 文件夹选择卡片 ----------
    def _folder_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12); v.setSpacing(8)
        head = QHBoxLayout(); head.setSpacing(8)
        badge = QLabel("1"); badge.setObjectName("Badge")
        badge.setAlignment(Qt.AlignCenter)
        head.addWidget(badge)
        tl = QLabel("资料文件夹"); tl.setObjectName("CardTitle")
        head.addWidget(tl); head.addStretch(1)
        v.addLayout(head)
        hint = QLabel("程序会递归扫描该文件夹下所有 PDF，自动挑出增值税专用发票。")
        hint.setObjectName("Hint"); hint.setWordWrap(True)
        v.addWidget(hint)
        row = QHBoxLayout(); row.setSpacing(8)
        self.ed_dir = QLineEdit()
        self.ed_dir.setPlaceholderText("点右侧“浏览…”选择含发票 PDF 的文件夹")
        self.ed_dir.textChanged.connect(self._refresh)
        row.addWidget(self.ed_dir, 1)
        b = QPushButton("浏览…"); b.setObjectName("Ghost")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self._pick)
        row.addWidget(b)
        v.addLayout(row)
        return card

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择资料文件夹", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def _refresh(self, *_):
        ok = bool(self.ed_dir.text().strip()) and os.path.isdir(self.ed_dir.text().strip())
        self.panel.run_btn.setEnabled(ok)
        if ok:
            self.panel.set_status("ready", "准备就绪，可开始扫描")
        else:
            self.panel.set_status("idle", "请选择资料文件夹")

    # ---------- 阶段一：扫描 ----------
    def _scan(self):
        root = self.ed_dir.text().strip()
        if not os.path.isdir(root):
            self.warn("提示", "请选择有效的资料文件夹。")
            return
        self.panel.clear_log()
        self.launch(lambda log: invoice_core.scan(root, log=log),
                    self.panel, self._scanned)

    def _scanned(self, result):
        self._result = result
        specials = [i for i in result.invoices if i.special]
        if not specials:
            self.panel.set_status("err", "未识别到任何增值税专用发票")
            self.warn("没有发票", "该文件夹里没识别到增值税专用发票。\n"
                      "请确认选对了文件夹，或查看“详细信息”日志。")
            return
        ym = invoice_core.detect_month(specials)
        self.panel.set_status("ok", "识别到专用发票 %d 张，请复核" % len(specials))
        self._review(result, ym)

    # ---------- 阶段二：复核 + 生成 ----------
    def _review(self, result, ym):
        from ..dialogs.invoice_review import InvoiceReviewPanel
        self._scan_result = result
        panel = InvoiceReviewPanel(result.invoices, ym)
        panel.confirmed.connect(self._do_generate)
        panel.cancelled.connect(self._cancel_review)
        self.main.open_panel(panel, "人工复核 · 增值税发票统计", key="review")

    def _cancel_review(self):
        self.main.close_panel("review")
        self.panel.set_status("ready", "已取消复核，未生成")

    def _do_generate(self, rows, out_ym):
        self.main.close_panel("review")
        if not rows:
            self.warn("提示", "没有勾选任何发票，未生成。")
            return
        result = self._scan_result
        self.launch(
            lambda log: invoice_core.generate(result, rows, out_ym, log=log),
            self.panel, self._done)

    def _done(self, res):
        self._out = res
        self.panel.set_status(
            "ok", "完成！专用发票 %d 张，存疑 %d 个" % (res["count"], res["suspects"]))
        self.btn_open.setEnabled(True)
        self.notify_done(
            res["out_dir"], "生成完成",
            "已生成汇总表并归档 %d 张专用发票。\n"
            "复核文件夹：%s\n输出目录：%s"
            % (res["count"], os.path.basename(res["review_dir"]), res["out_dir"]))

    def _open(self):
        self.open_folder(self._out.get("out_dir", ""))

    def guide_steps(self):
        return [
            (None, "欢迎使用增值税发票统计",
             "这个页面自动识别一个文件夹里的增值税专用发票,汇总成月度台账,\n"
             "并把专用发票单独归档供二次核对。分「扫描 → 复核 → 生成」两步。"),
            (self._fc, "① 选资料文件夹",
             "点「浏览…」选一个含发票 PDF 的文件夹。\n"
             "程序会递归扫描该文件夹下所有 PDF,自动挑出增值税专用发票。"),
            (self.panel, "② 扫描 → 复核 → 生成",
             "点「扫描识别发票」。识别完成后右侧弹出复核面板,可逐张核对、勾选;\n"
             "确认后自动生成月度汇总表。完成后点「打开输出文件夹」看台账与归档的发票。"),
        ]
