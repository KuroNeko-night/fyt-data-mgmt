# -*- coding: utf-8 -*-
"""
透视表人工复核对话框
====================
展示 analyze 得到的决策点，让用户确认：
  · 每个工作表是否纳入（附识别类型/可信度/原因）；
  · 被判为"疑似真实但会删除"的行是否保留；
  · 单位冲突 / 规格合并 的提示（只读，供知情）。
返回 choices，喂给 pivot_core.run。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
                               QHeaderView, QCheckBox, QAbstractItemView, QScrollArea,
                               QComboBox, QGridLayout)

from .. import theme


class PivotReviewDialog(QDialog):
    def __init__(self, plan, parent=None):
        super(PivotReviewDialog, self).__init__(parent)
        self.plan = plan
        self.setWindowTitle("人工复核 —— 销售表透视")
        self.setModal(True)
        self.setStyleSheet(theme.stylesheet())
        self.setSizeGripEnabled(True)          # 右下角可拖拽缩放
        self._sheet_cbs = {}     # id -> QCheckBox
        self._held_cbs = {}      # (sid, ridx) -> QCheckBox
        self._unit_combos = {}   # gk -> (QComboBox, default)  单位人工改选
        self._spec_combos = {}   # gk -> (QComboBox, default)  规格人工改选
        self._build()
        theme.fit_dialog(self, 760, 560)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        head = QLabel("请确认下列决策点。默认与全自动一致，可按需调整后再生成。")
        head.setObjectName("PageDesc"); head.setWordWrap(True)
        lay.addWidget(head)

        tabs = QTabWidget()
        tabs.addTab(self._sheets_tab(), "工作表纳入 (%d)" % len(self.plan["sheets"]))
        tabs.addTab(self._held_tab(), "疑似误删行 (%d)" % len(self.plan.get("held_index", [])))
        tabs.addTab(self._conflict_tab(), "单位/规格提示")
        lay.addWidget(tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消"); cancel.setObjectName("Ghost"); cancel.clicked.connect(self.reject)
        ok = QPushButton("按此生成"); ok.setObjectName("Primary"); ok.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(ok)
        lay.addLayout(row)

    def _sheets_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        tb = QTableWidget(len(self.plan["sheets"]), 5)
        tb.setHorizontalHeaderLabels(["纳入", "文件", "工作表", "识别类型", "可信度"])
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.verticalHeader().setVisible(False)
        hh = tb.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        for r, s in enumerate(self.plan["sheets"]):
            cb = QCheckBox(); cb.setChecked(bool(s["use"]))
            self._sheet_cbs[s["id"]] = cb
            holder = QWidget(); hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0); hl.setAlignment(Qt.AlignCenter); hl.addWidget(cb)
            tb.setCellWidget(r, 0, holder)
            tb.setItem(r, 1, QTableWidgetItem(s["file"]))
            it2 = QTableWidgetItem(s["sheet"]); it2.setToolTip(s.get("reason", ""))
            tb.setItem(r, 2, it2)
            tb.setItem(r, 3, QTableWidgetItem(s["kind"]))
            conf = QTableWidgetItem(str(s["confidence"]))
            if s["confidence"] < 60:
                conf.setForeground(Qt.red)
            tb.setItem(r, 4, conf)
        v.addWidget(tb)
        return w

    def _held_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        held = self.plan.get("held_index", [])
        if not held:
            lbl = QLabel("没有疑似误删的行。数据很干净，直接生成即可。")
            lbl.setObjectName("Hint"); v.addWidget(lbl); v.addStretch(1); return w
        info = QLabel("以下行被规则判为可能应删除，但疑似真实数据。勾选=保留进入汇总。")
        info.setObjectName("Hint"); info.setWordWrap(True); v.addWidget(info)
        tb = QTableWidget(len(held), 3)
        tb.setHorizontalHeaderLabels(["保留", "来源", "内容摘要"])
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.verticalHeader().setVisible(False)
        tb.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for r, h in enumerate(held):
            cb = QCheckBox(); self._held_cbs[(h["sid"], h["ridx"])] = cb
            holder = QWidget(); hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0); hl.setAlignment(Qt.AlignCenter); hl.addWidget(cb)
            tb.setCellWidget(r, 0, holder)
            tb.setItem(r, 1, QTableWidgetItem(str(h.get("sheet", ""))))
            tb.setItem(r, 2, QTableWidgetItem(str(h.get("summary", h.get("rec", "")))))
        v.addWidget(tb)
        return w

    def _conflict_tab(self):
        # 外层滚动区：条目再多也只在页内滚动，不会把窗口撑到屏幕外
        area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QScrollArea.NoFrame)
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(2, 2, 2, 2)
        uc = self.plan.get("unit_conflicts", [])
        sm = self.plan.get("spec_merges", [])
        if not uc and not sm:
            lbl = QLabel("没有单位冲突或规格合并需要关注。")
            lbl.setObjectName("Hint"); v.addWidget(lbl); v.addStretch(1)
            area.setWidget(w); return area
        tip = QLabel("下方为程序按多数原则的自动判断。可直接在「采用」下拉框改选其它写法，"
                     "也可手动输入自定义值；不改动即沿用自动结果。")
        tip.setObjectName("Hint"); tip.setWordWrap(True); v.addWidget(tip)
        if uc:
            v.addWidget(self._sec_editable(
                "单位冲突（同物料出现多种单位）", uc, "dist", self._unit_combos, self._fmt_unit_title))
        if sm:
            v.addWidget(self._sec_editable(
                "规格合并（相近规格归并）", sm, "variants", self._spec_combos, self._fmt_spec_title))
        v.addStretch(1)
        area.setWidget(w)
        return area

    @staticmethod
    def _fmt_dist(d):
        """{单位/规格: 次数} -> '件×5 / 个×2'，空值显示为(空)。"""
        try:
            items = d.items()
        except AttributeError:
            return str(d)
        return " / ".join("%s×%d" % (k if k else "(空)", n) for k, n in items)

    @staticmethod
    def _fmt_unit_title(c):
        title = c.get("name") or c.get("code") or "(未知物料)"
        code = (" [%s]" % c["code"]) if c.get("code") else ""
        spec = ("  规格 %s" % c["spec"]) if c.get("spec") else ""
        return "%s%s%s" % (title, code, spec)

    @staticmethod
    def _fmt_spec_title(c):
        title = c.get("name") or c.get("code") or "(未知物料)"
        code = (" [%s]" % c["code"]) if c.get("code") else ""
        return "%s%s" % (title, code)

    def _sec_editable(self, title, items, dist_key, store, title_fn):
        """一个可编辑区块：每个冲突项一行，右侧下拉框可改选/手填最终值。"""
        box = QWidget(); g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0); g.setHorizontalSpacing(12); g.setVerticalSpacing(8)
        t = QLabel(title); t.setObjectName("SecTitle")
        g.addWidget(t, 0, 0, 1, 3)
        shown = items[:200]
        for i, c in enumerate(shown):
            r = i + 1
            name = QLabel(title_fn(c)); name.setWordWrap(True)
            dist = QLabel("出现 " + self._fmt_dist(c.get(dist_key, {})))
            dist.setObjectName("Hint"); dist.setWordWrap(True)
            col = QWidget(); cv = QVBoxLayout(col); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(1)
            cv.addWidget(name); cv.addWidget(dist)
            g.addWidget(col, r, 0)
            g.addWidget(QLabel("采用"), r, 1, Qt.AlignRight | Qt.AlignVCenter)
            combo = self._make_combo(c.get(dist_key, {}), c.get("default", ""))
            store[c["gk"]] = (combo, c.get("default", ""))
            g.addWidget(combo, r, 2)
        g.setColumnStretch(0, 1)
        if len(items) > 200:
            more = QLabel("… 另有 %d 项未显示（将沿用自动判断）" % (len(items) - 200))
            more.setObjectName("Hint"); g.addWidget(more, len(shown) + 1, 0, 1, 3)
        return box

    def _make_combo(self, dist, default):
        """可编辑下拉框：候选=各写法(按出现次数)，当前=系统默认；允许手动输入。"""
        combo = QComboBox(); combo.setEditable(True); combo.setMinimumWidth(150)
        combo.setInsertPolicy(QComboBox.NoInsert)
        vals = []
        try:
            vals = list(dist.keys())
        except AttributeError:
            pass
        if default not in vals:
            vals.insert(0, default)
        for val in vals:
            combo.addItem(val if val != "" else "", val)   # 显示文本；空值显示空
        idx = combo.findData(default)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.setCurrentText(default)   # 确保编辑框显示默认值(含空值情形)
        return combo

    def choices(self):
        from core import pivot_core
        ch = pivot_core._default_choices(self.plan)
        for sid, cb in self._sheet_cbs.items():
            ch["sheets"][sid] = cb.isChecked()
        for key, cb in self._held_cbs.items():
            ch["held"][key] = cb.isChecked()
        # 单位/规格人工改选：仅当与系统默认不同才记为覆盖(报告据此统计"人工改动 N 处")
        ch["unit_overrides"] = self._collect_overrides(self._unit_combos)
        ch["spec_overrides"] = self._collect_overrides(self._spec_combos)
        return ch

    @staticmethod
    def _collect_overrides(store):
        ov = {}
        for gk, (combo, default) in store.items():
            cur = combo.currentText().strip()
            if cur != (default or "").strip():
                ov[gk] = cur
        return ov
