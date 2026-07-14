# -*- coding: utf-8 -*-
"""
DropArea —— 大号导入拖拽区（数据库页专用）
==========================================
拖拽或点击选择 Excel，发出 files 信号交给页面去分类归档。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QFileDialog

from .. import theme
from .. import icons

EXCEL_EXT = (".xlsx", ".xlsm", ".xls")


class DropArea(QFrame):
    files = Signal(list)

    def __init__(self, parent=None):
        super(DropArea, self).__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 26, 20, 26)
        v.setSpacing(10)
        v.setAlignment(Qt.AlignCenter)

        self._icon = QLabel()
        self._icon.setObjectName("DropIcon")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setFixedSize(44, 44); self._icon.setScaledContents(True)
        self._refresh_icon()
        v.addWidget(self._icon, 0, Qt.AlignCenter)
        t = QLabel("把表格拖到这里导入数据库")
        t.setObjectName("DropTitle")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        h = QLabel("程序会自动识别每张表的用途并归档；未能识别的会单独存放。")
        h.setObjectName("Hint")
        h.setAlignment(Qt.AlignCenter)
        h.setWordWrap(True)
        v.addWidget(h)
        btn = QPushButton("＋ 选择文件导入")
        btn.setObjectName("Primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._browse)
        v.addWidget(btn, 0, Qt.AlignCenter)

    def _refresh_icon(self):
        # 2× 物理分辨率 + setScaledContents 定尺，高 DPI 不裁切
        self._icon.setPixmap(icons.pixmap("upload", 88, None, 1.0))

    def _browse(self):
        filt = "Excel 文件 (*.xlsx *.xlsm *.xls);;所有文件 (*.*)"
        fs, _ = QFileDialog.getOpenFileNames(self, "选择要导入的表格", "", filt)
        if fs:
            self.files.emit(fs)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            theme.set_prop(self, "dragging", True)

    def dragLeaveEvent(self, e):
        theme.set_prop(self, "dragging", False)

    def dropEvent(self, e):
        theme.set_prop(self, "dragging", False)
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        ex = [p for p in paths if p.lower().endswith(EXCEL_EXT)]
        if ex:
            self.files.emit(ex)
        e.acceptProposedAction()
