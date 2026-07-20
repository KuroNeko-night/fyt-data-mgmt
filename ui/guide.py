# -*- coding: utf-8 -*-
"""
使用指引 —— 聚光灯式分步引导(coach-mark)
=========================================
在功能页上覆盖一层可交互引导:页面变暗、聚光灯高亮当前要操作的区域并
浮出说明气泡,分步带用户走一遍"每个地方放什么、怎么看结果"。

高亮的是**真实界面元素**(非录制动画),故永远与界面同步、随明暗主题变化、
离线可用、零素材。各功能页通过 BasePage.guide_steps() 声明步骤即可复用。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import (Qt, QEvent, QRect, QRectF, QPoint, QSize,
                            QEasingCurve, QVariantAnimation, Signal)
from PySide2.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide2.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton)

from . import theme


class GuideOverlay(QWidget):
    """覆盖在功能页上的聚光灯引导层。steps: [(widget|None, 标题, 说明), ...]。"""
    finished = Signal()

    def __init__(self, page, steps, scroll=None):
        super(GuideOverlay, self).__init__(page)
        self._page = page
        self._steps = list(steps)
        self._scroll = scroll
        self._idx = 0
        self._spot = QRect()
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setGeometry(page.rect())
        page.installEventFilter(self)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._place_card)
        self._build_card()

    def _build_card(self):
        """浮动说明卡:标题 + 说明 + 进度圆点 + 跳过/上一步/下一步。"""
        C = theme.COLORS
        self._card = QFrame(self)
        self._card.setObjectName("Card")
        self._card.setFixedWidth(320)
        v = QVBoxLayout(self._card)
        v.setContentsMargins(18, 15, 18, 13); v.setSpacing(9)
        self._title = QLabel("")
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size:15px; font-weight:bold; color:%s;"
                                  % C.get("heading", "#1f2d3d"))
        v.addWidget(self._title)
        self._body = QLabel("")
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.RichText)     # 富文本才能真正拉开行距(QSS line-height 对 QLabel 无效)
        self._body_color = C.get("text", "#222b3a")
        v.addWidget(self._body)
        row = QHBoxLayout(); row.setSpacing(8)
        self._dots = QLabel("")
        self._dots.setStyleSheet("color:%s; font-size:12px;" % C.get("accent", "#2f6bd8"))
        row.addWidget(self._dots); row.addStretch(1)
        self._skip = self._btn("跳过", "Mini", self.finish)
        self._prev = self._btn("上一步", "Ghost", self.prev)
        self._next = self._btn("下一步", "Primary", self.next)
        row.addWidget(self._skip); row.addWidget(self._prev); row.addWidget(self._next)
        v.addLayout(row)

    def _btn(self, text, obj, slot):
        b = QPushButton(text); b.setObjectName(obj)
        b.setCursor(Qt.PointingHandCursor)
        # 兜底最小高度:卡片在 __init__ 建成、样式表尚未 polish,adjustSize 会拿到
        # 偏小高度而把最大字号的 Primary 文字上下切掉。钉死最小高度即与 polish 时机无关。
        b.setMinimumHeight(38)
        b.clicked.connect(slot)
        return b

    def _html(self, text):
        """把说明文本转富文本:转义 + 段间留白拉开行距(QLabel QSS line-height 无效)。

        原文里的换行按"段落"处理,段间加 6px 上边距,读起来不挤。"""
        from html import escape
        paras = [escape(s) for s in (text or "").split("\n")]
        body = "".join(
            "<div style='margin-top:%dpx;'>%s</div>" % (0 if i == 0 else 6, s or "&nbsp;")
            for i, s in enumerate(paras))
        return ("<div style='font-size:13px; color:%s;'>%s</div>"
                % (self._body_color, body))

    # ---------- 生命周期 ----------
    def start(self):
        self.setGeometry(self._page.rect())
        self.show(); self.raise_(); self.setFocus()
        self._goto(0, animate=True)

    def finish(self):
        try:
            self._anim.stop()
        except Exception:
            pass
        self._page.removeEventFilter(self)
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # ---------- 步进 ----------
    def next(self):
        if self._idx >= len(self._steps) - 1:
            self.finish(); return
        self._goto(self._idx + 1)

    def prev(self):
        if self._idx > 0:
            self._goto(self._idx - 1)

    def _goto(self, idx, animate=True):
        idx = max(0, min(idx, len(self._steps) - 1))
        self._idx = idx
        w, title, body = self._steps[idx]
        self._title.setText(title)
        self._body.setText(self._html(body))
        self._sync_nav()
        target = self._rect_of(w)
        self._place_card(target)
        if not animate or (self._spot.isNull() or self._spot.isEmpty()):
            self._spot = target
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._spot)
        self._anim.setEndValue(target)
        self._anim.start()

    def _sync_nav(self):
        n = len(self._steps)
        self._dots.setText("  ".join("●" if i == self._idx else "○" for i in range(n)))
        self._prev.setVisible(self._idx > 0)
        self._next.setText("完成" if self._idx == n - 1 else "下一步")

    # ---------- 几何 ----------
    def _rect_of(self, w):
        """目标控件在本覆盖层坐标系里的高亮矩形;w 为 None 返回空矩形(整屏变暗)。"""
        if w is None:
            return QRect()
        try:
            if self._scroll is not None:
                self._scroll.ensureWidgetVisible(w, 40, 40)
            tl = w.mapTo(self._page, QPoint(0, 0))
            r = QRect(tl, w.size()).adjusted(-6, -6, 6, 6)
            vp = self._viewport_rect()
            if vp is not None:
                r = r.intersected(vp)
            return r
        except Exception:
            return QRect()

    def _viewport_rect(self):
        """滚动视口在本层坐标系里的矩形,用于裁剪高亮不越过表头/边缘。"""
        if self._scroll is None:
            return None
        try:
            vp = self._scroll.viewport()
            tl = vp.mapTo(self._page, QPoint(0, 0))
            return QRect(tl, vp.size())
        except Exception:
            return None

    def _on_anim(self, r):
        self._spot = r
        self.update()

    def _place_card(self, target=None):
        """把说明卡放到高亮块下方(放不下则上方;无目标则居中)。"""
        if target is None:
            target = self._spot
        self._card.adjustSize()
        cw, ch = self._card.width(), self._card.height()
        W, H = self.width(), self.height()
        m = 16
        if target is None or target.isNull() or target.isEmpty():
            x = (W - cw) // 2; y = (H - ch) // 2
        else:
            x = min(max(m, target.left()), W - cw - m)
            if target.bottom() + m + ch <= H - m:
                y = target.bottom() + m
            elif target.top() - m - ch >= m:
                y = target.top() - m - ch
            else:
                y = max(m, min((H - ch) // 2, H - ch - m))
        self._card.move(int(x), int(y))
        self._card.raise_()

    # ---------- 绘制 / 交互 ----------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 全层变暗,再挖出高亮圆角洞(洞内露出真实界面)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        r = self._spot
        if r is not None and not r.isNull() and not r.isEmpty():
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(r), 10, 10)
            path = path.subtracted(hole)
        p.fillPath(path, QColor(11, 16, 26, 205))
        # 高亮描边环:强调色
        if r is not None and not r.isNull() and not r.isEmpty():
            pen = QPen(QColor(theme.COLORS.get("accent", "#2f6bd8")), 2)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(r).adjusted(1, 1, -1, -1), 10, 10)
        p.end()

    def mousePressEvent(self, e):
        # 点暗区前进一步;点在高亮洞内则放行给下面的真实控件(不拦截)
        r = self._spot
        if r is not None and not r.isEmpty() and r.contains(e.pos()):
            e.ignore(); return
        self.next()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self.finish()
        elif k in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.next()
        elif k == Qt.Key_Left:
            self.prev()
        else:
            super(GuideOverlay, self).keyPressEvent(e)

    def eventFilter(self, obj, ev):
        # 页面尺寸变化时,覆盖层随之铺满并重定位当前步
        if obj is self._page and ev.type() == QEvent.Resize:
            self.setGeometry(self._page.rect())
            self._spot = self._rect_of(self._steps[self._idx][0])
            self._place_card(self._spot)
            self.update()
        return super(GuideOverlay, self).eventFilter(obj, ev)
