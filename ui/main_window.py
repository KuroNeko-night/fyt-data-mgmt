# -*- coding: utf-8 -*-
"""
主窗口 —— 侧栏导航 + 堆叠页面(带切换动画) + 功能分类
====================================================
功能按"人事 / 销售"等分组，另有设置、关于。为将来新增功能预留插槽
（在 NAV 列表加一项 + 一个页面即可）。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import (Qt, QEasingCurve, QTimer, QVariantAnimation, QSize,
                            QPropertyAnimation, QRect, QEvent, Signal)
from PySide2.QtGui import QPixmap, QPainter, QColor, QIcon
from PySide2.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QLabel, QPushButton, QStackedWidget, QApplication,
                               QButtonGroup, QScrollArea, QFrame,
                               QSystemTrayIcon, QMenu)

from . import theme
from . import icons
from .pages.home_page import HomePage
from .pages.attendance_page import AttendancePage
from .pages.reconcile_page import ReconcilePage
from .pages.arrival_page import ArrivalPage
from .pages.purchase_page import PurchasePage
from .pages.delivery_page import DeliveryPage
from .pages.pivot_page import PivotPage
from .pages.library_page import LibraryPage
from .pages.rename_page import RenamePage
from .pages.currency_page import CurrencyPage
from .pages.invoice_page import InvoicePage
from .pages.text_page import TextPage
from .pages.pdf_page import PdfPage
from .pages.excel_tools_page import ExcelToolsPage
from .pages.settings_page import SettingsPage
from .pages.about_page import AboutPage
from core import version, settings as settings_mod


# 导航定义：(分组, 标题, 页面键)；分组为 None 表示单列在底部
NAV = [
    ("", "首页", "home"),
    ("人事", "考勤数据填报", "attendance"),
    ("人事", "工时对账", "reconcile"),
    ("销售", "到料明细表", "arrival"),
    ("销售", "销售表透视", "pivot"),
    ("销售", "采购数对账", "purchase"),
    ("销售", "送货计划表", "delivery"),
    ("数据", "数据库", "library"),
    ("财务", "增值税发票统计", "invoice"),
    ("财务", "金额大写", "currency"),
    ("工具箱", "批量重命名", "rename"),
    ("工具箱", "文本工具箱", "text"),
    ("工具箱", "PDF 工具箱", "pdf"),
    ("工具箱", "Excel 工具箱", "excel"),
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
    # 监听线程收到"再次启动"事件后发此信号；跨线程 → 队列连接回 GUI 线程还原窗口
    _show_requested = Signal()

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
        self._tray = None          # 系统托盘图标（防 GC）
        self._force_quit = False   # True 时 closeEvent 放行真正退出
        self._tray_tip_shown = False
        self._show_event = None     # 单实例唤醒事件句柄
        self._show_thread = None    # 等待唤醒的监听线程
        self._show_requested.connect(self._restore_from_tray)
        self._build()
        self._build_tray()
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

        # 品牌头固定在顶部
        brand = QLabel("峰运通")
        brand.setObjectName("Brand")
        v.addWidget(brand)
        sub = QLabel("数据管理系统  " + version.version_str())
        sub.setObjectName("BrandSub")
        v.addWidget(sub)

        # 导航项放进可滚动区：功能增多也不会挤爆或撑出窗口
        scroll = QScrollArea()
        scroll.setObjectName("NavScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setAttribute(Qt.WA_StyledBackground, True)
        scroll.viewport().setAutoFillBackground(False)
        nav_host = QWidget()
        nav_host.setObjectName("NavHost")
        nav_host.setAttribute(Qt.WA_StyledBackground, True)
        nav_host.installEventFilter(self)        # 监听尺寸变化,重贴指示块宽度
        self._nav_host = nav_host
        nv = QVBoxLayout(nav_host)
        nv.setContentsMargins(0, 0, 0, 0)
        nv.setSpacing(0)

        # 选中指示:两片一起平滑滑动——
        #   填充块 fill 压在按钮"背后"(hover 提亮时会盖住它,无妨);
        #   蓝色竖条 stripe 浮在按钮"之上",所以 hover 也挡不住它。
        self._nav_fill = QWidget(nav_host)
        self._nav_fill.setObjectName("NavIndicator")
        self._nav_fill.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._nav_fill.hide()
        self._nav_stripe = QWidget(nav_host)
        self._nav_stripe.setObjectName("NavStripe")
        self._nav_stripe.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._nav_stripe.hide()
        self._nav_ind_anim = QPropertyAnimation(self._nav_fill, b"geometry", self)
        self._nav_ind_anim.setDuration(260)
        self._nav_ind_anim.setEasingCurve(QEasingCurve.OutCubic)
        # 动画每帧把竖条对齐到填充块左缘(x=0、3px 宽、同高)
        self._nav_ind_anim.valueChanged.connect(self._sync_nav_stripe)

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        last_group = None
        for group, title, key in NAV:
            if group != last_group:
                if group:                      # 空分组名(如首页)不画分组标题
                    gl = QLabel(group)
                    gl.setObjectName("NavGroup")
                    nv.addWidget(gl)
                last_group = group
            b = self._make_nav_btn(title, key)
            self._grp.addButton(b)
            self._nav_btns[key] = b
            nv.addWidget(b)
        self._refresh_nav_icons()
        nv.addStretch(1)
        self._nav_fill.lower()                   # 填充压到按钮之下
        self._nav_stripe.raise_()                # 竖条抬到按钮之上
        scroll.setWidget(nav_host)
        v.addWidget(scroll, 1)
        from . import smooth_scroll
        self._nav_smooth = smooth_scroll.enable(scroll, step=90, duration=260)

        # 底部提示固定在最下方
        tip = QLabel("兼容 Win7 · Python 3.8")
        tip.setObjectName("BrandSub")
        v.addWidget(tip)
        return bar

    def _make_nav_btn(self, title, key):
        """导航项：可选中的 QPushButton，内部用 QLabel 承载图标+文字。

        不用 QPushButton.setIcon —— 带 padding 的样式化按钮在高 DPI 下会把
        图标按原生尺寸绘制并裁切。改用内部 QLabel.setPixmap（与首页卡片同路径，
        实测在真机各 DPI 下都清晰）。选中/常态的配色由 _refresh_nav_icons 统一刷。
        """
        b = QPushButton()
        b.setObjectName("NavBtn")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, k=key: self.switch_to(k))
        h = QHBoxLayout(b)
        h.setContentsMargins(17, 0, 12, 0)
        h.setSpacing(11)
        ic = QLabel(); ic.setFixedSize(18, 18); ic.setScaledContents(True)
        ic.setAttribute(Qt.WA_TransparentForMouseEvents)
        lb = QLabel(title); lb.setObjectName("NavText")
        lb.setAttribute(Qt.WA_TransparentForMouseEvents)
        h.addWidget(ic, 0); h.addWidget(lb, 1)
        b._icon_lbl = ic
        b._text_lbl = lb
        b._nav_key = key
        return b

    def _refresh_nav_icons(self):
        """按当前主题+选中态给侧栏导航图标/文字上色（选中偏白，常态用前景色）。

        图标按 2× 物理分辨率(dpr=1)渲染，交给 setScaledContents 的定尺 QLabel 缩放，
        高/低 DPI 都清晰且不裁切——避免把 dpr 烘进位图导致定尺标签只画左上角。"""
        base = theme.COLORS.get("sidebar_fg", "#c7d2e8")
        for key, btn in self._nav_btns.items():
            on = btn.isChecked()
            color = "#ffffff" if on else base
            btn._icon_lbl.setPixmap(icons.pixmap(key, 36, color, 1.0))
            btn._text_lbl.setStyleSheet(
                "color:%s; font-size:13px; background:transparent;%s"
                % (color, " font-weight:bold;" if on else ""))

    def _sync_nav_stripe(self, rect):
        """把蓝色竖条对齐到填充块:左缘、3px 宽、同高。供动画每帧回调。"""
        st = getattr(self, "_nav_stripe", None)
        if st is not None:
            st.setGeometry(rect.x(), rect.y(), 3, rect.height())

    def _move_indicator(self, key, animate=True):
        """把选中指示(填充块+竖条)移到 key 对应按钮处;animate=True 时平滑滑动。

        两片与按钮同在 nav_host 坐标系,滚动时一起平移,无需跟随滚动条重算。
        首次布局未完成(高宽为 0)时延后重试,并确认此刻仍选中该键才落位。"""
        fill = getattr(self, "_nav_fill", None)
        btn = self._nav_btns.get(key)
        if fill is None or btn is None:
            return
        target = QRect(0, btn.y(), self._nav_host.width(), btn.height())
        if target.height() <= 1 or target.width() <= 1:     # 布局尚未成形,稍后再落位
            QTimer.singleShot(16, lambda k=key: self._move_indicator(k, False)
                              if self._nav_btns.get(k) and self._nav_btns[k].isChecked()
                              else None)
            return
        self._nav_ind_anim.stop()
        if not fill.isVisible():                             # 首次:直接落位,不滑
            fill.setGeometry(target); fill.show(); fill.lower()
            self._sync_nav_stripe(target)
            self._nav_stripe.show(); self._nav_stripe.raise_()
            return
        if not animate:
            fill.setGeometry(target)
            self._sync_nav_stripe(target)
            return
        fill.lower(); self._nav_stripe.raise_()              # 保持层序
        self._nav_ind_anim.setStartValue(fill.geometry())
        self._nav_ind_anim.setEndValue(target)
        self._nav_ind_anim.start()

    def eventFilter(self, obj, ev):
        # nav_host 尺寸变化(如滚动条出现使视口变窄)时,即时贴合指示块宽度
        if obj is getattr(self, "_nav_host", None) and ev.type() == QEvent.Resize:
            if self._cur_key is not None:
                self._move_indicator(self._cur_key, animate=False)
        return super(MainWindow, self).eventFilter(obj, ev)

    def _build_stack(self):
        self.stack = QStackedWidget()
        self.stack.setObjectName("Stack")       # 供 QSS 上不透明主题底色，杜绝换页白闪
        ctors = {"home": HomePage, "attendance": AttendancePage,
                 "reconcile": ReconcilePage, "arrival": ArrivalPage,
                 "pivot": PivotPage, "purchase": PurchasePage,
                 "delivery": DeliveryPage, "library": LibraryPage,
                 "rename": RenamePage, "currency": CurrencyPage,
                 "text": TextPage, "pdf": PdfPage, "excel": ExcelToolsPage,
                 "invoice": InvoicePage,
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
            self._refresh_nav_icons()            # 选中态变了，重染图标/文字色
            # 选中指示块滑到新位置(首次进入不滑,直接落位)
            self._move_indicator(key, animate=(self._cur_key is not None))
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
        icons.clear_cache()                      # 丢弃旧主题色图标缓存
        app = QApplication.instance()
        if app:
            theme.apply_palette(app)             # 同步染调色板，换页/新窗口不闪白
            app.setStyleSheet(theme.stylesheet())
        self._refresh_nav_icons()                # 用新主题色重染侧栏图标
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

    # ---------- 单实例唤醒 ----------
    def attach_show_event(self, handle):
        """接入单实例具名事件：起一个守护线程等它被 SetEvent，收到即还原窗口。

        再次启动本程序时，那个新进程会 SetEvent 后自杀（见 main._single_instance_guard），
        本线程随即唤醒、发信号回 GUI 线程把窗口从托盘/最小化拉回前台。
        句柄为空（非 Windows/建事件失败）时不起线程，不影响其余功能。
        """
        if not handle:
            return
        import threading
        self._show_event = handle
        t = threading.Thread(target=self._wait_show_loop, args=(handle,),
                             daemon=True)
        self._show_thread = t
        t.start()

    def _wait_show_loop(self, handle):
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        WAIT_OBJECT_0 = 0x0
        while not self._force_quit:
            r = k.WaitForSingleObject(handle, 500)   # 500ms 轮询，便于退出时收线程
            if r == WAIT_OBJECT_0:
                self._show_requested.emit()          # 队列连接 → GUI 线程还原

    # ---------- 系统托盘 ----------
    def _build_tray(self):
        """建系统托盘图标 + 右键菜单。系统不支持托盘时静默跳过（关闭即退出）。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        from core import paths
        import os
        icon = QIcon(os.path.join(paths.assets_dir(), "icon.ico"))
        if icon.isNull():
            icon = self.windowIcon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(version.APP_NAME)
        menu = QMenu()
        act_show = menu.addAction("打开主窗口")
        act_show.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        act_quit = menu.addAction("退出程序")
        act_quit.triggered.connect(self._quit_app)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        # 左键单击/双击托盘图标 → 还原窗口
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self):
        # 清掉最小化标志再显示，避免"还原后仍停在最小化"；然后置顶抢焦点
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized)
                            | Qt.WindowActive)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        """真正退出：放行 closeEvent 并收起托盘图标。"""
        self._force_quit = True
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """点关闭按钮：按设置最小化到托盘；托盘不可用或已选退出则正常关闭。"""
        if (self._force_quit or self._tray is None
                or not self.settings.get("minimize_to_tray", True)):
            if self._tray is not None:
                self._tray.hide()
            super(MainWindow, self).closeEvent(event)
            return
        event.ignore()
        self.hide()
        if not self._tray_tip_shown:                 # 首次隐藏时提示一次去哪了
            self._tray_tip_shown = True
            self._tray.showMessage(
                version.APP_NAME, "程序已最小化到托盘，仍在后台运行。\n"
                "点击托盘图标可重新打开，右键可退出。",
                QSystemTrayIcon.Information, 4000)
