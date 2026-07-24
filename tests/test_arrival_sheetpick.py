# -*- coding: utf-8 -*-
"""到料明细多子表选择回归测试(合成簿,可移植)。

钉死:含数据的子表即使不是活动表/第一张,也能被 _pick_data_ws 选中,
不再静默读到空的干扰子表(如 'Sheet2')而把全部物料误判为已收。
"""
import os
import tempfile
import unittest
import warnings

import openpyxl

from core import arrival_core as A

warnings.filterwarnings("ignore", message="Workbook contains no default style")

# locate_columns 需要的表头(编码/需求/剩余未收 为关键列)
HDR = ["物料编码", "物料名称", "供应商信息", "需求数", "剩余未收数"]
# 剩余未收数须为非零数值才算"未收"(extract 视非数值/0 为已收),故用真数字
DATA = ["8892602000", "右前踏板", "北京丰达", 360, 12]


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fyt_arr_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def mk(self, sheets, active_idx=0):
        """sheets: [(名, [行...]) ...]; active_idx 指定活动表。"""
        p = os.path.join(self._tmp, "plan.xlsx")
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for name, rows in sheets:
            ws = wb.create_sheet(title=name)
            for row in rows:
                ws.append(row)
        wb.active = active_idx
        wb.save(p)
        return p


class TestPickDataWs(_Tmp):
    def _pick(self, sheets, active_idx=0):
        p = self.mk(sheets, active_idx)
        wb = openpyxl.load_workbook(p, data_only=True)
        logs = []
        ws = A._pick_data_ws(wb, log=logs.append)
        name = ws.title
        wb.close()
        return name, logs

    def test_single_sheet_unchanged(self):
        name, logs = self._pick([("零件到货计划", [HDR, DATA])])
        self.assertEqual(name, "零件到货计划")
        self.assertEqual([l for l in logs if "子表" in l], [])   # 单表无噪音

    def test_active_valid_is_used(self):
        # 活动表(idx=1)有效 -> 用它
        name, logs = self._pick(
            [("Sheet2", [["空"], []]), ("零件到货计划", [HDR, DATA])],
            active_idx=1)
        self.assertEqual(name, "零件到货计划")

    def test_wrong_active_auto_corrects(self):
        # 活动表=空 Sheet2(idx=0) -> 应自动改读有数据的子表
        name, logs = self._pick(
            [("Sheet2", [["空表"], ["x"]]), ("零件到货计划", [HDR, DATA])],
            active_idx=0)
        self.assertEqual(name, "零件到货计划")
        self.assertTrue(any("改读" in l for l in logs), "应记录纠偏")

    def test_extract_reads_correct_sheet(self):
        # 端到端:错误活动表下 extract_unreceived 仍能取到那 1 行未收料
        p = self.mk([("Sheet2", [["空表"], ["x"]]),
                     ("零件到货计划", [HDR, DATA])], active_idx=0)
        rows = A.extract_unreceived(p)
        self.assertEqual(len(rows), 1)         # 若误读空表会得 0
        self.assertEqual(rows[0][0], "8892602000")


if __name__ == "__main__":
    unittest.main()
