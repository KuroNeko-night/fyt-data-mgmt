# -*- coding: utf-8 -*-
"""Excel 工具箱页 —— 多簿合并 / 按 Sheet 拆分 / 格式转换 / 多表纵向合并。"""
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                               QRadioButton, QButtonGroup, QComboBox, QCheckBox)
from ..animations import (AnimatedCheckBox as QCheckBox,   # 勾选带打勾动画
                          AnimatedComboBox as QComboBox)   # 下拉抽屉式拉开

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import excel_tools_core as ec

_XL_FILTER = "表格文件 (*.xlsx *.xlsm *.xls *.csv);;所有文件 (*.*)"
_XL_EXTS = [".xlsx", ".xlsm", ".xls", ".csv"]


class ExcelToolsPage(BasePage):
    def __init__(self, main):
        super(ExcelToolsPage, self).__init__(
            main, "Excel 工具箱",
            "多个工作簿合并、按工作表拆分、xls/xlsx/CSV 格式转换、"
            "多张同结构表纵向合并。基于本机处理。")

    def build_body(self, layout):
        layout.addWidget(self._mode_card())
        self.zone = FileZone(1, "表格文件", "拖入或选择 .xlsx/.xlsm/.xls/.csv,可多选。",
                             multi=True, exts=_XL_EXTS, file_filter=_XL_FILTER,
                             detail="合并/纵向合并需≥2个;按Sheet拆分只处理第1个文件。")
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
        row = QHBoxLayout(); row.setSpacing(16)
        self.grp = QButtonGroup(self)
        for i, (key, label) in enumerate([
                ("merge", "多簿合并"), ("split", "按 Sheet 拆分"),
                ("convert", "格式转换"), ("stack", "纵向合并同结构")]):
            rb = QRadioButton(label); rb.mode_key = key
            if i == 0:
                rb.setChecked(True)
            self.grp.addButton(rb, i)
            row.addWidget(rb)
        row.addStretch(1)
        self.grp.buttonClicked.connect(self._refresh)
        v.addLayout(row)
        return card

    def _param_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 12, 16, 12); v.setSpacing(8)
        # 转换目标
        self.conv_row = QHBoxLayout(); self.conv_row.setSpacing(10)
        self.conv_row.addWidget(QLabel("转换为"))
        self.cmb_target = QComboBox()
        self.cmb_target.addItem("xlsx（xls/csv → xlsx）", "xlsx")
        self.cmb_target.addItem("CSV（每个工作表一个 .csv）", "csv")
        self.conv_row.addWidget(self.cmb_target); self.conv_row.addStretch(1)
        v.addLayout(self.conv_row)
        # 纵向合并选项
        self.cb_header = QCheckBox("首行是表头（合并时只保留一次,并加“来源文件”列）")
        self.cb_header.setChecked(True)
        v.addWidget(self.cb_header)
        # 多簿合并选项:保留公式
        self.cb_formula = QCheckBox(
            "保留公式（否则转为计算结果值;跨表公式合并后会失效）")
        v.addWidget(self.cb_formula)
        self.tip = QLabel(""); self.tip.setObjectName("Hint"); self.tip.setWordWrap(True)
        v.addWidget(self.tip)
        return card

    def _mode(self):
        return self.grp.checkedButton().mode_key

    def _refresh(self, *_):
        mode = self._mode()
        files = self.zone.get()
        for i in range(self.conv_row.count()):
            w = self.conv_row.itemAt(i).widget()
            if w:
                w.setVisible(mode == "convert")
        self.cb_header.setVisible(mode == "stack")
        self.cb_formula.setVisible(mode == "merge")
        tips = {
            "merge": "把多个工作簿合到一个文件,每个源工作表成为一个 Sheet。需选 ≥2 个文件。",
            "split": "把第 1 个文件的每个工作表导出成单独的 .xlsx。",
            "convert": "老 .xls 或 .csv 转 .xlsx;或把 Excel 每个表导出为 CSV(UTF-8,Excel 可直接打开)。",
            "stack": "多张列结构相同的表纵向拼成一张大表(各取第 1 个工作表),常用于月度汇总。需 ≥2 个文件。",
        }
        self.tip.setText(tips.get(mode, ""))
        self._update_run(mode, files)

    def _update_run(self, mode, files):
        n = len(files)
        if mode in ("merge", "stack"):
            ok = n >= 2; msg = "已选 %d 个,需 ≥2" % n if not ok else "准备处理 %d 个文件" % n
        else:
            ok = n >= 1; msg = "请选择文件" if not ok else "准备处理"
        self.panel.run_btn.setEnabled(ok)
        self.panel.set_status("ready" if ok else "idle", msg)

    def _run(self):
        self.panel.clear_log()
        mode = self._mode()
        files = self.zone.get()
        target = self.cmb_target.currentData()
        has_header = self.cb_header.isChecked()
        keep_formula = self.cb_formula.isChecked()

        def job(log):
            if mode == "merge":
                return ec.merge_books(files, keep_formula=keep_formula, log=log)
            if mode == "split":
                return ec.split_sheets(files[0], log=log)
            if mode == "convert":
                return ec.convert(files, target, log=log)
            return ec.stack_tables(files, has_header=has_header, log=log)

        self.launch(job, self.panel, self._done)

    def _done(self, res):
        self._out_dir = res.get("out_dir", "")
        outs = res.get("out_files", [])
        self.panel.set_status("ok", "完成!生成 %d 个文件" % len(outs))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.notify_done(self._out_dir, "Excel 处理完成",
                         "已生成 %d 个文件。\n输出:%s" % (len(outs), self._out_dir))

    def _open(self):
        self.open_folder(self._out_dir)
