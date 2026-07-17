# -*- coding: utf-8 -*-
"""
矢量图标系统 —— 线性描边风格，跟随主题变色
==========================================
· 一套内嵌 SVG（2px 描边、圆角、24x24 视图框），不依赖外部图片文件；
· render(name, size, color) 把 SVG 描边色替换成主题色后栅格化成 QPixmap，
  高分屏按 devicePixelRatio 放大不糊；结果按 (name,size,color,dpr) 缓存；
· 主题切换只需 clear_cache() 后重新取图。
兼容 Windows 7 + Python 3.8 + PySide2(Qt5.15)。
"""
from PySide2.QtCore import Qt, QByteArray
from PySide2.QtGui import QPixmap, QIcon, QPainter

try:
    from PySide2.QtSvg import QSvgRenderer
    _HAS_SVG = True
except Exception:                       # 理论上不会发生（已确认可用），留兜底
    _HAS_SVG = False

from . import theme

# 所有图标统一 24x24 视图框，用 currentColor 占位，渲染时替换成主题色。
# stroke-width=2、圆角线帽，线性风格。
_P = ('fill="none" stroke="currentColor" stroke-width="2" '
      'stroke-linecap="round" stroke-linejoin="round"')

_SVG = {
    # —— 功能图标 ——
    "attendance":                       # 考勤：日历 + 对勾
        '<rect x="3" y="4" width="18" height="17" rx="2" {p}/>'
        '<path d="M3 9h18M8 2v4M16 2v4" {p}/>'
        '<path d="M8.5 14.5l2.5 2.5 4.5-5" {p}/>',
    "reconcile":                        # 对账：天平（立柱+横梁+两侧秤盘）
        '<path d="M12 4v16M9 20h6M4 7h16" {p}/>'
        '<path d="M4 7l-2.5 5M4 7l2.5 5M1.5 12q2.5 4.5 5 0" {p}/>'
        '<path d="M20 7l-2.5 5M20 7l2.5 5M17.5 12q2.5 4.5 5 0" {p}/>',
    "arrival":                          # 到料：纸箱
        '<path d="M3 7l9-4 9 4v10l-9 4-9-4V7z" {p}/>'
        '<path d="M3 7l9 4 9-4M12 11v10" {p}/>',
    "pivot":                            # 透视：柱状图
        '<path d="M4 20V4" {p}/><path d="M4 20h16" {p}/>'
        '<rect x="7" y="12" width="3" height="5" rx="0.6" {p}/>'
        '<rect x="12" y="8" width="3" height="9" rx="0.6" {p}/>'
        '<rect x="17" y="5" width="3" height="12" rx="0.6" {p}/>',
    "purchase":                         # 采购对账：清单 + 对勾
        '<rect x="4" y="3" width="16" height="18" rx="2" {p}/>'
        '<path d="M8 8h5M8 12h5M8 16h3" {p}/>'
        '<path d="M15.5 16l1.7 1.7 3-3.4" {p}/>',
    "delivery":                         # 送货计划：厢式货车
        '<path d="M2 6h11v9H2z" {p}/>'
        '<path d="M13 9h4l3 3v3h-7z" {p}/>'
        '<circle cx="6.5" cy="17" r="1.8" {p}/>'
        '<circle cx="16.5" cy="17" r="1.8" {p}/>',
    "library":                          # 数据库：三层堆叠
        '<ellipse cx="12" cy="5" rx="8" ry="3" {p}/>'
        '<path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" {p}/>'
        '<path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" {p}/>',
    "invoice":                          # 增值税发票：锯齿下沿的票据 + 文字行
        '<path d="M6 3h12v16l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3V3z" {p}/>'
        '<path d="M9 8h6M9 11h6M9 14h4" {p}/>',
    # —— 系统/导航 ——
    "home":
        '<path d="M4 11l8-7 8 7" {p}/>'
        '<path d="M6 10v9h12v-9" {p}/><path d="M10 19v-5h4v5" {p}/>',
    "settings":                         # 设置：三档滑块
        '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h9M17 17h3" {p}/>'
        '<circle cx="15" cy="7" r="2" {p}/>'
        '<circle cx="9" cy="12" r="2" {p}/>'
        '<circle cx="15" cy="17" r="2" {p}/>',
    "about":
        '<circle cx="12" cy="12" r="9" {p}/>'
        '<path d="M12 11v5M12 7.5v.5" {p}/>',
    # —— 零散 UI ——
    "upload":                           # 数据库导入拖拽区
        '<path d="M12 15V4M8 8l4-4 4 4" {p}/>'
        '<path d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" {p}/>',
    "check":
        '<path d="M4 12.5l5 5 11-11" {p}/>',
    "chevron":                          # 折叠箭头（指向右，展开时旋转由调用方处理）
        '<path d="M9 6l6 6-6 6" {p}/>',
    "folder":
        '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" {p}/>',
    "rename":                           # 批量重命名：文档 + 铅笔
        '<path d="M13 3H6a2 2 0 00-2 2v14a2 2 0 002 2h9" {p}/>'
        '<path d="M8 8h6M8 12h3" {p}/>'
        '<path d="M18.5 12.5l3 3L16 21l-3 .5.5-3 5-6z" {p}/>',
    "currency":                         # 金额大写：¥ 圆圈
        '<circle cx="12" cy="12" r="9" {p}/>'
        '<path d="M8.5 8l3.5 4 3.5-4M12 12v5M9.5 13.5h5M9.5 16h5" {p}/>',
    "text":                             # 文本工具：段落线条
        '<path d="M5 5h14M5 9h14M5 13h9M5 17h11" {p}/>',
    "pdf":                              # PDF：文档 + 折角
        '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" {p}/>'
        '<path d="M14 3v5h5" {p}/>'
        '<path d="M8.5 13h1a1.2 1.2 0 010 2.4h-1V13v4M14 13v4M14 13h1.6M14 15h1.4" {p}/>',
    "excel":                           # Excel：表格网格
        '<rect x="4" y="4" width="16" height="16" rx="2" {p}/>'
        '<path d="M4 10h16M4 15h16M10 4v16M15 4v16" {p}/>',
    "compare":                          # 表格比对：两张并排的表 + 中间对比箭头
        '<rect x="3" y="4" width="7.5" height="16" rx="1.5" {p}/>'
        '<rect x="13.5" y="4" width="7.5" height="16" rx="1.5" {p}/>'
        '<path d="M5 9h3.5M5 12.5h3.5M15.5 9h3.5M15.5 12.5h3.5" {p}/>',
}

_cache = {}


def _svg_bytes(name, color):
    body = _SVG[name].format(p=_P).replace("currentColor", color)
    doc = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
           'width="24" height="24">%s</svg>' % body)
    return QByteArray(doc.encode("utf-8"))


def pixmap(name, size=18, color=None, dpr=1.0):
    """渲染成 QPixmap。color 缺省用主题强调色。name 未知返回空图。"""
    if name not in _SVG or not _HAS_SVG:
        return QPixmap()
    color = color or theme.COLORS.get("accent", "#305496")
    key = (name, size, color, round(dpr, 2))
    pm = _cache.get(key)
    if pm is not None:
        return pm
    r = QSvgRenderer(_svg_bytes(name, color))
    px = max(1, int(size * dpr))
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    r.render(p)
    p.end()
    _cache[key] = pm
    return pm


def icon(name, size=18, color=None, dpr=1.0):
    """渲染成 QIcon（供 QPushButton.setIcon 等）。"""
    pm = pixmap(name, size, color, dpr)
    return QIcon(pm) if not pm.isNull() else QIcon()


def clear_cache():
    """主题切换后调用：丢弃旧色缓存，下次取图用新主题色。"""
    _cache.clear()
