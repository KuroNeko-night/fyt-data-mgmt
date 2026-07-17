# -*- coding: utf-8 -*-
"""rename_core 批量重命名：计划计算 + 落盘/撤销往返测试。"""
import os
import shutil
import tempfile
import unittest

from core import rename_core as rc


class TestNewFilename(unittest.TestCase):
    def test_find_replace(self):
        r = rc.RenameRule(find="旧", replace="新")
        self.assertEqual(rc._new_filename("旧表.xlsx", r, 0), "新表.xlsx")

    def test_prefix_suffix(self):
        r = rc.RenameRule(prefix="A_", suffix="_B")
        self.assertEqual(rc._new_filename("x.txt", r, 0), "A_x_B.txt")

    def test_base_name_and_seq(self):
        r = rc.RenameRule(base_name="考勤表", seq_enabled=True,
                          seq_start=1, seq_digits=3, seq_sep="_")
        self.assertEqual(rc._new_filename("whatever.xlsx", r, 0), "考勤表_001.xlsx")
        self.assertEqual(rc._new_filename("whatever.xlsx", r, 4), "考勤表_005.xlsx")

    def test_ext_lower(self):
        r = rc.RenameRule(ext_lower=True)
        self.assertEqual(rc._new_filename("A.XLSX", r, 0), "A.xlsx")

    def test_regex(self):
        r = rc.RenameRule(find=r"\d+", replace="#", use_regex=True)
        self.assertEqual(rc._new_filename("a12b3.txt", r, 0), "a#b#.txt")


class TestNameInvalid(unittest.TestCase):
    def test_illegal_chars(self):
        self.assertTrue(rc._name_invalid("a/b.txt"))
        self.assertTrue(rc._name_invalid("a:b.txt"))

    def test_trailing_dot_space(self):
        self.assertTrue(rc._name_invalid("a .txt "))
        self.assertTrue(rc._name_invalid("name."))

    def test_reserved(self):
        self.assertTrue(rc._name_invalid("CON.txt"))
        self.assertTrue(rc._name_invalid("nul"))

    def test_valid(self):
        self.assertFalse(rc._name_invalid("normal_name.xlsx"))


class TestBuildPlan(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="fyt_rename_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _touch(self, name):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        return p

    def test_ok_and_same(self):
        p1 = self._touch("a.txt")
        r = rc.RenameRule(prefix="X_")
        items = rc.build_plan([p1], r)
        self.assertEqual(items[0].status, "ok")
        self.assertEqual(items[0].new_name, "X_a.txt")

    def test_same_status(self):
        p1 = self._touch("a.txt")
        items = rc.build_plan([p1], rc.RenameRule(find="zzz", replace="q"))
        self.assertEqual(items[0].status, "same")

    def test_dup_within_batch(self):
        p1 = self._touch("a.txt")
        p2 = self._touch("b.txt")
        r = rc.RenameRule(base_name="same")   # 两个都算成 same.txt
        items = rc.build_plan([p1, p2], r)
        self.assertTrue(all(it.status == "dup" for it in items))

    def test_exists_on_disk(self):
        p1 = self._touch("a.txt")
        self._touch("b.txt")                  # 目标已存在
        r = rc.RenameRule(find="a", replace="b")
        items = rc.build_plan([p1], r)
        self.assertEqual(items[0].status, "exists")

    def test_summarize(self):
        p1 = self._touch("a.txt")
        s = rc.summarize(rc.build_plan([p1], rc.RenameRule(prefix="X_")))
        self.assertEqual(s["ok"], 1)
        self.assertEqual(s["total"], 1)
        self.assertEqual(s["blocked"], 0)


class TestApplyUndo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="fyt_rename2_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _touch(self, name):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        return p

    def test_apply_then_undo(self):
        p1 = self._touch("a.txt")
        p2 = self._touch("b.txt")
        items = rc.build_plan([p1, p2], rc.RenameRule(prefix="N_"))
        n, failed, undo_map = rc.apply_plan(items)
        self.assertEqual(n, 2)
        self.assertEqual(failed, [])
        self.assertTrue(os.path.exists(os.path.join(self.d, "N_a.txt")))
        self.assertFalse(os.path.exists(p1))
        # 撤销还原
        ok, ufailed = rc.undo(undo_map)
        self.assertEqual(ok, 2)
        self.assertTrue(os.path.exists(p1))
        self.assertFalse(os.path.exists(os.path.join(self.d, "N_a.txt")))

    def test_swap_names(self):
        # A->B, B->A 交换：两段式改名应无冲突
        p1 = self._touch("A.txt")
        p2 = self._touch("B.txt")
        r = rc.RenameRule(find="A", replace="TMP")  # 不用，构造手动 items
        items = [rc.PlanItem(p1, "B.txt", "ok"), rc.PlanItem(p2, "A.txt", "ok")]
        n, failed, undo_map = rc.apply_plan(items)
        self.assertEqual(n, 2)
        with open(os.path.join(self.d, "B.txt"), encoding="utf-8") as f:
            pass  # 存在即可
        self.assertTrue(os.path.exists(os.path.join(self.d, "A.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.d, "B.txt")))


if __name__ == "__main__":
    unittest.main()
