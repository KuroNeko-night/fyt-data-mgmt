# -*- coding: utf-8 -*-
"""
首次使用引导 —— 几页轻量介绍，带步进动画
========================================
第一次运行时弹出，介绍核心功能与输出位置。看过后不再自动弹。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QWidget,
                               QGraphicsOpacityEffect)

from .. import theme
from core import paths

STEPS = [
    ("欢迎使用 峰运通数据管理系统",
     "常用业务现在合而为一：\n\n"
     "· 考勤数据填报　· 工时对账\n· 到料明细表　· 销售表透视\n"
     "· 采购数对账　· 送货计划表\n\n"
     "另配金额大写、批量重命名、文本 / PDF / Excel 工具箱。\n"
     "左侧按“人事 / 销售 / 工具箱”等分组，点一下即可切换。"),
    ("统一的输出位置",
     "过去结果散落在各处，现在统一存到：\n\n"
     "  文档 / 峰运通数据管理系统 / 输出 / 功能 / 时间戳\n\n"
     "每次处理完会自动弹开所在文件夹。可在“设置”里改成源文件旁或自定义目录。"),
    ("拖拽 · 联动 · 可信度",
     "· 文件可直接拖到卡片里，支持多选、去重；\n"
     "· 考勤填报的结果可一键送去“工时对账”；\n"
     "· 对账与透视会给出可信度评分，低分会提示复核。\n\n"
     "准备好了，开始使用吧。"),
]


class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super(OnboardingDialog, self).__init__(parent)
        self.setWindowTitle("欢迎")
        self.setModal(True)
        self.setStyleSheet(theme.stylesheet())
        self._idx = 0
        self._build()
        theme.fit_dialog(self, 520, 400)     # 自适应屏幕并可缩放，避免小屏/高分屏下按钮出界

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)
        self.stack = QStackedWidget()
        for title, body in STEPS:
            self.stack.addWidget(self._page(title, body))
        lay.addWidget(self.stack, 1)

        self.dots = QLabel(); self.dots.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.dots)

        row = QHBoxLayout()
        self.skip = QPushButton("跳过"); self.skip.setObjectName("Mini")
        self.skip.clicked.connect(self.accept)
        row.addWidget(self.skip); row.addStretch(1)
        self.next = QPushButton("下一步"); self.next.setObjectName("Primary")
        self.next.clicked.connect(self._advance)
        row.addWidget(self.next)
        lay.addLayout(row)
        self._sync()

    def _page(self, title, body):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(12)
        t = QLabel(title); t.setStyleSheet("font-size:17px; font-weight:bold; color:%s;"
                                           % theme.COLORS["heading"])
        t.setWordWrap(True)
        b = QLabel(body); b.setWordWrap(True)
        b.setStyleSheet("font-size:13px; color:%s; line-height:150%%;" % theme.COLORS["text"])
        v.addWidget(t); v.addWidget(b, 1)
        return w

    def _advance(self):
        if self._idx >= len(STEPS) - 1:
            self.accept(); return
        self._idx += 1
        self.stack.setCurrentIndex(self._idx)
        self._fade(self.stack.currentWidget())
        self._sync()

    def _sync(self):
        self.dots.setText("   ".join("●" if i == self._idx else "○"
                                     for i in range(len(STEPS))))
        self.next.setText("开始使用" if self._idx == len(STEPS) - 1 else "下一步")

    def _fade(self, w):
        eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(220); a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: w.setGraphicsEffect(None))
        a.start(); self._a = a
