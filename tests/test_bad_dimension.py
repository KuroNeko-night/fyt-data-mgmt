# -*- coding: utf-8 -*-
"""坏 <dimension> 文件的整表漏读回归测试。

部分导出的 .xlsx 把工作表 <dimension> 标为单格(如 ref="A1"),openpyxl 以
read_only=True 读取时会信任该标签、只吐 1 行,导致整表静默漏读。仓库自带的考勤
"每日统计表"样本正是此类文件(6264 行会被读成 1 行),用它守护各读取路径。

样本缺失时自动 skip。
"""
import unittest
import warnings

from tests import sample_data as sd

warnings.filterwarnings("ignore", message="Workbook contains no default style")
warnings.filterwarnings("ignore", message=".*no default style.*")


class TestBadDimension(unittest.TestCase):
    def setUp(self):
        self.p = sd.attendance_source()
        if not self.p:
            self.skipTest("缺少考勤样本(坏 dimension 文件)")

    def _truth_rows(self):
        # 常规(非 read_only)模式的真实总行数,作为基准
        import openpyxl
        wb = openpyxl.load_workbook(self.p, data_only=True)
        n = sum(len(list(ws.iter_rows(values_only=True))) for ws in wb.worksheets)
        wb.close()
        return n

    def test_common_read_sheets_full(self):
        from core import common_core as cc
        got = sum(len(rows) for _, rows in cc.read_sheets(self.p))
        self.assertEqual(got, self._truth_rows())
        self.assertGreater(got, 1)

    def test_excel_tools_read_sheets_full(self):
        from core import excel_tools_core as et
        got = sum(len(rows) for _, rows in et._read_sheets(self.p))
        self.assertEqual(got, self._truth_rows())
        self.assertGreater(got, 1)

    def test_preview_reads_beyond_first_row(self):
        from core import preview_core as pv
        d = pv._read_xlsx(self.p, None, 200, 40)
        self.assertGreaterEqual(len(d.rows), 200)   # 修复前只有 1

    def test_compare_headers_find_real_row(self):
        from core import compare_core as cmp
        hs = cmp.read_headers(self.p)
        # 真表头在数据区(含"姓名"),坏 dimension 下修复前只能看到首行"基本信息"
        self.assertIn("姓名", hs)
        self.assertNotEqual(hs[:1], ["基本信息"])


if __name__ == "__main__":
    unittest.main()
