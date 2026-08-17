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
    """为真实样本集成测试提供隔离输出和主数据库目录。"""

    def setUp(self):
        """创建临时输出根并覆盖主数据库路径。"""

        self._tmp = tempfile.mkdtemp(prefix="fyt_it_")
        self._old_catalog = os.environ.get("FYT_CATALOG_PATH")
        os.environ["FYT_CATALOG_PATH"] = os.path.join(self._tmp, "catalog.json")  # 主数据库隔离

    def tearDown(self):
        """恢复环境并删除业务输出。"""

        if self._old_catalog is None:
            os.environ.pop("FYT_CATALOG_PATH", None)
        else:
            os.environ["FYT_CATALOG_PATH"] = self._old_catalog
        shutil.rmtree(self._tmp, ignore_errors=True)

    def out(self, name):
        """返回按业务名称划分的临时输出目录。"""

        d = os.path.join(self._tmp, name)
        os.makedirs(d, exist_ok=True)
        return d


class TestAttendance(_TmpOut):
    """在样本存在时验证考勤填报完整链路。"""

    def test_run(self):
        """真实考勤样本应生成文件，且填充数量不超过成功匹配的人日。"""

        tgt, src = sd.attendance_target(), sd.attendance_source()
        if not (tgt and src):
            self.skipTest("缺少考勤填报样本")  # 样本缺失跳过
        from core import attendance_core
        res = attendance_core.run([tgt], [src], out_dir=self.out("att"))
        self.assertTrue(res["out_files"])  # 输出文件列表非空
        self.assertTrue(os.path.isfile(res["out_files"][0]))  # 输出文件落盘
        # 每个待填表返回 (文件, 表名/结果, stats)
        stats = res["results"][0][2]
        self.assertGreater(stats["matched"], 0)  # 有匹配人员
        # 填了的时间行数不应超过匹配到的人天数
        self.assertLessEqual(stats["filled_time"], stats["matched"])  # 填充不超匹配


class TestReconcile(_TmpOut):
    """在样本存在时验证工时对账完整链路。"""

    def test_run(self):
        """真实工时对账应同时生成填充表、汇总表和可信度结果。"""

        tgt = sd.reconcile_target()
        src = sd.reconcile_sources()
        labor = sd.reconcile_labor()
        if not (tgt and src and labor):
            self.skipTest("缺少工时对账样本")
        from core import reconcile_core
        res = reconcile_core.run(tgt, src, labor, out_dir=self.out("rec"))
        self.assertTrue(os.path.isfile(res["filled_path"]))  # 填充表落盘
        self.assertTrue(os.path.isfile(res["summary_path"]))  # 汇总表落盘
        self.assertIn("credibility", res)  # 可信度结果存在


class TestPurchase(_TmpOut):
    """在样本存在时验证采购数量对账完整链路。"""

    def test_run(self):
        """真实采购对账应生成双方副本、报告和长度一致的匹配标记。"""

        f1, f2 = sd.purchase_ours(), sd.purchase_supplier()
        if not (f1 and f2):
            self.skipTest("缺少采购数对账样本")
        from core import purchase_core
        res = purchase_core.run(f1, f2, out_dir=self.out("pur"))
        self.assertTrue(os.path.isfile(res["report"]))  # 报告落盘
        self.assertTrue(os.path.isfile(res["out1"]))  # 我方副本
        self.assertTrue(os.path.isfile(res["out2"]))  # 供方副本
        self.assertGreater(len(res["pairs"]), 0)  # 存在匹配对
        # matched 列表长度应与各自行数一致
        self.assertEqual(len(res["matched1"]), len(res["rows1"]))
        self.assertEqual(len(res["matched2"]), len(res["rows2"]))


