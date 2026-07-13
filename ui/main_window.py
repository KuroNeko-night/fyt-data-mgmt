# -*- coding: utf-8 -*-
"""
主窗口 —— 侧栏导航 + 堆叠页面(带切换动画) + 功能分类
====================================================
功能按"考勤管理 / 数据处理"分组，另有设置、关于。为将来新增功能预留插槽
（在 NAV 列表加一项 + 一个页面即可）。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, QEasingCurve, QTimer, QVariantAnimation
from PySide2.QtGui import QPixmap, QPainter, QColor
from PySide2.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QLabel, QPushButton, QStackedWidget, QApplication,
                               QButtonGroup)

from . import theme
from .pages.home_page import HomePage
from .pages.attendance_page import AttendancePage
from .pages.reconcile_page import ReconcilePage
from .pages.arrival_page import ArrivalPage
from .pages.pivot_page import PivotPage
from .pages.library_page import LibraryPage
from .pages.settings_page import SettingsPage
from .pages.about_page import AboutPage
from core import version, settings as settings_mod


# 导航定义：(分组, 标题, 页面键)；分组为 None 表示单列在底部
NAV = [
    ("", "首页", "home"),
    ("考勤管理", "考勤数据填报", "attendance"),
    ("考勤管理", "工时对账", "reconcile"),
    ("数据处理", "到料明细表", "arrival"),
    ("数据处理", "透视表制作", "pivot"),
    ("数据", "数据库", "library"),
    ("系统", "设置", "settings"),
    ("系统", "关于 / 更新", "about"),
]


class _CrossFade(QWidget):
    """页面切换叠层：自绘两张静态快照做交叉淡入。

    不使用 QGraphicsOpacityEffect —— 那会把内容渲到离屏 ARGB 缓冲，首帧闪出
    未套样式的浅色底(深色模式下表现为白闪)，并关闭 ClearType 使文字发虚。
    这里始终"新页快照打底、旧页快照按 t 渐隐叠加", 全程不透明, 无闪、无重排。
    """
    def __init__(self, parent, old_pm, bg):
        super(_CrossFade, self).__init__(parent)
        self._old = old_pm
        self._new = None
        self._bg = QColor(bg)
        self._t = 0.0                       # 0→1: 旧页透明度 1→0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # 不透明绘制：告诉 Qt 本部件会铺满自身区域，切勿在绘制前把背景擦成
        # 调色板底色(默认浅色)。这是深色模式"白闪"的直接来源之一。
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_new(self, new_pm):
        self._new = new_pm
        self.update()

    def set_t(self, v):
        self._t = float(v)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)   # 先铺主题底色，任何缝隙都是深色不是白
        if self._new is not None:
            p.drawPixmap(self.rect(), self._new)
        if self._old is not None and self._t < 1.0:
            p.setOpacity(1.0 - self._t)
            p.drawPixmap(self.rect(), self._old)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle(version.full_title())
        self.resize(1040, 720)
        self.setMinimumSize(880, 600)
        self.settings = settings_mod.get_settings()
        self._pages = {}
        self._nav_btns = {}
        self._cur_key = None       # 当前页，用于判断是否需要切换动画
        self._xfade = None         # 交叉淡出叠层(QLabel)，防 GC
        self._xfade_anim = None
        self._build()
        self.switch_to("home")
        QTimer.singleShot(300, self._maybe_onboard)

    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_sidebar())
        lay.addWidget(self._build_stack(), 1)

    def _build_sidebar(self):
        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(210)
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        brand = QLabel("峰运通")
        brand.setObjectName("Brand")
        v.addWidget(brand)
        sub = QLabel("数据管理系统  " + version.version_str())
        sub.setObjectName("BrandSub")
        v.addWidget(sub)

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        last_group = None
        for group, title, key in NAV:
            if group != last_group:
                if group:                      # 空分组名(如首页)不画分组标题
                    gl = QLabel(group)
                    gl.setObjectName("NavGroup")
                    v.addWidget(gl)
                last_group = group
            b = QPushButton(title)
            b.setObjectName("NavBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.switch_to(k))
            self._grp.addButton(b)
            self._nav_btns[key] = b
            v.addWidget(b)
        v.addStretch(1)
        tip = QLabel("兼容 Win7 · Python 3.8")
        tip.setObjectName("BrandSub")
        v.addWidget(tip)
        return bar

    def _build_stack(self):
        self.stack = QStackedWidget()
        self.stack.setObjectName("Stack")       # 供 QSS 上不透明主题底色，杜绝换页白闪
        ctors = {"home": HomePage, "attendance": AttendancePage,
                 "reconcile": ReconcilePage, "arrival": ArrivalPage,
                 "pivot": PivotPage, "library": LibraryPage,
                 "settings": SettingsPage, "about": AboutPage}
        for _, _, key in NAV:
            page = ctors[key](self)
            self._pages[key] = page
            self.stack.addWidget(page)
        return self.stack

    def switch_to(self, key):
        page = self._pages.get(key)
        if page is None:
            return
        if self._nav_btns.get(key):
            self._nav_btns[key].setChecked(True)
        # 进入首页/数据库时刷新其数据库统计与列表
        fn = getattr(page, "refresh_view", None)
        if callable(fn):
            fn()
        prev = self.stack.currentWidget()
        same = (key == self._cur_key)
        do_anim = prev is not None and not same and self._cur_key is not None
        if not do_anim:
            self.stack.setCurrentWidget(page)
            self._cur_key = key
            return
        # 关键顺序：先用旧页快照盖住整块区域，再在其"背后"切换页面，
        # 这样 QStackedWidget 换页时那一帧擦成调色板浅底的动作完全被遮住
        # —— 这正是深色模式"白闪"的根源。
        bg = theme.COLORS.get("bg", "#ffffff")
        old_pm = self._grab(prev)
        self._clear_xfade()
        overlay = _CrossFade(self.stack, old_pm, bg)
        overlay.setGeometry(self.stack.rect())
        overlay.show(); overlay.raise_()
        self._xfade = overlay
        self.stack.setCurrentWidget(page)        # 在遮挡下换页
        self._cur_key = key
        overlay.raise_()                         # 换页后确保仍在最上层
        page.resize(self.stack.size())           # 使新页按最终尺寸布局
        new_pm = self._grab(page)
        if old_pm is None or new_pm is None:     # 抓取失败：直接撤叠层瞬切
            self._clear_xfade()
            return
        overlay.set_new(new_pm)
        self._crossfade(overlay)

    def _grab(self, widget):
        """把部件渲染成"带不透明背景"的静态位图；失败返回 None(退化为瞬切)。

        预填当前主题背景色再渲染 —— 透明底会让快照文字用灰度抗锯齿而发虚，
        不透明底则接近实时观感。位图携带 devicePixelRatio, 高分屏不糊。
        """
        try:
            w, h = widget.width(), widget.height()
            if w <= 0 or h <= 0:
                return None
            try:
                dpr = widget.devicePixelRatioF()
            except Exception:
                dpr = 1.0
            pm = QPixmap(int(w * dpr), int(h * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(QColor(theme.COLORS.get("bg", "#ffffff")))
            widget.render(pm)
            return pm if not pm.isNull() else None
        except Exception:
            return None

    def _crossfade(self, overlay):
        """旧页快照按 t 渐隐，露出背后已切换好的新页。自绘、全程不透明。"""
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(190)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(overlay.set_t)
        anim.finished.connect(self._clear_xfade)
        self._xfade = overlay
        self._xfade_anim = anim
        anim.start()

    def _clear_xfade(self):
        if self._xfade_anim is not None:
            try:
                self._xfade_anim.stop()
            except Exception:
                pass
        if self._xfade is not None:
            self._xfade.hide()
            self._xfade.deleteLater()
            self._xfade = None
        self._xfade_anim = None

    # ---------- 主题实时切换 ----------
    def apply_theme(self, mode):
        """切换主题模式并即时重贴样式表；动态属性会随之重新生效。"""
        theme.set_mode(mode)
        app = QApplication.instance()
        if app:
            theme.apply_palette(app)             # 同步染调色板，换页/新窗口不闪白
            app.setStyleSheet(theme.stylesheet())
        # 重贴样式表后，个别缓存了内联样式的部件让其重读配色
        for page in self._pages.values():
            fn = getattr(page, "on_theme_changed", None)
            if callable(fn):
                fn()

    # ---------- 页面联动 ----------
    def send_to_reconcile(self, paths):
        """考勤填报结果 -> 工时对账 的"数据来源"。"""
        self._pages["reconcile"].add_source_files(paths)
        self.switch_to("reconcile")

    def send_to_pivot(self, paths):
        """到料/其它 -> 透视表 来源（预留联动）。"""
        self._pages["pivot"].add_source_files(paths)
        self.switch_to("pivot")

    def _maybe_onboard(self):
        if not self.settings.get("onboarding_seen", False):
            from .dialogs.onboarding import OnboardingDialog
            dlg = OnboardingDialog(self)
            dlg.exec_()
            self.settings.set("onboarding_seen", True)
            self.settings.save()
