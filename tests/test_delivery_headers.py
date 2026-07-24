# -*- coding: utf-8 -*-
"""送货计划表头识别回归测试(合成簿,可移植)。

钉死本轮修复:
- SAP 列名 下阶物料/下阶物料描述 能被 detect_layout 映射为 code/cname;
- 「委外供应商属性」不再被当成供应商名称列(含'属性'的列排除);
- list_sheets 列子表、非 xlsx 返回 []。

只在临时目录造簿并读取,对用户数据零副作用。
"""
import os
import tempfile
import unittest
import warnings

import openpyxl

from core import delivery_core as D

warnings.filterwarnings("ignore", message="Workbook contains no default style")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fyt_dlv_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def mk(self, name, sheets):
        p = os.path.join(self._tmp, name)
        wb = openpyxl.Workbook()
        first = True
        for sn, rows in sheets.items():
            ws = wb.active if first else wb.create_sheet()
            ws.title = sn
            first = False
            for row in rows:
                ws.append(row)
        wb.save(p)
        return p


class TestDetectLayout(_Tmp):
    def _layout(self, header):
        p = self.mk("t.xlsx", {"S": [header, ["x"] * len(header)]})
        wb = openpyxl.load_workbook(p)
        hr, cols = D.detect_layout(wb["S"])
        wb.close()
        return hr, cols

    def test_sap_xiajie_maps_code_and_name(self):
        # SAP KD 清单用「下阶物料/下阶物料描述」而非零部件代码
        hr, cols = self._layout(["上阶物料", "下阶物料", "下阶物料描述", "数量"])
        self.assertIsNotNone(hr)
        self.assertIn("code", cols)
        self.assertIn("cname", cols)
        # code 应指向「下阶物料」列(第2列),而非「上阶物料」
        self.assertEqual(cols["code"], 2)

    def test_supplier_attr_not_taken_as_supplier_name(self):
        # 「委外供应商属性」含'供应商'子串,但不是供应商名称列,不能被抢
        hr, cols = self._layout(
            ["下阶物料", "委外供应商属性", "供应商代码", "供应商名称", "数量"])
        self.assertIsNotNone(hr)
        # 供应商名称列必须是第4列「供应商名称」,不是第2列「委外供应商属性」。
        # 硬断言(不加 if):若守卫失效 sup_name 会指向 2,此处即失败。
        self.assertIn("sup_name", cols)
        self.assertEqual(cols["sup_name"], 4)

    def test_classic_code_still_works(self):
        # 不回退:经典「零部件代码」仍可识别
        hr, cols = self._layout(["零部件代码", "零部件名称", "数量", "供应商代码"])
        self.assertIsNotNone(hr)
        self.assertIn("code", cols)


class TestListSheets(_Tmp):
    def test_lists_all_sheets_in_order(self):
        p = self.mk("multi.xlsx", {"Sheet1": [["a"]], "BOM": [["b"]],
                                   "发运清单": [["c"]]})
        self.assertEqual(D.list_sheets(p), ["Sheet1", "BOM", "发运清单"])

    def test_non_xlsx_returns_empty(self):
        p = os.path.join(self._tmp, "x.xls")
        with open(p, "w") as f:
            f.write("not a real xls")
        self.assertEqual(D.list_sheets(p), [])

    def test_missing_file_returns_empty(self):
        self.assertEqual(D.list_sheets(os.path.join(self._tmp, "nope.xlsx")), [])


if __name__ == "__main__":
    unittest.main()
