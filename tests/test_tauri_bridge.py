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
        self.assertTrue(health["ok"])  # 健康检查必须成功
        self.assertIn("version", health["data"])  # 返回包须含版本
        result = tauri_bridge.dispatch({
            "action": "currency.convert", "payload": {"amount": "123.45"}})
        self.assertTrue(result["data"]["success"])  # 金额转换必须成功
        self.assertEqual(result["data"]["text"], "壹佰贰拾叁元肆角伍分")  # 中文大写金额

    def test_unknown_action_is_rejected(self):
        """未登记动作必须在进入系统命令层前拒绝，防止任意命令执行。"""

        with self.assertRaisesRegex(ValueError, "不支持"):
            tauri_bridge.dispatch({"action": "os.shell", "payload": {}})  # 未登记动作必须抛错

    def test_settings_only_allows_whitelist(self):
        """设置更新只能修改公开键，陌生键不能被写入配置。"""

        with self.assertRaisesRegex(ValueError, "不允许修改"):
            tauri_bridge.dispatch({
                "action": "settings.update",
                "payload": {"values": {"dangerous_key": True}},  # 白名单外键必须拒绝
            })

    def test_settings_update_roundtrip(self):
        """允许的主题与减少动画设置应持久化并在响应中回读。"""

        temp_dir = tempfile.TemporaryDirectory(prefix="fyt_tauri_settings_")
        old_path = os.environ.get("FYT_CONFIG_PATH")
        old_instance = settings_mod._instance
        try:
            os.environ["FYT_CONFIG_PATH"] = os.path.join(temp_dir.name, "配置.json")  # 隔离配置路径
            settings_mod._instance = None  # 强制重建配置实例
            response = tauri_bridge.dispatch({
                "action": "settings.update",
                "payload": {"values": {"theme_mode": "dark", "reduce_motion": True}},
            })
            self.assertEqual(response["data"]["theme_mode"], "dark")  # 写后回读主题
            self.assertTrue(response["data"]["reduce_motion"])  # 写后回读动画开关
        finally:
            settings_mod._instance = old_instance
            if old_path is None:
                os.environ.pop("FYT_CONFIG_PATH", None)
            else:
                os.environ["FYT_CONFIG_PATH"] = old_path
            temp_dir.cleanup()  # 清理临时配置目录

    def test_library_summary_uses_json_object_storage(self):
        """资料库存储统计必须是具名对象，避免前端依赖位置数组。"""

        with mock.patch.object(tauri_bridge.library, "counts", return_value={"unknown": 2}), \
                mock.patch.object(tauri_bridge.library, "storage_stats", return_value=(2, 4096)), \
                mock.patch.object(tauri_bridge.library, "list_items", return_value=[]), \
                mock.patch.object(tauri_bridge.paths, "library_dir", return_value="C:\\数据库"):
            response = tauri_bridge.dispatch({"action": "library.summary"})["data"]
        self.assertEqual(response["storage"], {"files": 2, "bytes": 4096})  # 统计必须是对象
        self.assertEqual(response["library_dir"], "C:\\数据库")  # 目录键名稳定

    def test_task_streams_log_and_progress_events(self):
        """长任务既汇总日志，也要在 stderr 输出带 request_id 的实时事件。"""

        temp_dir = tempfile.TemporaryDirectory(prefix="fyt_tauri_events_")
        old_values = {key: os.environ.get(key) for key in (
            "FYT_TASK_HISTORY_PATH", "FYT_BRIDGE_EVENTS", "FYT_REQUEST_ID")}
        try:
            os.environ["FYT_TASK_HISTORY_PATH"] = os.path.join(temp_dir.name, "tasks.db")  # 隔离任务历史
            os.environ["FYT_BRIDGE_EVENTS"] = "1"  # 开启桥接事件流
            os.environ["FYT_REQUEST_ID"] = "request-event"  # 固定请求号
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
                      if line.startswith("__FYT_EVENT__")]  # 解析 stderr 事件行
            self.assertEqual(result["logs"], ["正在处理"])  # 日志汇总必须保留
            self.assertTrue(any(event["kind"] == "log" for event in events))  # 事件流须含日志
            self.assertTrue(any(event["kind"] == "progress" and event["value"] == 42
                                for event in events))  # 进度事件须带值
            self.assertTrue(all(event["request_id"] == "request-event" for event in events))  # 事件须带请求号
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            temp_dir.cleanup()  # 恢复环境并清理临时目录


if __name__ == "__main__":
    unittest.main()
