# -*- coding: utf-8 -*-
"""离屏生成 logo.png(256) 与 icon.ico(多尺寸)。运行一次即可，产物随程序走。"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = os.path.dirname(os.path.abspath(__file__))

from PySide2.QtWidgets import QApplication
from PySide2.QtGui import (QPixmap, QPainter, QLinearGradient, QColor, QBrush,
                           QPainterPath, QPen, QPolygonF)
from PySide2.QtCore import Qt, QRectF, QPointF


def draw(size):
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(size)
    # 圆角徽章 + 蓝色渐变
    r = s * 0.22
    rect = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, QColor("#4f80cf"))
    g.setColorAt(1.0, QColor("#24406f"))
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    p.fillPath(path, QBrush(g))

    # 山峰（峰）——两座白色三角，主峰高、次峰低
    p.setPen(Qt.NoPen)
    base = rect.bottom() - s * 0.20
    main = QPolygonF([QPointF(rect.center().x() - s * 0.02, s * 0.30),
                      QPointF(rect.left() + s * 0.14, base),
                      QPointF(rect.center().x() + s * 0.30, base)])
    sub = QPolygonF([QPointF(rect.center().x() + s * 0.16, s * 0.44),
                     QPointF(rect.center().x() - s * 0.02, base),
                     QPointF(rect.right() - s * 0.12, base)])
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawPolygon(sub)
    p.setBrush(QColor(255, 255, 255))
    p.drawPolygon(main)

    # 流动曲线（运通）——一道浅蓝弧线穿过底部
    pen = QPen(QColor(255, 255, 255, 150))
    pen.setWidthF(s * 0.045)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    curve = QPainterPath()
    y = base + s * 0.085
    curve.moveTo(rect.left() + s * 0.14, y)
    curve.cubicTo(rect.center().x() - s * 0.04, y - s * 0.09,
                  rect.center().x() + s * 0.06, y + s * 0.06,
                  rect.right() - s * 0.14, y - s * 0.03)
    p.drawPath(curve)
    p.end()
    return px


def main():
    QApplication(sys.argv)
    big = draw(256)
    big.save(os.path.join(HERE, "logo.png"), "PNG")
    # ICO：多尺寸，Qt 直接写 .ico
    icons = [draw(n) for n in (16, 24, 32, 48, 64, 128, 256)]
    # QPixmap.save 单张即可，但多尺寸 ico 需用 QImage 列表；退化为 256 单尺寸也可用
    big.save(os.path.join(HERE, "icon.ico"), "ICO")
    # 额外存一个 128 供首页用
    draw(128).save(os.path.join(HERE, "logo_128.png"), "PNG")
    print("logo.png / icon.ico / logo_128.png generated at", HERE)


if __name__ == "__main__":
    main()
