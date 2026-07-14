# -*- coding: utf-8 -*-
"""
数据库页 —— 自带存储 + 自动分类 + 归档管理
============================================
拖入任意表格，程序自动识别用途归档，展示每张表的类别/最后更新/大小/可信度；
支持搜索、多选批量移除/改判；未识别的单独归入“未识别”。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QBrush, QFont
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTreeWidget, QTreeWidgetItem, QMessageBox,
                               QInputDialog, QLineEdit, QAbstractItemView)

from .base_page import BasePage
from ..widgets.drop_area import DropArea
from .. import theme
from core import library, paths

# 每个类别一个小图标，让分组一眼可辨
CAT_ICON = {
    "att_source": "🕘", "att_target": "🗓", "rec_source": "📋",
    "rec_zong": "📑", "rec_labor": "🧾", "pivot_src": "📦",
    "arrival_plan": "🚚", library.UNKNOWN: "❓",
}


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0


def _conf_color(pct):
    """可信度配色：高=绿、中=橙、低=红，取当前主题色。"""
    c = theme.COLORS
    if pct >= 80:
        return c["ok"]
    if pct >= 55:
        return c["warn"]
    return c["err"]


class LibraryPage(BasePage):
    CONTENT_MAX = None      # 数据库页含宽表(类别/更新/大小/可信度多列)，铺满整行避免信息被截断

    def __init__(self, main):
        super(LibraryPage, self).__init__(
            main, "数据库",
            "把各处的表格拖进来，程序自动识别用途并归档。各功能可直接从这里取用所需的表。")

    def build_body(self, layout):
        self.drop = DropArea()
        self.drop.files.connect(self._import)
        layout.addWidget(self.drop)

        # 搜索 + 汇总
        top = QHBoxLayout(); top.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 搜索表名、类别、来源…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.search.setMaximumWidth(320)
        top.addWidget(self.search)
        self.summary = QLabel(""); self.summary.setObjectName("Hint")
        top.addWidget(self.summary)
        top.addStretch(1)
        layout.addLayout(top)

        # 操作条
        bar = QHBoxLayout(); bar.setSpacing(8)
        self.sel_lbl = QLabel(""); self.sel_lbl.setObjectName("Hint")
        bar.addWidget(self.sel_lbl)
        bar.addStretch(1)
        self.btn_all = QPushButton("全选"); self.btn_all.setObjectName("Mini")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_reclass = QPushButton("重新分类"); self.btn_reclass.setObjectName("Ghost")
        self.btn_reclass.clicked.connect(self._reclassify)
        self.btn_remove = QPushButton("移除"); self.btn_remove.setObjectName("Mini")
        self.btn_remove.clicked.connect(self._remove)
        self.btn_open = QPushButton("打开归档目录"); self.btn_open.setObjectName("Mini")
        self.btn_open.clicked.connect(lambda: self.open_folder(paths.library_dir()))
        for b in (self.btn_all, self.btn_reclass, self.btn_remove, self.btn_open):
            bar.addWidget(b)
        layout.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setObjectName("LibTree")
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["名称", "最后更新", "大小", "可信度"])
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.setColumnWidth(0, 360)
        self.tree.setColumnWidth(1, 130)
        self.tree.setColumnWidth(2, 80)
        self.tree.header().resizeSection(3, 90)
        self.tree.setMinimumHeight(300)
        self.tree.itemSelectionChanged.connect(self._on_sel)
        layout.addWidget(self.tree, 1)
        self._refresh()
        self._on_sel()

    # ---------- 展示 ----------
    def _refresh(self):
        self.tree.clear()
        cats = library.CATEGORIES + [library.UNKNOWN]
        total = 0
        head_font = QFont(); head_font.setBold(True)
        for cat in cats:
            items = library.list_items(cat)
            n = len(items)
            total += n
            if n == 0:
                continue
            title = "%s  %s  ·  %d 张" % (
                CAT_ICON.get(cat, "•"), library.CATEGORY_TITLES.get(cat, cat), n)
            top = QTreeWidgetItem(self.tree, [title, "", "", ""])
            top.setFirstColumnSpanned(True)
            top.setFlags(Qt.ItemIsEnabled)          # 分组行不可选
            top.setData(0, Qt.UserRole, None)
            top.setFont(0, head_font)
            top.setForeground(0, QBrush(QColor(theme.COLORS["heading"])))
            top.setExpanded(True)
            for it in sorted(items, key=lambda x: x.get("updated", ""), reverse=True):
                pct = it.get("confidence", 0)
                leaf = QTreeWidgetItem(top, [
                    "   " + it["name"], it.get("updated", ""),
                    _fmt_size(it.get("size", 0)), "● %d%%" % pct])
                leaf.setForeground(3, QBrush(QColor(_conf_color(pct))))
                leaf.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                leaf.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
                sig = "；".join(it.get("signals", [])) or "（无明显特征）"
                tip = "识别依据：%s\n归档路径：%s" % (sig, it.get("path", ""))
                if it.get("origin"):
                    tip += "\n来源：%s" % it["origin"]
                for c in range(4):
                    leaf.setToolTip(c, tip)
                blob = " ".join([it["name"], library.CATEGORY_TITLES.get(cat, ""),
                                 it.get("origin", ""), sig]).lower()
                leaf.setData(0, Qt.UserRole, (it["category"], it["name"]))
                leaf.setData(0, Qt.UserRole + 1, blob)   # 供搜索匹配
        parts = ["共 %d 张表" % total]
        cnt = library.counts()
        if cnt.get(library.UNKNOWN):
            parts.append("未识别 %d 张" % cnt[library.UNKNOWN])
        self.summary.setText("　·　".join(parts) if total else "数据库为空，拖入表格开始归档。")
        if self.search.text().strip():
            self._apply_filter(self.search.text())

    # ---------- 搜索 ----------
    def _apply_filter(self, text):
        q = (text or "").strip().lower()
        shown = 0
        for i in range(self.tree.topLevelItemCount()):
            grp = self.tree.topLevelItem(i)
            vis_children = 0
            for j in range(grp.childCount()):
                leaf = grp.child(j)
                blob = leaf.data(0, Qt.UserRole + 1) or ""
                match = (q in blob) if q else True
                leaf.setHidden(not match)
                if match:
                    vis_children += 1
            grp.setHidden(vis_children == 0)
            if vis_children:
                grp.setExpanded(True)
            shown += vis_children
        if q:
            self.summary.setText("搜索到 %d 张表" % shown if shown else "没有匹配的表")
        else:
            self._update_summary()

    def _update_summary(self):
        total = sum(library.counts().get(c, 0)
                    for c in library.CATEGORIES + [library.UNKNOWN])
        cnt = library.counts()
        parts = ["共 %d 张表" % total]
        if cnt.get(library.UNKNOWN):
            parts.append("未识别 %d 张" % cnt[library.UNKNOWN])
        self.summary.setText("　·　".join(parts) if total else "数据库为空，拖入表格开始归档。")

    # ---------- 选择 ----------
    def _selected_leaves(self):
        out = []
        for it in self.tree.selectedItems():
            key = it.data(0, Qt.UserRole)
            if key:
                out.append(key)
        return out

    def _select_all(self):
        self.tree.clearSelection()
        for i in range(self.tree.topLevelItemCount()):
            grp = self.tree.topLevelItem(i)
            if grp.isHidden():
                continue
            for j in range(grp.childCount()):
                leaf = grp.child(j)
                if not leaf.isHidden():
                    leaf.setSelected(True)

    def _on_sel(self):
        keys = self._selected_leaves()
        n = len(keys)
        self.btn_remove.setEnabled(n > 0)
        self.btn_reclass.setEnabled(n > 0)
        self.sel_lbl.setText("已选 %d 张" % n if n else "")

    # ---------- 导入 ----------
    def _import(self, files):
        files = [f for f in files if os.path.exists(f)]
        if not files:
            return
        items = library.import_many(files)
        self._refresh()
        lines, unknown = [], 0
        for it in items:
            if it["category"] == library.UNKNOWN:
                unknown += 1
            lines.append("· %s → %s（%d%%）" % (
                it["name"], library.CATEGORY_TITLES.get(it["category"], ""),
                it.get("confidence", 0)))
        msg = "已导入 %d 张表：\n\n%s" % (len(items), "\n".join(lines[:12]))
        if len(lines) > 12:
            msg += "\n… 等 %d 张" % len(lines)
        if unknown:
            msg += "\n\n其中 %d 张未能识别，已放入“未识别”，可稍后手动归类。" % unknown
        self.info("导入完成", msg)
        ret = QMessageBox.question(
            self, "删除原文件？",
            "表格已复制进数据库。是否删除原始文件？\n（删除后原位置将不再保留，数据库中的副本不受影响）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            gone = 0
            for f in files:
                try:
                    os.remove(f); gone += 1
                except Exception:
                    pass
            self.info("已删除", "已删除 %d 个原始文件。" % gone)

    # ---------- 批量移除 / 改判 ----------
    def _remove(self):
        keys = self._selected_leaves()
        if not keys:
            return
        if len(keys) == 1:
            body = "确定从数据库移除「%s」？" % keys[0][1]
        else:
            body = "确定从数据库移除选中的 %d 张表？" % len(keys)
        ret = QMessageBox.question(
            self, "移除", body + "\n（归档副本将一并删除，不影响其他位置的文件）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            for cat, name in keys:
                library.remove_item(cat, name, delete_file=True)
            self._refresh(); self._on_sel()

    def _reclassify(self):
        keys = self._selected_leaves()
        if not keys:
            return
        cats = library.CATEGORIES + [library.UNKNOWN]
        titles = [library.CATEGORY_TITLES[c] for c in cats]
        cur = cats.index(keys[0][0]) if keys[0][0] in cats else 0
        prompt = ("把「%s」归为：" % keys[0][1] if len(keys) == 1
                  else "把选中的 %d 张表统一归为：" % len(keys))
        choice, ok = QInputDialog.getItem(self, "重新分类", prompt, titles, cur, False)
        if ok and choice:
            new_cat = cats[titles.index(choice)]
            for cat, name in keys:
                if new_cat != cat:
                    library.reclassify(cat, name, new_cat)
            self._refresh(); self._on_sel()

    def refresh_view(self):
        """外部（导入后/切页时）刷新。"""
        self._refresh()

    def on_theme_changed(self):
        """主题切换后重建，让分组标题色/可信度色跟随新配色。"""
        if hasattr(self.drop, "_refresh_icon"):
            self.drop._refresh_icon()
        self._refresh()
