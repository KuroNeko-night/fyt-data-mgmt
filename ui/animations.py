# -*- coding: utf-8 -*-
"""
交互微动画组件
==============
· AnimatedComboBox：下拉像"抽屉"一样从上向下拉开(高度动画)，非瞬间弹出；
· AnimatedCheckBox：勾选时对勾描绘 + 填充带回弹地放大，取消时反向。
两者纯几何/描绘动画，不走离屏缓冲，文字保持清晰。
兼容 Windows 7 + Python 3.8 + PySide2(Qt5.15)。
"""
from PySide2.QtCore import (Qt, QRect, QPoint, QPointF, QEasingCurve, QTimer,
                            QPropertyAnimation, QVariantAnimation)
from PySide2.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide2.QtWidgets import QComboBox, QCheckBox, QDialog

from . import theme


class AnimatedComboBox(QComboBox):
    """下拉列表"抽屉式"拉开：弹出后把承载窗口高度从 0 动画到目标高。"""
    def showPopup(self):
        super(AnimatedComboBox, self).showPopup()
        try:
            container = self.view().window()      # 弹出列表所在的顶层窗口
            final = container.geometry()
            if final.height() <= 2:
                return
            start = QRect(final.x(), final.y(), final.width(), 1)
            container.setGeometry(start)
            anim = QPropertyAnimation(container, b"geometry", self)
            anim.setDuration(170)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(start)
            anim.setEndValue(final)
            anim.start()
            self._popup_anim = anim               # 存引用防 GC
        except Exception:
            pass                                  # 动画失败不影响功能


class AnimatedCheckBox(QCheckBox):
    """自绘勾选框：勾选时填充带回弹放大 + 对勾逐段描绘,取消时反向收回。

    完全自绘(不依赖 QSS 的 ::indicator),因此能做描绘动画;配色每帧从
    theme 读取,主题切换自动跟随。保留原生 sizeHint 让布局与其它控件一致。"""
    _BOX = 16                                     # 勾选框边长(与 QSS 一致)
    _GAP = 8                                      # 框与文字间距

    def __init__(self, *a, **kw):
        super(AnimatedCheckBox, self).__init__(*a, **kw)
        self._p = 1.0 if self.isChecked() else 0.0     # 勾选进度 0→1
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.valueChanged.connect(self._on_val)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, on):
        self._anim.stop()
        self._anim.setStartValue(float(self._p))
        self._anim.setEndValue(1.0 if on else 0.0)
        # 勾选用回弹(OutBack)更"弹",取消用干脆的 OutCubic
        self._anim.setEasingCurve(QEasingCurve.OutBack if on else QEasingCurve.OutCubic)
        self._anim.start()

    def _on_val(self, v):
        self._p = float(v)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        C = theme.COLORS
        box = self._BOX
        y = (self.height() - box) // 2
        r = QRect(2, y, box, box)
        prog = max(0.0, min(1.0, self._p))        # 夹取(OutBack 会略越界)
        # 底框:未选描边、已选填充色(填充随进度从中心回弹放大)
        p.setPen(QPen(QColor(C.get("scroll", "#c3cde0")), 2))
        p.setBrush(QColor(C.get("input_bg", "#ffffff")))
        p.drawRoundedRect(r, 5, 5)
        if prog > 0.01:
            acc = QColor(C.get("accent", "#305496"))
            side = box * prog
            fill = QRect(0, 0, int(side), int(side))
            fill.moveCenter(r.center())
            p.setPen(Qt.NoPen)
            p.setBrush(acc)
            p.drawRoundedRect(fill, 5 * prog, 5 * prog)
        # 对勾:按进度描绘(prog<0.35 还没画,之后从起点画到终点)
        if prog > 0.35:
            seg = (prog - 0.35) / 0.65
            a = QPointF(r.left() + box * 0.26, r.top() + box * 0.52)
            b = QPointF(r.left() + box * 0.44, r.top() + box * 0.70)
            c = QPointF(r.left() + box * 0.76, r.top() + box * 0.32)
            path = QPainterPath(a)
            if seg <= 0.5:                        # 前半段:a→b
                t = seg / 0.5
                path.lineTo(a + (b - a) * t)
            else:                                 # 后半段:b→c
                path.lineTo(b)
                t = (seg - 0.5) / 0.5
                path.lineTo(b + (c - b) * t)
            pen = QPen(QColor("#ffffff"), 2.2)
            pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        # 文字
        if self.text():
            p.setPen(QColor(C.get("text", "#222b3a")))
            tx = r.right() + self._GAP
            p.drawText(QRect(tx, 0, self.width() - tx, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


def fade_window_in(win, duration=200, rise=0):
    """顶层窗口整体淡入(可选轻微上浮)。走 setWindowOpacity —— 由 DWM 合成器
    处理,不经离屏 ARGB 缓冲,文字保持 ClearType 清晰(区别于 QGraphicsOpacityEffect)。
    返回动画列表(调用方存引用防 GC);失败即刻恢复不透明,绝不把窗口留在透明态。"""
    try:
        win.setWindowOpacity(0.0)
        fade = QPropertyAnimation(win, b"windowOpacity", win)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        anims = [fade]
        if rise:
            final = win.pos()
            start = QPoint(final.x(), final.y() + rise)
            win.move(start)
            mv = QPropertyAnimation(win, b"pos", win)
            mv.setDuration(int(duration * 1.15))
            mv.setStartValue(start)
            mv.setEndValue(final)
            mv.setEasingCurve(QEasingCurve.OutCubic)
            anims.append(mv)
        for a in anims:
            a.start()
        # 兜底:无论动画成败,略过时长后强制不透明,杜绝卡在半透明/全透明
        QTimer.singleShot(duration + 260, lambda: win.setWindowOpacity(1.0))
        return anims
    except Exception:
        try:
            win.setWindowOpacity(1.0)
        except Exception:
            pass
        return []


class AnimatedDialog(QDialog):
    """对话框弹出微动画:首次显示时窗口淡入 + 轻微上浮。

    位移/透明度均作用于顶层窗口本身(合成器级),不渲染到离屏缓冲,文字清晰。
    exec_() 前几何未定,故在 showEvent(super 已完成居中)首帧再启动,只跑一次。"""
    def __init__(self, *a, **kw):
        super(AnimatedDialog, self).__init__(*a, **kw)
        self._pop_done = False
        self._pop_anims = []

    def showEvent(self, e):
        super(AnimatedDialog, self).showEvent(e)
        if self._pop_done:
            return
        self._pop_done = True
        self._pop_anims = fade_window_in(self, duration=180, rise=14)
