# -*- coding: utf-8 -*-
"""设置页。统一输出位置(解决混乱点) + 启动检查更新 + 打开数据目录。"""
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QRadioButton, QButtonGroup, QLineEdit, QPushButton,
                               QFileDialog, QCheckBox)
from ..animations import AnimatedCheckBox as QCheckBox   # 勾选带打勾动画

from .base_page import BasePage
from core import settings as settings_mod, paths, version, library


class SettingsPage(BasePage):
    def __init__(self, main):
        self.settings = settings_mod.get_settings()
        super(SettingsPage, self).__init__(
            main, "设置", "统一管理各功能的输出位置与系统选项。改动即时生效。")

    def build_body(self, layout):
        # 双列布局：把卡片分到左右两栏，宽屏时充分利用横向空间、消除大片留白。
        cols = QHBoxLayout(); cols.setSpacing(14)
        left = QVBoxLayout(); left.setSpacing(14)
        right = QVBoxLayout(); right.setSpacing(14)
        cols.addLayout(left, 1); cols.addLayout(right, 1)

        left.addWidget(self._card_output())
        left.addWidget(self._card_storage())
        left.addStretch(1)

        right.addWidget(self._card_appearance())
        right.addWidget(self._card_behavior())
        right.addWidget(self._card_system())
        right.addStretch(1)

        layout.addLayout(cols)

        # 精致收尾：品牌页脚
        layout.addStretch(1)
        foot = QLabel("%s · © 2026 %s" % (version.APP_NAME, version.PUBLISHER))
        foot.setObjectName("Hint"); foot.setAlignment(Qt.AlignCenter)
        layout.addWidget(foot)

        self._load()

    # ---------- 各卡片 ----------
    def _card_output(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(8)
        t = QLabel("输出位置"); t.setObjectName("SecTitle"); v.addWidget(t)
        h = QLabel("各功能的处理结果统一按此规则存放，按“功能/时间戳”归档。")
        h.setObjectName("Hint"); h.setWordWrap(True); v.addWidget(h)
        self.grp = QButtonGroup(self)
        self.rb_unified = QRadioButton("文档下统一文件夹（推荐）")
        self.rb_beside = QRadioButton("源文件旁的 output 文件夹")
        self.rb_custom = QRadioButton("自定义文件夹")
        for i, rb in enumerate((self.rb_unified, self.rb_beside, self.rb_custom)):
            self.grp.addButton(rb, i); v.addWidget(rb)
            rb.toggled.connect(self._on_mode)
        self.lbl_unified = QLabel("→ " + paths.default_output_root())
        self.lbl_unified.setObjectName("Hint"); self.lbl_unified.setWordWrap(True)
        v.addWidget(self.lbl_unified)
        row = QHBoxLayout()
        self.ed_custom = QLineEdit(self.settings.custom_output_root)
        self.ed_custom.setPlaceholderText("选择一个自定义输出根目录…")
        btn = QPushButton("浏览…"); btn.setObjectName("Mini"); btn.clicked.connect(self._pick)
        row.addWidget(self.ed_custom, 1); row.addWidget(btn)
        v.addLayout(row)
        return card

    def _card_appearance(self):
        card = QFrame(); card.setObjectName("Card")
        va = QVBoxLayout(card); va.setContentsMargins(16, 14, 16, 14); va.setSpacing(8)
        ta = QLabel("外观"); ta.setObjectName("SecTitle"); va.addWidget(ta)
        ha = QLabel("选择界面主题。“跟随系统”会自动匹配 Windows 的浅色/深色设置。")
        ha.setObjectName("Hint"); ha.setWordWrap(True); va.addWidget(ha)
        self.grp_theme = QButtonGroup(self)
        self.rb_auto = QRadioButton("跟随系统（推荐）")
        self.rb_light = QRadioButton("浅色")
        self.rb_dark = QRadioButton("深色")
        theme_row = QHBoxLayout(); theme_row.setSpacing(18)
        for rb in (self.rb_auto, self.rb_light, self.rb_dark):
            self.grp_theme.addButton(rb); theme_row.addWidget(rb)
            rb.toggled.connect(self._on_theme)
        theme_row.addStretch(1)
        va.addLayout(theme_row)
        return card

    def _card_behavior(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(8)
        t = QLabel("处理行为"); t.setObjectName("SecTitle"); v.addWidget(t)
        h = QLabel("控制各功能处理完成后的收尾动作。")
        h.setObjectName("Hint"); h.setWordWrap(True); v.addWidget(h)
        self.cb_autoopen = QCheckBox("处理完成后自动打开输出文件夹")
        self.cb_autoopen.setChecked(bool(self.settings.get("auto_open_output", True)))
        self.cb_autoopen.toggled.connect(
            lambda on: self._save_bool("auto_open_output", on))
        v.addWidget(self.cb_autoopen)
        self.cb_donedlg = QCheckBox("处理完成后弹出结果提示框")
        self.cb_donedlg.setChecked(bool(self.settings.get("show_done_dialog", True)))
        self.cb_donedlg.toggled.connect(
            lambda on: self._save_bool("show_done_dialog", on))
        v.addWidget(self.cb_donedlg)
        self.cb_tray = QCheckBox("点关闭按钮时最小化到托盘（而非退出程序）")
        self.cb_tray.setChecked(bool(self.settings.get("minimize_to_tray", True)))
        self.cb_tray.toggled.connect(
            lambda on: self._save_bool("minimize_to_tray", on))
        v.addWidget(self.cb_tray)
        return card

    def _card_storage(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(8)
        t = QLabel("数据库存储"); t.setObjectName("SecTitle"); v.addWidget(t)
        self.lbl_store = QLabel("统计中…"); self.lbl_store.setObjectName("Hint")
        self.lbl_store.setWordWrap(True); v.addWidget(self.lbl_store)
        r = QHBoxLayout()
        b_open = QPushButton("打开归档目录"); b_open.setObjectName("Ghost")
        b_open.clicked.connect(lambda: self._open(paths.library_dir()))
        b_ref = QPushButton("刷新统计"); b_ref.setObjectName("Mini")
        b_ref.clicked.connect(self._refresh_storage)
        r.addWidget(b_open); r.addWidget(b_ref); r.addStretch(1)
        v.addLayout(r)
        self._refresh_storage()
        return card

    def _card_system(self):
        card = QFrame(); card.setObjectName("Card")
        v2 = QVBoxLayout(card); v2.setContentsMargins(16, 14, 16, 14); v2.setSpacing(8)
        t2 = QLabel("系统"); t2.setObjectName("SecTitle"); v2.addWidget(t2)
        self.cb_update = QCheckBox("启动时自动检查更新")
        self.cb_update.setChecked(bool(self.settings.get("check_update_on_start", False)))
        self.cb_update.toggled.connect(self._on_update_toggle)
        v2.addWidget(self.cb_update)
        r2 = QHBoxLayout()
        b_data = QPushButton("打开数据目录"); b_data.setObjectName("Ghost")
        b_data.clicked.connect(lambda: self._open(paths.app_data_dir()))
        b_log = QPushButton("打开错误日志"); b_log.setObjectName("Ghost")
        b_log.clicked.connect(self._open_log)
        r2.addWidget(b_data); r2.addWidget(b_log); r2.addStretch(1)
        v2.addLayout(r2)
        return card

    def _load(self):
        mode = self.settings.output_mode
        {"unified": self.rb_unified, "beside": self.rb_beside,
         "custom": self.rb_custom}.get(mode, self.rb_unified).setChecked(True)
        self.ed_custom.setEnabled(mode == "custom")
        tmode = self.settings.theme_mode
        {"auto": self.rb_auto, "light": self.rb_light,
         "dark": self.rb_dark}.get(tmode, self.rb_auto).setChecked(True)

    def _on_theme(self, *_):
        if not any((self.rb_auto.isChecked(), self.rb_light.isChecked(),
                    self.rb_dark.isChecked())):
            return
        mode = ("auto" if self.rb_auto.isChecked()
                else "light" if self.rb_light.isChecked() else "dark")
        if mode == self.settings.theme_mode:
            return
        self.settings.set("theme_mode", mode)
        self.settings.save()
        self.main.apply_theme(mode)      # 实时换肤

    def _on_mode(self, *_):
        if self.rb_unified.isChecked(): mode = "unified"
        elif self.rb_beside.isChecked(): mode = "beside"
        else: mode = "custom"
        self.ed_custom.setEnabled(mode == "custom")
        self.settings.set("output_mode", mode)
        self.settings.save()

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出根目录", self.ed_custom.text() or "")
        if d:
            self.ed_custom.setText(d)
            self.settings.set("custom_output_root", d)
            self.rb_custom.setChecked(True)
            self.settings.save()

    def _on_update_toggle(self, on):
        self.settings.set("check_update_on_start", bool(on))
        self.settings.save()

    def refresh_view(self):
        """进入设置页时刷新数据库存储统计（可能刚导入过文件）。"""
        if hasattr(self, "lbl_store"):
            self._refresh_storage()

    def _save_bool(self, key, on):
        self.settings.set(key, bool(on))
        self.settings.save()

    def _refresh_storage(self):
        try:
            n, nbytes = library.storage_stats()
            self.lbl_store.setText(
                "已归档 %d 张表 · 占用 %s\n位置：%s"
                % (n, library.human_size(nbytes), paths.library_dir()))
        except Exception:
            self.lbl_store.setText("位置：%s" % paths.library_dir())

    def _open_log(self):
        p = paths.crash_log_path()
        try:
            if os.path.isfile(p):
                os.startfile(p)
            else:
                self.info("暂无日志", "还没有产生任何错误日志，程序运行正常。")
        except Exception:
            pass

    def _open(self, d):
        try:
            if d and os.path.isdir(d):
                os.startfile(d)
        except Exception:
            pass
