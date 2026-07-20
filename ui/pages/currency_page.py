# -*- coding: utf-8 -*-
"""金额大写页 —— 输入数字,实时转成中文大写人民币,可一键复制。"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                               QLineEdit, QPushButton, QApplication)

from .base_page import BasePage
from .. import theme
from core import currency_core


class CurrencyPage(BasePage):
    CONTENT_MAX = 720

    def __init__(self, main):
        super(CurrencyPage, self).__init__(
            main, "金额大写",
            "输入阿拉伯数字金额,自动转成规范的中文大写人民币,开票、合同、报销可直接用。")

    def build_body(self, layout):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(12)

        row = QHBoxLayout(); row.setSpacing(10)
        row.addWidget(QLabel("金额(元)"))
        self.ed = QLineEdit()
        self.ed.setPlaceholderText("例如 12345.6，支持负数与千分位逗号")
        self.ed.textChanged.connect(self._convert)
        row.addWidget(self.ed, 1)
        v.addLayout(row)

        self.out = QLabel("—")
        self.out.setObjectName("CapResult")
        self.out.setWordWrap(True)
        self.out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.out.setMinimumHeight(64)
        v.addWidget(self.out)

        bar = QHBoxLayout()
        self.hint = QLabel("在上方输入金额即可"); self.hint.setObjectName("Hint")
        bar.addWidget(self.hint); bar.addStretch(1)
        self.btn_copy = QPushButton("复制大写"); self.btn_copy.setObjectName("Ghost")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_copy.setEnabled(False)
        bar.addWidget(self.btn_copy)
        v.addLayout(bar)

        layout.addWidget(card)
        layout.addStretch(1)

    def _convert(self, *_):
        text = self.ed.text()
        if not text.strip():
            self.out.setText("—"); self.hint.setText("在上方输入金额即可")
            self.btn_copy.setEnabled(False); return
        ok, res = currency_core.to_capital(text)
        self.out.setText(res)
        self.btn_copy.setEnabled(ok)
        self.hint.setText("转换成功,可复制" if ok else res)

    def _copy(self):
        cb = QApplication.clipboard()
        cb.setText(self.out.text())
        self.hint.setText("已复制到剪贴板")

    def on_theme_changed(self):
        super(CurrencyPage, self).on_theme_changed()

    def guide_steps(self):
        return [
            (None, "欢迎使用金额大写",
             "输入阿拉伯数字金额,自动转成规范的中文大写人民币,开票、合同、报销可直接用。"),
            (self.ed, "① 输入金额",
             "在这里输入数字,如 12345.6。支持负数与千分位逗号,边输边转。"),
            (self.out, "② 看大写结果",
             "转换结果实时显示在这里,如「壹万贰仟叁佰肆拾伍元陆角整」。可用鼠标选中复制。"),
            (self.btn_copy, "③ 一键复制",
             "点「复制大写」把结果放进剪贴板,直接粘到票据/合同里即可。"),
        ]
