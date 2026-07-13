# -*- coding: utf-8 -*-
"""
BasePage —— 功能页公共骨架
==========================
统一的标题/说明头 + 可滚动内容区 + 线程运行辅助。
子类在 build_body(layout) 填内容，用 self.launch(fn, panel, on_done) 跑 core。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os
import traceback

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QLabel, QScrollArea,
                               QFrame, QMessageBox)

from ..worker import Worker


class BasePage(QWidget):
    def __init__(self, main, title, desc):
        super(BasePage, self).__init__()
        self.main = main
        self._worker = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        head.addWidget(t)
        d = QLabel(desc)
        d.setObjectName("PageDesc")
        d.setWordWrap(True)
        head.addWidget(d)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 让滚动区透明，露出窗口背景（否则深色主题下视口会是默认浅色）
        scroll.setAttribute(Qt.WA_StyledBackground, True)
        scroll.viewport().setAutoFillBackground(False)
        body_host = QWidget()
        body_host.setAttribute(Qt.WA_StyledBackground, True)
        body_host.setStyleSheet("background: transparent;")
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.body = QVBoxLayout(body_host)
        self.body.setContentsMargins(0, 0, 6, 0)
        self.body.setSpacing(14)
        scroll.setWidget(body_host)
        outer.addWidget(scroll, 1)

        self.build_body(self.body)
        self._apply_shadows()

    def build_body(self, layout):
        """子类实现。"""
        raise NotImplementedError

    # ---------- 卡片描边（美化 + 主题联动） ----------
    def _apply_shadows(self):
        """不再用 QGraphicsDropShadowEffect 做投影。

        图形特效会把卡片(含其中文字)整体渲到离屏缓冲，导致文字改用灰度抗锯齿、
        在浅色底上明显发虚。改由 QSS 的边框+圆角+表面色区分卡片, 文字保持 ClearType 清晰。
        这里主动清掉可能残留的旧特效。"""
        from PySide2.QtWidgets import QFrame
        for card in self.findChildren(QFrame):
            if card.objectName() == "Card" and card.graphicsEffect() is not None:
                card.setGraphicsEffect(None)

    def on_theme_changed(self):
        """主题切换后的联动钩子（主窗口 apply_theme 会调用）。"""
        self._apply_shadows()

    # ---------- 线程运行 ----------
    def launch(self, fn, panel, on_done):
        """在子线程跑 fn(log=...)；panel 为 RunPanel；on_done(result) 成功回调。"""
        panel.busy(True)
        w = Worker(fn)
        w.sig_log.connect(panel.log_line)
        w.sig_done.connect(lambda res: self._finish_ok(res, panel, on_done))
        w.sig_error.connect(lambda msg, tb: self._finish_err(msg, tb, panel))
        self._worker = w
        w.start()

    def _finish_ok(self, res, panel, on_done):
        panel.busy(False)
        try:
            on_done(res)
        except Exception:
            panel.log_line(traceback.format_exc())

    def _finish_err(self, msg, tb, panel):
        panel.busy(False)
        friendly = self._friendly_error(msg)
        panel.set_status("err", friendly)
        # 技术细节写进折叠日志与崩溃日志文件，不在弹窗里堆给客户
        panel.log_line("【错误】" + msg)
        panel.log_line(tb)
        panel.show_log(True)                 # 出错时自动展开详细信息
        self._save_crash(tb)
        QMessageBox.warning(
            self, "处理未完成",
            "%s\n\n如需排查，可点面板上的“详细信息”查看，或联系技术支持。" % friendly)

    def _friendly_error(self, msg):
        """把常见异常翻译成客户能懂的一句话。"""
        m = (msg or "").lower()
        if "permission" in m or "拒绝访问" in msg or "being used" in m or "使用" in msg:
            return "文件正被占用或无写入权限，请关闭正在打开的表格后重试。"
        if "no such file" in m or "cannot find" in m or "找不到" in msg:
            return "找不到某个文件，可能已被移动或删除，请重新选择。"
        if "not a zip" in m or "corrupt" in m or "badzip" in m:
            return "有文件已损坏或不是有效的 Excel，请检查后重试。"
        return "处理时遇到问题：" + (msg or "未知错误")

    def _save_crash(self, tb):
        try:
            from core import paths
            import datetime
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(paths.crash_log_path(), "a", encoding="utf-8") as f:
                f.write("\n===== %s (处理错误) =====\n%s\n" % (stamp, tb))
        except Exception:
            pass

    def open_folder(self, path):
        try:
            if path and os.path.isdir(path):
                os.startfile(path)          # Windows
            elif path:
                os.startfile(os.path.dirname(path))
        except Exception:
            pass

    def info(self, title, text):
        QMessageBox.information(self, title, text)

    def warn(self, title, text):
        QMessageBox.warning(self, title, text)
