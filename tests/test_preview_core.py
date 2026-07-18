# -*- coding: utf-8 -*-
"""文件预览读取 preview_core 的单元测试(合成文件,可移植)。

钉死:xlsx 只取前 N 行且报截断、多子表能切换、csv 编码/分隔符探测、
不存在/不支持的类型走 error 而非抛异常。
"""
import os
import tempfile
import unittest
import warnings

import openpyxl

from core import preview_core as P

warnings.filterwarnings("ignore", message="Workbook contains no default style")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fyt_prev_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _xlsx(self, sheets):
        """sheets: {name: [row, ...]}。返回路径。"""
        p = os.path.join(self._tmp, "t.xlsx")
        wb = openpyxl.Workbook()
        first = True
        for name, rows in sheets.items():
            ws = wb.active if first else wb.create_sheet()
            ws.title = name
            first = False
            for row in rows:
                ws.append(row)
        wb.save(p)
        return p


class TestXlsx(_Tmp):
    def test_reads_header_and_rows(self):
        p = self._xlsx({"S1": [["编码", "名称", "数量"],
                               ["A1", "甲", 10], ["A2", "乙", 20]]})
        d = P.read_preview(p)
        self.assertEqual(d.error, "")
        self.assertEqual(d.rows[0], ["编码", "名称", "数量"])
        self.assertEqual(d.rows[1], ["A1", "甲", "10"])   # 整数去 .0
        self.assertEqual(d.sheet, "S1")

    def test_truncates_to_max_rows(self):
        rows = [["h"]] + [[i] for i in range(100)]
        p = self._xlsx({"S1": rows})
        d = P.read_preview(p, max_rows=10)
        self.assertEqual(d.nrows, 10)
        self.assertTrue(d.truncated)

    def test_multi_sheet_switch(self):
        p = self._xlsx({"A": [["x"], [1]], "B": [["y"], [2]]})
        self.assertEqual(P.list_sheets(p), ["A", "B"])
        d = P.read_preview(p, sheet="B")
        self.assertEqual(d.sheet, "B")
        self.assertEqual(d.rows[0], ["y"])
        self.assertEqual(sorted(d.sheets), ["A", "B"])


class TestCsvAndErrors(_Tmp):
    def test_csv_comma(self):
        p = os.path.join(self._tmp, "t.csv")
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            f.write("编码,名称\nA1,甲\nA2,乙\n")
        d = P.read_preview(p)
        self.assertEqual(d.error, "")
        self.assertEqual(d.rows[0], ["编码", "名称"])
        self.assertEqual(d.rows[1], ["A1", "甲"])

    def test_csv_gbk(self):
        p = os.path.join(self._tmp, "g.csv")
        with open(p, "w", encoding="gbk", newline="") as f:
            f.write("列一,列二\n甲,乙\n")
        d = P.read_preview(p)
        self.assertEqual(d.error, "")
        self.assertEqual(d.rows[0], ["列一", "列二"])

    def test_missing_file(self):
        d = P.read_preview(os.path.join(self._tmp, "nope.xlsx"))
        self.assertNotEqual(d.error, "")
        self.assertEqual(d.rows, [])

    def test_unsupported_type(self):
        p = os.path.join(self._tmp, "x.pdf")
        with open(p, "wb") as f:
            f.write(b"%PDF-1.4")
        d = P.read_preview(p)
        self.assertIn("不支持", d.error)


if __name__ == "__main__":
    unittest.main()
