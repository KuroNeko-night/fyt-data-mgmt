# -*- coding: utf-8 -*-
"""
FileZone —— 可复用的文件选择卡片（拖拽 + 按钮，追加去重）
=========================================================
保留两程序的核心交互：拖拽或按钮都是"追加"（非覆盖）、去重、
校验存在性与 Excel 扩展名；双击移除；序号徽标在有文件时变绿勾。
单文件模式(multi=False)则替换。Qt 原生拖拽，无需 tkinterdnd2。

兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt, Signal, QSize, QEasingCurve, QVariantAnimation
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QFileDialog, QSizePolicy)

from .. import theme

EXCEL_EXT = (".xlsx", ".xlsm", ".xls")


class FileZone(QFrame):
    changed = Signal(list)     # 文件列表变化时发出当前路径列表
    file_clicked = Signal(str) # 单击某个文件行时发出其路径(供侧栏预览)

    def __init__(self, index, title, hint, multi=True,
                 only_xlsx=False, detail="", library_cats=None, parent=None,
                 exts=None, file_filter=None):
        super(FileZone, self).__init__(parent)
        self.setObjectName("Card")
        self._index = index
        self._title = title
        self._multi = multi
        # exts 显式给定时覆盖默认(供 PDF / CSV 等非 Excel 场景复用本组件)
        if exts:
            self._exts = tuple(e.lower() for e in exts)
        else:
            self._exts = (".xlsx", ".xlsm") if only_xlsx else EXCEL_EXT
        self._filter = file_filter
        # 可从数据库选表的类别列表（None 表示不接库）
        self._lib_cats = list(library_cats) if library_cats else None
        self._paths = []
        self._row_anims = []       # 行高动画引用(防 GC)
        self._pending_del = []     # 正在做"收缩消失"的待删行
        self.setAcceptDrops(True)
        self._build(title, hint, detail)

    # ---------- 构建 ----------
    def _build(self, title, hint, detail):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.badge = QLabel(str(self._index))
        self.badge.setObjectName("Badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self._style_badge(False)
        head.addWidget(self.badge)
        tl = QLabel(title)
        tl.setObjectName("CardTitle")
        head.addWidget(tl)
        if detail:
            q = QLabel("?")
            q.setObjectName("Help")
            q.setAlignment(Qt.AlignCenter)
            q.setToolTip(detail)
            q.setCursor(Qt.WhatsThisCursor)
            head.addWidget(q)
        head.addStretch(1)
        self.count = QLabel("")
        self.count.setObjectName("OkText")
        head.addWidget(self.count)
        lay.addLayout(head)

        h = QLabel(hint)
        h.setObjectName("Hint")
        h.setWordWrap(True)
        lay.addWidget(h)

        self.listw = QListWidget()
        self.listw.setFixedHeight(78 if self._multi else 40)
        self.listw.itemDoubleClicked.connect(lambda *_: self._remove_selected())
        self.listw.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self.listw)

        btns = QHBoxLayout()
        btns.setSpacing(6)
        add = QPushButton("＋ 添加文件")
        add.setObjectName("Ghost")
        add.clicked.connect(self._browse)
        btns.addWidget(add)
        if self._lib_cats:
            self.lib_btn = QPushButton("从数据库选择")
            self.lib_btn.setObjectName("Ghost")
            self.lib_btn.clicked.connect(self._pick_from_library)
            btns.addWidget(self.lib_btn)
        rm = QPushButton("删除选中")
        rm.setObjectName("Mini")
        rm.clicked.connect(self._remove_selected)
        btns.addWidget(rm)
        clr = QPushButton("清空")
        clr.setObjectName("Mini")
        clr.clicked.connect(self.clear)
        btns.addWidget(clr)
        btns.addStretch(1)
        tip = QLabel("可拖拽文件到此")
        tip.setObjectName("Hint")
        btns.addWidget(tip)
        lay.addLayout(btns)

    # ---------- 徽标样式（动态属性驱动，随主题自动变色） ----------
    def _style_badge(self, done):
        self.badge.setText("✓" if done else str(self._index))
        theme.set_prop(self.badge, "done", bool(done))

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._flash(True)

    def dragLeaveEvent(self, e):
        self._flash(False)

    def dropEvent(self, e):
        self._flash(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_paths(paths)
        e.acceptProposedAction()

    def _flash(self, on):
        """拖拽悬停高亮：动态属性驱动，随主题变色。"""
        theme.set_prop(self, "dragging", bool(on))

    # ---------- 文件操作 ----------
    def _browse(self):
        filt = self._filter or "Excel 文件 (*.xlsx *.xlsm *.xls);;所有文件 (*.*)"
        if self._multi:
            files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", filt)
        else:
            f, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filt)
            files = [f] if f else []
        if files:
            self.add_paths(files)

    def add_paths(self, paths):
        before = len(self._paths)
        added = 0
        for raw in paths:
            p = self._clean(raw)
            if not p or not os.path.exists(p):
                continue
            if os.path.splitext(p)[1].lower() not in self._exts:
                continue
            if not self._multi:
                self._paths = [p]
                added = 1
                before = 0                       # 单文件替换:整行都当"新行"放大进场
                break
            if p not in self._paths:
                self._paths.append(p)
                added += 1
        if added:
            self._render(grow_from=before)       # 仅新增的尾部行做"放大进场"
            self.changed.emit(list(self._paths))
        return added

    def _clean(self, raw):
        s = str(raw).strip().strip("{}").strip('"').strip("'")
        return s

    def _on_item_clicked(self, item):
        """单击文件行 -> 发路径,供主窗口在侧栏预览。行序与 self._paths 对齐。"""
        r = self.listw.row(item)
        if 0 <= r < len(self._paths):
            self.file_clicked.emit(self._paths[r])

    def _remove_selected(self):
        rows = sorted(r for r in (self.listw.row(i) for i in self.listw.selectedItems())
                      if 0 <= r < len(self._paths))
        if not rows:
            return
        self._pending_del = rows
        anims = []
        for r in rows:                           # 选中行"收缩到 0"再真正删除
            it = self.listw.item(r)
            h0 = self.listw.sizeHintForRow(r)
            if h0 <= 0:
                h0 = it.sizeHint().height() or 22
            a = QVariantAnimation(self)
            a.setDuration(170)
            a.setEasingCurve(QEasingCurve.InCubic)
            a.setStartValue(int(h0))
            a.setEndValue(0)
            a.valueChanged.connect(lambda v, itm=it: itm.setSizeHint(QSize(0, int(v))))
            anims.append(a)
        self._row_anims = anims
        anims[0].finished.connect(self._commit_delete)   # 同时长,一起结束
        for a in anims:
            a.start()

    def _commit_delete(self):
        for r in sorted(self._pending_del, reverse=True):
            if 0 <= r < len(self._paths):
                del self._paths[r]
        self._pending_del = []
        self._render()                           # 重建(无动画)
        self.changed.emit(list(self._paths))

    def clear(self):
        if self._paths:
            self._paths = []
            self._render()
            self.changed.emit([])

    def _render(self, grow_from=None):
        self.listw.clear()
        for i, p in enumerate(self._paths, 1):
            it = QListWidgetItem("  %d.  %s" % (i, os.path.basename(p)))
            it.setToolTip(p)
            self.listw.addItem(it)
        n = len(self._paths)
        self.count.setText("已选 %d 个" % n if n else "")
        self._style_badge(n > 0)
        if grow_from is not None and n > grow_from:
            self._grow_rows(grow_from)           # 新增行"由小放大"弹性进场

    def _grow_rows(self, start_row):
        """把 [start_row, 末尾] 的新行从 0 高度带回弹地放大到自然高度。"""
        anims = []
        for r in range(start_row, self.listw.count()):
            it = self.listw.item(r)
            nat = self.listw.sizeHintForRow(r)
            if nat <= 0:
                nat = 22
            it.setSizeHint(QSize(0, 0))          # 先压平,避免整高闪一下
            a = QVariantAnimation(self)
            a.setDuration(260)
            a.setEasingCurve(QEasingCurve.OutBack)   # 回弹,略微过冲更有弹性
            a.setStartValue(0)
            a.setEndValue(int(nat))
            a.valueChanged.connect(
                lambda v, itm=it: itm.setSizeHint(QSize(0, max(0, int(v)))))
            a.finished.connect(
                lambda itm=it, h=int(nat): itm.setSizeHint(QSize(0, h)))
            anims.append(a)
        self._row_anims = anims
        for a in anims:
            a.start()

    def get(self):
        return list(self._paths)

    def set_paths(self, paths):
        self._paths = []
        self.add_paths(paths)

    # ---------- 数据库联动 ----------
    def _pick_from_library(self):
        from ..dialogs.library_picker import LibraryPicker
        dlg = LibraryPicker(self._lib_cats, multi=self._multi, parent=self,
                            title="从数据库选择 · " + self._title)
        if dlg.exec_():
            chosen = dlg.chosen()
            if chosen:
                self.add_paths(chosen)

    def refresh_lib_count(self):
        """刷新"从数据库选择"按钮上的库内数量提示。"""
        if not self._lib_cats:
            return
        from core import library
        n = sum(len(library.list_items(c)) for c in self._lib_cats)
        self.lib_btn.setText("从数据库选择（%d）" % n if n else "从数据库选择")
        self.lib_btn.setEnabled(n > 0)
