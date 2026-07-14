# -*- coding: utf-8 -*-
"""
批量重命名页 —— 办公通用小工具(纯本地、可预览、可撤销)
========================================================
拖入/选择任意文件 → 设置规则(查找替换/前后缀/统一基名+序号/扩展名小写) →
实时预览新名并标出冲突 → 一键应用(就地改名) → 可一键撤销上次操作。
全宽布局(CONTENT_MAX=None)，预览表信息不被截断。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QBrush
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QFrame, QPushButton, QLineEdit, QCheckBox,
                               QSpinBox, QComboBox, QFileDialog, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QMessageBox)

from .base_page import BasePage
from .. import theme
from core import rename_core

# 状态 → (中文, 颜色键)。ok 用普通前景，其余用告警/错误色。
_STATUS_CN = {
    "ok": ("将重命名", "ok"), "same": ("无变化", "hint"),
    "empty": ("新名为空", "err"), "invalid": ("名称非法", "err"),
    "dup": ("批次内重名", "err"), "exists": ("目标已存在", "warn"),
}


class RenamePage(BasePage):
    CONTENT_MAX = None      # 预览表较宽，铺满整行

    def __init__(self, main):
        self._paths = []            # 当前文件列表(全路径，顺序即序号顺序)
        self._undo_map = None       # 上次应用的撤销映射
        super(RenamePage, self).__init__(
            main, "批量重命名",
            "把文件拖进来，按规则批量改名：查找替换、加前后缀、统一基名+序号。"
            "先预览再应用，支持一键撤销。")
        self.setAcceptDrops(True)

    def build_body(self, layout):
        layout.addWidget(self._files_card(), 1)
        layout.addWidget(self._rules_card())
        layout.addWidget(self._apply_card())
        self._refresh_preview()

    # ---------- 文件区 ----------
    def _files_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(8)
        top = QHBoxLayout()
        t = QLabel("文件列表"); t.setObjectName("SecTitle"); top.addWidget(t)
        top.addStretch(1)
        b_add = QPushButton("＋ 添加文件"); b_add.setObjectName("Mini")
        b_add.clicked.connect(self._add_files)
        b_del = QPushButton("移除所选"); b_del.setObjectName("Mini")
        b_del.clicked.connect(self._remove_selected)
        b_clr = QPushButton("清空"); b_clr.setObjectName("Mini")
        b_clr.clicked.connect(self._clear)
        b_up = QPushButton("上移"); b_up.setObjectName("Mini")
        b_up.clicked.connect(lambda: self._move(-1))
        b_dn = QPushButton("下移"); b_dn.setObjectName("Mini")
        b_dn.clicked.connect(lambda: self._move(1))
        for b in (b_up, b_dn, b_add, b_del, b_clr):
            top.addWidget(b)
        v.addLayout(top)
        hint = QLabel("可把文件从资源管理器拖到此页任意位置。顺序即序号顺序，用上移/下移调整。")
        hint.setObjectName("Hint"); hint.setWordWrap(True); v.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["原文件名", "新文件名", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(240)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        v.addWidget(self.table, 1)
        return card

    # ---------- 规则区 ----------
    def _rules_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(10)
        t = QLabel("重命名规则"); t.setObjectName("SecTitle"); v.addWidget(t)
        order = QLabel("执行顺序：统一基名 → 查找替换 → 序号 → 前后缀 → 扩展名。"
                       "改动任一项都会即时更新上方预览。")
        order.setObjectName("Hint"); order.setWordWrap(True); v.addWidget(order)

        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(10)
        # 查找替换
        g.addWidget(QLabel("查找"), 0, 0)
        self.ed_find = QLineEdit(); self.ed_find.setPlaceholderText("要替换掉的文字，可留空")
        g.addWidget(self.ed_find, 0, 1)
        g.addWidget(QLabel("替换为"), 0, 2)
        self.ed_repl = QLineEdit(); self.ed_repl.setPlaceholderText("替换成的文字，可留空=删除")
        g.addWidget(self.ed_repl, 0, 3)
        self.cb_regex = QCheckBox("按正则表达式")
        g.addWidget(self.cb_regex, 0, 4)
        # 前后缀
        g.addWidget(QLabel("前缀"), 1, 0)
        self.ed_prefix = QLineEdit(); self.ed_prefix.setPlaceholderText("加在最前，如 2026_")
        g.addWidget(self.ed_prefix, 1, 1)
        g.addWidget(QLabel("后缀"), 1, 2)
        self.ed_suffix = QLineEdit(); self.ed_suffix.setPlaceholderText("加在扩展名前，如 _已核")
        g.addWidget(self.ed_suffix, 1, 3)
        self.cb_lower = QCheckBox("扩展名转小写")
        g.addWidget(self.cb_lower, 1, 4)
        # 统一基名
        g.addWidget(QLabel("统一基名"), 2, 0)
        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("填了则把主名整体替换成它(常配合序号)，如 考勤表")
        g.addWidget(self.ed_base, 2, 1, 1, 4)
        v.addLayout(g)
        v.addLayout(self._seq_row())

        for w in (self.ed_find, self.ed_repl, self.ed_prefix, self.ed_suffix, self.ed_base):
            w.textChanged.connect(self._refresh_preview)
        for c in (self.cb_regex, self.cb_lower):
            c.toggled.connect(self._refresh_preview)
        return card

    def _seq_row(self):
        row = QHBoxLayout(); row.setSpacing(8)
        self.cb_seq = QCheckBox("追加序号")
        self.cb_seq.toggled.connect(self._on_seq_toggle)
        row.addWidget(self.cb_seq)
        row.addWidget(QLabel("起始"))
        self.sp_start = QSpinBox(); self.sp_start.setRange(0, 999999); self.sp_start.setValue(1)
        self.sp_start.setFixedWidth(80)
        row.addWidget(self.sp_start)
        row.addWidget(QLabel("位数"))
        self.sp_digits = QSpinBox(); self.sp_digits.setRange(1, 8); self.sp_digits.setValue(3)
        self.sp_digits.setFixedWidth(60)
        row.addWidget(self.sp_digits)
        row.addWidget(QLabel("分隔符"))
        self.ed_sep = QLineEdit("_"); self.ed_sep.setFixedWidth(60)
        row.addWidget(self.ed_sep)
        row.addStretch(1)
        for w in (self.sp_start, self.sp_digits):
            w.valueChanged.connect(self._refresh_preview)
        self.ed_sep.textChanged.connect(self._refresh_preview)
        # 初始禁用序号细项
        for w in (self.sp_start, self.sp_digits, self.ed_sep):
            w.setEnabled(False)
        return row

    # ---------- 应用区 ----------
    def _apply_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(10)
        row = QHBoxLayout(); row.setSpacing(10)
        self.btn_apply = QPushButton("应用重命名"); self.btn_apply.setObjectName("Primary")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.clicked.connect(self._apply)
        row.addWidget(self.btn_apply)
        self.btn_undo = QPushButton("撤销上次"); self.btn_undo.setObjectName("Ghost")
        self.btn_undo.setCursor(Qt.PointingHandCursor)
        self.btn_undo.clicked.connect(self._undo)
        self.btn_undo.setEnabled(False)
        row.addWidget(self.btn_undo)
        row.addStretch(1)
        self.dot = QLabel("●"); self.dot.setObjectName("StatusDot")
        self.lbl_status = QLabel("等待添加文件"); self.lbl_status.setObjectName("Hint")
        row.addWidget(self.dot); row.addWidget(self.lbl_status)
        v.addLayout(row)
        return card

    def _on_seq_toggle(self, on):
        for w in (self.sp_start, self.sp_digits, self.ed_sep):
            w.setEnabled(on)
        self._refresh_preview()

    def _set_status(self, kind, text):
        theme.set_prop(self.dot, "state", kind)
        self.lbl_status.setText(text)

    # ---------- 规则收集 & 预览 ----------
    def _rule(self):
        return rename_core.RenameRule(
            find=self.ed_find.text(), replace=self.ed_repl.text(),
            use_regex=self.cb_regex.isChecked(),
            prefix=self.ed_prefix.text(), suffix=self.ed_suffix.text(),
            base_name=self.ed_base.text(),
            seq_enabled=self.cb_seq.isChecked(),
            seq_start=self.sp_start.value(), seq_digits=self.sp_digits.value(),
            seq_sep=self.ed_sep.text(), ext_lower=self.cb_lower.isChecked())

    def _refresh_preview(self, *_):
        rule = self._rule()
        plan = rename_core.build_plan(self._paths, rule)
        self._plan = plan
        self.table.setRowCount(len(plan))
        for r, it in enumerate(plan):
            cn, ckey = _STATUS_CN.get(it.status, (it.status, "hint"))
            c0 = QTableWidgetItem(it.old_name)
            c1 = QTableWidgetItem(it.new_name or "—")
            c2 = QTableWidgetItem(cn + (("：" + it.note) if it.note and it.status not in ("ok", "same") else ""))
            color = theme.COLORS.get(ckey, theme.COLORS["text"])
            if it.status not in ("ok",):
                brush = QBrush(QColor(color))
                for c in (c0, c1, c2):
                    c.setForeground(brush)
            self.table.setItem(r, 0, c0)
            self.table.setItem(r, 1, c1)
            self.table.setItem(r, 2, c2)
        self._update_apply_state(plan, rule)

    def _update_apply_state(self, plan, rule):
        s = rename_core.summarize(plan)
        if not self._paths:
            self.btn_apply.setEnabled(False)
            self._set_status("idle", "等待添加文件")
        elif rule.is_noop():
            self.btn_apply.setEnabled(False)
            self._set_status("idle", "请设置至少一条规则")
        elif s["ok"] == 0:
            self.btn_apply.setEnabled(False)
            self._set_status("warn", "没有可重命名的文件（%d 项冲突或无变化）" % (s["blocked"] + s["same"]))
        else:
            self.btn_apply.setEnabled(True)
            msg = "将重命名 %d 个文件" % s["ok"]
            if s["blocked"]:
                msg += "；%d 项有冲突将跳过" % s["blocked"]
            self._set_status("ready", msg)

    # ---------- 应用 / 撤销 ----------
    def _apply(self):
        plan = getattr(self, "_plan", None)
        if not plan:
            return
        s = rename_core.summarize(plan)
        if s["ok"] == 0:
            return
        ask = "确认重命名 %d 个文件？此操作会就地修改文件名。" % s["ok"]
        if s["blocked"]:
            ask += "\n（%d 项存在冲突，将自动跳过）" % s["blocked"]
        if QMessageBox.question(self, "确认应用", ask,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.Yes) != QMessageBox.Yes:
            return
        n, failed, undo_map = rename_core.apply_plan(plan)
        self._undo_map = undo_map if undo_map else None
        self.btn_undo.setEnabled(bool(self._undo_map))
        # 用新名更新文件列表(成功项)，失败/未变项保留原路径
        moved = {old: new for new, old in undo_map}
        self._paths = [moved.get(p, p) for p in self._paths]
        self._refresh_preview()
        if failed:
            self._set_status("warn", "完成 %d 个，%d 个失败" % (n, len(failed)))
            detail = "\n".join("· %s：%s" % (nm, er) for nm, er in failed[:8])
            self.warn("部分未成功", "成功重命名 %d 个。\n以下未成功：\n%s" % (n, detail))
        else:
            self._set_status("ok", "已重命名 %d 个文件" % n)
            self.info("完成", "已成功重命名 %d 个文件。如需还原，点“撤销上次”。" % n)

    def _undo(self):
        if not self._undo_map:
            return
        ok, failed = rename_core.undo(self._undo_map)
        # 还原后把列表指回原路径
        back = {cur: origin for cur, origin in self._undo_map}
        self._paths = [back.get(p, p) for p in self._paths]
        self._undo_map = None
        self.btn_undo.setEnabled(False)
        self._refresh_preview()
        if failed:
            self.warn("撤销部分失败", "已还原 %d 个，%d 个未能还原。" % (ok, len(failed)))
        else:
            self._set_status("ok", "已撤销，还原 %d 个文件" % ok)

    # ---------- 文件列表管理 ----------
    def _add_paths(self, paths):
        have = set(os.path.normcase(p) for p in self._paths)
        for p in paths:
            if os.path.isfile(p) and os.path.normcase(p) not in have:
                self._paths.append(p)
                have.add(os.path.normcase(p))
        self._refresh_preview()

    def _add_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "选择要重命名的文件", "",
                                             "所有文件 (*.*)")
        if fs:
            self._add_paths(fs)

    def _remove_selected(self):
        rows = sorted((i.row() for i in self.table.selectionModel().selectedRows()),
                      reverse=True)
        for r in rows:
            if 0 <= r < len(self._paths):
                del self._paths[r]
        self._refresh_preview()

    def _clear(self):
        self._paths = []
        self._refresh_preview()

    def _move(self, delta):
        rows = sorted(i.row() for i in self.table.selectionModel().selectedRows())
        if not rows:
            return
        if delta < 0:
            for r in rows:
                if r > 0:
                    self._paths[r - 1], self._paths[r] = self._paths[r], self._paths[r - 1]
        else:
            for r in reversed(rows):
                if r < len(self._paths) - 1:
                    self._paths[r + 1], self._paths[r] = self._paths[r], self._paths[r + 1]
        self._refresh_preview()
        # 重选移动后的行
        self.table.clearSelection()
        for r in rows:
            nr = r + delta
            if 0 <= nr < len(self._paths):
                self.table.selectRow(nr)

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        files = [p for p in paths if os.path.isfile(p)]
        if files:
            self._add_paths(files)
        e.acceptProposedAction()
