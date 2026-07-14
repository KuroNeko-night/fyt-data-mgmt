# -*- coding: utf-8 -*-
"""ClickableCard —— 首页快捷入口卡片（整卡可点，含矢量图标/标题/说明）。"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QFrame, QVBoxLayout, QLabel

from .. import icons


class ClickableCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key, icon_name, title, desc, parent=None):
        super(ClickableCard, self).__init__(parent)
        self.setObjectName("EntryCard")
        self._key = key
        self._icon_name = icon_name
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(8)
        self._ic = QLabel(); self._ic.setObjectName("EntryIcon")
        self._ic.setFixedSize(28, 28); self._ic.setScaledContents(True)
        v.addWidget(self._ic)
        t = QLabel(title); t.setObjectName("EntryTitle")
        v.addWidget(t)
        d = QLabel(desc); d.setObjectName("EntryDesc")
        d.setWordWrap(True)
        v.addWidget(d, 1)
        self.refresh_icon()

    def refresh_icon(self):
        """按当前主题色重绘图标（主题切换时调用）。

        2× 物理分辨率 + setScaledContents 定尺 QLabel：高/低 DPI 都清晰不裁切。"""
        self._ic.setPixmap(icons.pixmap(self._icon_name, 56, None, 1.0))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit(self._key)
        super(ClickableCard, self).mouseReleaseEvent(e)
