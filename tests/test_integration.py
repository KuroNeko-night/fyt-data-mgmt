# -*- coding: utf-8 -*-
"""端到端集成测试：用仓库自带样本数据跑各功能 run()。

输出统一写到临时目录（显式传 out_dir），不落到用户文档目录。
样本数据缺失的用例自动 skip，保证无样本环境下不误报失败。
"""
import os
import shutil
import tempfile
import unittest
import warnings

from tests import sample_data as sd

# openpyxl 对无默认样式的簿会告警，与测试无关，静音以免干扰输出
warnings.filterwarnings("ignore", message="Workbook contains no default style")


class _TmpOut(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fyt_it_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def out(self, name):
        d = os.path.join(self._tmp, name)
        os.makedirs(d, exist_ok=True)
        return d


class TestAttendance(_TmpOut):
    def test_run(self):
        tgt, src = sd.attendance_target(), sd.attendance_source()
        if not (tgt and src):
            self.skipTest("缺少考勤填报样本")
        from core import attendance_core
        res = attendance_core.run([tgt], [src], out_dir=self.out("att"))
        self.assertTrue(res["out_files"])
        self.assertTrue(os.path.isfile(res["out_files"][0]))
        # 每个待填表返回 (文件, 表名/结果, stats)
        stats = res["results"][0][2]
        self.assertGreater(stats["matched"], 0)
        # 填了的时间行数不应超过匹配到的人天数
        self.assertLessEqual(stats["filled_time"], stats["matched"])


class TestReconcile(_TmpOut):
    def test_run(self):
        tgt = sd.reconcile_target()
        src = sd.reconcile_sources()
        labor = sd.reconcile_labor()
        if not (tgt and src and labor):
            self.skipTest("缺少工时对账样本")
        from core import reconcile_core
        res = reconcile_core.run(tgt, src, labor, out_dir=self.out("rec"))
        self.assertTrue(os.path.isfile(res["filled_path"]))
        self.assertTrue(os.path.isfile(res["summary_path"]))
        self.assertIn("credibility", res)


class TestPurchase(_TmpOut):
    def test_run(self):
        f1, f2 = sd.purchase_ours(), sd.purchase_supplier()
        if not (f1 and f2):
            self.skipTest("缺少采购数对账样本")
        from core import purchase_core
        res = purchase_core.run(f1, f2, out_dir=self.out("pur"))
        self.assertTrue(os.path.isfile(res["report"]))
        self.assertTrue(os.path.isfile(res["out1"]))
        self.assertTrue(os.path.isfile(res["out2"]))
        self.assertGreater(len(res["pairs"]), 0)
        # matched 列表长度应与各自行数一致
        self.assertEqual(len(res["matched1"]), len(res["rows1"]))
        self.assertEqual(len(res["matched2"]), len(res["rows2"]))


class TestDelivery(_TmpOut):
    def test_run(self):
        bom, sup = sd.delivery_bom(), sd.delivery_supplier()
        if not (bom and sup):
            self.skipTest("缺少送货计划样本")
        from core import delivery_core
        res = delivery_core.run(bom, sup, out_dir=self.out("deliv"),
                                order_type="SUB")
        self.assertTrue(os.path.isfile(res["plan_path"]))
        self.assertGreater(res["rows"], 0)
        self.assertEqual(res["order_type"], "SUB")
        # 顺序任意也应正确辨识主表/供应商来源（不抛异常即通过辨识）
        self.assertTrue(res["master_file"])
        self.assertTrue(res["supplier_file"])
        self.assertTrue(res.get("supplier_used"))

    def test_run_without_supplier(self):
        """供应商明细可选：只给物料清单也应正常生成，供应商列留空不报未匹配。"""
        bom = sd.delivery_bom()
        if not bom:
            self.skipTest("缺少送货计划样本")
        from core import delivery_core
        res = delivery_core.run(bom, out_dir=self.out("deliv_nosup"),
                                order_type="KD")
        self.assertTrue(os.path.isfile(res["plan_path"]))
        self.assertGreater(res["rows"], 0)
        self.assertEqual(res["order_type"], "KD")
        # 若样本 bom 自带供应商列会 supplier_used=True；否则应留空且不计未匹配
        if not res["supplier_used"]:
            self.assertEqual(res["missing"], [])
            self.assertEqual(res["supplier_file"], "")


class TestArrival(_TmpOut):
    def test_run(self):
        plans = sd.arrival_plans()
        if not plans:
            self.skipTest("缺少到料明细样本")
        from core import arrival_core
        rows = [{"path": p, "batch_no": "", "total": 566,
                 "remark": "", "include": True} for p in plans]
        res = arrival_core.run(rows, top_label="截止16点的数据",
                               out_dir=self.out("arr"))
        self.assertTrue(os.path.isfile(res["out_file"]))
        self.assertEqual(len(res["results"]), len(plans))

    def test_detect_batch(self):
        plans = sd.arrival_plans()
        if not plans:
            self.skipTest("缺少到料明细样本")
        from core import arrival_core
        # 批次识别应返回字符串（识别不到为空串，不应抛异常）
        self.assertIsInstance(arrival_core.detect_batch(plans[0]), str)


class TestPivotMeasureText(unittest.TestCase):
    """度量列(最终采购数量)混入文本时,透视缓存不得把整列判为字符串。
    否则 Excel 刷新透视后该字段求和归零,与静态总计背离。"""

    def test_stray_text_in_measure_stays_numeric(self):
        from core import pivot_core as P
        rows = [
            ["", "A1", "甲", "S", 1, "个", 10],
            ["", "A1", "甲", "S", 1, "个", "见附表"],   # 混入文本
            ["", "A2", "乙", "T", 1, "个", 5],
        ]
        meta = P.build_fields_meta(rows)
        df = meta[P.DATA_FIELD]
        self.assertFalse(df["has_str"])              # 度量列不因文本被判字符串
        xml = P.cache_records_xml(rows, meta)
        self.assertNotIn("见附表", xml)               # 文本不进缓存(不出现 <s v="见附表">)
        self.assertNotIn("<s ", xml)                  # 度量列无字符串项,全部 <n>/<m>
        self.assertEqual(xml.count("<n "), 5)         # 两行度量(10,5)+三行数量(1,1,1)
        # 静态聚合把文本计 0,A1 合计=10,与缓存口径一致
        a1 = [g for g in P.aggregate(rows) if g[0] == "A1"][0]
        self.assertEqual(a1[4], 10.0)


class TestPivot(_TmpOut):
    def test_run(self):
        srcs = sd.pivot_sources()
        if not srcs:
            self.skipTest("缺少透视表样本")
        from core import pivot_core
        res = pivot_core.run(srcs, out_dir=self.out("piv"))
        self.assertTrue(os.path.isfile(res["out"]))
        self.assertGreater(res["groups"], 0)
        self.assertGreater(res["total"], 0)
        # 勾稽：分组数不应超过清洗行数
        self.assertLessEqual(res["groups"], res["clean_rows"])
        self.assertIn(res["level"], ("可信", "需复核", "存疑"))
        # 生成了可信度报告
        if res.get("report"):
            self.assertTrue(os.path.isfile(res["report"]))


class TestInvoice(_TmpOut):
    def test_scan_and_generate(self):
        folder = sd.invoice_folder()
        if not folder:
            self.skipTest("缺少发票样本")
        from core import invoice_core
        result = invoice_core.scan(folder)
        specials = [i for i in result.invoices if i.special]
        self.assertGreater(len(specials), 0, "应识别到至少一张专用发票")
        ym = invoice_core.detect_month(specials)
        rows = [i.as_row() for i in invoice_core.filter_month(specials, ym)]
        res = invoice_core.generate(result, rows, ym, out_dir=self.out("inv"))
        self.assertTrue(os.path.isfile(res["xlsx"]))
        self.assertTrue(os.path.isdir(res["review_dir"]))
        self.assertEqual(res["count"], len(rows))


if __name__ == "__main__":
    unittest.main()
