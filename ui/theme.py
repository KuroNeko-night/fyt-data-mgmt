# -*- coding: utf-8 -*-
"""
主题：浅色 / 深色双配色 + 跟随系统 + 字体（Win7 回退）+ QSS
============================================================
· 三种模式：auto(跟随系统) / light / dark；
· COLORS 始终指向"当前生效"的配色，原地更新，旧引用不失效；
· 状态样式尽量交给 QSS 动态属性驱动，切换主题只需重贴样式表。
兼容 Windows 7 + Python 3.8 + PySide2(Qt5.15)。
"""

# ---------------- 浅色（现代 SaaS：冷调浅灰底 + 白卡 + 柔描边 + 浅侧栏） ----------------
LIGHT = {
    "bg": "#f4f6fa", "surface": "#ffffff", "surface2": "#f7f9fc",
    # 浅侧栏：近白表面，靠右侧细分隔线(sidebar_line)与内容区区分
    "sidebar": "#fbfcfe", "sidebar_h": "#eef2f8", "sidebar_a": "#e8effb",
    "sidebar_fg": "#4b5768", "sidebar_dim": "#9aa4b5", "sidebar_grp": "#9aa4b5",
    "sidebar_line": "#e6eaf1", "brand_fg": "#1c2431",
    # 强调色统一到更亮的一族（比旧 #305496 更现代、更透气）
    "accent": "#2f6bd8", "accent_l": "#4a82e8", "accent_d": "#2456b4",
    "accent_soft": "#e8effb",
    "heading": "#1f2a3d", "text": "#1c2431", "sub": "#5a6678", "hint": "#8a93a3",
    "line": "#e4e8f0", "ok": "#1f9d57", "warn": "#c47a1a", "err": "#d64545",
    "ghost_hover": "#eef4ff", "mini_bg": "#f0f3f8", "mini_hover": "#e6ebf3",
    "input_bg": "#ffffff", "list_bg": "#fbfcfe", "sel_fg": "#ffffff",
    "card_hover": "#fafbff", "pill_bg": "#eef2f8",
    "scroll": "#cdd5e2", "track": "#eef1f6", "logbg": "#1b1f27", "logfg": "#e6e9f0",
    "tip_bg": "#2b3446", "tip_fg": "#ffffff", "tip_bd": "#2f6bd8",
    "dis_bg": "#e6eaf1", "dis_fg": "#a8b0be", "shadow": "#18000000",
}

# ---------------- 深色（与浅色同结构：侧栏收敛到 surface 同族，不再纯黑） ----------------
DARK = {
    "bg": "#14171d", "surface": "#1e222b", "surface2": "#252a35",
    "sidebar": "#181c24", "sidebar_h": "#252b38", "sidebar_a": "#2a3348",
    "sidebar_fg": "#aeb8cc", "sidebar_dim": "#6f7a92", "sidebar_grp": "#6f7a92",
    "sidebar_line": "#262c38", "brand_fg": "#eef1f7",
    "accent": "#5a8ce8", "accent_l": "#6f9cf0", "accent_d": "#4275d4",
    "accent_soft": "#243248",
    "heading": "#b8ccf0", "text": "#e6e9f0", "sub": "#a2acc0", "hint": "#727d94",
    "line": "#2e3542", "ok": "#41c47e", "warn": "#e2953f", "err": "#e46a5c",
    "ghost_hover": "#242c3d", "mini_bg": "#272d3a", "mini_hover": "#313849",
    "input_bg": "#252a35", "list_bg": "#1a1e26", "sel_fg": "#ffffff",
    "card_hover": "#242935", "pill_bg": "#272d3a",
    "scroll": "#3a4350", "track": "#1e222b", "logbg": "#12151c", "logfg": "#c9d1e0",
    "tip_bg": "#2b3446", "tip_fg": "#ffffff", "tip_bd": "#5a8ce8",
    "dis_bg": "#2e3542", "dis_fg": "#66708a", "shadow": "#40000000",
}


# COLORS 始终指向当前生效配色（原地更新，保证旧引用不失效）
COLORS = dict(LIGHT)
_mode = "auto"          # auto | light | dark
_effective = "light"    # 实际生效：light | dark

