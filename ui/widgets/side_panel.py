# -*- coding: utf-8 -*-
"""
RightPanel —— 右侧常驻面板(选项卡式)
=====================================
承载多块内容(文件预览、人工复核、结果明细),每块是一个**选项卡**:
- 业务分区(复核/结果)可**独立关闭**(选项卡上的 ✕),互不影响;
- "文件预览"分区**不带关闭钮**,其显隐由顶栏切换钮单独控制。

分区以 key 唯一标识:add_section 同 key 即替换内容;remove_section 移除。
整块面板的展开/收起宽度由 MainWindow 的横向 QSplitter 驱动。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QScrollArea, QWidget,
                               QTabWidget, QTabBar)


class RightPanel(QFrame):
    """右侧选项卡面板。每个分区一个 tab,业务分区可独立关闭,预览分区不可关闭。"""
    closed = Signal()                     # 无任何分区时发出(供主窗口收起整块)
    section_closed = Signal(str)          # 某分区被用户关闭,携带其 key

    def __init__(self, parent=None):
        super(RightPanel, self).__init__(parent)
        self.setObjectName("RightPanel")
        self._widgets = {}                # key -> 内容 widget(scroll 的子)
        self._scrolls = {}                # key -> QScrollArea(装进 tab 的那层)
        self._closable = {}               # key -> bool
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("PanelTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.setTabsClosable(True)      # 关闭钮按分区单独控制(不可关的抹掉按钮)
        self._tabs.setElideMode(Qt.ElideRight)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        v.addWidget(self._tabs, 1)

    # ---------- 分区 API ----------
    def add_section(self, key, title, widget, closable=True):
        """新增或替换一个分区(选项卡)。同 key 复用并替换内容。返回内容 widget。"""
        self._closable[key] = closable
        if key in self._scrolls:                       # 已有 -> 替换内容与标题
            scroll = self._scrolls[key]
            old = scroll.takeWidget()
            if old is not None and old is not widget:
                old.setParent(None); old.deleteLater()
            scroll.setWidget(widget if widget is not None else QWidget())
            self._widgets[key] = widget
            idx = self._tabs.indexOf(scroll)
            if idx >= 0:
                self._tabs.setTabText(idx, title or "")
                self._tabs.setCurrentIndex(idx)
            return widget
        scroll = QScrollArea()                          # 新建一层滚动区装进 tab
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("PanelScroll")
        scroll.setWidget(widget if widget is not None else QWidget())
        self._scrolls[key] = scroll
        self._widgets[key] = widget
        idx = self._tabs.addTab(scroll, title or "")
        if not closable:                                # 预览分区:抹掉这条 tab 的 ✕
            self._strip_close_button(idx)
        self._tabs.setCurrentIndex(idx)
        return widget

    def remove_section(self, key):
        scroll = self._scrolls.pop(key, None)
        self._widgets.pop(key, None)
        self._closable.pop(key, None)
        if scroll is None:
            return
        idx = self._tabs.indexOf(scroll)
        if idx >= 0:
            self._tabs.removeTab(idx)
        scroll.setParent(None); scroll.deleteLater()
        if not self._scrolls:
            self.closed.emit()

    def has_sections(self):
        return bool(self._scrolls)

    def has_section(self, key):
        return key in self._scrolls

    def section_keys(self):
        # 按当前 tab 顺序返回(用户可拖动重排)
        order = []
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            for k, s in self._scrolls.items():
                if s is w:
                    order.append(k); break
        return order

    def _strip_close_button(self, idx):
        """去掉某个 tab 的关闭钮(不可关闭分区,如文件预览)。"""
        bar = self._tabs.tabBar()
        for side in (QTabBar.RightSide, QTabBar.LeftSide):
            btn = bar.tabButton(idx, side)
            if btn is not None:
                btn.deleteLater()
                bar.setTabButton(idx, side, None)

    def _on_tab_close_requested(self, idx):
        w = self._tabs.widget(idx)
        key = None
        for k, s in self._scrolls.items():
            if s is w:
                key = k; break
        if key is None or not self._closable.get(key, True):
            return                                       # 不可关分区:忽略
        self.remove_section(key)
        self.section_closed.emit(key)

    # ---------- 兼容旧接口(单内容) ----------
    def set_content(self, widget, title=""):
        self.add_section("main", title, widget, closable=True)

    def clear_content(self):
        for key in self.section_keys():
            self.remove_section(key)
