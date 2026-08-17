# -*- coding: utf-8 -*-
"""任务历史 SQLite 基础设施测试。"""
import os
import tempfile
import unittest

from core import task_history


class TestTaskHistory(unittest.TestCase):
    """验证本机任务历史成功、取消、中断恢复和未知任务保护。"""

    def setUp(self):
        """创建隔离 SQLite 任务库。"""

        self.tmp = tempfile.TemporaryDirectory(prefix="fyt_tasks_")
        self.db = os.path.join(self.tmp.name, "tasks.db")

    def tearDown(self):
        """删除任务库和临时目录。"""

        self.tmp.cleanup()

    def test_success_lifecycle(self):
        """任务从开始到成功应保留输入、结果、日志、输出目录和持续时间。"""

        task_id = task_history.start_task(
            "attendance", "考勤填报", {"files": 2}, db_path=self.db)
        self.assertTrue(task_id)  # 新任务必须有 ID
        self.assertEqual(task_history.summary(self.db)["running"], 1)  # 运行中计数
        self.assertTrue(task_history.finish_task(
            task_id, "ok", "处理完成", "C:\\output", db_path=self.db))
        rows = task_history.list_recent(db_path=self.db)
        self.assertEqual(len(rows), 1)  # 只有一条记录
        self.assertEqual(rows[0]["status"], "ok")  # 状态落库
        self.assertEqual(rows[0]["output_dir"], "C:\\output")  # 输出目录保留
        self.assertIsNotNone(rows[0]["duration_ms"])  # 持续时间必须记录

    def test_interrupted_recovery_and_clear(self):
        task_history.start_task("pivot", "销售表透视", db_path=self.db)
        self.assertEqual(task_history.mark_interrupted(self.db), 1)  # 中断标记生效
        rows = task_history.list_recent(db_path=self.db)
        self.assertEqual(rows[0]["status"], "interrupted")
        self.assertIn("未正常结束", rows[0]["message"])  # 中断原因友好
        self.assertIsNotNone(rows[0]["duration_ms"])
        self.assertEqual(task_history.clear_finished(self.db), 1)  # 清理一条终态
        self.assertEqual(task_history.summary(self.db)["total"], 0)

    def test_unknown_task_cannot_finish(self):
        self.assertFalse(task_history.finish_task(
            "missing", "failed", "不存在", db_path=self.db))  # 未知任务不允许改状态

    def test_cancel_request_only_marks_matching_task(self):
        """按 request_id 取消只能影响对应运行任务，不得波及其他请求。"""

        matching = task_history.start_task(
            "pivot", "透视任务", {"request_id": "request-a"}, db_path=self.db)
        other = task_history.start_task(
            "arrival", "到料任务", {"request_id": "request-b"}, db_path=self.db)
        self.assertEqual(task_history.cancel_request("request-a", self.db), 1)  # 按请求号取消一条
        rows = {row["id"]: row for row in task_history.list_recent(db_path=self.db)}
        self.assertEqual(rows[matching]["status"], "cancelled")  # 匹配任务被取消
        self.assertEqual(rows[matching]["message"], "用户已取消任务")
        self.assertEqual(rows[other]["status"], "running")  # 其他请求不受影响


if __name__ == "__main__":
    unittest.main()
