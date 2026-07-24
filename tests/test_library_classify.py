# -*- coding: utf-8 -*-
"""数据库分类器回归测试。

分两层：
1) 合成工作簿(可移植,任何机器/CI 都跑)——钉死已修复的关键行为:
   多标签归类、list_items/counts 兼容旧索引、reclassify 重置标签、
   deliv_supp 的 SAP(下阶物料)判据。
2) 真实样本黄金矩阵(缺样本自动 skip)——35 样本→期望类别不回退。

只读取/分类,不写用户库(注入假索引或用 tmp),对运行中的程序零副作用。
"""
import os
import tempfile
import unittest
import warnings

import openpyxl

from core import library as L
from tests import sample_data as sd

warnings.filterwarnings("ignore", message="Workbook contains no default style")


def _wb(path, sheets):
    """按 {表名: [表头行, 数据行...]} 造一个 xlsx。"""
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        ws.title = name
        first = False
        for row in rows:
            ws.append(row)
    wb.save(path)


class _TmpFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fyt_lib_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def mk(self, name, sheets):
        p = os.path.join(self._tmp, name)
        _wb(p, sheets)
        return p


# 常用表头行(与 _score_sheet 的判据对应)
SUPP_HDR = ["批次号", "属性", "下阶物料", "下阶物料描述",
            "供应商代码", "供应商名称", "合计", "库区"]
SUPP_ROW = ["GK1", "KD", "8892602000", "右前踏板", "100079", "北京丰达", "360", "M62"]
PIVOT_HDR = ["版本序号", "材料编号", "材料名称", "规格", "数量", "单位", "最终采购数量"]
PIVOT_ROW = [1, "MAT001", "纸箱", "600x400", "10", "个", "120"]


class TestClassifySynthetic(_TmpFile):
    """合成簿:钉死判据,不依赖任何外部样本。"""

    def test_deliv_supp_sap_xiajie(self):
        # SAP 表用「下阶物料」作编码,靠 供应商代码+供应商名称 定性
        p = self.mk("供应商表.xlsx", {"Sheet1": [SUPP_HDR, SUPP_ROW]})
        r = L.classify(p)
        self.assertEqual(r["category"], "deliv_supp")
        self.assertIn("deliv_supp", r["categories"])

    def test_pivot_src(self):
        p = self.mk("包材核算.xlsx",
                    {"包装方案汇总及包材用量计算": [PIVOT_HDR, PIVOT_ROW]})
        self.assertEqual(L.classify(p)["category"], "pivot_src")

    def test_multi_label_cross_feature(self):
        # 一个文件:子表A=供应商明细, 子表B=透视源 -> 应得两个标签
        p = self.mk("跨功能.xlsx", {
            "供应商表": [SUPP_HDR, SUPP_ROW],
            "包装方案汇总及包材用量计算": [PIVOT_HDR, PIVOT_ROW],
        })
        r = L.classify(p)
        self.assertIn("deliv_supp", r["categories"])
        self.assertIn("pivot_src", r["categories"])
        # sheets 映射应指出各标签命中的子表
        self.assertEqual(r["sheets"]["deliv_supp"], "供应商表")
        self.assertEqual(r["sheets"]["pivot_src"], "包装方案汇总及包材用量计算")

    def test_single_label_files_stay_single(self):
        # 纯供应商表不应被误加其它标签(防多标签泛滥)
        p = self.mk("纯供应商.xlsx", {"Sheet1": [SUPP_HDR, SUPP_ROW]})
        self.assertEqual(L.classify(p)["categories"], ["deliv_supp"])

    def test_unknown_below_threshold(self):
        p = self.mk("杂表.xlsx", {"Sheet1": [["甲", "乙", "丙"], [1, 2, 3]]})
        r = L.classify(p)
        self.assertEqual(r["category"], L.UNKNOWN)
        self.assertEqual(r["categories"], [])


