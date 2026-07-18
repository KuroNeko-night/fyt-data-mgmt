# -*- coding: utf-8 -*-
"""
RightPanel —— 右侧滑出面板（承载原"子窗口"内容）
=================================================
结果 / 复核 / 参数确认类内容不再单开窗口打断，而是嵌进主窗口右侧的
可拖拽面板：顶部标题条(标题 + 关闭) + 可滚动内容区。

自身只负责"装什么、怎么显示"；展开/收起的宽度与分隔条占比由
MainWindow 通过 QSplitter 驱动（见 main_window.open_panel/close_panel）。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QWidget)


class RightPanel(QFrame):
    closed = Signal()                     # 用户点关闭时发出,供主窗口收起分隔条

    def __init__(self, parent=None):
        super(RightPanel, self).__init__(parent)
        self.setObjectName("RightPanel")
        self._content = None
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QFrame(); header.setObjectName("PanelHeader")
        hb = QHBoxLayout(header)
        hb.setContentsMargins(16, 0, 8, 0)
        hb.setSpacing(8)
        self.title = QLabel("")
        self.title.setObjectName("PanelTitle")
        hb.addWidget(self.title, 1)
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("PanelClose")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.clicked.connect(self.closed.emit)
        hb.addWidget(self.close_btn, 0, Qt.AlignVCenter)
        v.addWidget(header)

        # 可滚动内容区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setObjectName("PanelScroll")
        self._scroll.setWidget(QWidget())   # 初始空白占位
        v.addWidget(self._scroll, 1)

    # ---------- 供主窗口调用 ----------
    def set_content(self, widget, title=""):
        """换入新内容部件并更新标题。

        用 takeWidget() 取出旧部件而非直接 setWidget —— 后者会 **删除** 旧部件,
        会误删调用方仍持有的内容/占位。取出后旧部件交还调用方(或随本次丢弃)。"""
        old = self._scroll.takeWidget()
        if old is not None and old is not widget:
            old.setParent(None)
            old.deleteLater()               # 旧面板内容用完即弃(每次打开都新建)
        self._content = widget
        self.title.setText(title or "")
        self._scroll.setWidget(widget if widget is not None else QWidget())

    def clear_content(self):
        """清空内容，显示空白占位。"""
        self.set_content(None, "")

