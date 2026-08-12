# -*- coding: utf-8 -*-
"""Tauri-Python JSON 桥接契约测试。"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from core import settings as settings_mod
from core import tauri_bridge


class TestTauriBridge(unittest.TestCase):
    """保护桥接动作白名单、设置白名单和标准错误流事件协议。"""

    def test_health_and_currency(self):
        """无文件基础动作应返回统一 ok/data 包装和当前版本。"""

        health = tauri_bridge.dispatch({"action": "system.health"})
        self.assertTrue(health["ok"])
        self.assertIn("version", health["data"])
        result = tauri_bridge.dispatch({
            "action": "currency.convert", "payload": {"amount": "123.45"}})
        self.assertTrue(result["data"]["success"])
        self.assertEqual(result["data"]["text"], "壹佰贰拾叁元肆角伍分")

    def test_unknown_action_is_rejected(self):
        """未登记动作必须在进入系统命令层前拒绝，防止任意命令执行。"""

        with self.assertRaisesRegex(ValueError, "不支持"):
            tauri_bridge.dispatch({"action": "os.shell", "payload": {}})

    def test_settings_only_allows_whitelist(self):
        """设置更新只能修改公开键，陌生键不能被写入配置。"""

        with self.assertRaisesRegex(ValueError, "不允许修改"):
            tauri_bridge.dispatch({
                "action": "settings.update",
                "payload": {"values": {"dangerous_key": True}},
            })

    def test_settings_update_roundtrip(self):
        """允许的主题与减少动画设置应持久化并在响应中回读。"""

        temp_dir = tempfile.TemporaryDirectory(prefix="fyt_tauri_settings_")
        old_path = os.environ.get("FYT_CONFIG_PATH")
        old_instance = settings_mod._instance
        try:
            os.environ["FYT_CONFIG_PATH"] = os.path.join(temp_dir.name, "配置.json")
            settings_mod._instance = None
            response = tauri_bridge.dispatch({
                "action": "settings.update",
                "payload": {"values": {"theme_mode": "dark", "reduce_motion": True}},
            })
            self.assertEqual(response["data"]["theme_mode"], "dark")
            self.assertTrue(response["data"]["reduce_motion"])
        finally:
            settings_mod._instance = old_instance
            if old_path is None:
                os.environ.pop("FYT_CONFIG_PATH", None)
            else:
                os.environ["FYT_CONFIG_PATH"] = old_path
            temp_dir.cleanup()

    def test_library_summary_uses_json_object_storage(self):
        """资料库存储统计必须是具名对象，避免前端依赖位置数组。"""

        with mock.patch.object(tauri_bridge.library, "counts", return_value={"unknown": 2}), \
                mock.patch.object(tauri_bridge.library, "storage_stats", return_value=(2, 4096)), \
                mock.patch.object(tauri_bridge.library, "list_items", return_value=[]), \
                mock.patch.object(tauri_bridge.paths, "library_dir", return_value="C:\\数据库"):
            response = tauri_bridge.dispatch({"action": "library.summary"})["data"]
        self.assertEqual(response["storage"], {"files": 2, "bytes": 4096})
        self.assertEqual(response["library_dir"], "C:\\数据库")

    def test_task_streams_log_and_progress_events(self):
        """长任务既汇总日志，也要在 stderr 输出带 request_id 的实时事件。"""

        temp_dir = tempfile.TemporaryDirectory(prefix="fyt_tauri_events_")
        old_values = {key: os.environ.get(key) for key in (
            "FYT_TASK_HISTORY_PATH", "FYT_BRIDGE_EVENTS", "FYT_REQUEST_ID")}
        try:
            os.environ["FYT_TASK_HISTORY_PATH"] = os.path.join(temp_dir.name, "tasks.db")
            os.environ["FYT_BRIDGE_EVENTS"] = "1"
            os.environ["FYT_REQUEST_ID"] = "request-event"
            stream = io.StringIO()

            def callback(log, progress):
                """模拟业务任务按标准回调报告一条日志和一次进度。"""

                log("正在处理")
                progress(42)
                return {"out_dir": temp_dir.name}

            with contextlib.redirect_stderr(stream):
                result = tauri_bridge._task("demo", "事件测试", callback)
            events = [json.loads(line[len("__FYT_EVENT__"):])
                      for line in stream.getvalue().splitlines()
                      if line.startswith("__FYT_EVENT__")]
            self.assertEqual(result["logs"], ["正在处理"])
            self.assertTrue(any(event["kind"] == "log" for event in events))
            self.assertTrue(any(event["kind"] == "progress" and event["value"] == 42
                                for event in events))
            self.assertTrue(all(event["request_id"] == "request-event" for event in events))
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
