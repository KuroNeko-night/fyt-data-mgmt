# -*- coding: utf-8 -*-
"""paths 输出目录解析测试（用临时目录，不污染用户文档）。"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

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

    def test_web_output_root_overrides_global_settings(self):
        """Web 子进程必须写入任务隔离目录，不能落到共享文档目录。"""
        with mock.patch.dict(os.environ, {"FYT_WEB_OUTPUT_ROOT": self.d}):
            out = paths.resolve_output_dir(
                "delivery", mode="custom", custom_root="C:\\shared", ts="web-job")
        self.assertTrue(out.startswith(os.path.join(self.d, "送货计划")))

    def test_feature_dirs_cover_all_features(self):
        for key in ("attendance", "reconcile", "arrival", "pivot",
                    "purchase", "delivery", "invoice", "excel_tools", "pdf_tools"):
            self.assertIn(key, paths.FEATURE_DIRS)

    def test_timestamp_format(self):
        ts = paths.timestamp()
        self.assertRegex(ts, r"^\d{8}_\d{4}$")

    def test_same_timestamp_does_not_overwrite(self):
        """同一分钟(同一时间戳)多次生成,应得到互不相同的目录,不再互相覆盖。"""
        ts = "20260101_1030"
        dirs = [paths.resolve_output_dir("delivery", mode="custom",
                                         custom_root=self.d, ts=ts)
                for _ in range(3)]
        # 三次调用得到三个不同、且都真实存在的目录
        self.assertEqual(len(set(dirs)), 3)
        for d in dirs:
            self.assertTrue(os.path.isdir(d))
        # 第一个是原始时间戳,后两个带 _2 / _3 后缀
        self.assertEqual(os.path.basename(dirs[0]), ts)
        self.assertEqual(os.path.basename(dirs[1]), ts + "_2")
        self.assertEqual(os.path.basename(dirs[2]), ts + "_3")

    def test_unique_dir_helper(self):
        base = os.path.join(self.d, "x")
        self.assertEqual(paths._unique_dir(base), base)   # 不存在则原样
        os.makedirs(base)
        self.assertEqual(paths._unique_dir(base), base + "_2")


class TestCrashLogRotation(unittest.TestCase):
    """崩溃日志体积轮转:超限转 .old 只留一份,长期使用有界。"""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="fyt_crashlog_")
        self.log = os.path.join(self.d, "错误日志.txt")
        # 把 crash_log_path 临时指到临时目录,避免污染用户文档
        self._orig = paths.crash_log_path
        paths.crash_log_path = lambda: self.log
        self._orig_max = paths._CRASH_LOG_MAX
        paths._CRASH_LOG_MAX = 1024          # 调小上限便于测试

    def tearDown(self):
        paths.crash_log_path = self._orig
        paths._CRASH_LOG_MAX = self._orig_max
        shutil.rmtree(self.d, ignore_errors=True)

    def test_append_writes_with_stamp(self):
        paths.append_crash_log("boom traceback")
        with open(self.log, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("boom traceback", content)
        self.assertIn("=====", content)     # 带时间戳头

    def test_rotation_caps_size(self):
        # 反复写超过上限,应触发轮转:主文件重开、旧内容进 .old
        for i in range(50):
            paths.append_crash_log("X" * 200 + (" line%d" % i))
        self.assertTrue(os.path.isfile(self.log + ".old"))
        # 主文件在最近一次轮转后重开,远小于"累计总量"
        self.assertLess(os.path.getsize(self.log), paths._CRASH_LOG_MAX + 4096)
        # 最新一条一定在主文件里(轮转不丢当前写入)
        with open(self.log, encoding="utf-8") as f:
            self.assertIn("line49", f.read())

    def test_only_one_old_kept(self):
        # 多次轮转只保留一份 .old(不无限堆历史)
        for i in range(120):
            paths.append_crash_log("Y" * 200)
        olds = [n for n in os.listdir(self.d) if n.endswith(".old")]
        self.assertEqual(len(olds), 1)

    def test_never_raises(self):
        # 写日志本身绝不抛异常(目录不存在等也吞掉)
        paths.crash_log_path = lambda: os.path.join(self.d, "no", "such", "dir", "e.txt")
        try:
            paths.append_crash_log("whatever")
        except Exception:
            self.fail("append_crash_log 不应抛异常")


if __name__ == "__main__":
    unittest.main()
