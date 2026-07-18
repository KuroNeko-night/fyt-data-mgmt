# -*- coding: utf-8 -*-
"""选择即扫描 BasePage.scan_on_select + delivery_core.analyze 的单测(offscreen)。

钉死:analyze 只读预检报角色/来源、缓存按 mtime 命中免线程、防抖只跑最后一次、
代次守卫丢弃过期结果(可取消)。
"""
import os
import time
import tempfile
import unittest
import warnings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
warnings.filterwarnings("ignore")

import openpyxl
from PySide2.QtWidgets import QApplication, QVBoxLayout

from core import delivery_core as D
from ui.pages.base_page import BasePage

_app = QApplication.instance() or QApplication([])


def _xlsx(tmp, header, rows):
    p = os.path.join(tmp, "t.xlsx")
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(p)
    return p


class _Page(BasePage):
    def __init__(self):
        super(_Page, self).__init__(None, "T", "d")

    def build_body(self, layout):
        pass


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fyt_an_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_header_detected(self):
        p = _xlsx(self.tmp, ["物料号", "物料名称", "需求数"], [["A1", "甲", 1]])
        r = D.analyze(p)
        self.assertTrue(r["ok"])
        self.assertEqual(r["source"], "header")
        self.assertEqual(r["roles"]["code"], 1)

    def test_shape_fallback(self):
        # 表头文字不可识别,靠形态兜底
        rows = [["A%04d" % i, "名%d" % i, 5 + i] for i in range(8)]
        p = _xlsx(self.tmp, ["c1", "c2", "c3"], rows)
        r = D.analyze(p)
        self.assertTrue(r["ok"])
        self.assertEqual(r["source"], "shape")

    def test_failure_reports_error(self):
        p = _xlsx(self.tmp, ["甲", "乙"], [["文本一", "文本二"]])
        r = D.analyze(p)
        self.assertFalse(r["ok"])
        self.assertNotEqual(r["error"], "")


class TestScanOnSelect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fyt_sos_")
        self.page = _Page()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pump(self, ms=600):
        end = time.time() + ms / 1000.0
        while time.time() < end:
            _app.processEvents()
            time.sleep(0.01)

    def test_scan_calls_back(self):
        p = _xlsx(self.tmp, ["物料号", "物料名称", "需求数"], [["A1", "甲", 1]])
        got = []
        self.page.scan_on_select(p, D.analyze, got.append)
        self._pump()
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0]["ok"])

    def test_cache_hits_synchronously(self):
        p = _xlsx(self.tmp, ["物料号", "物料名称", "需求数"], [["A1", "甲", 1]])
        got = []
        self.page.scan_on_select(p, D.analyze, got.append)
        self._pump()
        self.assertEqual(len(got), 1)
        # 第二次:未改文件 -> 缓存同步命中,不排队线程
        got2 = []
        self.page.scan_on_select(p, D.analyze, got2.append)
        self.assertEqual(len(got2), 1)          # 立即回调(未 pump)

    def test_debounce_runs_last_only(self):
        p1 = _xlsx(self.tmp, ["物料号", "物料名称", "需求数"], [["A1", "甲", 1]])
        p2 = os.path.join(self.tmp, "t2.xlsx")
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["物料号", "物料名称", "需求数"]); ws.append(["B1", "乙", 2]); wb.save(p2)
        seen = []
        # 快速连点两个文件,只应回调最后一个
        self.page.scan_on_select(p1, D.analyze, lambda r: seen.append(("p1", r)))
        self.page.scan_on_select(p2, D.analyze, lambda r: seen.append(("p2", r)))
        self._pump()
        self.assertEqual([s[0] for s in seen], ["p2"])

    def test_cancel_discards(self):
        p = _xlsx(self.tmp, ["物料号", "物料名称", "需求数"], [["A1", "甲", 1]])
        seen = []
        self.page.scan_on_select(p, D.analyze, seen.append)
        self.page.cancel_scan()                 # 立刻取消
        self._pump()
        self.assertEqual(seen, [])              # 过期结果被丢弃


if __name__ == "__main__":
    unittest.main()
