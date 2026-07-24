# -*- coding: utf-8 -*-
"""增量缓存索引与文件失效测试。"""
import json
import os
import tempfile
import unittest
from unittest import mock

from core import incremental_cache
from core import pivot_core
from core import settings as settings_mod


class TestIncrementalCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fyt_cache_")
        self.input_path = os.path.join(self.tmp.name, "输入.xlsx")
        self.store_path = os.path.join(self.tmp.name, "cache.json")
        self.output_path = os.path.join(self.tmp.name, "结果.xlsx")
        with open(self.input_path, "wb") as file_obj:
            file_obj.write(b"v1")
        with open(self.output_path, "wb") as file_obj:
            file_obj.write(b"result")

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_tracks_content_and_parameters(self):
        first = incremental_cache.make_key("pivot", [self.input_path], {"a": 1})
        second = incremental_cache.make_key("pivot", [self.input_path], {"a": 1})
        self.assertEqual(first, second)
        with open(self.input_path, "wb") as file_obj:
            file_obj.write(b"v2")
        changed = incremental_cache.make_key("pivot", [self.input_path], {"a": 1})
        self.assertNotEqual(first, changed)

    def test_put_get_and_missing_artifact_invalidation(self):
        key = incremental_cache.make_key("pivot", [self.input_path], {"a": 1})
        result = {"out": self.output_path, "groups": 2}
        self.assertTrue(incremental_cache.put(
            key, "pivot", result, [self.output_path], path=self.store_path))
        hit = incremental_cache.get(key, path=self.store_path)
        self.assertTrue(hit["cache_hit"])
        self.assertEqual(hit["groups"], 2)
        os.remove(self.output_path)
        self.assertIsNone(incremental_cache.get(key, path=self.store_path))
        self.assertEqual(incremental_cache.stats(self.store_path)["entries"], 0)

    def test_clear_keeps_artifacts(self):
        key = incremental_cache.make_key("pivot", [self.input_path])
        incremental_cache.put(key, "pivot", {"out": self.output_path},
                               [self.output_path], path=self.store_path)
        self.assertEqual(incremental_cache.clear(self.store_path), 1)
        self.assertTrue(os.path.exists(self.output_path))
        with open(self.store_path, "r", encoding="utf-8") as file_obj:
            self.assertEqual(json.load(file_obj)["entries"], [])

    def test_pivot_cache_snapshot_excludes_row_plan_and_tuple_keys(self):
        sentinel = "M-DO-NOT-CACHE"
        result = {
            "out": self.output_path,
            "groups": 1,
            "review": {
                "plan": {"sheets": [{"kept": [[1, sentinel, "材料", "S", 1, "个", 2]]}]},
                "choices": {"held": {(1, 2): True}},
                "held_kept_n": 1,
                "held_kept_total": 2,
                "held_total_n": 1,
                "unit_conflicts": [],
                "spec_merges": [],
            },
        }
        compact = pivot_core._cacheable_result(result)
        key = incremental_cache.make_key("pivot", [self.input_path])
        self.assertTrue(incremental_cache.put(
            key, "pivot", compact, [self.output_path], path=self.store_path))

        hit = incremental_cache.get(key, path=self.store_path)
        self.assertFalse(hit["review"]["details_cached"])
        self.assertNotIn("plan", hit["review"])
        self.assertNotIn("choices", hit["review"])
        with open(self.store_path, "r", encoding="utf-8") as file_obj:
            self.assertNotIn(sentinel, file_obj.read())

    def test_pivot_run_reuses_cached_result(self):
        old_path = os.environ.get("FYT_INCREMENTAL_CACHE_PATH")
        os.environ["FYT_INCREMENTAL_CACHE_PATH"] = self.store_path
        settings = settings_mod.get_settings()
        old_enabled = settings.get("enable_incremental_cache", True)
        settings._data["enable_incremental_cache"] = True
        out_dir = os.path.join(self.tmp.name, "out")
        os.makedirs(out_dir)
        logs = []

        def apply_plan(_plan, _choices, out_path, log=None):
            with open(out_path, "wb") as file_obj:
                file_obj.write(b"xlsx")
            report = os.path.join(out_dir, "可信度报告.txt")
            with open(report, "w", encoding="utf-8") as file_obj:
                file_obj.write("可信")
            return {"out": out_path, "report": report, "groups": 1,
                    "total": 2, "level": "可信", "score": 100}

        plan = {"sheets": [], "held_index": [], "unit_conflicts": [],
                "spec_merges": []}
        try:
            with mock.patch.object(pivot_core, "warn_if_uncached"), \
                    mock.patch.object(pivot_core, "analyze_workbooks", return_value=plan), \
                    mock.patch.object(pivot_core, "_default_choices", return_value={}), \
                    mock.patch.object(pivot_core, "apply_plan", side_effect=apply_plan) as apply_mock:
                first = pivot_core.run(self.input_path, out_dir=out_dir, log=logs.append)
                second = pivot_core.run(self.input_path, out_dir=out_dir, log=logs.append)
            self.assertFalse(first.get("cache_hit", False))
            self.assertTrue(second["cache_hit"])
            self.assertEqual(apply_mock.call_count, 1)
            self.assertTrue(any("已复用" in line for line in logs))
        finally:
            settings._data["enable_incremental_cache"] = old_enabled
            if old_path is None:
                os.environ.pop("FYT_INCREMENTAL_CACHE_PATH", None)
            else:
                os.environ["FYT_INCREMENTAL_CACHE_PATH"] = old_path


if __name__ == "__main__":
    unittest.main()
