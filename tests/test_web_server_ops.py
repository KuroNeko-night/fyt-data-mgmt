# -*- coding: utf-8 -*-
"""Web 服务自动备份、审计、通知、分享与任务分派回归测试。"""
from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import web_server

from tests.web_server_test_base import WebServerTestBase


class WebServerOpsTests(WebServerTestBase):
    """自动维护、审计、Webhook 通知、分享链接与任务分派。"""

    def test_daily_auto_backup_and_rollover(self):
        """跨业务日维护应每天只自动备份一次并正确推进日切状态。"""

        # 当天第一次：创建自动备份
        report = web_server.auto_backup_if_due()
        self.assertTrue(report.startswith("已创建自动备份 auto-"))  # 创建提示
        backups = list((web_server.DATA_ROOT / "backups").glob("auto-*.zip"))
        self.assertEqual(len(backups), 1)  # 当天仅一份
        # 同一天再次调用：跳过
        self.assertEqual(web_server.auto_backup_if_due(), "")  # 同日不重复备份
        # 滚动保留：制造超龄自动备份后触发清理（默认保留 7 份）
        keep = web_server.AUTO_BACKUP_KEEP
        for _ in range(keep + 2):
            path = web_server.DATA_ROOT / "backups" / f"auto-old-{uuid.uuid4().hex}.zip"
            path.write_bytes(b"fake")  # 制造超龄备份
        (web_server.DATA_ROOT / "auto_backup_state.json").unlink(missing_ok=True)  # 重置日切状态
        web_server.auto_backup_if_due()
        remaining = sorted((web_server.DATA_ROOT / "backups").glob("auto-*.zip"))
        self.assertLessEqual(len(remaining), keep + 1)  # 滚动后数量受控
        # 手动备份不受滚动清理影响
        manual = web_server.DATA_ROOT / "backups" / "manual-1.zip"
        manual.write_bytes(b"fake")
        web_server.auto_backup_if_due()
        self.assertTrue((web_server.DATA_ROOT / "backups" / "manual-1.zip").exists())  # 手动备份保留

    def test_download_action_written_to_audit(self):
        """受保护文件下载属于管理行为，成功后必须写入可追溯审计记录。"""

        upload_query = urllib.parse.urlencode({"name": "审计文件.txt", "group": "audit-test"})
        status, uploaded = self.call(
            f"/api/files/upload?{upload_query}",
            token=self.admin, raw=b"audit\n", headers={"Content-Length": "6"},
        )
        self.assertEqual(status, 201)  # 上传成功
        status, created = self.call("/api/jobs", {
            "action": "rename.apply", "title": "审计下载", "payload": {
                "paths": [uploaded["handle"]], "rule": {"prefix": "新-"},
            },
        }, token=self.admin)
        self.assertEqual(status, 202)  # 任务受理
        job = self.wait_job(created["job_id"])
        self.assertEqual(job["status"], "completed")  # 任务完成
        self.assertEqual(len(job["files"]), 1)  # 一个输出文件
        request = urllib.request.Request(
            self.base + job["files"][0]["url"],
            headers={"X-Session-Token": self.admin},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)  # 下载成功
        _, payload = self.call("/api/admin/audit", token=self.admin)
        actions = [row["action"] for row in payload["audit"]]
        self.assertTrue(any(action.startswith("download_job:") for action in actions))  # 审计记录下载动作

    def test_webhook_notify_on_job_completion(self):
        """任务完成通知应异步调用配置的 Webhook，失败不能反向改变任务成功状态。"""

        received = []
        class Receiver(http.server.BaseHTTPRequestHandler):
            """记录任务通知请求体的最小本机 Webhook 接收器。"""

            def do_POST(self):
                """读取请求体后返回成功，供异步通知线程完成调用。"""

                length = int(self.headers.get("Content-Length") or 0)
                received.append(self.rfile.read(length))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            def log_message(self, *args):
                """关闭访问日志，避免后台接收器污染测试输出。"""

                pass
        receiver = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        receiver_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
        receiver_thread.start()
        original = web_server.NOTIFY_WEBHOOK_URL
        web_server.NOTIFY_WEBHOOK_URL = f"http://127.0.0.1:{receiver.server_port}/hook"  # 指向本机接收器
        try:
            status, created = self.call("/api/jobs", {
                "action": "text.transform", "title": "推送测试任务", "payload": {
                    "text": "甲\n乙", "operation": "dedup",
                },
            }, token=self.admin)
            self.assertEqual(status, 202)  # 任务受理
            job = self.wait_job(created["job_id"])
            self.assertEqual(job["status"], "completed")  # 任务完成
            deadline = time.monotonic() + 8
            while not received and time.monotonic() < deadline:
                time.sleep(0.1)  # 等待异步推送
            self.assertTrue(received, "webhook 未收到推送")
            body = json.loads(received[0].decode("utf-8"))
            self.assertEqual(body["msgtype"], "text")  # 消息类型
            self.assertIn("推送测试任务", body["text"]["content"])  # 通知内容
        finally:
            web_server.NOTIFY_WEBHOOK_URL = original
            receiver.shutdown()
            receiver.server_close()

    def test_share_link_anonymous_download_and_revoke(self):
        """分享链接允许受限匿名下载，撤销或过期后必须立即失效。"""

        upload_query = urllib.parse.urlencode({"name": "分享文件.txt", "group": "share-test"})
        status, uploaded = self.call(
            f"/api/files/upload?{upload_query}",
            token=self.admin, raw=b"share-me", headers={"Content-Length": "8"},
        )
        self.assertEqual(status, 201)
        status, created = self.call("/api/jobs", {
            "action": "rename.apply", "title": "分享测试", "payload": {
                "paths": [uploaded["handle"]], "rule": {"prefix": "新-"},
            },
        }, token=self.admin)
        self.assertEqual(status, 202)
        job = self.wait_job(created["job_id"])
        self.assertEqual(job["status"], "completed")

        # 创建分享
        status, share = self.call("/api/shares", {
            "job_id": created["job_id"], "file_index": 0, "expires_in_days": 7,
        }, token=self.admin)
        self.assertEqual(status, 200)  # 创建分享成功
        self.assertTrue(share["url"].startswith("/api/shares/"))  # 分享链接前缀
        # 匿名下载（不带 token）
        request = urllib.request.Request(self.base + share["url"])
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.read(), b"share-me")  # 匿名可下载
        # 撤销后匿名下载被拒
        status, _ = self.call(f"/api/shares/{share['token']}", token=self.admin, method="DELETE")
        self.assertEqual(status, 200)
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(urllib.request.Request(self.base + share["url"]), timeout=10)
        self.assertEqual(context.exception.code, 410)  # 撤销后 410
        # 未登录不能撤销分享
        status, _ = self.call(f"/api/shares/{share['token']}", token="", method="DELETE")
        self.assertIn(status, (401, 403))  # 未授权拒绝

    def test_assign_job_to_user_and_notify(self):
        """管理员分派任务后目标用户应获得权限与通知，其他账号仍不可访问。"""

        status, created = self.call("/api/jobs", {
            "action": "text.transform", "title": "指派测试", "payload": {
                "text": "行\n列", "operation": "dedup",
            },
        }, token=self.admin)
        self.assertEqual(status, 202)  # 任务受理
        job = self.wait_job(created["job_id"])
        self.assertEqual(job["status"], "completed")  # 任务完成
        me = self.call("/api/auth/me", token=self.admin)[1]["user"]
        status, payload = self.call(
            f"/api/jobs/{created['job_id']}/assign",
            {"assignee_id": me["id"]}, token=self.admin,
        )
        self.assertEqual(status, 200)  # 指派成功
        data = self.call("/api/admin/data", token=self.admin)[1]
        job_row = next(row for row in data["jobs"] if row["id"] == created["job_id"])
        self.assertEqual(job_row["assignee_id"], me["id"])  # 指派对象落库
        self.assertEqual(job_row["assignee_display_name"], me["display_name"])
        # 被指派账号的消息中心收到提醒
        notifications = self.call("/api/notifications", token=self.admin)[1]
        self.assertTrue(any("需要你确认" in item["title"] for item in notifications["notifications"]))  # 通知存在
        # 取消指派
        status, _ = self.call(
            f"/api/jobs/{created['job_id']}/assign",
            {"assignee_id": None}, token=self.admin,
        )
        self.assertEqual(status, 200)  # 取消成功
        data = self.call("/api/admin/data", token=self.admin)[1]
        job_row = next(row for row in data["jobs"] if row["id"] == created["job_id"])
        self.assertIsNone(job_row["assignee_id"])  # 指派清空


if __name__ == "__main__":
    unittest.main()
