# -*- coding: utf-8 -*-
"""
RunPanel —— 运行区(主按钮 + 状态点 + 进度条 + 可折叠详细信息)
==============================================================
面向客户：平时只显示友好的状态行与进度；技术日志默认收进"详细信息"
折叠区，需要排查时才展开。各功能页共用。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QProgressBar, QPlainTextEdit)

from .. import theme


class RunPanel(QFrame):
    def __init__(self, run_text="开始处理", parent=None):
        super(RunPanel, self).__init__(parent)
        self.setObjectName("Card")
        self._has_log = False
        self._build(run_text)

    def _build(self, run_text):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.run_btn = QPushButton(run_text)
        self.run_btn.setObjectName("Primary")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        top.addWidget(self.run_btn)
        self.extra_btns = QHBoxLayout()
        self.extra_btns.setSpacing(6)
        top.addLayout(self.extra_btns)
        top.addStretch(1)
        self.dot = QLabel("●")
        self.dot.setObjectName("StatusDot")
        self.status = QLabel("准备就绪")
        self.status.setObjectName("Hint")
        top.addWidget(self.dot)
        top.addWidget(self.status)
        lay.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)     # 不确定动画
        self.progress.setTextVisible(False)
        self.progress.hide()
        lay.addWidget(self.progress)

        # 折叠：详细信息（技术日志）
        self.toggle = QPushButton("▸ 详细信息")
        self.toggle.setObjectName("Link")
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setCheckable(True)
        self.toggle.clicked.connect(self._toggle_log)
        self.toggle.hide()               # 有日志后才出现
        lay.addWidget(self.toggle, 0, Qt.AlignLeft)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        self.log.hide()                  # 默认折叠
        lay.addWidget(self.log, 1)

        self.set_status("idle", "准备就绪")

    # ---------- 供页面调用 ----------
    def add_action(self, text, slot, primary=False):
        b = QPushButton(text)
        b.setObjectName("Ghost" if not primary else "Primary")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        b.setEnabled(False)
        self.extra_btns.addWidget(b)
        return b

    def log_line(self, msg):
        self.log.appendPlainText(msg)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
        if not self._has_log:
            self._has_log = True
            self.toggle.show()           # 出现"详细信息"入口，但不自动展开

    def clear_log(self):
        self.log.clear()
        self._has_log = False
        self.toggle.hide()
        self.toggle.setChecked(False)
        self.toggle.setText("▸ 详细信息")
        self.log.hide()

    def show_log(self, on=True):
        """展开/收起详细信息（供报错时自动展开）。"""
        self.toggle.setChecked(on)
        self._toggle_log()

    def _toggle_log(self):
        on = self.toggle.isChecked()
        self.log.setVisible(on)
        self.toggle.setText(("▾ 详细信息" if on else "▸ 详细信息"))

    def busy(self, on):
        self.run_btn.setEnabled(not on)
        self.progress.setVisible(on)
        if on:
            self.set_status("busy", "处理中，请稍候…")

    def set_status(self, kind, text):
        theme.set_prop(self.dot, "state", kind)
        self.status.setText(text)
