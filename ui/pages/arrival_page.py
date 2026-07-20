# -*- coding: utf-8 -*-
"""到料明细表页。送货计划表 -> 每日主料到料明细。含每批次总数/备注编辑。"""
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox)

from .base_page import BasePage
from ..widgets.file_zone import FileZone
from ..widgets.run_panel import RunPanel
from core import arrival_core, settings as settings_mod


class ArrivalPage(BasePage):
    def __init__(self, main):
        self.settings = settings_mod.get_settings()
        super(ArrivalPage, self).__init__(
            main, "到料明细表",
            "扫描送货计划表，统计未收料物料，生成每日主料到料明细（样式与示例一致）。")

    def build_body(self, layout):
        # 顶部标签设置
        top = QFrame(); top.setObjectName("Card")
        tv = QHBoxLayout(top); tv.setContentsMargins(14, 10, 14, 10); tv.setSpacing(10)
        tv.addWidget(QLabel("表头标签："))
        self.ed_label = QLineEdit(self.settings.arrival.get("top_label", "截止16点的数据"))
        tv.addWidget(self.ed_label, 1)
        self._label_card = top
        layout.addWidget(top)

        self.zone = FileZone(1, "送货计划表", "含未收料数据的送货计划，可多选/拖拽。",
                             multi=True, library_cats=["arrival_plan"],
                             detail="程序按表头文字自动识别列（物料编码/名称/供应商信息/需求数/剩余未收数），表头顺序不同也能正确处理；识别不到时回退固定列。")
        self.zone.changed.connect(self._on_files)
        layout.addWidget(self.zone)

        card = QFrame(); card.setObjectName("Card")
        cv = QVBoxLayout(card); cv.setContentsMargins(14, 12, 14, 12); cv.setSpacing(8)
        cv.addWidget(QLabel("批次设置（自动识别批次号，可改主料总类数与备注）"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["批次号", "主料总共类", "备注"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setMinimumHeight(140)
        cv.addWidget(self.table)
        self._batch_card = card
        layout.addWidget(card)

        self.panel = RunPanel("生成到料明细")
        self.panel.run_btn.clicked.connect(self._run)
        self.btn_open = self.panel.add_action("打开输出文件夹", self._open)
        layout.addWidget(self.panel)
        self._out_dir = ""
        self._refresh()

    def _on_files(self, paths):
        """文件变化时，重建批次表：自动识别批次号，回填记忆的总类数/备注。"""
        cur = self._collect_rows()          # 保留已编辑的值（按路径）
        self.table.setRowCount(0)
        mem = self.settings.arrival.get("batches", {})
        default_total = int(self.settings.arrival.get("last_total", 566))
        for p in paths:
            bn = arrival_core.detect_batch(p)
            saved = mem.get(bn, {})
            prev = cur.get(p, {})
            total = prev.get("total", saved.get("total", default_total))
            remark = prev.get("remark", saved.get("remark", ""))
            self._add_row(p, bn, total, remark)
        self._refresh()

    def _add_row(self, path, bn, total, remark):
        r = self.table.rowCount()
        self.table.insertRow(r)
        it0 = QTableWidgetItem(bn or "(未识别)")
        it0.setData(Qt.UserRole, path)
        it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
        it0.setToolTip(os.path.basename(path))
        self.table.setItem(r, 0, it0)
        sp = QSpinBox(); sp.setRange(0, 100000); sp.setValue(int(total))
        self.table.setCellWidget(r, 1, sp)
        self.table.setItem(r, 2, QTableWidgetItem(remark))

    def _collect_rows(self):
        out = {}
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if not it:
                continue
            path = it.data(Qt.UserRole)
            sp = self.table.cellWidget(r, 1)
            rm = self.table.item(r, 2)
            out[path] = {"batch_no": it.text() if it.text() != "(未识别)" else "",
                         "total": sp.value() if sp else 566,
                         "remark": rm.text() if rm else "", "include": True}
        return out

    def add_source_files(self, paths):
        self.zone.add_paths(paths)

    def refresh_view(self):
        self.zone.refresh_lib_count()

    def _refresh(self, *_):
        ok = self.table.rowCount() > 0
        self.panel.run_btn.setEnabled(ok)
        self.panel.set_status("ready" if ok else "idle",
                              "准备就绪（%d 个批次）" % self.table.rowCount() if ok else "请添加送货计划表")

    def _run(self):
        self.panel.clear_log()
        rows_map = self._collect_rows()
        rows = list(rows_map.values())
        for path, row in rows_map.items():
            row["path"] = path
        top_label = self.ed_label.text().strip() or "截止16点的数据"
        self.launch(lambda log: arrival_core.run(rows, top_label=top_label, log=log),
                    self.panel, self._done)

    def _done(self, res):
        self._out_dir = res.get("out_dir", "")
        results = res.get("results", [])
        self.panel.set_status("ok", "完成！%d 个批次已写入" % len(results))
        self.btn_open.setEnabled(bool(self._out_dir))
        lines = "\n".join("· 批次 %s：未收料 %d 类，到货 %d" % (b, d, a)
                          for b, d, a, t in results)
        self.notify_done(self._out_dir, "生成完成",
                         "%s\n输出：%s" % (lines, res.get("out_file", "")))

    def _open(self):
        self.open_folder(self._out_dir)

    def guide_steps(self):
        return [
            (None, "欢迎使用到料明细表",
             "这个页面扫描送货计划表,统计未收料物料,生成每日主料到料明细\n"
             "(样式与示例一致)。跟着高亮走一遍即可上手。"),
            (self.zone, "① 放送货计划表",
             "把含未收料数据的送货计划拖到这里,可多选。\n"
             "程序按表头文字自动识别列(物料编码/名称/供应商/需求数/剩余未收数),表头顺序不同也认得。"),
            (self._batch_card, "② 核对批次设置",
             "程序自动识别每个文件的批次号。这里可改「主料总共类」数与「备注」,\n"
             "改过的值会被记住,下次同批次自动回填。"),
            (self._label_card, "③ 表头标签(可选)",
             "生成表顶部显示的说明文字,默认「截止16点的数据」,可按需要改。"),
            (self.panel, "生成 · 看结果",
             "点「生成到料明细」。完成后状态行汇报各批次未收料类数与到货数,\n"
             "点「打开输出文件夹」查看生成的明细表。"),
        ]
