# -*- coding: utf-8 -*-
"""批次跟踪：按批次号聚合任务历史与结果文件。"""
from __future__ import annotations

import os
import tempfile
import unittest

from core import batch_track_core, task_history


class BatchTrackCoreTests(unittest.TestCase):
    """验证批次跟踪把任务标题、状态和输出文件名共同纳入搜索。"""

    def setUp(self):
        """创建跨两个成功业务和一个失败业务的合成任务历史。"""

        self.temp = tempfile.TemporaryDirectory(prefix="fyt_batch_track_")
        self.db_path = os.path.join(self.temp.name, "tasks.db")
        self.out_dir = os.path.join(self.temp.name, "输出")
        os.makedirs(self.out_dir, exist_ok=True)
        with open(os.path.join(self.out_dir, "26036-02.xlsx"), "w", encoding="utf-8") as handle:
            handle.write("")
        with open(os.path.join(self.out_dir, "26163A.xlsx"), "w", encoding="utf-8") as handle:
            handle.write("")
        # 构造任务历史：同批次跨多个环节
        task_id = task_history.start_task("delivery", "送货计划", db_path=self.db_path)
        task_history.finish_task(task_id, "ok", "处理完成", self.out_dir, db_path=self.db_path)
        task_id = task_history.start_task("purchase_plan", "采购计划导入", db_path=self.db_path)
        task_history.finish_task(task_id, "ok", "处理完成", self.out_dir, db_path=self.db_path)
        task_id = task_history.start_task("attendance", "考勤数据填报", db_path=self.db_path)
        task_history.finish_task(task_id, "failed", "处理失败", "", db_path=self.db_path)

    def tearDown(self):
        """删除任务数据库和结果文件。"""

        self.temp.cleanup()

    def test_search_by_batch_number(self):
        """批次号应命中多个业务任务及对应结果文件。"""

        result = batch_track_core.search("26036", db_path=self.db_path)
        features = [item["feature"] for item in result["items"]]
        self.assertEqual(sorted(features), ["delivery", "purchase_plan"])
        # 输出目录里的文件名命中也应命中（含 26036-02.xlsx）
        self.assertTrue(any("26036-02.xlsx" in item["files"] for item in result["items"]))

    def test_search_excludes_other_batches_and_unrelated(self):
        """搜索结果只保留命中批次或标题的任务，并保留失败状态。"""

        # 同一输出目录含 26163A.xlsx，两个任务都会命中
        result = batch_track_core.search("26163A", db_path=self.db_path)
        self.assertEqual(sorted(item["feature"] for item in result["items"]), ["delivery", "purchase_plan"])
        self.assertTrue(any("26163A.xlsx" in item["files"] for item in result["items"]))
        result = batch_track_core.search("考勤", db_path=self.db_path)
        self.assertEqual([item["feature"] for item in result["items"]], ["attendance"])
        self.assertEqual(result["items"][0]["status"], "failed")

    def test_empty_keyword_returns_nothing(self):
        """空白查询不应返回全部任务历史。"""

        result = batch_track_core.search("  ", db_path=self.db_path)
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
