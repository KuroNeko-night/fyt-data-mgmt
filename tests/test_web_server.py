"""局域网 Web 服务的认证、任务和文件权限回归测试。"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from openpyxl import Workbook

import web_server


class WebServerTests(unittest.TestCase):
    """使用临时 SQLite 与 HTTP 端口验证 Web 服务主链路。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = (web_server.DATA_ROOT, web_server.DB_PATH, web_server.STATIC_ROOT)
        web_server.DATA_ROOT = Path(self.temp.name)
        web_server.DB_PATH = web_server.DATA_ROOT / "accounts.sqlite3"
        web_server.STATIC_ROOT = web_server.DATA_ROOT / "dist"
        web_server.init_db()
        self.server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.admin = self.call("/api/auth/login", {"username": "admin", "password": "admin123456"})[1]["token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        web_server.DATA_ROOT, web_server.DB_PATH, web_server.STATIC_ROOT = self.original
        self.temp.cleanup()

    def call(self, path, payload=None, token="", raw=None, headers=None):
        data = raw if raw is not None else None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        request.add_header("Content-Type", "application/json" if raw is None else "application/octet-stream")
        if token:
            request.add_header("X-Session-Token", token)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read()
                return response.status, json.loads(body) if "json" in (response.headers.get("Content-Type") or "") else body
        except urllib.error.HTTPError as error:
            body = error.read()
            return error.code, json.loads(body)

    def wait_job(self, job_id):
        for _ in range(80):
            status, payload = self.call(f"/api/jobs/{job_id}", token=self.admin)
            self.assertEqual(status, 200)
            job = payload["job"]
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.05)
        self.fail("任务未在测试时间内结束")

    def test_requires_login(self):
        status, payload = self.call("/api/overview")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "请先登录")

    def test_text_task_and_upload_download(self):
        status, created = self.call("/api/jobs", {
            "action": "text.transform", "title": "测试文本", "payload": {
                "text": "乙\n甲\n乙", "operation": "dedup",
            },
        }, token=self.admin)
        self.assertEqual(status, 202)
        job = self.wait_job(created["job_id"])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["text"], "乙\n甲")

        upload_query = urllib.parse.urlencode({"name": "原文件.txt", "group": "test-group"})
        status, uploaded = self.call(
            f"/api/files/upload?{upload_query}",
            token=self.admin, raw=b"sample\n", headers={"Content-Length": "7"},
        )
        self.assertEqual(status, 201)
        status, created = self.call("/api/jobs", {
            "action": "rename.apply", "title": "测试重命名", "payload": {
                "paths": [uploaded["handle"]], "rule": {"prefix": "新-"},
            },
        }, token=self.admin)
        self.assertEqual(status, 202)
        job = self.wait_job(created["job_id"])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(job["files"]), 1)
        request = urllib.request.Request(self.base + job["files"][0]["url"], headers={"X-Session-Token": self.admin})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.read(), b"sample\n")

        status, board = self.call("/api/dashboard", token=self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(board["metrics"]["completed_jobs"], 2)
        self.assertEqual(len(board["trend"]), 7)
        self.assertIn("text", {item["key"] for item in board["feature_usage"]})
        self.assertGreaterEqual(len(board["recent_files"]), 1)

    def test_compare_review_continues_same_job(self):
        def book_bytes(rows):
            book = Workbook()
            sheet = book.active
            for row in rows:
                sheet.append(row)
            stream = __import__("io").BytesIO()
            book.save(stream)
            return stream.getvalue()

        handles = []
        for name, content in (("a.xlsx", [["编号", "数量"], ["A-1", 1]]),
                              ("b.xlsx", [["编号", "数量"], ["A-1", 2]])):
            query = urllib.parse.urlencode({"name": name, "group": "review-group"})
            status, uploaded = self.call(
                f"/api/files/upload?{query}", token=self.admin,
                raw=book_bytes(content), headers={"Content-Length": str(len(book_bytes(content)))},
            )
            self.assertEqual(status, 201)
            handles.append(uploaded["handle"])

        status, created = self.call("/api/jobs", {
            "action": "web.compare.review", "title": "表格比对复核", "payload": {
                "file1": [handles[0]], "file2": [handles[1]],
            },
        }, token=self.admin)
        self.assertEqual(status, 202)
        prepared = self.wait_job(created["job_id"])
        self.assertEqual(prepared["status"], "completed")
        self.assertTrue(prepared["review_pending"])
        self.assertIn("编号", prepared["result"]["common"])

        status, board = self.call("/api/dashboard", token=self.admin)
        self.assertEqual(status, 200)
        usage_keys = {item["key"] for item in board["feature_usage"]}
        self.assertIn("compare", usage_keys)
        self.assertNotIn("web", usage_keys)
        self.assertEqual(board["metrics"]["completed_jobs"], 0)
        self.assertEqual(board["metrics"]["running_jobs"], 1)
        self.assertEqual(board["status_breakdown"]["review"], 1)
        self.assertTrue(board["recent_jobs"][0]["review_pending"])

        status, resumed = self.call(f"/api/jobs/{created['job_id']}/review", {
            "choices": {"key": "编号"},
        }, token=self.admin)
        self.assertEqual(status, 202)
        self.assertEqual(resumed["job_id"], created["job_id"])
        completed = self.wait_job(created["job_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertFalse(completed["review_pending"])
        self.assertEqual(completed["result"]["result"]["counts"]["diffs"], 1)
        self.assertEqual(len(completed["files"]), 1)


if __name__ == "__main__":
    unittest.main()
