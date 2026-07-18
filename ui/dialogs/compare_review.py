# -*- coding: utf-8 -*-
"""表格比对结果对话框
==================
只读展示 compare_core.run/compare 的结果:
  · 差异明细:关键列 / 列名 / A 值 / B 值(值不同的单元格,红底);
  · 只在A / 只在B:关键列只出现在单边的整行(黄底);
  · 概要:各项计数一览。
沿用工时对账/透视复核对话框的外观。兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Signal
from PySide2.QtGui import QColor
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView)

_RED = QColor("#FFC7CE")
_YELLOW = QColor("#FFEB9C")


class CompareResultPanel(QWidget):
    """表格比对结果 —— 右侧只读面板部件（原对话框正文）。
    点关闭发 closed 信号。"""
    closed = Signal()

    def __init__(self, result, parent=None):
        super(CompareResultPanel, self).__init__(parent)
        self.result = result
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)
        cn = self.result["counts"]
        head = QLabel("关键列「%s」· 差异 %d 处 · 只在A %d 行 · 只在B %d 行 · 配对 %d 行"
                      % (self.result["key"], cn["diffs"], cn["only_a"],
                         cn["only_b"], cn["matched"]))
        head.setObjectName("PageDesc"); head.setWordWrap(True)
        lay.addWidget(head)

        tabs = QTabWidget()
        tabs.addTab(self._diff_tab(), "差异明细 (%d)" % cn["diffs"])
        tabs.addTab(self._only_tab(self.result["only_a"]), "只在A (%d)" % cn["only_a"])
        tabs.addTab(self._only_tab(self.result["only_b"]), "只在B (%d)" % cn["only_b"])
        tabs.addTab(self._summary_tab(), "概要")
        lay.addWidget(tabs, 1)

        row = QHBoxLayout(); row.addStretch(1)
        close = QPushButton("关闭"); close.setObjectName("Primary")
        close.clicked.connect(self.closed.emit)
        row.addWidget(close)
        lay.addLayout(row)

    def _mk_table(self, headers):
        tb = QTableWidget(0, len(headers))
        tb.setHorizontalHeaderLabels(headers)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.setSelectionBehavior(QAbstractItemView.SelectRows)
        tb.setAlternatingRowColors(True)
        tb.verticalHeader().setVisible(False)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return tb

    def _diff_tab(self):
        tb = self._mk_table([self.result["key"], "列名", "A 值", "B 值"])
        for d in self.result["diffs"]:
            r = tb.rowCount(); tb.insertRow(r)
            tb.setItem(r, 0, QTableWidgetItem(str(d["key"])))
            tb.setItem(r, 1, QTableWidgetItem(str(d["column"])))
            ia = QTableWidgetItem("" if d["a"] is None else str(d["a"]))
            ib = QTableWidgetItem("" if d["b"] is None else str(d["b"]))
            ia.setBackground(_RED); ib.setBackground(_RED)
            tb.setItem(r, 2, ia); tb.setItem(r, 3, ib)
        return tb

    def _only_tab(self, items):
        cols = list(items[0]["row"].keys()) if items else [self.result["key"]]
        tb = self._mk_table(cols)
        for it in items:
            r = tb.rowCount(); tb.insertRow(r)
            for c, name in enumerate(cols):
                v = it["row"].get(name)
                cell = QTableWidgetItem("" if v is None else str(v))
                cell.setBackground(_YELLOW)
                tb.setItem(r, c, cell)
        return tb

    def _summary_tab(self):
        cn = self.result["counts"]
        tb = self._mk_table(["项目", "数量"])
        rows = [("关键列", self.result["key"]),
                ("比较列数", len(self.result["columns"])),
                ("值差异(单元格)", cn["diffs"]), ("配对成功(行)", cn["matched"]),
                ("只在A的行", cn["only_a"]), ("只在B的行", cn["only_b"]),
                ("A重复键", cn["dup_a"]), ("B重复键", cn["dup_b"]),
                ("A关键列空行", cn["blank_a"]), ("B关键列空行", cn["blank_b"])]
        for name, val in rows:
            r = tb.rowCount(); tb.insertRow(r)
            tb.setItem(r, 0, QTableWidgetItem(str(name)))
            tb.setItem(r, 1, QTableWidgetItem(str(val)))
        return tb
