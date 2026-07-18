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

from PySide2.QtCore import Qt, QTimer
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QScrollArea, QFrame)

from ..worker import Worker
from ..widgets.notice_bar import NoticeBar
from core import settings as settings_mod


class BasePage(QWidget):
    CONTENT_MAX = 1100          # 内容列最大宽度(px)，宽屏时超出部分留白居中

    def __init__(self, main, title, desc):
        super(BasePage, self).__init__()
        self.main = main
        self._worker = None
        self._scan_worker = None        # 预扫描 Worker(与运行 Worker 分开,互不打断)
        self._scan_gen = 0              # 代次守卫:丢弃过期扫描结果(相当于"取消")
        self._scan_cache = {}           # path -> (mtime, result),按 mtime 失效
        self._scan_timer = None         # 防抖定时器
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)

        # 标题头也限同宽居中，与下方内容列左右对齐。
        # CONTENT_MAX 为 None 时不限宽、铺满整行（数据库页等宽表场景用）。
        head_row = QHBoxLayout(); head_row.setContentsMargins(0, 0, 0, 0); head_row.setSpacing(0)
        head_col = QWidget()
        if self.CONTENT_MAX:
            head_col.setMaximumWidth(self.CONTENT_MAX)
        head = QVBoxLayout(head_col)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        t.setAlignment(Qt.AlignHCenter)
        head.addWidget(t)
        d = QLabel(desc)
        d.setObjectName("PageDesc")
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignHCenter)          # 简介逐行居中,与标题对齐更美观
        head.addWidget(d)
        if self.CONTENT_MAX:
            head_row.addStretch(1); head_row.addWidget(head_col, 0); head_row.addStretch(1)
        else:
            head_row.addWidget(head_col, 1)   # 不限宽：标题头铺满整行
        outer.addLayout(head_row)

        # 页内通知条：结果/完成/错误在此就地显示,不再弹窗打断
        self.notice = NoticeBar()
        outer.addWidget(self.notice)

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
        # 限宽居中：内容列最宽 CONTENT_MAX，宽屏时两侧 stretch 均分留白，
        # 窄屏时 stretch 收为 0，内容列自适应铺满。避免最大化时卡片被拉成长条。
        row = QHBoxLayout(body_host)
        row.setContentsMargins(0, 0, 6, 0)
        row.setSpacing(0)
        column = QWidget()
        column.setAttribute(Qt.WA_StyledBackground, True)
        column.setStyleSheet("background: transparent;")
        self.body = QVBoxLayout(column)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(14)
        if self.CONTENT_MAX:
            column.setMaximumWidth(self.CONTENT_MAX)
            row.addStretch(1)
            row.addWidget(column, 0)
            row.addStretch(1)
        else:
            row.addWidget(column, 1)          # 不限宽：内容列铺满整行
        scroll.setWidget(body_host)
        outer.addWidget(scroll, 1)
        from .. import smooth_scroll
        self._smooth = smooth_scroll.enable(scroll)   # 平滑滚动(防 GC 存引用)

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

    # ---------- 选择即扫描(预检,不写盘) ----------
    _SCAN_DEBOUNCE_MS = 250

    def scan_on_select(self, path, analyze_fn, on_ready, debounce_ms=None):
        """用户选/切文件后调用:防抖 + 后台跑 analyze_fn(path,log=) + 按 mtime 缓存。

        - analyze_fn: 只读预检函数(如 delivery_core.analyze),返回可缓存的结果对象。
        - on_ready(result): 主线程回调,拿到预检结果(缓存命中则同步立即回调)。
        - 快速连点/切换只跑最后一次(防抖);过期结果被代次守卫丢弃(可取消)。
        - "生成"按钮不该依赖此扫描,仍各自写盘;此处只为提前反馈。"""
        if not path:
            return
        # 缓存命中(且文件未变)直接回调,不起线程
        cached = self._scan_cache.get(path)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if cached and mtime is not None and cached[0] == mtime:
            on_ready(cached[1])
            return
        # 防抖:重置定时器,只跑最后一次
        if self._scan_timer is not None:
            self._scan_timer.stop()
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(lambda: self._start_scan(path, mtime, analyze_fn, on_ready))
        t.start(self._SCAN_DEBOUNCE_MS if debounce_ms is None else debounce_ms)
        self._scan_timer = t

    def _start_scan(self, path, mtime, analyze_fn, on_ready):
        self._scan_gen += 1
        gen = self._scan_gen

        def job(log):
            return analyze_fn(path, log=log)

        w = Worker(job)

        def _ok(res, g=gen, p=path, mt=mtime):
            if g != self._scan_gen:
                return                          # 已被更晚的选择取代 -> 丢弃(取消)
            if mt is not None:
                self._scan_cache[p] = (mt, res)
            try:
                on_ready(res)
            except Exception:
                pass

        def _err(msg, tb, g=gen):
            if g != self._scan_gen:
                return
            try:
                on_ready(None)                  # 预检失败不打断主流程,交回调决定
            except Exception:
                pass

        w.sig_done.connect(_ok)
        w.sig_error.connect(_err)
        self._scan_worker = w                   # 存引用防 GC
        w.start()

    def cancel_scan(self):
        """作废在途预扫描结果(如离开页面 / 清空文件时)。"""
        self._scan_gen += 1
        if self._scan_timer is not None:
            self._scan_timer.stop()

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
        panel.log_line("[错误] " + msg)
        panel.log_line(tb)
        panel.show_log(True)
        self._save_crash(tb)
        # 不再弹窗打断：通知条就地显示错误摘要，详情在日志里
        self.notice.show_notice("err",
            "%s  (可点下方[详细信息]查看，或联系技术支持)" % friendly)

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

    def notify_done(self, out_dir, title, text):
        """处理完成后的统一收尾：按设置决定是否自动打开输出目录、是否弹提示。

        设置页的“自动打开输出文件夹 / 完成后弹出提示”开关经由此方法生效，
        各功能页调用它替代直接 open_folder + info。"""
        st = settings_mod.get_settings()
        if st.get("auto_open_output", True):
            self.open_folder(out_dir)
        if st.get("show_done_dialog", True):
            # 结果就地通知,附"打开输出文件夹"操作;不再弹窗打断
            actions = None
            if out_dir:
                actions = [("打开输出文件夹", lambda d=out_dir: self.open_folder(d))]
            self.notice.show_notice("ok", text, actions=actions)

    def info(self, title, text):
        """页内信息提示（替代 information 弹窗）。title 并入正文一行显示。"""
        body = ("%s：%s" % (title, text)) if title else text
        self.notice.show_notice("info", body)

    def warn(self, title, text):
        """页内警告提示（替代 warning 弹窗）。"""
        body = ("%s：%s" % (title, text)) if title else text
        self.notice.show_notice("warn", body)

    def confirm(self, text, on_yes, yes_label="确定", kind="warn"):
        """页内确认(替代 QMessageBox.question 打断式弹窗)。

        通知条右侧给一个确认按钮,点击才执行 on_yes;点关闭即取消。用于删除/覆盖
        等破坏性操作前的二次确认——不打断、就地可见、默认不执行。"""
        self.notice.show_notice(kind, text, actions=[(yes_label, on_yes)])