FONT_CANDIDATES = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑",
                   "PingFang SC", "Segoe UI", "Tahoma"]
MONO_CANDIDATES = ["Consolas", "Cascadia Mono", "Courier New"]
_ui_font = None
_mono_font = None


def pick_font():
    """挑一个系统真正装了的中文字体（Win7 回退）。缓存。"""
    global _ui_font
    if _ui_font:
        return _ui_font
    try:
        from PySide2.QtGui import QFontDatabase
        fams = set(QFontDatabase().families())
        for f in FONT_CANDIDATES:
            if f in fams:
                _ui_font = f
                break
    except Exception:
        pass
    _ui_font = _ui_font or "Microsoft YaHei"
    return _ui_font


def pick_mono():
    global _mono_font
    if _mono_font:
        return _mono_font
    try:
        from PySide2.QtGui import QFontDatabase
        fams = set(QFontDatabase().families())
        for f in MONO_CANDIDATES:
            if f in fams:
                _mono_font = f
                break
    except Exception:
        pass
    _mono_font = _mono_font or "Consolas"
    return _mono_font


def system_is_dark():
    """读 Windows 注册表判断系统是否深色。Win7/读取失败一律视为浅色。"""
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        winreg.CloseKey(k)
        return val == 0
    except Exception:
        return False


def set_mode(mode):
    """设置主题模式并解析生效配色。返回生效字符串 light/dark。"""
    global _mode, _effective
    _mode = mode if mode in ("auto", "light", "dark") else "auto"
    if _mode == "auto":
        _effective = "dark" if system_is_dark() else "light"
    else:
        _effective = _mode
    src = DARK if _effective == "dark" else LIGHT
    COLORS.clear()
    COLORS.update(src)
    return _effective


def current_mode():
    return _mode


def effective():
    return _effective


def is_dark():
    return _effective == "dark"


def stylesheet():
    """全局 QSS。基于当前 COLORS 与字体。"""
    return _QSS.format(font=pick_font(), **COLORS)


def apply_palette(app):
    """把当前配色写进 QPalette。

    关键：QSS 的 background 只管"部件如何绘制"，而 Windows 原生的背景擦除、
    以及部分部件的 base/window 底色取自 QPalette。若调色板仍是默认浅色，深色
    主题下换页/新建窗口那一帧会被系统用白刷子擦一下 —— 这正是"白闪"的真凶。
    这里把窗口/基底/文字/按钮等角色一并染成主题色，从源头杜绝白底。
    """
    from PySide2.QtGui import QPalette, QColor
    C = COLORS
    def col(k, fallback="#000000"):
        return QColor(C.get(k, fallback))
    pal = QPalette()
    win = col("bg"); base = col("input_bg", "surface"); text = col("text")
    pal.setColor(QPalette.Window, win)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, col("surface2"))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, col("surface"))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.ToolTipBase, col("tip_bg"))
    pal.setColor(QPalette.ToolTipText, col("tip_fg"))
    pal.setColor(QPalette.Highlight, col("accent"))
    pal.setColor(QPalette.HighlightedText, col("sel_fg", "#ffffff"))
    pal.setColor(QPalette.PlaceholderText, col("hint"))
    pal.setColor(QPalette.Link, col("accent_l"))
    dis = col("dis_fg")
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, dis)
    app.setPalette(pal)


