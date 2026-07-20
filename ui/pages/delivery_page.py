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
            "上传物料清单(供应商明细可选)，选择订单类型(SUB/KD)，自动生成送货计划：按物料号"
            "带出供应商、统一填 KD/SUB；可再传一张往期送货计划，按物料编码带出 CASE/班组。")

    def build_body(self, layout):
        self.z_list = FileZone(1, "物料清单（单个）",
                               "含物料号与数量的清单，选 1 个。", multi=False,
                               library_cats=["deliv_bom"],
                               detail="决定送货计划的行与需求数（物料编码/名称/需求数取此表）。")
        self.z_sup = FileZone(2, "供应商明细（可选）",
                              "含零部件代码与供应商的明细，选 1 个；不传则供应商列留空。",
                              multi=False, library_cats=["deliv_supp"],
                              detail="按物料号查供应商代码与名称。两份文件顺序可随意，程序自动辨识。"
                                     "不提供时供应商代码/名称留空，可稍后人工补填。")
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
        self.cb_list.currentIndexChanged.connect(lambda *_: self._scan_main())

        layout.addWidget(self.z_list)
        layout.addWidget(self._sheet_row("物料清单工作表", self.cb_list))
        layout.addWidget(self.z_sup)
        layout.addWidget(self._sheet_row("供应商明细工作表", self.cb_sup))
        self.z_ref.changed.connect(self._refresh)
        layout.addWidget(self.z_ref)

        self._ot_card = self._order_card()
        layout.addWidget(self._ot_card)

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
        if cb is self.cb_list:               # 物料清单变化 -> 预检表头
            self._scan_main()

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

    def guide_steps(self):
        """使用指引:按①②③④→生成→看结果的顺序,聚光灯带走一遍。"""
        return [
            (None, "欢迎使用送货计划表制作",
             "这个页面把「物料清单 + 供应商明细」自动合成一张 16 列的送货计划。\n"
             "跟着高亮走一遍,大概 30 秒就能上手。点「下一步」开始。"),
            (self.z_list, "① 放物料清单",
             "把含物料号与需求数的清单拖到这里,或点「＋ 添加文件」选择。\n"
             "这张表决定送货计划有哪些行、每行要多少——是主表。"),
            (self.z_sup, "② 放供应商明细(可选)",
             "有含零部件代码与供应商的明细就放这里,程序按物料号自动带出供应商代码/名称;\n"
             "两张表拖入顺序随便,会自己认主表与供应商来源。不放也行——供应商两列会留空,\n"
             "可稍后在表里人工补填,不影响其余列的生成。"),
            (self.z_ref, "③ 参考送货计划(可选)",
             "有往期做好的送货计划就放这里,能按物料编码带出 CASE/班组;\n"
             "没有就跳过,这两列留空即可,不影响生成。"),
            (self._ot_card, "④ 选订单类型",
             "选 SUB 还是 KD。生成表的「KD/SUB」列会整列统一填这个值。"),
            (self.panel, "生成 + 看状态",
             "点「生成送货计划」。处理时这里显示进度,完成后状态行会告诉你共几行、\n"
             "供应商匹配了多少、有没有没匹配上的(未匹配的会留空供人工补填)。"),
            (self.panel, "结果在哪 · 怎么看",
             "完成后程序会自动弹开结果所在文件夹。也可点这里的「打开送货计划」直接看表、\n"
             "或「打开输出文件夹」。文件统一存在 文档/峰运通数据管理系统/输出/ 下,按时间戳归档。"),
        ]

    def refresh_view(self):
        for z in (self.z_list, self.z_sup, self.z_ref):
            z.refresh_lib_count()

    def _refresh(self, *_):
        # 供应商明细已是可选：只要有物料清单即可生成。
        ok = bool(self.z_list.get())
        self.panel.run_btn.setEnabled(ok)
        if ok:
            tail = "" if self.z_sup.get() else " · 未选供应商明细(供应商列将留空)"
            self.panel.set_status(
                "ready", "准备就绪 · 订单类型 %s%s" % (self._order_type(), tail))
        else:
            self.panel.set_status("idle", "还需选择：物料清单")

    def _scan_main(self):
        """物料清单选定/切表后预检其表头,提前提示识别情况(不写盘)。"""
        paths = self.z_list.get()
        if not paths:
            self.cancel_scan()
            return
        sheet = self.cb_list.currentData()
        self.scan_on_select(
            paths[0], lambda p, log=None: delivery_core.analyze(p, sheet=sheet, log=log),
            self._on_scan_ready)

    def _on_scan_ready(self, res):
        if not res:
            return
        if not res.get("ok"):
            self.notice.show_notice("warn",
                "物料清单未能识别表头(需含“物料号/编码”列):%s" % res.get("error", ""))
        elif res.get("source") == "shape":
            self.notice.show_notice("warn",
                "物料清单靠数据形态猜出列(第 %d 行为表头),生成前请核对列是否对应正确。"
                % res.get("header_row", 0))
        else:
            self.notice.show_notice("ok",
                "物料清单识别成功:表头第 %d 行,共约 %d 行数据。"
                % (res.get("header_row", 0), res.get("n_rows", 0)))

    def _run(self):
        self.panel.clear_log()
        f1 = self.z_list.get()[0]
        sup = self.z_sup.get()
        f2 = sup[0] if sup else None         # 供应商明细可选:未选则传 None
        ref = self.z_ref.get()
        ref_plan = ref[0] if ref else None
        ot = self._order_type()
        self.btn_open.setEnabled(False)
        self.btn_plan.setEnabled(False)
        sa = self.cb_list.currentData()      # None=自动(第一表);否则用户所选子表名
        sb = self.cb_sup.currentData() if f2 else None
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
        sup_used = res.get("supplier_used", True)
        self.btn_open.setEnabled(bool(self._out_dir))
        self.btn_plan.setEnabled(bool(self._plan))
        if not sup_used:
            # 未提供供应商明细:供应商两列按设计留空,不算异常。
            st = "完成 · %s · %d 行 · 供应商列留空(未提供明细)" % (ot, n)
            if res.get("case_used"):
                st += " · CASE/班组 %d" % res.get("case_hit", 0)
            self.panel.set_status("ok", st)
            tail = "未提供供应商明细，供应商代码/名称两列已留空，可稍后人工补填。\n"
            if res.get("case_used"):
                tail += ("CASE/班组 已按物料编码匹配 %d / %d 行。\n"
                         % (res.get("case_hit", 0), n))
            self.notify_done(
                self._out_dir, "送货计划已生成",
                "订单类型 %s，共 %d 行。\n%s输出：%s" % (ot, n, tail, self._out_dir))
            return
        kind = "ok" if miss == 0 else "warn"
        st = "完成 · %s · %d 行 · 供应商匹配 %d · 未匹配 %d" % (ot, n, n - miss, miss)
        if res.get("case_used"):
            st += " · CASE/班组 %d" % res.get("case_hit", 0)
        self.panel.set_status(kind, st)
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
