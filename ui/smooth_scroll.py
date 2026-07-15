# -*- coding: utf-8 -*-
"""
平滑滚动 —— 拦截滚轮事件，用缓动动画把滚动条推向目标值
========================================================
QScrollArea 默认滚轮是"一格一跳",观感生硬。这里在视口上装事件过滤器,
每次滚轮把目标值累加/夹取到 [min,max],再用 OutCubic 动画平滑逼近,
连续快滚会顺势叠加,松手后缓停。只接管纵向滚轮;内部可滚动子部件
(表格/日志)会先吃掉滚轮,不会被这里劫持。
兼容 Windows 7 + Python 3.8 + PySide2(Qt5.15)。
"""
from PySide2.QtCore import QObject, QEvent, QEasingCurve, QVariantAnimation


class SmoothScroller(QObject):
    def __init__(self, area, step=118, duration=300):
        super(SmoothScroller, self).__init__(area)
        self._bar = area.verticalScrollBar()
        self._step = step
        self._duration = duration
        self._target = self._bar.value()
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(
            lambda v: self._bar.setValue(int(round(v))))
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Wheel:
            return False
        dy = ev.angleDelta().y()
        mn, mx = self._bar.minimum(), self._bar.maximum()
        if dy == 0 or mx <= mn:
            return False
        # 空闲时以当前实际位置为起点,连续滚动时在既有目标上继续累加
        if self._anim.state() != QVariantAnimation.Running:
            self._target = self._bar.value()
        self._target = max(mn, min(mx, self._target - dy / 120.0 * self._step))
        self._anim.stop()
        self._anim.setStartValue(float(self._bar.value()))
        self._anim.setEndValue(float(self._target))
        self._anim.setDuration(self._duration)
        self._anim.start()
        return True                      # 已接管,阻止默认跳步滚动


def enable(area, step=118, duration=300):
    """给一个 QScrollArea/QAbstractScrollArea 开启平滑滚动。返回过滤器对象(防 GC)。"""
    return SmoothScroller(area, step, duration)
