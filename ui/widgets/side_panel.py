# -*- coding: utf-8 -*-
"""
RightPanel —— 右侧常驻面板(纵向可堆叠、可折叠的多分区)
========================================================
从"一次只装一块内容"升级为"纵向 QSplitter 承载多个分区":文件预览、人工复核、
结果明细可**同屏共存**,各分区有自己的标题条(标题 + 折叠 + 可选关闭),彼此按
高度公平分配、可拖拽调节、可折叠让路。展开/收起整块面板的宽度由 MainWindow 的
横向 QSplitter 驱动(见 open_panel/close_panel)。

分区以 key 唯一标识:add_section 同 key 即替换内容;remove_section 移除。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal, QEasingCurve, QPropertyAnimation
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QWidget, QSplitter,
                               QSizePolicy)


class PanelSection(QFrame):
    """单个分区:标题条(折叠钮 + 标题 + 可选关闭钮)+ 可滚动内容区。"""
    closed = Signal(str)          # 关闭钮点击,携带本分区 key
    toggled = Signal()            # 折叠/展开后发出,供容器重排高度

    HEADER_H = 40                 # 标题条固定高;折叠态整块即缩到这个高度,避免裁切错位

    def __init__(self, key, title, widget, closable=True, parent=None):
        super(PanelSection, self).__init__(parent)
        self.setObjectName("PanelSection")
        self._key = key
        self._collapsed = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QFrame(); header.setObjectName("PanelHeader")
        header.setFixedHeight(self.HEADER_H)   # 固定高,与折叠态高度一致,内容不被挤压
        hb = QHBoxLayout(header)
        hb.setContentsMargins(10, 0, 8, 0)
        hb.setSpacing(6)
        self._fold = QPushButton("▾")
        self._fold.setObjectName("PanelFold")
        self._fold.setCursor(Qt.PointingHandCursor)
        self._fold.setFixedSize(22, 22)
        self._fold.setToolTip("折叠 / 展开")
        self._fold.clicked.connect(self.toggle)
        hb.addWidget(self._fold, 0, Qt.AlignVCenter)
        self._title = QLabel(title)
        self._title.setObjectName("PanelTitle")
        hb.addWidget(self._title, 1, Qt.AlignVCenter)
        if closable:
            close_btn = QPushButton("✕")
            close_btn.setObjectName("PanelClose")
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setFixedSize(24, 24)
            close_btn.clicked.connect(lambda: self.closed.emit(self._key))
            hb.addWidget(close_btn, 0, Qt.AlignVCenter)
        v.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setObjectName("PanelScroll")
        self._scroll.setWidget(widget if widget is not None else QWidget())
        v.addWidget(self._scroll, 1)
        self._header = header

    # ---------- 访问 ----------
    def key(self):
        return self._key

    def set_title(self, title):
        self._title.setText(title or "")

    def set_widget(self, widget):
        old = self._scroll.takeWidget()
        if old is not None and old is not widget:
            old.setParent(None)
            old.deleteLater()
        self._scroll.setWidget(widget if widget is not None else QWidget())

    def is_collapsed(self):
        return self._collapsed

    def toggle(self):
        self._collapsed = not self._collapsed
        self._fold.setText("▸" if self._collapsed else "▾")
        self._scroll.setVisible(not self._collapsed)
        # 折叠态:整块缩到标题条固定高(容器据此重排);展开态:恢复自由伸缩
        if self._collapsed:
            self.setMaximumHeight(self.HEADER_H)
        else:
            self.setMaximumHeight(16777215)
        self.toggled.emit()

    def header_height(self):
        return self.HEADER_H


class RightPanel(QFrame):
    closed = Signal()                     # 兼容旧接口:无分区时收起整块面板
    section_closed = Signal(str)          # 某分区被关闭,携带其 key

    def __init__(self, parent=None):
        super(RightPanel, self).__init__(parent)
        self.setObjectName("RightPanel")
        self._sections = {}               # key -> PanelSection
        self._order = []                  # key 顺序(添加序)
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setObjectName("PanelSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(4)
        v.addWidget(self._splitter, 1)
        # 无分区时的占位:居中提示"暂无内容",让侧栏默认可见也不显空洞
        self._placeholder = QWidget()
        self._placeholder.setObjectName("PanelEmpty")
        pv = QVBoxLayout(self._placeholder)
        pv.setContentsMargins(16, 16, 16, 16)
        hint = QLabel("暂无内容\n选择文件预览,或点功能页的“人工核对”")
        hint.setObjectName("PanelEmptyHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        pv.addStretch(1); pv.addWidget(hint); pv.addStretch(1)
        self._splitter.addWidget(self._placeholder)

    # ---------- 分区 API ----------
    def add_section(self, key, title, widget, closable=True):
        """新增或替换一个分区。返回该 PanelSection。同 key 复用并替换内容。"""
        self._drop_placeholder()
        if key in self._sections:
            sec = self._sections[key]
            sec.set_title(title)
            sec.set_widget(widget)
            return sec
        sec = PanelSection(key, title, widget, closable=closable)
        sec.closed.connect(self._on_section_closed)
        sec.toggled.connect(self._rebalance)
        self._sections[key] = sec
        self._order.append(key)
        self._splitter.addWidget(sec)
        self._rebalance()
        return sec

    def remove_section(self, key):
        sec = self._sections.pop(key, None)
        if sec is None:
            return
        if key in self._order:
            self._order.remove(key)
        sec.setParent(None)
        sec.deleteLater()
        if not self._sections:
            self._splitter.addWidget(self._placeholder)
            self._placeholder.show()
        self._rebalance()

    def has_sections(self):
        return bool(self._sections)

    def section_keys(self):
        return list(self._order)

    def _drop_placeholder(self):
        if self._placeholder.parent() is not None:
            self._placeholder.setParent(None)

    def _on_section_closed(self, key):
        self.remove_section(key)
        self.section_closed.emit(key)
        if not self._sections:
            self.closed.emit()            # 全空 -> 通知主窗口收起整块

    def _rebalance(self):
        """展开的分区平分高度,折叠的只占标题条高。"""
        secs = [self._sections[k] for k in self._order]
        if not secs:
            return
        total = max(self._splitter.height(), 1)
        collapsed = [s for s in secs if s.is_collapsed()]
        expanded = [s for s in secs if not s.is_collapsed()]
        ch = sum(s.header_height() for s in collapsed)
        share = int((total - ch) / max(1, len(expanded))) if expanded else 0
        sizes = []
        for s in secs:
            sizes.append(s.header_height() if s.is_collapsed() else max(80, share))
        self._splitter.setSizes(sizes)

    def resizeEvent(self, e):
        super(RightPanel, self).resizeEvent(e)
        self._rebalance()

    # ---------- 兼容旧接口(单内容) ----------
    def set_content(self, widget, title=""):
        """兼容旧 open_panel:等价于加/替换一个 key='main' 的可关闭分区。"""
        self.add_section("main", title, widget, closable=True)

    def clear_content(self):
        for key in list(self._order):
            self.remove_section(key)
