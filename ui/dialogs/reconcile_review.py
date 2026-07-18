# -*- coding: utf-8 -*-
"""
工时对账人工确认对话框
======================
展示 reconcile_core.analyze 的识别结果，让用户在对账前确认：
  · 结构识别：待对表用哪个工作表、姓名/所属公司/出勤工时列(可纠正)；
    各数据来源与对账单的识别概况(只读)；
  · 姓名匹配：把"仅对账单有"的姓名手动配对到"仅我司有"的姓名，
    声明二者是同一个人(别名/错字/空格)，避免误报"仅一方有"。
返回 choices，喂给 reconcile_core.run。
沿用透视表复核对话框的外观与交互。兼容 Windows 7 + Python 3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView, QGridLayout)

from ..animations import AnimatedComboBox as QComboBox   # 下拉抽屉式拉开

_NOPAIR = "— 不配对 —"


class ReconcileReviewPanel(QWidget):
    """工时对账人工确认 —— 右侧面板部件（原对话框正文）。
    确认后 accepted 带回 choices；取消发 cancelled。"""
    accepted = Signal(object)
    cancelled = Signal()

    def __init__(self, plan, parent=None):
        super(ReconcileReviewPanel, self).__init__(parent)
        self.plan = plan
        self._role_combos = {}     # role -> (QComboBox, 默认1based)  待对表列纠正
        self._sheet_combo = None   # 待对表工作表选择
        self._pair_combos = {}     # 劳务姓名 -> QComboBox(选我司姓名)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        head = QLabel("请确认程序的识别结果。默认与全自动一致，可按需纠正后再对账。")
        head.setObjectName("PageDesc"); head.setWordWrap(True)
        lay.addWidget(head)

        tabs = QTabWidget()
        tabs.addTab(self._structure_tab(), "结构识别")
        n_pair = len(self.plan.get("only_labor", []))
        tabs.addTab(self._names_tab(), "姓名匹配 (%d)" % n_pair)
        lay.addWidget(tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消"); cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.cancelled.emit)
        ok = QPushButton("按此对账"); ok.setObjectName("Primary")
        ok.clicked.connect(lambda: self.accepted.emit(self.choices()))
        row.addWidget(cancel); row.addWidget(ok)
        lay.addLayout(row)

    # ---------- Tab1 结构识别 ----------
    def _col_upper(self, t):
        cand = [t.get("name_col") or 0, t.get("comp_col") or 0,
                t.get("work_col") or 0, t.get("check_col") or 0]
        return max(20, min(60, max(cand) + 10))

    def _col_combo(self, default1, upper):
        """列选择下拉：第1列…第N列，data=1based 列号。default1 为 None 时加“(无)”。"""
        cb = QComboBox(); cb.setMinimumWidth(120)
        if not default1:
            cb.addItem("(无)", 0)
        for c in range(1, upper + 1):
            cb.addItem("第 %d 列" % c, c)
        idx = cb.findData(default1 or 0)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        return cb

    def _structure_tab(self):
        t = self.plan["target"]
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)

        # 待对表：可纠正
        cap = QLabel("待对表（可纠正识别）"); cap.setObjectName("SecTitle")
        v.addWidget(cap)
        g = QGridLayout(); g.setHorizontalSpacing(12); g.setVerticalSpacing(8)
        fn = QLabel(t["file"]); fn.setObjectName("Hint"); fn.setWordWrap(True)
        g.addWidget(fn, 0, 0, 1, 4)
        # 工作表
        g.addWidget(QLabel("工作表"), 1, 0, Qt.AlignRight | Qt.AlignVCenter)
        self._sheet_combo = QComboBox(); self._sheet_combo.setMinimumWidth(160)
        for s in (t.get("sheets") or [t["sheet"]]):
            self._sheet_combo.addItem(s, s)
        si = self._sheet_combo.findData(t["sheet"])
        if si >= 0:
            self._sheet_combo.setCurrentIndex(si)
        g.addWidget(self._sheet_combo, 1, 1)
        upper = self._col_upper(t)
        # 姓名列 / 所属公司列 / 出勤工时列
        specs = [("name", "姓名列", t.get("name_col")),
                 ("comp", "所属公司列", t.get("comp_col")),
                 ("work", "出勤工时列", t.get("work_col"))]
        for i, (role, label, dft) in enumerate(specs):
            r = 2 + i
            g.addWidget(QLabel(label), r, 0, Qt.AlignRight | Qt.AlignVCenter)
            cb = self._col_combo(dft, upper)
            self._role_combos[role] = (cb, dft)
            g.addWidget(cb, r, 1)
        info = QLabel("逐日列共识别 %d 个；数据起始行第 %d 行。"
                      % (len(t.get("day_cols") or []), t.get("data_start") or 0))
        info.setObjectName("Hint"); info.setWordWrap(True)
        g.addWidget(info, 2, 2, 3, 2)
        g.setColumnStretch(3, 1)
        v.addLayout(g)

        # 数据来源 + 对账单：只读概况
        tb = QTableWidget(0, 4)
        tb.setHorizontalHeaderLabels(["类别", "文件", "工作表", "识别人数"])
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.verticalHeader().setVisible(False)
        hh = tb.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for kind, key in (("数据来源", "sources"), ("对账单", "labor")):
            for it in self.plan.get(key, []):
                r = tb.rowCount(); tb.insertRow(r)
                tb.setItem(r, 0, QTableWidgetItem(kind))
                tb.setItem(r, 1, QTableWidgetItem(it.get("file", "")))
                tb.setItem(r, 2, QTableWidgetItem(str(it.get("sheet") or "(自动)")))
                cnt = QTableWidgetItem(str(it.get("people", 0)))
                if not it.get("people"):
                    cnt.setForeground(Qt.red)
                tb.setItem(r, 3, cnt)
        v.addWidget(tb, 1)
        return w

    # ---------- Tab2 姓名匹配 ----------
    def _names_tab(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)
        only_labor = self.plan.get("only_labor", [])
        only_zong = self.plan.get("only_zong", [])
        if not only_labor:
            lbl = QLabel("两侧姓名已全部对上，没有需要人工配对的名字。直接对账即可。")
            lbl.setObjectName("Hint"); lbl.setWordWrap(True)
            v.addWidget(lbl); v.addStretch(1)
            return w
        info = QLabel("下列姓名只在对账单出现、未在我司总表匹配到。若因别名/错字/空格"
                      "其实是同一人，可在右侧选择对应的我司姓名；不配对则按“仅劳务公司有”记异常。")
        info.setObjectName("Hint"); info.setWordWrap(True)
        v.addWidget(info)

        tb = QTableWidget(len(only_labor), 2)
        tb.setHorizontalHeaderLabels(["对账单姓名（仅劳务有）", "配对到我司姓名"])
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.verticalHeader().setVisible(False)
        tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for r, nm in enumerate(only_labor):
            tb.setItem(r, 0, QTableWidgetItem(nm))
            cb = QComboBox(); cb.setEditable(True); cb.setMinimumWidth(160)
            cb.setInsertPolicy(QComboBox.NoInsert)
            cb.addItem(_NOPAIR, "")
            for z in only_zong:
                cb.addItem(z, z)
            cb.setCurrentIndex(0)
            self._pair_combos[nm] = cb
            tb.setCellWidget(r, 1, cb)
        v.addWidget(tb, 1)
        return w

    # ---------- 收集结果 ----------
    def choices(self):
        ch = {"target_sheet": None, "target_roles": {}, "aliases": {}}
        t = self.plan["target"]
        # 工作表：与识别不同才记
        if self._sheet_combo is not None:
            cur = self._sheet_combo.currentData()
            if cur and cur != t.get("sheet"):
                ch["target_sheet"] = cur
        # 列纠正：与识别默认不同才记(1based)
        for role, (cb, dft) in self._role_combos.items():
            cur = cb.currentData()
            if cur and cur != (dft or 0):
                ch["target_roles"][role] = int(cur)
        # 姓名配对
        for lab_nm, cb in self._pair_combos.items():
            val = cb.currentData()
            if not val:                      # 可编辑：也允许直接输入我司姓名
                txt = cb.currentText().strip()
                val = txt if txt and txt != _NOPAIR else ""
            if val:
                ch["aliases"][lab_nm] = val
        return ch
