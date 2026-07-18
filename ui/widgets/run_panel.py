# -*- coding: utf-8 -*-
"""
RunPanel —— 运行区(主按钮 + 状态点 + 进度条 + 可折叠详细信息)
==============================================================
面向客户：平时只显示友好的状态行与进度；技术日志默认收进"详细信息"
折叠区，需要排查时才展开。各功能页共用。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, QEasingCurve, QPropertyAnimation
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
        # 状态胶囊：圆点 + 文案包进一个柔底圆角块，观感更成品
        pill = QFrame(); pill.setObjectName("StatusPill")
        ph = QHBoxLayout(pill); ph.setContentsMargins(11, 5, 13, 5); ph.setSpacing(7)
        self.dot = QLabel("●")
        self.dot.setObjectName("StatusDot")
        self.status = QLabel("准备就绪")
        self.status.setObjectName("StatusText")
        ph.addWidget(self.dot)
        ph.addWidget(self.status)
        top.addWidget(pill)
        lay.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)     # 不确定动画
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(0)   # 收起态高度 0,显示时用动画拉开
        self.progress.hide()
        lay.addWidget(self.progress)
        self._prog_anim = QPropertyAnimation(self.progress, b"maximumHeight", self)
        self._prog_anim.setDuration(200)
        self._prog_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._prog_anim.finished.connect(self._hide_progress_if_collapsed)

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
        self.log.setMinimumHeight(0)     # 允许高度动画收到 0；展开后解除限高铺满
        self.log.setMaximumHeight(0)
        self.log.hide()                  # 默认折叠
        lay.addWidget(self.log, 1)
        self._log_anim = QPropertyAnimation(self.log, b"maximumHeight", self)
        self._log_anim.setDuration(240)
        self._log_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._log_anim.finished.connect(self._on_log_anim_done)
        self._log_target = 200           # 展开动画目标高度(px)

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
        self._log_anim.stop()            # 停掉可能在跑的展开/收起动画
        self.log.clear()
        self._has_log = False
        self.toggle.hide()
        self.toggle.setChecked(False)
        self.toggle.setText("▸ 详细信息")
        self.log.setMaximumHeight(0)     # 复位限高,下次展开从 0 平滑拉开
        self.log.hide()

    def show_log(self, on=True):
        """展开/收起详细信息（供报错时自动展开）。"""
        self.toggle.setChecked(on)
        self._toggle_log()

    def _toggle_log(self):
        on = self.toggle.isChecked()
        self.toggle.setText(("▾ 详细信息" if on else "▸ 详细信息"))
        self._log_anim.stop()
        if on:
            self.log.setVisible(True)
            self.log.setMaximumHeight(0)
            self._log_anim.setStartValue(0)
            self._log_anim.setEndValue(self._log_target)
        else:
            self._log_anim.setStartValue(self.log.height())
            self._log_anim.setEndValue(0)
        self._log_anim.start()

    def _on_log_anim_done(self):
        if self.toggle.isChecked():
            self.log.setMaximumHeight(16777215)   # 展开完成:解除限高,允许铺满剩余空间
        else:
            self.log.setVisible(False)            # 收起完成:彻底隐藏不占位

    def busy(self, on):
        self.run_btn.setEnabled(not on)
        # 次级按钮(add_action 加的"打开输出/送去对账"等)处理中也要禁用,防二次触发。
        # busy(True) 时先记住各自原启用态,busy(False) 时精确恢复——避免误开本应
        # 禁用(尚无输出)的按钮。
        if on:
            self._extra_saved = []
            for i in range(self.extra_btns.count()):
                w = self.extra_btns.itemAt(i).widget()
                if w is not None:
                    self._extra_saved.append((w, w.isEnabled()))
                    w.setEnabled(False)
        else:
            for w, en in getattr(self, "_extra_saved", []):
                w.setEnabled(en)
            self._extra_saved = []
        self._reveal_progress(on)
        if on:
            self.set_status("busy", "处理中，请稍候…")

    def _reveal_progress(self, on):
        """进度条显隐用高度动画平滑拉开/收起,而非瞬间蹦出。"""
        self._prog_anim.stop()
        if on:
            self.progress.setMaximumHeight(0)
            self.progress.show()
            self._prog_anim.setStartValue(0)
            self._prog_anim.setEndValue(14)       # 5px 条 + 上下微留白
            self._prog_anim.start()
        else:
            start = max(self.progress.height(), 1)
            self._prog_anim.setStartValue(start)
            self._prog_anim.setEndValue(0)
            self._prog_anim.start()

    def _hide_progress_if_collapsed(self):
        # 收起动画结束(目标高 0)才真正隐藏；展开结束时高度>0,不误隐
        if self.progress.maximumHeight() <= 0:
            self.progress.hide()

    def set_status(self, kind, text):
        theme.set_prop(self.dot, "state", kind)
        self.status.setText(text)
