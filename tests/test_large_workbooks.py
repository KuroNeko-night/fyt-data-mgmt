# -*- coding: utf-8 -*-
"""大文件只读流式路径回归测试。"""
import os
import re
import tempfile
import unittest
import zipfile

import openpyxl

from core import common_core
from core import pivot_core


def _break_dimension(path):
    """把首张工作表的 dimension 伪造为 A1，复现真实业务导出文件。"""
    broken_path = os.path.join(os.path.dirname(path), "坏范围.xlsx")
    with zipfile.ZipFile(path, "r") as source, \
            zipfile.ZipFile(broken_path, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                text = payload.decode("utf-8")
                text = re.sub(r'<dimension ref="[^"]+"\s*/>',
                              '<dimension ref="A1"/>', text, count=1)
                payload = text.encode("utf-8")
            target.writestr(info, payload)
    return broken_path


class TestLargeWorkbookStreaming(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        source_path = os.path.join(self.temp_dir.name, "源表.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "包装方案汇总"
        ws.append(["版本序号", "材料编号", "材料名称", "规格", "数量", "单位",
                   "最终采购数量"])
        for index in range(1, 121):
            ws.append([1, "M%04d" % index, "材料%d" % index, "S", 1, "个", index])
        wb.save(source_path)
        wb.close()
        self.path = _break_dimension(source_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_common_stream_repairs_bad_dimension(self):
        wb = common_core.load_data_only_stream(self.path)
        try:
            rows = list(wb.active.iter_rows(values_only=True))
        finally:
            wb.close()
        self.assertEqual(len(rows), 121)
        self.assertEqual(rows[-1][1], "M0120")

    def test_pivot_analysis_keeps_all_rows(self):
        plan = pivot_core.analyze_workbooks([self.path])
        self.assertEqual(len(plan["sheets"]), 1)
        sheet = plan["sheets"][0]
        self.assertTrue(sheet["use"])
        self.assertEqual(len(sheet["kept"]), 120)
        self.assertEqual(sheet["kept"][-1][pivot_core.F_CODE], "M0120")

    def test_readonly_conflicts_match_copy_and_mutate_path(self):
        rows = [
            [1, "M1", "纸箱", "500×300，20/包", 1, "个/套", 2],
            [1, "M1", "纸箱", "500x300", 1, "个", 3],
            [1, "M2", "纸箱", "600x400", 1, "个", 4],
        ]
        copied = [list(row) for row in rows]
        pivot_core.unify_specs(copied)
        expected = pivot_core.compute_unit_best(copied)

        canon, _groups, _sample = pivot_core.compute_spec_canon(rows)
        actual = pivot_core._compute_unit_best(lambda: iter(rows), spec_canon=canon)

        self.assertEqual(actual, expected)
        self.assertEqual(rows[0][pivot_core.F_SPEC], "500×300，20/包")


if __name__ == "__main__":
    unittest.main()
