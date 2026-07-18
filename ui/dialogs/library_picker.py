# -*- coding: utf-8 -*-
"""
从数据库选表对话框
==================
功能页调用：给定一个或多个类别，列出库中该类表，用户勾选后返回路径。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QAbstractItemView)

from .. import theme
from core import library


from ..animations import AnimatedDialog


class LibraryPicker(AnimatedDialog):
    def __init__(self, categories, multi=True, parent=None, title="从数据库选择"):
        super(LibraryPicker, self).__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(theme.stylesheet())
        self._multi = multi
        self._cats = categories if isinstance(categories, (list, tuple)) else [categories]
        self._build()
        self._load()
        theme.fit_dialog(self, 560, 460)     # 自适应屏幕并可缩放

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)
        cat_names = "、".join(library.CATEGORY_TITLES.get(c, c) for c in self._cats)
        head = QLabel("数据库中「%s」的表：" % cat_names)
        head.setObjectName("SecTitle")
        head.setWordWrap(True)
        v.addWidget(head)

        self.listw = QListWidget()
        self.listw.setSelectionMode(
            QAbstractItemView.ExtendedSelection if self._multi
            else QAbstractItemView.SingleSelection)
        self.listw.itemDoubleClicked.connect(lambda *_: self.accept())
        v.addWidget(self.listw, 1)

        self.empty = QLabel("该类别下暂无表。请先在“数据库”页导入。")
        self.empty.setObjectName("Hint")
        self.empty.hide()
        v.addWidget(self.empty)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消"); cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("选择"); ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        v.addLayout(row)

    def _load(self):
        self._items = []
        seen = set()                       # 多标签文件在多类别 picker 里只列一次(按路径去重)
        for cat in self._cats:
            for it in library.list_items(cat):
                key = it.get("path") or (it.get("category"), it.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                self._items.append(it)
        self._items.sort(key=lambda x: x.get("updated", ""), reverse=True)
        for it in self._items:
            label = "%s   ·   %s   ·   更新 %s   ·   可信度 %d%%" % (
                it["name"], library.CATEGORY_TITLES.get(it["category"], ""),
                it.get("updated", ""), it.get("confidence", 0))
            qi = QListWidgetItem(label)
            qi.setToolTip(it.get("path", ""))
            self.listw.addItem(qi)
        if not self._items:
            self.listw.hide()
            self.empty.show()

    def chosen(self):
        """返回选中的文件路径列表。"""
        out = []
        for i in range(self.listw.count()):
            if self.listw.item(i).isSelected():
                p = self._items[i].get("path", "")
                if p and os.path.exists(p):
                    out.append(p)
        return out