def fit_dialog(dlg, want_w, want_h, resizable=True):
    """按期望尺寸打开对话框，但绝不超出屏幕可用区域(留边距)，并居中。

    解决小屏 / 高分屏缩放下窗口过大、按钮跑到屏幕外、且无法缩放的问题。
    resizable=True 时允许用户拖拽缩放(右下角出现缩放柄)。
    """
    from PySide2.QtWidgets import QApplication
    try:
        scr = QApplication.desktop().availableGeometry(dlg)
        w = min(want_w, scr.width() - 40)
        h = min(want_h, scr.height() - 60)
        dlg.resize(w, h)
        dlg.setMaximumSize(scr.width(), scr.height())
        if resizable:
            dlg.setSizeGripEnabled(True)
        dlg.move(scr.x() + (scr.width() - w) // 2,
                 scr.y() + (scr.height() - h) // 2)
    except Exception:
        dlg.resize(want_w, want_h)


def repolish(widget):
    """动态属性变化后，让 QSS 重新生效（不必重贴整表）。"""
    try:
        st = widget.style()
        st.unpolish(widget)
        st.polish(widget)
        widget.update()
    except Exception:
        pass


def set_prop(widget, name, value):
    """设置动态属性并立即 repolish。bool 转成小写字符串以匹配 QSS 选择器。"""
    widget.setProperty(name, str(value).lower() if isinstance(value, bool) else value)
    repolish(widget)


_QSS = """
* {{ font-family: "{font}"; color: {text}; outline: none; }}
QMainWindow, QWidget#Root {{ background: {bg}; }}
QStackedWidget#Stack {{ background: {bg}; }}
QDialog {{ background: {bg}; }}

/* 侧栏 —— 浅色近白表面，靠右侧细分隔线与内容区区分 */
QWidget#Sidebar {{ background: {sidebar}; border-right: 1px solid {sidebar_line}; }}
QScrollArea#NavScroll {{ background: transparent; border: none; }}
QWidget#NavHost {{ background: transparent; }}
QLabel#Brand {{ color: {brand_fg}; font-size: 18px; font-weight: bold; padding: 22px 16px 2px 20px; letter-spacing: 1px; }}
QLabel#BrandSub {{ color: {sidebar_dim}; font-size: 10px; padding: 0 16px 16px 20px; }}
QPushButton#NavBtn {{
    background: transparent; border: none; border-left: 3px solid transparent;
    min-height: 44px; text-align: left;
}}
/* 常态透明,让背后的选中指示块透出;hover 才轻微提亮。选中态由 NavIndicator 承担 */
QPushButton#NavBtn:hover {{ background: {sidebar_h}; }}
/* 选中指示,两片平滑滑动:填充块(浅蓝 tint)在按钮之下、强调色竖条在按钮之上(hover 挡不住) */
QWidget#NavIndicator {{ background: {sidebar_a}; border-radius: 8px; }}
QWidget#NavStripe {{ background: {accent}; border-radius: 2px; }}
QLabel#NavText {{ background: transparent; }}
QLabel#NavGroup {{ color: {sidebar_grp}; font-size: 10px; padding: 18px 16px 4px 20px; letter-spacing: 2px; font-weight: bold; }}

/* 卡片 */
QFrame#Card {{ background: {surface}; border: 1px solid {line}; border-radius: 14px; }}
QFrame#Card[dragging="true"] {{ border: 2px solid {accent_l}; background: {accent_soft}; }}

/* 数据库导入拖拽区 */
QFrame#DropArea {{
    background: {surface2}; border: 2px dashed {scroll}; border-radius: 16px;
}}
QFrame#DropArea[dragging="true"] {{ border: 2px dashed {accent}; background: {accent_soft}; }}
QLabel#DropIcon {{ font-size: 40px; color: {accent}; }}
QLabel#DropTitle {{ font-size: 15px; font-weight: bold; color: {heading}; }}

/* 首页 */
QFrame#HeroCard {{
    background: {surface}; border: 1px solid {line}; border-radius: 16px;
}}
QLabel#HeroTitle {{ font-size: 24px; font-weight: bold; color: {heading}; }}
QLabel#HeroPill {{
    background: {accent_soft}; color: {accent}; border-radius: 9px;
    font-size: 11px; font-weight: bold; padding: 2px 10px;
}}
QFrame#HeroRule {{ background: {accent}; border: none; border-radius: 2px; }}
QLabel#HeroDesc {{ font-size: 12px; color: {sub}; line-height: 150%; }}
QLabel#SecTitle {{ font-size: 14px; font-weight: bold; color: {heading}; padding: 2px 0; }}
QFrame#EntryCard {{
    background: {surface}; border: 1px solid {line}; border-radius: 14px; min-height: 98px;
}}
QFrame#EntryCard:hover {{ border: 1px solid {accent}; background: {card_hover}; }}
QLabel#EntryIcon {{ font-size: 22px; }}
QLabel#EntryTitle {{ font-size: 14px; font-weight: bold; color: {heading}; }}
QLabel#EntryDesc {{ font-size: 11px; color: {hint}; }}
QPushButton#CollapseHead {{
    text-align: left; border: none; background: transparent; color: {heading};
    font-size: 13px; font-weight: bold; padding: 7px 2px;
}}
QPushButton#CollapseHead:hover {{ color: {accent}; }}
QLabel#CollapseBody {{
    color: {text}; font-size: 12px; padding: 2px 6px 10px 18px; line-height: 150%;
}}
QLabel#CollapseBody code {{ background: {surface2}; color: {accent}; padding: 1px 4px; }}
QLabel#PageTitle {{ font-size: 22px; font-weight: bold; color: {text}; }}
QLabel#PageDesc {{ font-size: 12px; color: {sub}; }}
QLabel#SecTitle {{ font-size: 13px; font-weight: bold; color: {heading}; }}
QLabel#CardTitle {{ font-size: 13px; font-weight: bold; color: {text}; }}
QLabel#Hint {{ color: {hint}; font-size: 11px; }}
QLabel#OkText {{ color: {ok}; font-size: 11px; }}
QLabel#CapResult {{
    background: {surface2}; border: 1px solid {line}; border-radius: 9px;
    color: {heading}; font-size: 20px; font-weight: bold; padding: 14px 16px;
}}

/* 序号/完成 徽标 —— 动态属性 done 驱动 */
QLabel#Badge {{
    background: {accent}; color: #ffffff; border-radius: 13px;
    font-weight: bold; font-size: 12px; min-width: 26px; min-height: 26px;
    max-width: 26px; max-height: 26px;
}}
QLabel#Badge[done="true"] {{ background: {ok}; }}

/* 圆形帮助徽章 */
QLabel#Help {{
    background: {pill_bg}; color: {sub}; border: 1px solid {line}; border-radius: 9px;
    font-size: 11px; font-weight: bold; min-width: 18px; min-height: 18px;
    max-width: 18px; max-height: 18px; qproperty-alignment: AlignCenter;
}}
QLabel#Help:hover {{ background: {accent}; color: #ffffff; border: 1px solid {accent}; }}

/* 状态胶囊 —— 柔底圆角块承载圆点+文案 */
QFrame#StatusPill {{ background: {pill_bg}; border-radius: 12px; }}
QLabel#StatusText {{ font-size: 11px; color: {sub}; background: transparent; }}

/* 状态点 —— 动态属性 state 驱动 */
QLabel#StatusDot {{ font-size: 11px; color: {hint}; background: transparent; }}
QLabel#StatusDot[state="ready"] {{ color: {accent}; }}
QLabel#StatusDot[state="busy"]  {{ color: {accent_l}; }}
QLabel#StatusDot[state="ok"]    {{ color: {ok}; }}
QLabel#StatusDot[state="warn"]  {{ color: {warn}; }}
QLabel#StatusDot[state="err"]   {{ color: {err}; }}

/* 主按钮 */
QPushButton#Primary {{
    background: {accent}; color: #ffffff; border: none; border-radius: 10px;
    padding: 10px 24px; font-size: 13px; font-weight: bold;
}}
QPushButton#Primary:hover {{ background: {accent_l}; }}
QPushButton#Primary:pressed {{ background: {accent_d}; }}
QPushButton#Primary:disabled {{ background: {dis_bg}; color: {dis_fg}; }}

/* 次按钮 */
QPushButton#Ghost {{
    background: transparent; color: {accent}; border: 1px solid {accent};
    border-radius: 10px; padding: 8px 16px; font-size: 12px;
}}
QPushButton#Ghost:hover {{ background: {ghost_hover}; }}
QPushButton#Ghost:disabled {{ color: {dis_fg}; border: 1px solid {line}; }}
QPushButton#Mini {{
    background: {mini_bg}; color: {sub}; border: 1px solid {line};
    border-radius: 8px; padding: 5px 12px; font-size: 11px;
}}
QPushButton#Mini:hover {{ background: {mini_hover}; color: {text}; }}

/* 折叠"详细信息"链接式按钮 */
QPushButton#Link {{
    background: transparent; color: {sub}; border: none; padding: 3px 2px;
    font-size: 11px; text-align: left;
}}
QPushButton#Link:hover {{ color: {accent}; }}

/* 列表/拖拽区 */
QListWidget {{
    background: {list_bg}; border: 1px solid {line}; border-radius: 9px;
    padding: 4px; font-size: 12px;
}}
QListWidget::item {{ padding: 5px 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {ghost_hover}; }}
QListWidget::item:selected {{ background: {accent}; color: {sel_fg}; }}

/* 日志 */
QPlainTextEdit#Log {{
    background: {logbg}; color: {logfg}; border: 1px solid {line}; border-radius: 9px;
    font-family: "{font}"; font-size: 11px; padding: 8px;
}}

/* 输入 */
QLineEdit, QComboBox, QSpinBox {{
    background: {input_bg}; border: 1px solid {line}; border-radius: 8px;
    padding: 7px 10px; font-size: 12px; color: {text};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border: 1px solid {scroll}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
QLineEdit:disabled {{ color: {hint}; background: {surface2}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {surface}; border: 1px solid {line}; selection-background-color: {accent};
    selection-color: #ffffff; outline: none;
}}

/* 复选/单选 —— 显式描边+填充，深浅色都清晰可见 */
QCheckBox, QRadioButton {{ font-size: 12px; color: {text}; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; background: {input_bg}; border: 2px solid {scroll};
}}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border: 2px solid {accent_l}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent}; border: 2px solid {accent};
}}
QCheckBox::indicator:checked {{ image: url(none); }}

/* 表格 */
QTableWidget {{
    background: {surface}; border: 1px solid {line}; border-radius: 8px;
    gridline-color: {line}; font-size: 12px;
}}
QHeaderView::section {{
    background: {surface2}; color: {sub}; border: none; border-bottom: 1px solid {line};
    padding: 6px 8px; font-size: 11px; font-weight: bold;
}}
QTableWidget::item:selected {{ background: {accent}; color: #ffffff; }}

/* 数据库树 */
QTreeWidget#LibTree {{
    background: {list_bg}; border: 1px solid {line}; border-radius: 10px;
    font-size: 12px; outline: none; padding: 4px 4px 6px 4px;
    show-decoration-selected: 1;
}}
QTreeWidget#LibTree::item {{
    height: 30px; color: {text}; border: none;
    border-top: 1px solid transparent; border-bottom: 1px solid transparent;
}}
QTreeWidget#LibTree::item:hover {{ background: {ghost_hover}; }}
QTreeWidget#LibTree::item:selected {{ background: {accent}; color: {sel_fg}; }}
QTreeWidget#LibTree::branch {{ background: transparent; }}
QTreeWidget#LibTree QHeaderView::section {{
    background: {surface2}; color: {sub}; border: none;
    border-bottom: 1px solid {line}; padding: 7px 10px;
    font-size: 11px; font-weight: bold;
}}

QTabWidget::pane {{ border: 1px solid {line}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {sub}; padding: 7px 14px; font-size: 12px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; font-weight: bold; }}

/* 进度条 —— 更细更圆润 */
QProgressBar {{ background: {pill_bg}; border: none; border-radius: 3px; height: 5px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

/* 滚动条 —— 显式给轨道底色 + 透明的翻页区,杜绝未上色时的黑白方块回退样式 */
QScrollBar:vertical {{
    background: {track}; width: 11px; margin: 0; border: none; border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {scroll}; border-radius: 4px; min-height: 32px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent_l}; }}
QScrollBar:horizontal {{
    background: {track}; height: 11px; margin: 0; border: none; border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {scroll}; border-radius: 4px; min-width: 32px; margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {accent_l}; }}
/* 箭头行 & 翻页区都清零/透明:否则 Qt 会绘制默认贴图(即黑白格) */
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; background: none; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* 提示气泡 —— 显式 border-color/background-color，修复不显示 */
QToolTip {{
    background-color: {tip_bg}; color: {tip_fg}; border: 1px solid {tip_bd};
    border-radius: 6px; padding: 6px 9px; font-size: 12px;
}}

/* 弹窗按钮 */
QMessageBox {{ background: {surface}; }}
QMessageBox QPushButton {{
    background: {accent}; color: #ffffff; border: none; border-radius: 7px;
    padding: 6px 18px; font-size: 12px; min-width: 68px;
}}
QMessageBox QPushButton:hover {{ background: {accent_l}; }}

/* ---------- 导航折叠按钮 ---------- */
QPushButton#NavToggle {{
    background: transparent; color: {sidebar_dim}; border: 1px solid {sidebar_line};
    border-radius: 13px; font-size: 15px; font-weight: bold; padding: 0;
}}
QPushButton#NavToggle:hover {{ background: {sidebar_h}; color: {brand_fg}; }}
QPushButton#NavToggle:pressed {{ background: {sidebar_a}; }}

/* ---------- 右侧滑出面板 ---------- */
QFrame#RightPanel {{ background: {surface}; border-left: 1px solid {line}; }}
QFrame#PanelHeader {{
    background: {surface2}; border-bottom: 1px solid {line};
}}
QLabel#PanelTitle {{ font-size: 13px; font-weight: bold; color: {heading}; background: transparent; }}
QPushButton#PanelClose {{
    background: transparent; color: {sub}; border: none; border-radius: 14px; font-size: 14px;
}}
QPushButton#PanelClose:hover {{ background: {mini_hover}; color: {err}; }}
QScrollArea#PanelScroll {{ background: {surface}; border: none; }}
QFrame#PanelSection {{ background: {surface}; }}
QWidget#PanelEmpty {{ background: {surface}; }}
QLabel#PanelEmptyHint {{ color: {sub}; font-size: 12px; background: transparent; }}
QPushButton#PanelFold {{
    background: transparent; color: {sub}; border: none; font-size: 12px;
}}
QPushButton#PanelFold:hover {{ color: {accent}; }}
QSplitter#PanelSplitter::handle {{ background: {line}; }}
QSplitter#PanelSplitter::handle:vertical {{ height: 1px; }}
QSplitter#PanelSplitter::handle:hover {{ background: {accent}; }}

/* ---------- 文件预览 ---------- */
QFrame#FilePreview {{ background: {surface}; }}
QLabel#PreviewName {{ font-size: 12px; font-weight: bold; color: {heading}; background: transparent; }}
QTableWidget#PreviewTable {{
    background: {surface}; border: 1px solid {line}; gridline-color: {line};
    font-size: 12px; color: {text};
}}
QTableWidget#PreviewTable::item {{ padding: 2px 6px; }}

/* 分隔条：细、低调，悬停高亮 */
QSplitter#ContentSplitter::handle {{ background: {line}; }}
QSplitter#ContentSplitter::handle:horizontal {{ width: 1px; }}
QSplitter#ContentSplitter::handle:hover {{ background: {accent}; }}

/* ---------- 页内通知条 ---------- */
QFrame#NoticeBar {{
    background: {surface2}; border: 1px solid {line}; border-radius: 10px;
}}
QLabel#NoticeText {{ font-size: 12px; color: {text}; background: transparent; }}
QLabel#NoticeDot {{ font-size: 12px; color: {hint}; background: transparent; }}
QLabel#NoticeDot[state="ok"]   {{ color: {ok}; }}
QLabel#NoticeDot[state="warn"] {{ color: {warn}; }}
QLabel#NoticeDot[state="err"]  {{ color: {err}; }}
QLabel#NoticeDot[state="info"] {{ color: {accent}; }}
QPushButton#NoticeAction {{
    background: transparent; color: {accent}; border: 1px solid {accent};
    border-radius: 8px; padding: 4px 12px; font-size: 11px;
}}
QPushButton#NoticeAction:hover {{ background: {ghost_hover}; }}
QPushButton#NoticeClose {{
    background: transparent; color: {hint}; border: none; border-radius: 12px; font-size: 12px;
}}
QPushButton#NoticeClose:hover {{ background: {mini_hover}; color: {sub}; }}
"""
