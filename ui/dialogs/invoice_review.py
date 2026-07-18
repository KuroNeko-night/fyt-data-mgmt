# -*- coding: utf-8 -*-
"""
增值税发票统计 —— 人工复核对话框
================================
生成前弹出，逐张核对识别结果（把关键判断交给人，而非全自动写死）：
  · 号码/日期/金额只读（机器可靠）；销售方/费用项目/税率/备注可改；
  · 每行前有勾选框，可排除某张票；
  · 顶部可改目标月份、可勾“同时含普通发票”（默认只统计专用发票）。
确认后 result_rows() 返回写表用的行 dict 列表 + 最终月份。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QWidget,
                               QLineEdit, QCheckBox, QPushButton, QFrame,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QAbstractItemView)

COLS = ["✓", "发票号码", "开票日期", "销售方名称", "费用项目",
        "不含税金额", "税额", "价税合计", "税率/征收方式", "备注"]
_READONLY = {1, 2, 5, 6, 7}       # 只读列索引（机器可靠字段）


class InvoiceReviewPanel(QWidget):
    """增值税发票统计人工复核 —— 右侧面板部件（原对话框正文）。
    确认后 confirmed 带回 (rows, ym)；取消发 cancelled。"""
    confirmed = Signal(object, object)
    cancelled = Signal()

    def __init__(self, items, ym, parent=None):
        super(InvoiceReviewPanel, self).__init__(parent)
        self._all = items
        self._ym = ym
        self._rows = []
        self._build()
        self._reload()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        head = QLabel("逐张核对下方发票。号码/日期/金额已锁定；销售方、费用项目、"
                      "税率、备注可直接改。取消勾选可排除某张票。")
        head.setObjectName("PageDesc"); head.setWordWrap(True)
        lay.addWidget(head)

        top = QHBoxLayout(); top.setSpacing(8)
        top.addWidget(QLabel("目标月份（YYYY-MM）："))
        self.ed_ym = QLineEdit(self._ym)
        self.ed_ym.setMaximumWidth(120)
        self.ed_ym.editingFinished.connect(self._reload)
        top.addWidget(self.ed_ym)
        self.chk_normal = QCheckBox("同时含普通发票（默认只统计专用发票）")
        self.chk_normal.toggled.connect(self._reload)
        top.addWidget(self.chk_normal)
        top.addStretch(1)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("Hint")
        top.addWidget(self.lbl_count)
        lay.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hdr = self.table.horizontalHeader()
        for c in (3, 4, 9):
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setObjectName("Sep")
        lay.addWidget(line)
        row = QHBoxLayout()
        self.lbl_sum = QLabel(""); self.lbl_sum.setObjectName("Hint")
        row.addWidget(self.lbl_sum); row.addStretch(1)
        cancel = QPushButton("取消"); cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.cancelled.emit)
        ok = QPushButton("生成汇总表"); ok.setObjectName("Primary")
        ok.clicked.connect(self._on_ok)
        row.addWidget(cancel); row.addWidget(ok)
        lay.addLayout(row)

    def _on_ok(self):
        rows, ym = self.result_rows()
        self.confirmed.emit(rows, ym)

    def _reload(self):
        """按当前月份/普通票开关，重新过滤并填表。"""
        ym = self.ed_ym.text().strip()
        rows = [i for i in self._all
                if (self.chk_normal.isChecked() or i.special)]
        rows = [i for i in rows if not ym or (i.date or "").startswith(ym)]
        rows.sort(key=lambda i: (i.date or "", i.num or ""))
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r, inv in enumerate(rows):
            self._fill_row(r, inv)
        self.lbl_count.setText("共 %d 张" % len(rows))
        self._update_sum()

    def _fill_row(self, r, inv):
        d = inv.as_row()
        vals = ["", d["num"], d["date"], d["seller"], d["item"],
                _fmt(d["amount"]), _fmt(d["tax"]), _fmt(d["total"]),
                _fmt_rate(d["rate"]), d["note"]]
        for c, val in enumerate(vals):
            if c == 0:
                it = QTableWidgetItem()
                it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                it.setCheckState(Qt.Checked)
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)
                continue
            it = QTableWidgetItem(str(val))
            if c in _READONLY:
                it.setFlags(Qt.ItemIsEnabled)           # 只读
            self.table.setItem(r, c, it)

    def _update_sum(self):
        amt = sum((i.amount or 0) for i in self._rows)
        tax = sum((i.tax or 0) for i in self._rows)
        tot = sum((i.total or 0) for i in self._rows)
        self.lbl_sum.setText("合计：不含税 %.2f ｜ 税额 %.2f ｜ 价税合计 %.2f"
                             % (amt, tax, tot))

    def result_rows(self):
        """读回勾选行（含人工编辑），返回 (rows, ym)。金额沿用机器原值。"""
        out = []
        for r, inv in enumerate(self._rows):
            chk = self.table.item(r, 0)
            if chk is None or chk.checkState() != Qt.Checked:
                continue
            out.append(dict(
                num=inv.num, date=inv.date,
                seller=self._text(r, 3), item=self._text(r, 4),
                amount=inv.amount, tax=inv.tax, total=inv.total,
                rate=_parse_rate(self._text(r, 8)), note=self._text(r, 9)))
        return out, (self.ed_ym.text().strip() or self._ym)

    def _text(self, r, c):
        it = self.table.item(r, c)
        return it.text().strip() if it else ""


def _fmt(v):
    return "" if v is None else ("%.2f" % v)


def _fmt_rate(r):
    """内部值 → 显示：小数显示成 '13%'，字符串原样。"""
    if isinstance(r, float):
        return "%g%%" % round(r * 100, 4)
    return str(r or "")


def _parse_rate(s):
    """显示串 → 存储值：'13%'→0.13；'9%+6%'原样；空→''。"""
    s = (s or "").strip()
    if not s:
        return ""
    if "+" in s:
        return s
    try:
        return round(float(s.rstrip("%")) / 100.0, 4)
    except ValueError:
        return s
