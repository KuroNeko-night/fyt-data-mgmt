# -*- coding: utf-8 -*-
"""进度上报 Progress 与 RunPanel.set_progress 测试。"""
import os
import sys
import shutil
import tempfile
import unittest
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.common_core import Progress

warnings.filterwarnings("ignore", message="Workbook contains no default style")


class TestProgress(unittest.TestCase):
    def _rec(self):
        seen = []
        return seen, (lambda v: seen.append(v))

    def test_none_callback_is_noop(self):
        # progress=None:全程不报错、不产生任何调用
        p = Progress(None, stages=[("a", 50), ("b", 50)])
        p.stage("a"); p.tick(1, 2); p.stage("b"); p.done()   # 不应抛异常

    def test_stage_boundaries(self):
        seen, cb = self._rec()
        p = Progress(cb, stages=[("a", 50), ("b", 50)])
        p.stage("a")                     # 进入 a:0
        p.stage("b")                     # 进入 b:50
        p.done()                         # 100
        self.assertEqual(seen[0], 0)
        self.assertIn(50, seen)
        self.assertEqual(seen[-1], 100)

    def test_tick_interpolates_within_stage(self):
        seen, cb = self._rec()
        p = Progress(cb, stages=[("a", 40), ("b", 60)])
        p.stage("a")
        p.tick(1, 2)                     # a 区间 [0,40) 的一半 → 20
        p.tick(2, 2)                     # a 末尾 → 40
        self.assertIn(20, seen)
        self.assertIn(40, seen)

    def test_monotonic_never_decreases(self):
        # 只增不减:即便回调乱序,发出的值也应单调不降
        seen, cb = self._rec()
        p = Progress(cb, stages=[("a", 100)])
        p.stage("a")
        p.tick(5, 10)                    # 50
        p.tick(1, 10)                    # 想回退到 10 → 被丢弃
        p.tick(8, 10)                    # 80
        self.assertEqual(seen, sorted(seen))
        self.assertNotIn(10, seen)

    def test_weights_normalize(self):
        # 权重之和不必为 100,内部按比例归一
        seen, cb = self._rec()
        p = Progress(cb, stages=[("a", 1), ("b", 3)])   # a 占 25%,b 占 75%
        p.stage("a"); p.stage("b")
        self.assertIn(25, seen)          # 进入 b 时应报到 25%


class TestE2EProgress(unittest.TestCase):
    """端到端:各 core 的 run/scan/generate 真跑一次,断言进度 0→100 且单调。

    样本缺失的用例自动 skip;compare 用内建合成表,无需样本。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fyt_prog_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _cap(self):
        seq = []
        return seq, (lambda v: seq.append(v))

    def _assert_clean(self, seq):
        self.assertTrue(seq, "未收到任何进度")
        self.assertEqual(seq[0], 0, "起点非 0：%s" % seq)
        self.assertEqual(seq[-1], 100, "终点非 100：%s" % seq)
        self.assertEqual(seq, sorted(seq), "进度非单调：%s" % seq)

    def test_compare_progress(self):
        # compare 用合成两表,不依赖仓库样本
        import openpyxl
        from core import compare_core
        def mk(name, rows):
            p = os.path.join(self._tmp, name)
            wb = openpyxl.Workbook(); ws = wb.active
            for r in rows:
                ws.append(r)
            wb.save(p); wb.close()
            return p
        hdr = ["物料编码", "名称", "数量"]
        a = mk("a.xlsx", [hdr, ["M01", "纸箱", 10], ["M02", "螺丝", 5]])
        b = mk("b.xlsx", [hdr, ["M01", "纸箱", 10], ["M02", "螺丝", 6]])
        seq, cb = self._cap()
        compare_core.run(a, b, key="物料编码", out_dir=self._tmp,
                         log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)

    def test_purchase_progress(self):
        from tests import sample_data as sd
        f1, f2 = sd.purchase_ours(), sd.purchase_supplier()
        if not (f1 and f2):
            self.skipTest("缺少采购对账样本")
        from core import purchase_core
        seq, cb = self._cap()
        purchase_core.run(f1, f2, out_dir=self._tmp,
                          log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)

    def test_attendance_progress(self):
        from tests import sample_data as sd
        tgt, src = sd.attendance_target(), sd.attendance_source()
        if not (tgt and src):
            self.skipTest("缺少考勤填报样本")
        from core import attendance_core
        seq, cb = self._cap()
        attendance_core.run([tgt], [src], out_dir=self._tmp,
                            log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)

    def test_arrival_progress(self):
        from tests import sample_data as sd
        plans = sd.arrival_plans()
        if not plans:
            self.skipTest("缺少到料明细样本")
        from core import arrival_core
        rows = [{"path": p, "batch_no": "", "total": 566,
                 "remark": "", "include": True} for p in plans]
        seq, cb = self._cap()
        arrival_core.run(rows, top_label="截止16点的数据", out_dir=self._tmp,
                         log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)

    def test_invoice_scan_progress(self):
        from tests import sample_data as sd
        folder = sd.invoice_folder()
        if not folder:
            self.skipTest("缺少发票样本")
        from core import invoice_core
        seq, cb = self._cap()
        invoice_core.scan(folder, log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)

    def test_pivot_progress(self):
        from tests import sample_data as sd
        srcs = sd.pivot_sources()
        if not srcs:
            self.skipTest("缺少透视样本")
        from core import pivot_core
        seq, cb = self._cap()
        pivot_core.run(srcs, out_dir=self._tmp,
                       log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)

    def test_reconcile_progress(self):
        from tests import sample_data as sd
        tgt, src, lab = (sd.reconcile_target(), sd.reconcile_sources(),
                         sd.reconcile_labor())
        if not (tgt and src and lab):
            self.skipTest("缺少对账样本")
        from core import reconcile_core
        seq, cb = self._cap()
        reconcile_core.run(tgt, src, lab, out_dir=self._tmp,
                           log=lambda *a, **k: None, progress=cb)
        self._assert_clean(seq)


if __name__ == "__main__":
    unittest.main()
