# -*- coding: utf-8 -*-
"""
NoticeBar —— 页内通知条（替代打断式弹窗）
==========================================
处理结果 / 完成提示 / 错误信息不再弹 QMessageBox 打断操作，
而是从页面内容区顶部平滑滑入一条通知：左侧状态圆点 + 文案 +
可选行内操作按钮（如"打开输出"）+ 右侧关闭。可设自动消失。

滑入/滑出走 maximumHeight 动画，不使用 QGraphicsEffect（防糊字/白闪）。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, QEasingCurve, QPropertyAnimation, QTimer
from PySide2.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy)

from .. import theme


class NoticeBar(QFrame):
    def __init__(self, parent=None):
        super(NoticeBar, self).__init__(parent)
        self.setObjectName("NoticeBar")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._action_btns = []
        self._build()
        self.setMaximumHeight(0)          # 默认收起
        self.hide()
        self._anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_done)
        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self.dismiss)

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 10, 10)
        h.setSpacing(9)
        self.dot = QLabel("●")
        self.dot.setObjectName("NoticeDot")
        h.addWidget(self.dot, 0, Qt.AlignVCenter)
        self.msg = QLabel("")
        self.msg.setObjectName("NoticeText")
        self.msg.setWordWrap(True)
        h.addWidget(self.msg, 1)
        self._btn_host = QHBoxLayout()
        self._btn_host.setSpacing(6)
        h.addLayout(self._btn_host)
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("NoticeClose")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.dismiss)
        h.addWidget(self.close_btn, 0, Qt.AlignVCenter)

    # ---------- 供页面调用 ----------
    def show_notice(self, kind, text, actions=None, auto_ms=0):
        """显示一条通知。
        kind: ok/warn/err/info —— 决定圆点颜色；
        actions: [(文案, 槽函数), ...] —— 生成行内按钮，点后自动关闭；
        auto_ms: >0 时该毫秒后自动收起(成功提示常用,错误建议 0 由用户手动关)。"""
        theme.set_prop(self.dot, "state", kind)
        self.msg.setText(text or "")
        self._clear_actions()
        for label, slot in (actions or []):
            b = QPushButton(label)
            b.setObjectName("NoticeAction")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=slot: self._on_action(s))
            self._btn_host.addWidget(b)
            self._action_btns.append(b)
        self._slide_in()
        self._auto.stop()
        if auto_ms and auto_ms > 0:
            self._auto.start(auto_ms)

    def dismiss(self):
        """收起并隐藏。"""
        self._auto.stop()
        if not self.isVisible():
            return
        self._anim.stop()
        self._anim.setStartValue(self.height())
        self._anim.setEndValue(0)
        self._anim.start()

    # ---------- 内部 ----------
    def _on_action(self, slot):
        try:
            if callable(slot):
                slot()
        finally:
            self.dismiss()

    def _clear_actions(self):
        for b in self._action_btns:
            self._btn_host.removeWidget(b)
            b.deleteLater()
        self._action_btns = []

    def _slide_in(self):
        self._anim.stop()
        self.setMaximumHeight(0)
        self.show()
        target = self.sizeHint().height()
        self._anim.setStartValue(0)
        self._anim.setEndValue(max(target, 40))
        self._anim.start()

    def _on_anim_done(self):
        if self.maximumHeight() <= 0:
            self.hide()              # 收起完成才隐藏,不占位
        else:
            self.setMaximumHeight(16777215)   # 展开完成解除限高,允许换行自适应
