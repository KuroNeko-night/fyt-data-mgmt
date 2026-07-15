# -*- coding: utf-8 -*-
"""送货计划表制作页。物料清单 + 供应商明细 -> 一张 16 列送货计划。

以物料清单逐行为主，按物料号从供应商明细查供应商代码/名称，其余到货跟单列留空
供后续填写。两份文件拖入顺序任意，程序按是否含供应商列自动辨识主表与供应商来源。
"""
from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import delivery_core


class DeliveryPage(BasePage):
    def __init__(self, main):
        super(DeliveryPage, self).__init__(
            main, "送货计划表制作",
            "上传物料清单与供应商明细，自动生成送货计划：按物料号带出供应商，"
            "其余到货/收货列留空供跟单填写。")

    def build_body(self, layout):
        self.z_list = FileZone(1, "物料清单（单个）",
                               "含物料号与数量的清单，选 1 个。", multi=False,
                               library_cats=["deliv_bom"],
                               detail="决定送货计划的行与需求数（物料编码/名称/需求数取此表）。")
        self.z_sup = FileZone(2, "供应商明细（单个）",
                              "含零部件代码与供应商的明细，选 1 个。", multi=False,
                              library_cats=["deliv_supp"],
                              detail="按物料号查供应商代码与名称。两份文件顺序可随意，程序自动辨识。")
        for z in (self.z_list, self.z_sup):
            z.changed.connect(self._refresh)
            layout.addWidget(z)

        self.panel = RunPanel("生成送货计划")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        self.btn_plan = self.panel.add_action("打开送货计划", self._open_plan)
        layout.addWidget(self.panel)
        self._out_dir = ""
        self._plan = ""
        self._refresh()

    def refresh_view(self):
        for z in (self.z_list, self.z_sup):
            z.refresh_lib_count()

    def _refresh(self, *_):
        ok = bool(self.z_list.get()) and bool(self.z_sup.get())
        self.panel.run_btn.setEnabled(ok)
        if ok:
            self.panel.set_status("ready", "准备就绪")
        else:
            need = []
            if not self.z_list.get(): need.append("物料清单")
            if not self.z_sup.get(): need.append("供应商明细")
            self.panel.set_status("idle", "还需选择：" + "、".join(need))

    def _run(self):
        self.panel.clear_log()
        f1 = self.z_list.get()[0]
        f2 = self.z_sup.get()[0]
        self.btn_open.setEnabled(False)
        self.btn_plan.setEnabled(False)
        self.launch(lambda log: delivery_core.run(f1, f2, log=log),
                    self.panel, self._done)

    def _done(self, res):
        self._out_dir = res.get("out_dir", "")
        self._plan = res.get("plan_path", "")
        n = res.get("rows", 0)
        miss = len(res.get("missing", []))
        kind = "ok" if miss == 0 else "warn"
        self.panel.set_status(
            kind, "完成 · %d 行 · 供应商匹配 %d · 未匹配 %d" % (n, n - miss, miss))
        self.btn_open.setEnabled(bool(self._out_dir))
        self.btn_plan.setEnabled(bool(self._plan))
        tail = ("有 %d 个物料未匹配到供应商，已留空，请人工补填。\n" % miss) if miss else ""
        self.notify_done(
            self._out_dir, "送货计划已生成",
            "共 %d 行，供应商匹配 %d 个。\n%s输出：%s"
            % (n, n - miss, tail, self._out_dir))

    def _open(self):
        self.open_folder(self._out_dir)

    def _open_plan(self):
        import os
        try:
            if self._plan and os.path.isfile(self._plan):
                os.startfile(self._plan)
        except Exception:
            pass