class TestDelivery(_TmpOut):
    """在样本存在时验证送货计划制作与供应商补全。"""

    def test_run(self):
        """真实 BOM 与供应商资料应正确辨识角色并生成 SUB 送货计划。"""

        bom, sup = sd.delivery_bom(), sd.delivery_supplier()
        if not (bom and sup):
            self.skipTest("缺少送货计划样本")
        from core import delivery_core
        res = delivery_core.run(bom, sup, out_dir=self.out("deliv"),
                                order_type="SUB")
        self.assertTrue(os.path.isfile(res["plan_path"]))  # 送货计划落盘
        self.assertGreater(res["rows"], 0)  # 有明细行
        self.assertEqual(res["order_type"], "SUB")  # 订单类型透传
        # 顺序任意也应正确辨识主表/供应商来源（不抛异常即通过辨识）
        self.assertTrue(res["master_file"])  # 主表来源辨识
        self.assertTrue(res["supplier_file"])  # 供应商来源辨识
        self.assertTrue(res.get("supplier_used"))  # 供应商补全生效

    def test_run_without_supplier(self):
        """供应商明细可选：只给物料清单也应正常生成，供应商列留空不报未匹配。"""
        bom = sd.delivery_bom()
        if not bom:
            self.skipTest("缺少送货计划样本")
        from core import delivery_core
        res = delivery_core.run(bom, out_dir=self.out("deliv_nosup"),
                                order_type="KD")
        self.assertTrue(os.path.isfile(res["plan_path"]))  # 无供应商也生成
        self.assertGreater(res["rows"], 0)
        self.assertEqual(res["order_type"], "KD")  # 订单类型透传
        # 若样本 bom 自带供应商列会 supplier_used=True；否则应留空且不计未匹配
        if not res["supplier_used"]:
            self.assertEqual(res["missing"], [])  # 无未匹配
            self.assertEqual(res["supplier_file"], "")


class TestArrival(_TmpOut):
    """在样本存在时验证每日到料提取与输出。"""

    def test_run(self):
        """全部真实到料样本应逐批进入同一输出报告。"""

        plans = sd.arrival_plans()
        if not plans:
            self.skipTest("缺少到料明细样本")
        from core import arrival_core
        rows = [{"path": p, "batch_no": "", "total": 566,
                 "remark": "", "include": True} for p in plans]
        res = arrival_core.run(rows, top_label="截止16点的数据",
                               out_dir=self.out("arr"))
        self.assertTrue(os.path.isfile(res["out_file"]))  # 输出落盘
        self.assertEqual(len(res["results"]), len(plans))  # 逐批返回结果

    def test_detect_batch(self):
        plans = sd.arrival_plans()
        if not plans:
            self.skipTest("缺少到料明细样本")
        from core import arrival_core
        # 批次识别应返回字符串（识别不到为空串，不应抛异常）
        self.assertIsInstance(arrival_core.detect_batch(plans[0]), str)  # 识别返回字符串


class TestPivotMeasureText(unittest.TestCase):
    """度量列(最终采购数量)混入文本时,透视缓存不得把整列判为字符串。
    否则 Excel 刷新透视后该字段求和归零,与静态总计背离。"""

    def test_stray_text_in_measure_stays_numeric(self):
        """度量列混入说明文本时，缓存仍应保持数值口径并忽略该文本。"""

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
        self.assertEqual(a1[4], 10.0)  # 聚合结果与缓存口径一致


class TestPivot(_TmpOut):
    """在样本存在时验证销售表制作完整链路。"""

    def test_run(self):
        """真实销售表样本应生成结果、可信度和不超过清洗行数的分组。"""

        srcs = sd.pivot_sources()
        if not srcs:
            self.skipTest("缺少透视表样本")
        from core import pivot_core
        res = pivot_core.run(srcs, out_dir=self.out("piv"))
        self.assertTrue(os.path.isfile(res["out"]))  # 结果落盘
        self.assertGreater(res["groups"], 0)  # 有分组
        self.assertGreater(res["total"], 0)  # 有总量
        # 勾稽：分组数不应超过清洗行数
        self.assertLessEqual(res["groups"], res["clean_rows"])  # 分组不超行数
        self.assertIn(res["level"], ("可信", "需复核", "存疑"))  # 可信度等级合法
        # 生成了可信度报告
        if res.get("report"):
            self.assertTrue(os.path.isfile(res["report"]))


class TestInvoice(_TmpOut):
    """在样本存在时验证发票扫描与报表生成。"""

    def test_scan_and_generate(self):
        """真实发票目录应完成扫描、月份筛选、台账生成和复核目录输出。"""

        folder = sd.invoice_folder()
        if not folder:
            self.skipTest("缺少发票样本")
        from core import invoice_core
        result = invoice_core.scan(folder)
        specials = [i for i in result.invoices if i.special]
        self.assertGreater(len(specials), 0, "应识别到至少一张专用发票")  # 至少一张专票
        ym = invoice_core.detect_month(specials)
        rows = [i.as_row() for i in invoice_core.filter_month(specials, ym)]
        res = invoice_core.generate(result, rows, ym, out_dir=self.out("inv"))
        self.assertTrue(os.path.isfile(res["xlsx"]))  # 台账落盘
        self.assertTrue(os.path.isdir(res["review_dir"]))  # 复核目录存在
        self.assertEqual(res["count"], len(rows))  # 行数一致


if __name__ == "__main__":
    unittest.main()
