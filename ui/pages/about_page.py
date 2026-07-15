# -*- coding: utf-8 -*-
"""关于 / 更新页。显示版本信息，检查更新（更新源未配置时给出说明）。"""
import os

from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QPixmap
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QProgressBar, QApplication, QMessageBox)

from .base_page import BasePage
from ..worker import Worker
from .. import icons
from core import version, updater, paths


class AboutPage(BasePage):
    def __init__(self, main):
        super(AboutPage, self).__init__(main, "关于 / 更新", "版本信息与在线更新。")

    def build_body(self, layout):
        # 上排：版本卡 + 更新卡 并排（等宽），充分利用横向空间
        top = QHBoxLayout(); top.setSpacing(14)
        top.addWidget(self._version_card(), 1)
        top.addWidget(self._update_card(), 1)
        layout.addLayout(top)

        # 中排：集成功能宽卡（六大核心业务图标 + 名称）
        layout.addWidget(self._features_card())

        # 底部：品牌页脚，自然收尾，避免大片空白
        layout.addStretch(1)
        layout.addWidget(self._footer())

        self._pending = None        # 待安装的新版信息（检查到更新后暂存）
        self._refresh_update_status()

    def _version_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(6)
        head = QHBoxLayout(); head.setSpacing(12)
        logo = QLabel()
        p = os.path.join(paths.assets_dir(), "logo_128.png")
        if os.path.exists(p):
            logo.setPixmap(QPixmap(p).scaled(48, 48, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
        head.addWidget(logo, 0, Qt.AlignTop)
        namecol = QVBoxLayout(); namecol.setSpacing(2)
        name = QLabel(version.APP_NAME); name.setStyleSheet("font-size:17px; font-weight:bold;")
        namecol.addWidget(name)
        ver = QLabel("版本 " + version.version_str()); ver.setObjectName("Hint")
        namecol.addWidget(ver)
        head.addLayout(namecol, 1)
        v.addLayout(head)
        v.addWidget(self._kv("构建日期", version.BUILD_DATE))
        v.addWidget(self._kv("发布方", version.PUBLISHER))
        v.addWidget(self._kv("运行环境", "Windows 7+ · Python 3.8 · PySide2"))
        v.addStretch(1)
        return card

    def _update_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(8)
        t = QLabel("在线更新"); t.setObjectName("SecTitle"); v.addWidget(t)
        self.status = QLabel(); self.status.setObjectName("Hint"); self.status.setWordWrap(True)
        v.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setVisible(False)
        v.addWidget(self.bar)
        v.addStretch(1)
        row = QHBoxLayout()
        self.btn = QPushButton("检查更新"); self.btn.setObjectName("Primary")
        self.btn.clicked.connect(self._on_button)
        row.addWidget(self.btn); row.addStretch(1)
        v.addLayout(row)
        return card

    def _features_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 16, 20, 16); v.setSpacing(12)
        t = QLabel("集成功能"); t.setObjectName("SecTitle"); v.addWidget(t)
        row = QHBoxLayout(); row.setSpacing(10)
        feats = [("attendance", "考勤填报"), ("reconcile", "工时对账"),
                 ("arrival", "到料明细"), ("pivot", "销售表透视"),
                 ("purchase", "采购对账"), ("delivery", "送货计划")]
        self._feat_icons = []
        for key, label in feats:
            item = QFrame(); item.setObjectName("EntryCard")
            iv = QVBoxLayout(item); iv.setContentsMargins(14, 14, 14, 14); iv.setSpacing(8)
            # 2× 物理分辨率 + setScaledContents 定尺，避免高 DPI 下定尺标签裁切
            ic = QLabel(); ic.setFixedSize(26, 26); ic.setScaledContents(True)
            ic.setPixmap(icons.pixmap(key, 52, None, 1.0))
            iv.addWidget(ic)
            self._feat_icons.append((ic, key))
            lb = QLabel(label); lb.setObjectName("EntryTitle")
            iv.addWidget(lb)
            row.addWidget(item, 1)
        v.addLayout(row)
        return card

    def on_theme_changed(self):
        super(AboutPage, self).on_theme_changed()
        for ic, key in getattr(self, "_feat_icons", []):
            ic.setPixmap(icons.pixmap(key, 52, None, 1.0))

    def _footer(self):
        f = QLabel("%s · © 2026 %s · 保留所有权利"
                   % (version.APP_NAME, version.PUBLISHER))
        f.setObjectName("Hint"); f.setAlignment(Qt.AlignCenter)
        return f

    def _kv(self, k, val):
        w = QLabel("%s：%s" % (k, val)); w.setObjectName("PageDesc"); return w

    def _refresh_update_status(self):
        if updater.is_configured():
            self.status.setText("已配置更新源，可点击检查是否有新版本。")
            self.btn.setEnabled(True)
        else:
            self.status.setText("更新源尚未配置。仓库建立后，在 core/version.py 填入 "
                                "GITHUB_OWNER/GITHUB_REPO 或 UPDATE_MANIFEST_URL 即可启用在线更新。")
            self.btn.setEnabled(False)

    def _on_button(self):
        """一个按钮两种角色：无待装版本=检查更新；有=下载并安装。"""
        if self._pending:
            self._download_and_install()
        else:
            self._check()

    def _check(self):
        self.btn.setEnabled(False)
        self.status.setText("正在检查…")
        w = Worker(lambda log=None: updater.check_update())
        w.sig_done.connect(self._on_result)
        w.sig_error.connect(lambda m, tb: self._on_result({"status": "error", "msg": m}))
        self._w = w
        w.start()

    def _on_result(self, res):
        self.btn.setEnabled(True)
        self._pending = None
        self.btn.setText("检查更新")
        if not res:
            self.status.setText("更新源未配置。")
        elif res.get("status") == "latest":
            self.status.setText("已是最新版本（%s）。" % version.version_str())
        elif res.get("status") == "update":
            if not res.get("url"):
                self.status.setText("发现新版本 v%s，但更新清单未提供下载地址，请联系管理员。"
                                    % res.get("version"))
                return
            self._pending = res
            self.btn.setText("下载并安装 v%s" % res.get("version"))
            notes = res.get("notes", "") or "（无更新说明）"
            self.status.setText("发现新版本 v%s：\n%s" % (res.get("version"), notes))
        else:
            self.status.setText("检查失败：%s\n请检查网络后重试。" % res.get("msg", "网络错误"))

    def _download_and_install(self):
        res = self._pending
        self.btn.setEnabled(False)
        self.bar.setValue(0); self.bar.setVisible(True)
        self.status.setText("正在下载安装包…")
        url = res.get("url")
        w = Worker(lambda log=None, progress=None:
                   updater.download_installer(url, progress=progress, log=log))
        w.sig_progress.connect(self.bar.setValue)
        w.sig_log.connect(self.status.setText)
        w.sig_done.connect(self._on_downloaded)
        w.sig_error.connect(self._on_download_error)
        self._w = w
        w.start()

    def _on_download_error(self, msg, tb):
        self.bar.setVisible(False)
        self.btn.setEnabled(True)
        self.status.setText("下载失败：%s\n可稍后重试，或联系管理员手动更新。" % msg)

    def _on_downloaded(self, path):
        self.bar.setValue(100)
        self.status.setText("下载完成，即将启动安装向导。\n程序会自动退出，请按向导完成安装后重新打开。")
        ret = QMessageBox.information(
            self, "开始安装",
            "安装包已下载完成，点击「确定」后将启动安装向导，本程序会自动关闭。\n"
            "（安装过程可能弹出系统权限提示，请选择「是」。）",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Ok)
        if ret != QMessageBox.Ok:
            self.btn.setEnabled(True)
            self.status.setText("已取消安装。安装包已下载至临时目录，可稍后再装。")
            return
        try:
            updater.run_installer(path)
        except Exception as e:
            self.btn.setEnabled(True)
            self.status.setText("启动安装程序失败：%s" % e)
            return
        # 延迟退出，给安装器起进程的时间，随后释放旧文件占用
        QTimer.singleShot(800, QApplication.quit)
