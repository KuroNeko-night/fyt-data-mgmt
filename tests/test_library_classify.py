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
from unittest import mock

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
    wb.save(path)  # 生成多工作表分类样本


class _TmpFile(unittest.TestCase):
    """为分类器合成文件用例提供隔离目录和工作簿工厂。"""

    def setUp(self):
        """创建不接触正式数据库目录的临时文件根。"""

        self._tmp = tempfile.mkdtemp(prefix="fyt_lib_")

    def tearDown(self):
        """递归删除合成工作簿和分类临时文件。"""

        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def mk(self, name, sheets):
        """按给定工作表结构生成待分类 xlsx。"""

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
        """SAP“下阶物料”表应结合供应商列识别为送货供应商资料。"""

        # SAP 表用「下阶物料」作编码,靠 供应商代码+供应商名称 定性
        p = self.mk("供应商表.xlsx", {"Sheet1": [SUPP_HDR, SUPP_ROW]})
        r = L.classify(p)
        self.assertEqual(r["category"], "deliv_supp")  # SAP 下阶物料表归类
        self.assertIn("deliv_supp", r["categories"])

    def test_pivot_src(self):
        """包材用量和最终采购数量字段应识别为销售表制作源数据。"""

        p = self.mk("包材核算.xlsx",
                    {"包装方案汇总及包材用量计算": [PIVOT_HDR, PIVOT_ROW]})
        self.assertEqual(L.classify(p)["category"], "pivot_src")  # 销售源数据归类

    def test_multi_label_cross_feature(self):
        """不同子表分别命中业务时，一个文件应同时保存两个分类标签和表名映射。"""

        # 一个文件:子表A=供应商明细, 子表B=透视源 -> 应得两个标签
        p = self.mk("跨功能.xlsx", {
            "供应商表": [SUPP_HDR, SUPP_ROW],
            "包装方案汇总及包材用量计算": [PIVOT_HDR, PIVOT_ROW],
        })
        r = L.classify(p)
        self.assertIn("deliv_supp", r["categories"])  # 多标签命中
        self.assertIn("pivot_src", r["categories"])
        # sheets 映射应指出各标签命中的子表
        self.assertEqual(r["sheets"]["deliv_supp"], "供应商表")  # 标签对应子表
        self.assertEqual(r["sheets"]["pivot_src"], "包装方案汇总及包材用量计算")

    def test_single_label_files_stay_single(self):
        """纯供应商表不得因宽松评分产生无关附加标签。"""

        # 纯供应商表不应被误加其它标签(防多标签泛滥)
        p = self.mk("纯供应商.xlsx", {"Sheet1": [SUPP_HDR, SUPP_ROW]})
        self.assertEqual(L.classify(p)["categories"], ["deliv_supp"])  # 单一标签不泛滥

    def test_unknown_below_threshold(self):
        """无业务特征的普通表应落入未知分类且 categories 为空。"""

        p = self.mk("杂表.xlsx", {"Sheet1": [["甲", "乙", "丙"], [1, 2, 3]]})
        r = L.classify(p)
        self.assertEqual(r["category"], L.UNKNOWN)  # 低于阈值归未知
        self.assertEqual(r["categories"], [])  # 无标签


class TestIndexMultiLabel(unittest.TestCase):
    """list_items/counts 的多标签与旧索引兼容(注入假索引,不碰真实库)。"""

    def setUp(self):
        """注入同时含新多标签条目和旧单标签条目的内存索引。"""

        self._orig = L._load_index
        self._fake = {"items": [
            {"name": "跨功能.xlsx", "category": "pivot_src",
             "categories": ["pivot_src", "deliv_supp"],
             "path": "X/跨功能.xlsx", "updated": "2026-07-17"},
            {"name": "旧条目.xlsx", "category": "deliv_bom",   # 无 categories:测回退
             "path": "Y/旧.xlsx", "updated": "2026-07-16"},
        ]}
        L._load_index = lambda: self._fake  # 注入假索引

    def tearDown(self):
        """恢复真实索引加载函数，避免影响后续文件库测试。"""

        L._load_index = self._orig

    def test_list_items_hits_secondary_label(self):
        """按次要标签筛选时也应命中多标签文件。"""

        names = [it["name"] for it in L.list_items("deliv_supp")]
        self.assertIn("跨功能.xlsx", names)      # 附加标签也命中

    def test_list_items_legacy_fallback(self):
        """旧索引没有 categories 时仍回退使用主 category。"""

        names = [it["name"] for it in L.list_items("deliv_bom")]
        self.assertIn("旧条目.xlsx", names)      # 旧条目无 categories 仍可查

    def test_counts_each_label_once(self):
        """多标签文件在每个所属类别各计一次，但同一类别不重复计数。"""

        c = L.counts()
        self.assertEqual(c["pivot_src"], 1)  # 主标签计数
        self.assertEqual(c["deliv_supp"], 1)     # 多标签在每类各计一次
        self.assertEqual(c["deliv_bom"], 1)

    def test_remove_item_via_secondary_label(self):
        """通过次要标签定位的文件也应能从索引删除。"""

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


