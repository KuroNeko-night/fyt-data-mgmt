# -*- coding: utf-8 -*-
"""文本工具箱页 —— 粘贴文本,一键去重/排序/去空行/加行号/提取邮箱手机号等。"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QFrame, QPushButton, QPlainTextEdit, QCheckBox,
                               QApplication)
from ..animations import AnimatedCheckBox as QCheckBox   # 勾选带打勾动画

from .base_page import BasePage
from core import text_core as tc

# (按钮文字, 处理函数)。函数签名统一 (text)->text,带选项的用 lambda 包一层(运行时读复选框)。
_OPS = [
    ("行去重", "dedup"), ("排序", "sort"), ("倒序", "reverse"),
    ("去空行", "remove_empty"), ("去首尾空格", "trim"), ("压缩空格", "collapse"),
    ("转大写", "upper"), ("转小写", "lower"), ("加行号", "line_numbers"),
    ("提取邮箱", "email"), ("提取手机号", "phone"), ("提取网址", "url"),
]


class TextPage(BasePage):
    CONTENT_MAX = None

    def __init__(self, main):
        super(TextPage, self).__init__(
            main, "文本工具箱",
            "粘贴或输入文本,按需一键处理:去重、排序、去空行、加行号、"
            "提取邮箱/手机号/网址等。结果可复制或回填。")

    def build_body(self, layout):
        top = QHBoxLayout(); top.setSpacing(14)
        top.addWidget(self._editor_card("原文本", True), 1)
        top.addWidget(self._editor_card("结果", False), 1)
        layout.addLayout(top, 1)
        layout.addWidget(self._ops_card())

    def _editor_card(self, title, is_src):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(14, 12, 14, 12); v.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel(title); t.setObjectName("CardTitle"); head.addWidget(t)
        head.addStretch(1)
        lbl = QLabel(""); lbl.setObjectName("Hint"); head.addWidget(lbl)
        v.addLayout(head)
        ed = QPlainTextEdit(); ed.setMinimumHeight(300)
        v.addWidget(ed, 1)
        btns = QHBoxLayout(); btns.setSpacing(6)
        if is_src:
            self.src = ed; self.src_stat = lbl
            ed.textChanged.connect(self._update_stat)
            b_clr = QPushButton("清空"); b_clr.setObjectName("Mini")
            b_clr.clicked.connect(lambda: ed.setPlainText(""))
            btns.addStretch(1); btns.addWidget(b_clr)
        else:
            self.dst = ed; self.dst_stat = lbl
            ed.setReadOnly(True)
            b_copy = QPushButton("复制结果"); b_copy.setObjectName("Ghost")
            b_copy.clicked.connect(self._copy)
            b_back = QPushButton("← 回填到原文本"); b_back.setObjectName("Mini")
            b_back.clicked.connect(self._back)
            btns.addStretch(1); btns.addWidget(b_back); btns.addWidget(b_copy)
        v.addLayout(btns)
        return card

    def _ops_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(14, 12, 14, 12); v.setSpacing(10)
        t = QLabel("操作"); t.setObjectName("SecTitle"); v.addWidget(t)

        opt = QHBoxLayout(); opt.setSpacing(16)
        self.cb_ic = QCheckBox("忽略大小写(去重/排序)")
        self.cb_num = QCheckBox("按数字排序")
        self.cb_desc = QCheckBox("降序/倒序")
        self.cb_pad = QCheckBox("行号补零对齐")
        for c in (self.cb_ic, self.cb_num, self.cb_desc, self.cb_pad):
            opt.addWidget(c)
        opt.addStretch(1)
        v.addLayout(opt)

        grid = QGridLayout(); grid.setSpacing(8)
        for i, (label, key) in enumerate(_OPS):
            b = QPushButton(label); b.setObjectName("Mini")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._apply(k))
            grid.addWidget(b, i // 6, i % 6)
        v.addLayout(grid)
        return card

    # ---------- 逻辑 ----------
    def _apply(self, key):
        text = self.src.toPlainText()
        ic = self.cb_ic.isChecked()
        if key == "dedup":
            res = tc.dedup_lines(text, ignore_case=ic)
        elif key == "sort":
            res = tc.sort_lines(text, reverse=self.cb_desc.isChecked(),
                                numeric=self.cb_num.isChecked(), ignore_case=ic)
        elif key == "reverse":
            res = tc.reverse_lines(text)
        elif key == "remove_empty":
            res = tc.remove_empty_lines(text)
        elif key == "trim":
            res = tc.trim_lines(text)
        elif key == "collapse":
            res = tc.collapse_spaces(text)
        elif key == "upper":
            res = tc.to_upper(text)
        elif key == "lower":
            res = tc.to_lower(text)
        elif key == "line_numbers":
            res = tc.add_line_numbers(text, pad=self.cb_pad.isChecked())
        elif key in ("email", "phone", "url"):
            res = tc.extract(text, key)
            if not res:
                res = "(未找到%s)" % {"email": "邮箱", "phone": "手机号", "url": "网址"}[key]
        else:
            res = text
        self.dst.setPlainText(res)
        self._update_stat()

    def _update_stat(self):
        s = tc.stats(self.src.toPlainText())
        self.src_stat.setText("行 %d · 字符 %d" % (s["lines"], s["chars"]))
        d = tc.stats(self.dst.toPlainText())
        self.dst_stat.setText("行 %d · 字符 %d" % (d["lines"], d["chars"]))

    def _copy(self):
        QApplication.clipboard().setText(self.dst.toPlainText())
        self.dst_stat.setText("已复制到剪贴板")

    def _back(self):
        self.src.setPlainText(self.dst.toPlainText())
