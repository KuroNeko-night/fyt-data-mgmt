# -*- coding: utf-8 -*-
"""任务历史 SQLite 基础设施测试。"""
import os
import tempfile
import unittest

from core import task_history


class TestTaskHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fyt_tasks_")
        self.db = os.path.join(self.tmp.name, "tasks.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_lifecycle(self):
        task_id = task_history.start_task(
            "attendance", "考勤填报", {"files": 2}, db_path=self.db)
        self.assertTrue(task_id)
        self.assertEqual(task_history.summary(self.db)["running"], 1)
        self.assertTrue(task_history.finish_task(
            task_id, "ok", "处理完成", "C:\\output", db_path=self.db))
        rows = task_history.list_recent(db_path=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["output_dir"], "C:\\output")
        self.assertIsNotNone(rows[0]["duration_ms"])

    def test_interrupted_recovery_and_clear(self):
        task_history.start_task("pivot", "销售表透视", db_path=self.db)
        self.assertEqual(task_history.mark_interrupted(self.db), 1)
        rows = task_history.list_recent(db_path=self.db)
        self.assertEqual(rows[0]["status"], "interrupted")
        self.assertIn("未正常结束", rows[0]["message"])
        self.assertIsNotNone(rows[0]["duration_ms"])
        self.assertEqual(task_history.clear_finished(self.db), 1)
        self.assertEqual(task_history.summary(self.db)["total"], 0)

    def test_unknown_task_cannot_finish(self):
        self.assertFalse(task_history.finish_task(
            "missing", "failed", "不存在", db_path=self.db))

    def test_cancel_request_only_marks_matching_task(self):
        matching = task_history.start_task(
            "pivot", "透视任务", {"request_id": "request-a"}, db_path=self.db)
        other = task_history.start_task(
            "arrival", "到料任务", {"request_id": "request-b"}, db_path=self.db)
        self.assertEqual(task_history.cancel_request("request-a", self.db), 1)
        rows = {row["id"]: row for row in task_history.list_recent(db_path=self.db)}
        self.assertEqual(rows[matching]["status"], "cancelled")
        self.assertEqual(rows[matching]["message"], "用户已取消任务")
        self.assertEqual(rows[other]["status"], "running")


if __name__ == "__main__":
    unittest.main()
