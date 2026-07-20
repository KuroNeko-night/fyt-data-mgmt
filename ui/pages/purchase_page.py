# -*- coding: utf-8 -*-
"""采购数对账页。我方对账单 + 供应商对单明细 -> 两张上色表 + 一张并排汇报单。

把两方逐行匹配：绿=对上、黄=未对上，并在汇报单里给出未对上原因，供人工一眼核对。
双方名称可自定义（不填默认"我方/供方"），报表内容随之显示，绝不写死具体供应商名。
"""
import os

from PySide2.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel,
                               QLineEdit)

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import purchase_core


class PurchasePage(BasePage):
    def __init__(self, main):
        super(PurchasePage, self).__init__(
            main, "采购数对账",
            "把我方对账单与供应商对单明细逐行核对，数量列上色，"
            "并生成并排汇报单标出未对上原因。")

    def build_body(self, layout):
        self.z_ours = FileZone(1, "我方对账单（单个）",
                               "我方导出的采购/对账明细，选 1 个。", multi=False,
                               library_cats=["purchase_stmt"],
                               detail="程序在此表数量列上色，并作为汇报单“我方”一侧。")
        self.z_supp = FileZone(2, "供应商对单明细（单个）",
                               "供应商发来的对单，选 1 个。", multi=False,
                               library_cats=["purchase_stmt"],
                               detail="与我方逐行比对，作为汇报单“供方”一侧。")
        for z in (self.z_ours, self.z_supp):
            z.changed.connect(self._refresh)
            layout.addWidget(z)

        self._nm_card = self._name_card()
        layout.addWidget(self._nm_card)

        self.panel = RunPanel("开始对账")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        self.btn_report = self.panel.add_action("打开汇报单", self._open_report)
        layout.addWidget(self.panel)
        self._out_dir = ""
        self._report = ""
        self._refresh()

    def _name_card(self):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(14, 12, 14, 12); v.setSpacing(8)
        t = QLabel("双方名称（可选）"); t.setObjectName("CardTitle")
        v.addWidget(t)
        h = QHBoxLayout(); h.setSpacing(10)
        h.addWidget(QLabel("我方"))
        self.ed_ours = QLineEdit(); self.ed_ours.setPlaceholderText("默认：我方")
        h.addWidget(self.ed_ours, 1)
        h.addWidget(QLabel("供方"))
        self.ed_supp = QLineEdit(); self.ed_supp.setPlaceholderText("默认：供方（填供应商名）")
        h.addWidget(self.ed_supp, 1)
        v.addLayout(h)
        tip = QLabel("填了就显示在汇报单里；留空用通用的“我方/供方”。")
        tip.setObjectName("Hint")
        v.addWidget(tip)
        return card

    def refresh_view(self):
        for z in (self.z_ours, self.z_supp):
            z.refresh_lib_count()

    def _refresh(self, *_):
        ok = bool(self.z_ours.get()) and bool(self.z_supp.get())
        self.panel.run_btn.setEnabled(ok)
        if ok:
            self.panel.set_status("ready", "准备就绪")
        else:
            need = []
            if not self.z_ours.get(): need.append("我方对账单")
            if not self.z_supp.get(): need.append("供应商对单")
            self.panel.set_status("idle", "还需选择：" + "、".join(need))

    def _run(self):
        self.panel.clear_log()
        f1 = self.z_ours.get()[0]
        f2 = self.z_supp.get()[0]
        n1 = self.ed_ours.text().strip() or "我方"
        n2 = self.ed_supp.text().strip() or "供方"
        self.btn_open.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.launch(
            lambda log: purchase_core.run(f1, f2, name1=n1, name2=n2, log=log),
            self.panel, self._done)

    def _done(self, res):
        self._out_dir = res.get("out_dir", "")
        self._report = res.get("report", "")
        n_pair = len(res.get("pairs", []))
        um1 = len(res["matched1"]) - sum(res["matched1"])
        um2 = len(res["matched2"]) - sum(res["matched2"])
        nqc = len(res.get("qty_conflicts", []))
        kind = "ok" if (um1 == 0 and um2 == 0) else "warn"
        self.panel.set_status(
            kind, "完成 · 配对 %d 对 · 未对上 我方%d/供方%d · 数量疑点 %d 处"
            % (n_pair, um1, um2, nqc))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.btn_report.setEnabled(bool(self._report))
        self.notify_done(
            self._out_dir, "对账完成",
            "配对 %d 对\n未对上：我方 %d 条 / 供方 %d 条\n数量疑点 %d 处\n输出：%s"
            % (n_pair, um1, um2, nqc, self._out_dir))

    def _open(self):
        self.open_folder(self._out_dir)

    def _open_report(self):
        try:
            if self._report and os.path.isfile(self._report):
                os.startfile(self._report)
        except Exception:
            pass

    def guide_steps(self):
        return [
            (None, "欢迎使用采购数对账",
             "这个页面把我方对账单与供应商对单逐行核对,数量列上色(绿=对上、黄=没对上),\n"
             "并生成一张并排汇报单标出未对上原因。跟着高亮走一遍即可。"),
            (self.z_ours, "① 放我方对账单(单个)",
             "我方导出的采购/对账明细,选 1 个。\n"
             "程序在这张表的数量列上色,并作为汇报单的「我方」一侧。"),
            (self.z_supp, "② 放供应商对单明细(单个)",
             "供应商发来的对单,选 1 个。\n"
             "与我方逐行比对,作为汇报单的「供方」一侧。"),
            (self._nm_card, "③ 双方名称(可选)",
             "填了就显示在汇报单里(如具体供应商名);留空则用通用的「我方/供方」。"),
            (self.panel, "开始对账 · 看汇报单",
             "点「开始对账」。完成后状态行给出配对数、双方未对上条数与数量疑点数;\n"
             "点「打开汇报单」看并排核对结果,或「打开输出文件夹」看上色后的两张表。"),
        ]
