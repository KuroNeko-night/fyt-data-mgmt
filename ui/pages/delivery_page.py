# -*- coding: utf-8 -*-
"""送货计划表制作页。物料清单 + 供应商明细 -> 一张 16 列送货计划。

以物料清单逐行为主，按物料号从供应商明细查供应商代码/名称，其余到货跟单列留空
供后续填写。两份文件拖入顺序任意，程序按是否含供应商列自动辨识主表与供应商来源。
"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QRadioButton, QButtonGroup, QComboBox)

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import delivery_core


class DeliveryPage(BasePage):
    def __init__(self, main):
        super(DeliveryPage, self).__init__(
            main, "送货计划表制作",
            "上传物料清单与供应商明细，选择订单类型(SUB/KD)，自动生成送货计划：按物料号"
            "带出供应商、统一填 KD/SUB；可再传一张往期送货计划，按物料编码带出 CASE/班组。")

    def build_body(self, layout):
        self.z_list = FileZone(1, "物料清单（单个）",
                               "含物料号与数量的清单，选 1 个。", multi=False,
                               library_cats=["deliv_bom"],
                               detail="决定送货计划的行与需求数（物料编码/名称/需求数取此表）。")
        self.z_sup = FileZone(2, "供应商明细（单个）",
                              "含零部件代码与供应商的明细，选 1 个。", multi=False,
                              library_cats=["deliv_supp"],
                              detail="按物料号查供应商代码与名称。两份文件顺序可随意，程序自动辨识。")
        self.z_ref = FileZone(3, "参考送货计划（可选）",
                              "一张往期做好的送货计划，选 1 个；不传则 CASE/班组 留空。",
                              multi=False, library_cats=["arrival_plan"],
                              detail="按物料编码带出 CASE / CASE托数 / 班组。自动跳过透视汇总表。")
        # 子表下拉:多子表文件(如 SAP 导出的 KD 清单含 Sheet1/BOM/发运清单…)默认
        # 只读第一子表未必是想要的表,故给物料清单/供应商明细各配一个"工作表"下拉。
        self.cb_list = self._sheet_combo()
        self.cb_sup = self._sheet_combo()
        self.z_list.changed.connect(lambda ps: self._fill_sheets(self.cb_list, ps))
        self.z_sup.changed.connect(lambda ps: self._fill_sheets(self.cb_sup, ps))

        layout.addWidget(self.z_list)
        layout.addWidget(self._sheet_row("物料清单工作表", self.cb_list))
        layout.addWidget(self.z_sup)
        layout.addWidget(self._sheet_row("供应商明细工作表", self.cb_sup))
        self.z_ref.changed.connect(self._refresh)
        layout.addWidget(self.z_ref)

        layout.addWidget(self._order_card())

        self.panel = RunPanel("生成送货计划")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        self.btn_plan = self.panel.add_action("打开送货计划", self._open_plan)
        layout.addWidget(self.panel)
        self._out_dir = ""
        self._plan = ""
        self._refresh()

    def _sheet_combo(self):
        cb = QComboBox()
        cb.addItem("自动（默认第一个工作表）", None)
        cb.setEnabled(False)
        return cb

    def _sheet_row(self, label, cb):
        """把"工作表"标签+下拉包成一行,紧贴其上方的文件区。"""
        row = QFrame()
        h = QHBoxLayout(row)
        h.setContentsMargins(14, 0, 14, 4); h.setSpacing(8)
        lb = QLabel(label + "："); lb.setObjectName("Hint")
        h.addWidget(lb); h.addWidget(cb, 1)
        return row

    def _fill_sheets(self, cb, paths):
        """文件选定后填充其子表列表;单表或读失败则只留"自动"项并禁用。"""
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("自动（默认第一个工作表）", None)
        names = delivery_core.list_sheets(paths[0]) if paths else []
        for nm in names:
            cb.addItem(nm, nm)
        # 仅在有 2 个及以上子表时才让用户选;单表无需选
        cb.setEnabled(len(names) >= 2)
        cb.setCurrentIndex(0)
        cb.blockSignals(False)
        self._refresh()

    def _order_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12); v.setSpacing(8)
        head = QHBoxLayout(); head.setSpacing(8)
        badge = QLabel("4"); badge.setObjectName("Badge")
        badge.setAlignment(Qt.AlignCenter)
        head.addWidget(badge)
        tl = QLabel("订单类型"); tl.setObjectName("CardTitle")
        head.addWidget(tl); head.addStretch(1)
        v.addLayout(head)
        hint = QLabel("选择本次订单类型，生成表的「KD/SUB」列将整列统一填入该值。")
        hint.setObjectName("Hint"); hint.setWordWrap(True)
        v.addWidget(hint)
        self.grp_ot = QButtonGroup(self)
        self.rb_sub = QRadioButton("SUB 订单")
        self.rb_kd = QRadioButton("KD 订单")
        self.rb_sub.setChecked(True)
        row = QHBoxLayout(); row.setSpacing(24)
        for rb in (self.rb_sub, self.rb_kd):
            self.grp_ot.addButton(rb); row.addWidget(rb)
            rb.toggled.connect(self._refresh)
        row.addStretch(1)
        v.addLayout(row)
        return card

    def _order_type(self):
        return "KD" if self.rb_kd.isChecked() else "SUB"

    def refresh_view(self):
        for z in (self.z_list, self.z_sup, self.z_ref):
            z.refresh_lib_count()

    def _refresh(self, *_):
        ok = bool(self.z_list.get()) and bool(self.z_sup.get())
        self.panel.run_btn.setEnabled(ok)
        if ok:
            self.panel.set_status("ready", "准备就绪 · 订单类型 %s" % self._order_type())
        else:
            need = []
            if not self.z_list.get(): need.append("物料清单")
            if not self.z_sup.get(): need.append("供应商明细")
            self.panel.set_status("idle", "还需选择：" + "、".join(need))

    def _run(self):
        self.panel.clear_log()
        f1 = self.z_list.get()[0]
        f2 = self.z_sup.get()[0]
        ref = self.z_ref.get()
        ref_plan = ref[0] if ref else None
        ot = self._order_type()
        self.btn_open.setEnabled(False)
        self.btn_plan.setEnabled(False)
        sa = self.cb_list.currentData()      # None=自动(第一表);否则用户所选子表名
        sb = self.cb_sup.currentData()
        self.launch(
            lambda log: delivery_core.run(f1, f2, sheet_a=sa, sheet_b=sb, log=log,
                                          order_type=ot, ref_plan=ref_plan),
            self.panel, self._done)

    def _done(self, res):
        self._out_dir = res.get("out_dir", "")
        self._plan = res.get("plan_path", "")
        n = res.get("rows", 0)
        miss = len(res.get("missing", []))
        ot = res.get("order_type") or "未指定"
        kind = "ok" if miss == 0 else "warn"
        st = "完成 · %s · %d 行 · 供应商匹配 %d · 未匹配 %d" % (ot, n, n - miss, miss)
        if res.get("case_used"):
            st += " · CASE/班组 %d" % res.get("case_hit", 0)
        self.panel.set_status(kind, st)
        self.btn_open.setEnabled(bool(self._out_dir))
        self.btn_plan.setEnabled(bool(self._plan))
        tail = ("有 %d 个物料未匹配到供应商，已留空，请人工补填。\n" % miss) if miss else ""
        if res.get("case_used"):
            tail += ("CASE/班组 已按物料编码匹配 %d / %d 行。\n"
                     % (res.get("case_hit", 0), n))
        self.notify_done(
            self._out_dir, "送货计划已生成",
            "订单类型 %s，共 %d 行，供应商匹配 %d 个。\n%s输出：%s"
            % (ot, n, n - miss, tail, self._out_dir))

    def _open(self):
        self.open_folder(self._out_dir)

    def _open_plan(self):
        import os
        try:
            if self._plan and os.path.isfile(self._plan):
                os.startfile(self._plan)
        except Exception:
            pass
