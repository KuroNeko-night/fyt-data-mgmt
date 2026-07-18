# -*- coding: utf-8 -*-
"""FilePreview —— 常驻侧栏的文件预览网格。

选中/点击一个文件即在右侧看到它的前若干行(见 core.preview_core),不必打开 Excel。
多子表时顶部给一个下拉切换;读取在子线程,避免大表卡界面。空态显示占位提示。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QAbstractItemView, QStackedWidget, QWidget)

from ..animations import AnimatedComboBox as QComboBox
from ..worker import Worker
from core import preview_core


class FilePreview(QFrame):
    """文件预览部件。调用 show_file(path) 载入;clear() 回到空态。"""

    def __init__(self, parent=None):
        super(FilePreview, self).__init__(parent)
        self.setObjectName("FilePreview")
        self._path = ""
        self._worker = None
        self._gen = 0                       # 代次守卫:丢弃过期的异步结果
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        bar = QHBoxLayout(); bar.setSpacing(8)
        self._name = QLabel("")
        self._name.setObjectName("PreviewName")
        self._name.setWordWrap(False)
        bar.addWidget(self._name, 1)
        self._sheet_cmb = QComboBox()
        self._sheet_cmb.setMinimumWidth(120)
        self._sheet_cmb.hide()
        self._sheet_cmb.currentIndexChanged.connect(self._on_sheet_changed)
        bar.addWidget(self._sheet_cmb, 0)
        v.addLayout(bar)

        self._stack = QStackedWidget()
        # 空态占位
        empty = QWidget()
        el = QVBoxLayout(empty); el.setContentsMargins(0, 30, 0, 0)
        tip = QLabel("在左侧点击一个文件即可在此预览前 %d 行" % preview_core.DEFAULT_ROWS)
        tip.setObjectName("Hint"); tip.setAlignment(Qt.AlignCenter); tip.setWordWrap(True)
        el.addWidget(tip); el.addStretch(1)
        self._empty = empty
        self._stack.addWidget(empty)

        self._table = QTableWidget()
        self._table.setObjectName("PreviewTable")
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.verticalHeader().setVisible(False)
        self._stack.addWidget(self._table)
        v.addWidget(self._stack, 1)

        self._status = QLabel("")
        self._status.setObjectName("Hint")
        v.addWidget(self._status)

    # ---------- 对外 ----------
    def show_file(self, path):
        """载入并预览一个文件(异步)。同一文件重复调用会刷新。"""
        if not path:
            self.clear()
            return
        self._path = path
        self._name.setText(os.path.basename(path))
        self._name.setToolTip(path)
        self._sheet_cmb.blockSignals(True)
        self._sheet_cmb.clear()
        self._sheet_cmb.hide()
        self._sheet_cmb.blockSignals(False)
        self._status.setText("正在读取…")
        self._load_async(path, None)

    def clear(self):
        self._path = ""
        self._gen += 1                      # 作废在途结果
        self._name.setText("")
        self._name.setToolTip("")
        self._sheet_cmb.hide()
        self._status.setText("")
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._stack.setCurrentWidget(self._empty)

    # ---------- 异步读取 ----------
    def _load_async(self, path, sheet):
        self._gen += 1
        gen = self._gen

        def job(log):
            return preview_core.read_preview(path, sheet=sheet)

        w = Worker(job)
        w.sig_done.connect(lambda data, g=gen: self._on_loaded(data, g))
        w.sig_error.connect(lambda msg, tb, g=gen: self._on_error(msg, g))
        self._worker = w                    # 存引用防 GC
        w.start()

    def _on_loaded(self, data, gen):
        if gen != self._gen:
            return                          # 已被更晚的选择取代,丢弃
        if data.error:
            self._on_error(data.error, gen)
            return
        # 子表下拉(多于一张才显示)
        self._sheet_cmb.blockSignals(True)
        self._sheet_cmb.clear()
        if len(data.sheets) > 1:
            for nm in data.sheets:
                self._sheet_cmb.addItem(nm)
            if data.sheet in data.sheets:
                self._sheet_cmb.setCurrentText(data.sheet)
            self._sheet_cmb.show()
        else:
            self._sheet_cmb.hide()
        self._sheet_cmb.blockSignals(False)
        self._fill_table(data)

    def _on_error(self, msg, gen):
        if gen != self._gen:
            return
        self._table.setRowCount(0); self._table.setColumnCount(0)
        self._stack.setCurrentWidget(self._empty)
        self._status.setText("预览失败:%s" % msg)

    def _on_sheet_changed(self, *_):
        if self._path:
            self._status.setText("正在读取…")
            self._load_async(self._path, self._sheet_cmb.currentText())

    def _fill_table(self, data):
        rows = data.rows
        ncols = data.ncols
        self._table.setColumnCount(ncols)
        self._table.setRowCount(max(0, len(rows) - 1) if rows else 0)
        if rows:
            # 首行当表头
            headers = rows[0] + [""] * (ncols - len(rows[0]))
            self._table.setHorizontalHeaderLabels(
                [h or ("列%d" % (i + 1)) for i, h in enumerate(headers)])
            for r, row in enumerate(rows[1:]):
                for c in range(ncols):
                    val = row[c] if c < len(row) else ""
                    self._table.setItem(r, c, QTableWidgetItem(val))
        self._stack.setCurrentWidget(self._table)
        note = "前 %d 行%s" % (data.nrows, "(已截断)" if data.truncated else "")
        self._status.setText(note)