class TestReclassifyConflict(unittest.TestCase):
    """验证人工重分类遇到同名目标和索引写入失败时的文件事务。"""

    def setUp(self):
        """创建隔离文件库根，避免重分类触碰正式资料库。"""

        self._tmp = tempfile.mkdtemp(prefix="fyt_reclassify_")

    def tearDown(self):
        """删除源、目标和事务备份文件。"""

        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _run(self, save_result=True):
        """构造源目标同名冲突，并可模拟索引原子保存失败。"""

        library_root = os.path.join(self._tmp, "library")
        source_dir = os.path.join(library_root, L.CATEGORY_DIRS["att_source"])
        target_dir = os.path.join(library_root, L.CATEGORY_DIRS["rec_zong"])
        os.makedirs(source_dir, exist_ok=True)
        os.makedirs(target_dir, exist_ok=True)
        name = "同名文件.xlsx"
        source = os.path.join(source_dir, name)
        target = os.path.join(target_dir, name)
        with open(source, "wb") as stream:
            stream.write(b"source")
        with open(target, "wb") as stream:
            stream.write(b"existing")
        index = {"items": [{
            "name": name, "category": "att_source", "categories": ["att_source"],
            "path": source, "updated": "2026-01-01",
        }]}
        saved = []
        # 路径和索引函数全部指向临时对象，真实数据库分类索引不会被读取或写入。
        with mock.patch.object(L.paths, "library_dir", return_value=library_root), \
             mock.patch.object(L.paths, "library_index_path", return_value=os.path.join(self._tmp, "index.json")), \
             mock.patch.object(L, "_load_index", return_value=index), \
             mock.patch.object(L, "_save_index", side_effect=lambda value: saved.append(value) or save_result):
            result = L.reclassify("att_source", name, "rec_zong")  # 重分类到目标类别
        return result, source, target, saved

    def test_existing_destination_is_preserved_until_move_succeeds(self):
        """目标同名旧文件应先备份，源移动及索引保存成功后再清除备份。"""

        result, source, target, saved = self._run()
        self.assertTrue(result)  # 重分类成功
        self.assertFalse(os.path.exists(source))  # 源文件已移走
        with open(target, "rb") as stream:
            self.assertEqual(stream.read(), b"source")  # 目标内容为源内容
        self.assertFalse(os.path.exists(target + ".reclassify.bak"))  # 备份已清除
        self.assertEqual(saved[0]["items"][0]["path"], target)  # 索引路径更新

    def test_index_failure_restores_both_files(self):
        """索引保存失败时必须同时恢复源文件和原目标文件内容。"""

        result, source, target, _ = self._run(save_result=False)
        self.assertFalse(result)  # 索引保存失败返回失败
        with open(source, "rb") as stream:
            self.assertEqual(stream.read(), b"source")  # 源文件恢复
        with open(target, "rb") as stream:
            self.assertEqual(stream.read(), b"existing")  # 目标文件恢复


class TestGoldenMatrix(unittest.TestCase):
    """真实补充样本→期望类别(缺样本自动 skip)。锁死本轮修复不回退。"""

    def _check(self, path, expect):
        """有真实补充样本时检查黄金分类，缺样本则友好跳过。"""

        if not path:
            self.skipTest("缺少补充样本")
        self.assertEqual(L.classify(path)["category"], expect,
                         "%s 应归为 %s" % (os.path.basename(path), expect))

    def test_kd_bom(self):
        """真实 KD BOM 样本应稳定识别为送货 BOM。"""

        self._check(sd.supp_kd_bom(), "deliv_bom")

    def test_kd_supplier(self):
        """真实 KD 供应商样本应稳定识别为供应商资料。"""

        self._check(sd.supp_kd_supplier(), "deliv_supp")

    def test_pfep_all_pivot(self):
        """所有可用 PFEP 样本都应识别为销售表制作源数据。"""

        srcs = sd.supp_pfep_sources()
        if not srcs:
            self.skipTest("缺少 PFEP 样本")  # 样本缺失跳过
        for p in srcs:
            self.assertEqual(L.classify(p)["category"], "pivot_src",
                             "%s 应归 pivot_src" % os.path.basename(p))  # 黄金类别不回退


if __name__ == "__main__":
    unittest.main()


class TestClassifyReadFailure(_TmpFile):
    """整表读不出(损坏/加密)时:归 unknown 且经 log 上报,不再静默。"""

    def _corrupt(self, name="坏.xlsx"):
        """写入非 ZIP 内容，模拟损坏或加密的 xlsx。"""

        p = os.path.join(self._tmp, name)
        with open(p, "wb") as f:
            f.write(b"this is not a real xlsx zip container")
        return p

    def test_corrupt_logs_warning(self):
        """读取失败应归入未知分类并通过可选日志报告原因。"""

        logs = []
        info = L.classify(self._corrupt(), log=logs.append)
        self.assertEqual(info["category"], L.UNKNOWN)  # 损坏文件归未知
        self.assertTrue(any("无法读取" in l for l in logs),
                        "损坏文件应记读取失败告警")  # 日志上报

    def test_corrupt_log_none_backcompat(self):
        """调用方不提供日志回调时仍应保持旧版不抛错行为。"""

        # 不传 log 时不得抛异常,行为与旧版一致(仍归 unknown)
        info = L.classify(self._corrupt())
        self.assertEqual(info["category"], L.UNKNOWN)  # 无日志回调也不抛错

    def test_valid_file_no_false_warning(self):
        """正常工作簿不得产生“无法读取”的误报警告。"""

        logs = []
        p = self.mk("正常.xlsx", {"S": [PIVOT_HDR, PIVOT_ROW]})
        L.classify(p, log=logs.append)
        self.assertEqual([l for l in logs if "无法读取" in l], [])  # 正常文件无误报