class TestIndexMultiLabel(unittest.TestCase):
    """list_items/counts 的多标签与旧索引兼容(注入假索引,不碰真实库)。"""

    def setUp(self):
        self._orig = L._load_index
        self._fake = {"items": [
            {"name": "跨功能.xlsx", "category": "pivot_src",
             "categories": ["pivot_src", "deliv_supp"],
             "path": "X/跨功能.xlsx", "updated": "2026-07-17"},
            {"name": "旧条目.xlsx", "category": "deliv_bom",   # 无 categories:测回退
             "path": "Y/旧.xlsx", "updated": "2026-07-16"},
        ]}
        L._load_index = lambda: self._fake

    def tearDown(self):
        L._load_index = self._orig

    def test_list_items_hits_secondary_label(self):
        names = [it["name"] for it in L.list_items("deliv_supp")]
        self.assertIn("跨功能.xlsx", names)      # 附加标签也命中

    def test_list_items_legacy_fallback(self):
        names = [it["name"] for it in L.list_items("deliv_bom")]
        self.assertIn("旧条目.xlsx", names)      # 旧条目无 categories 仍可查

    def test_counts_each_label_once(self):
        c = L.counts()
        self.assertEqual(c["pivot_src"], 1)
        self.assertEqual(c["deliv_supp"], 1)     # 多标签在每类各计一次
        self.assertEqual(c["deliv_bom"], 1)

    def test_remove_item_via_secondary_label(self):
        # 从附加标签(deliv_supp)删除多标签条目应生效(主类别是 pivot_src)
        saved = {}
        orig_save = L._save_index
        L._save_index = lambda idx: saved.update(idx)
        try:
            n = L.remove_item("deliv_supp", "跨功能.xlsx", delete_file=False)
        finally:
            L._save_index = orig_save
        self.assertEqual(n, 1)                    # 按附加标签匹配到并移除
        names = [it["name"] for it in saved["items"]]
        self.assertNotIn("跨功能.xlsx", names)


class TestGoldenMatrix(unittest.TestCase):
    """真实补充样本→期望类别(缺样本自动 skip)。锁死本轮修复不回退。"""

    def _check(self, path, expect):
        if not path:
            self.skipTest("缺少补充样本")
        self.assertEqual(L.classify(path)["category"], expect,
                         "%s 应归为 %s" % (os.path.basename(path), expect))

    def test_kd_bom(self):
        self._check(sd.supp_kd_bom(), "deliv_bom")

    def test_kd_supplier(self):
        self._check(sd.supp_kd_supplier(), "deliv_supp")

    def test_pfep_all_pivot(self):
        srcs = sd.supp_pfep_sources()
        if not srcs:
            self.skipTest("缺少 PFEP 样本")
        for p in srcs:
            self.assertEqual(L.classify(p)["category"], "pivot_src",
                             "%s 应归 pivot_src" % os.path.basename(p))


if __name__ == "__main__":
    unittest.main()


class TestClassifyReadFailure(_TmpFile):
    """整表读不出(损坏/加密)时:归 unknown 且经 log 上报,不再静默。"""

    def _corrupt(self, name="坏.xlsx"):
        p = os.path.join(self._tmp, name)
        with open(p, "wb") as f:
            f.write(b"this is not a real xlsx zip container")
        return p

    def test_corrupt_logs_warning(self):
        logs = []
        info = L.classify(self._corrupt(), log=logs.append)
        self.assertEqual(info["category"], L.UNKNOWN)
        self.assertTrue(any("无法读取" in l for l in logs),
                        "损坏文件应记读取失败告警")

    def test_corrupt_log_none_backcompat(self):
        # 不传 log 时不得抛异常,行为与旧版一致(仍归 unknown)
        info = L.classify(self._corrupt())
        self.assertEqual(info["category"], L.UNKNOWN)

    def test_valid_file_no_false_warning(self):
        logs = []
        p = self.mk("正常.xlsx", {"S": [PIVOT_HDR, PIVOT_ROW]})
        L.classify(p, log=logs.append)
        self.assertEqual([l for l in logs if "无法读取" in l], [])
