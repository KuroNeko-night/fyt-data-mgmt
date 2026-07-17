# -*- coding: utf-8 -*-
"""paths 输出目录解析测试（用临时目录，不污染用户文档）。"""
import os
import shutil
import tempfile
import unittest

from core import paths


class TestResolveOutputDir(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="fyt_paths_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_custom_mode_uses_feature_cn(self):
        out = paths.resolve_output_dir("arrival", mode="custom",
                                       custom_root=self.d, ts="20260101_0000")
        self.assertTrue(os.path.isdir(out))
        # 归档到 中文功能名/时间戳
        self.assertEqual(os.path.basename(out), "20260101_0000")
        self.assertEqual(os.path.basename(os.path.dirname(out)), "到料明细")

    def test_beside_mode(self):
        src = os.path.join(self.d, "src", "x.xlsx")
        os.makedirs(os.path.dirname(src))
        out = paths.resolve_output_dir("pivot", mode="beside", src_path=src,
                                       ts="20260101_0000")
        self.assertTrue(os.path.isdir(out))
        # 源文件旁 output/时间戳
        self.assertIn("output", out)
        self.assertTrue(out.startswith(os.path.join(self.d, "src")))

    def test_unknown_feature_falls_back_to_key(self):
        out = paths.resolve_output_dir("zzz_unknown", mode="custom",
                                       custom_root=self.d, ts="t")
        self.assertEqual(os.path.basename(os.path.dirname(out)), "zzz_unknown")

    def test_feature_dirs_cover_all_features(self):
        for key in ("attendance", "reconcile", "arrival", "pivot",
                    "purchase", "delivery", "invoice", "excel_tools", "pdf_tools"):
            self.assertIn(key, paths.FEATURE_DIRS)

    def test_timestamp_format(self):
        ts = paths.timestamp()
        self.assertRegex(ts, r"^\d{8}_\d{4}$")


if __name__ == "__main__":
    unittest.main()
