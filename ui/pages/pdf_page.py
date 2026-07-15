# -*- coding: utf-8 -*-
"""PDF 工具箱页 —— 合并 / 拆分 / 提取页 / 删除页。基于 pypdf,后台线程执行。"""
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                               QRadioButton, QButtonGroup, QLineEdit, QComboBox)
from ..animations import AnimatedComboBox as QComboBox   # 下拉抽屉式拉开

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import pdf_core

_PDF_FILTER = "PDF 文件 (*.pdf);;所有文件 (*.*)"


class PdfPage(BasePage):
    def __init__(self, main):
        super(PdfPage, self).__init__(
            main, "PDF 工具箱",
            "合并多个 PDF、按页拆分、提取或删除指定页。纯本地处理,不上传。")

    def build_body(self, layout):
        layout.addWidget(self._mode_card())
        self.zone = FileZone(1, "PDF 文件", "拖入或选择 PDF,可多选;合并时按此顺序。",
                             multi=True, exts=[".pdf"], file_filter=_PDF_FILTER,
                             detail="合并需要 2 个及以上;拆分/提取/删除只处理第 1 个文件。")
        self.zone.changed.connect(self._refresh)
        layout.addWidget(self.zone)
        layout.addWidget(self._param_card())

        self.panel = RunPanel("开始处理")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        layout.addWidget(self.panel)
        layout.addStretch(1)
        self._out_dir = ""
        self._refresh()

    def _mode_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 12, 16, 12); v.setSpacing(8)
        t = QLabel("选择操作"); t.setObjectName("SecTitle"); v.addWidget(t)
        row = QHBoxLayout(); row.setSpacing(18)
        self.grp = QButtonGroup(self)
        for i, (key, label) in enumerate([
                ("merge", "合并多个 PDF"), ("split", "拆分 PDF"),
                ("extract", "提取指定页"), ("delete", "删除指定页")]):
            rb = QRadioButton(label); rb.mode_key = key
            if i == 0:
                rb.setChecked(True)
            self.grp.addButton(rb, i)
            row.addWidget(rb)
        row.addStretch(1)
        self.grp.buttonClicked.connect(self._on_mode)
        v.addLayout(row)
        return card

    def _param_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 12, 16, 12); v.setSpacing(8)
        # 拆分方式
        self.split_row = QHBoxLayout(); self.split_row.setSpacing(10)
        self.split_row.addWidget(QLabel("拆分方式"))
        self.cmb_split = QComboBox()
        self.cmb_split.addItem("每页一个文件", "each")
        self.cmb_split.addItem("按范围分段(下方填写)", "ranges")
        self.cmb_split.currentIndexChanged.connect(self._refresh)
        self.split_row.addWidget(self.cmb_split); self.split_row.addStretch(1)
        v.addLayout(self.split_row)
        # 页码范围
        self.range_row = QHBoxLayout(); self.range_row.setSpacing(10)
        self.range_row.addWidget(QLabel("页码范围"))
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText("如 1,3,5-8,12-（看到的页码,从 1 起;拆分分段用逗号隔开各段）")
        self.ed_range.textChanged.connect(self._refresh)
        self.range_row.addWidget(self.ed_range, 1)
        v.addLayout(self.range_row)
        self.lbl_pages = QLabel(""); self.lbl_pages.setObjectName("Hint")
        v.addWidget(self.lbl_pages)
        return card

    def _mode(self):
        return self.grp.checkedButton().mode_key

    def _on_mode(self, *_):
        self._refresh()

    def _refresh(self, *_):
        mode = self._mode()
        files = self.zone.get()
        # 参数可见性
        show_split = (mode == "split")
        need_range = (mode in ("extract", "delete")) or \
                     (mode == "split" and self.cmb_split.currentData() == "ranges")
        for i in range(self.split_row.count()):
            w = self.split_row.itemAt(i).widget()
            if w:
                w.setVisible(show_split)
        for i in range(self.range_row.count()):
            w = self.range_row.itemAt(i).widget()
            if w:
                w.setVisible(need_range)
        # 单文件操作时显示第一个文件页数
        self.lbl_pages.setVisible(need_range or mode == "split")
        if files and mode != "merge":
            try:
                n = pdf_core.page_count(files[0])
                self.lbl_pages.setText("「%s」共 %d 页" %
                                       (self._name(files[0]), n))
            except pdf_core.PdfError as e:
                self.lbl_pages.setText(str(e))
        else:
            self.lbl_pages.setText("")
        self._update_run(mode, files)

    def _update_run(self, mode, files):
        ok = False
        if mode == "merge":
            ok = len(files) >= 2
            msg = "已选 %d 个,合并需 ≥2" % len(files) if not ok else "准备合并 %d 个 PDF" % len(files)
        else:
            has_range = bool(self.ed_range.text().strip())
            if mode == "split" and self.cmb_split.currentData() == "each":
                ok = len(files) >= 1
            else:
                ok = len(files) >= 1 and has_range
            msg = "请选择 PDF" if not files else \
                  ("请填写页码范围" if (not ok and mode != "merge") else "准备处理")
        self.panel.run_btn.setEnabled(ok)
        self.panel.set_status("ready" if ok else "idle", msg)

    def _name(self, p):
        import os
        return os.path.basename(p)

    def _run(self):
        self.panel.clear_log()
        mode = self._mode()
        files = self.zone.get()
        spec = self.ed_range.text()
        split_mode = self.cmb_split.currentData()

        def job(log):
            if mode == "merge":
                return pdf_core.merge(files, log=log)
            if mode == "split":
                return pdf_core.split(files[0], mode=split_mode, spec=spec, log=log)
            if mode == "extract":
                return pdf_core.extract_pages(files[0], spec, log=log)
            return pdf_core.delete_pages(files[0], spec, log=log)

        self.launch(job, self.panel, self._done)

    def _done(self, res):
        self._out_dir = res.get("out_dir", "")
        outs = res.get("out_files", [])
        self.panel.set_status("ok", "完成!生成 %d 个文件" % len(outs))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.notify_done(self._out_dir, "PDF 处理完成",
                         "已生成 %d 个文件。\n输出:%s" % (len(outs), self._out_dir))

    def _open(self):
        self.open_folder(self._out_dir)
