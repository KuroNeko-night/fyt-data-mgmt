# -*- coding: utf-8 -*-
"""Collapsible —— 可折叠段落（标题按钮 + 富文本内容），用于帮助文档。

展开/收起用 maximumHeight 动画平滑滑动，而非瞬间显隐。"""
from PySide2.QtCore import Qt, QEasingCurve, QPropertyAnimation
from PySide2.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel


class Collapsible(QFrame):
    def __init__(self, title, html, expanded=False, parent=None):
        super(Collapsible, self).__init__(parent)
        self.setObjectName("Collapsible")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._title = title
        self.btn = QPushButton(("▾  " if expanded else "▸  ") + title)
        self.btn.setObjectName("CollapseHead")
        self.btn.setCheckable(True)
        self.btn.setChecked(expanded)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._toggle)
        v.addWidget(self.btn)

        self.body = QLabel(html)
        self.body.setObjectName("CollapseBody")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.RichText)
        self.body.setOpenExternalLinks(True)
        self.body.setVisible(expanded)
        self.body.setMaximumHeight(16777215 if expanded else 0)
        v.addWidget(self.body)

        self._anim = QPropertyAnimation(self.body, b"maximumHeight", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_done)

    def _toggle(self):
        on = self.btn.isChecked()
        self.btn.setText(("▾  " if on else "▸  ") + self._title)
        self._anim.stop()
        # 目标高度按内容真实高度算(受当前宽度换行影响)
        h = self.body.sizeHint().height()
        if on:
            self.body.setVisible(True)
            self.body.setMaximumHeight(0)
            self._anim.setStartValue(0)
            self._anim.setEndValue(h)
        else:
            self._anim.setStartValue(self.body.height())
            self._anim.setEndValue(0)
        self._anim.start()

    def _on_anim_done(self):
        if not self.btn.isChecked():
            self.body.setVisible(False)          # 收起后彻底隐藏,不占位
        else:
            self.body.setMaximumHeight(16777215) # 展开后解除限高,允许后续自适应
