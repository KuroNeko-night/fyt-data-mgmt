# -*- coding: utf-8 -*-
"""Web 服务回归测试的公共基类。

本模块不包含任何测试方法，只承载各拆分测试模块共用的临时数据根初始化、
HTTP 请求封装和任务轮询逻辑，避免每个模块重复维护同一套服务器生命周期。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import web_server


class WebServerTestBase(unittest.TestCase):
    """使用临时 SQLite 与 HTTP 端口验证 Web 服务主链路。"""

    def setUp(self):
        """为每个用例创建隔离数据根、首次管理员库和随机本机 HTTP 端口。"""

        self.temp = tempfile.TemporaryDirectory()
        self.original = (web_server.DATA_ROOT, web_server.DB_PATH, web_server.STATIC_ROOT)
        # 同时替换数据、数据库和静态目录，任何上传、输出或备份都只能落入临时目录。
        web_server.DATA_ROOT = Path(self.temp.name)  # 数据根隔离
        web_server.DB_PATH = web_server.DATA_ROOT / "accounts.sqlite3"  # 数据库隔离
        web_server.STATIC_ROOT = web_server.DATA_ROOT / "dist"  # 静态目录隔离
        os.environ["FYT_ADMIN_PASSWORD"] = "admin123456"  # 仅用于临时数据库
        web_server.init_db()
        # 端口 0 由系统分配空闲端口，避免并行或残留测试进程造成固定端口冲突。
        self.server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"  # 随机端口基地址
        self.admin = self.call("/api/auth/login", {"username": "admin", "password": "admin123456"})[1]["token"]  # 管理员登录令牌

    def tearDown(self):
        """停止测试服务器、恢复模块级路径并删除全部临时运行数据。"""

        os.environ.pop("FYT_ADMIN_PASSWORD", None)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        web_server.DATA_ROOT, web_server.DB_PATH, web_server.STATIC_ROOT = self.original  # 恢复模块路径
        self.temp.cleanup()

    def _encode_payload(self, raw, payload):
        """raw 用于文件上传等二进制请求；payload 按服务端默认 UTF-8 JSON 编码。"""
        if raw is not None:
            return raw
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=False).encode()

    def _decode_response(self, response):
        """把正常响应按 Content-Type 解析为 JSON 或原始字节。"""
        body = response.read()
        if "json" in (response.headers.get("Content-Type") or ""):
            return json.loads(body)
        return body

    def _decode_error(self, error):
        """权限拒绝和参数错误是待断言的正常测试结果，统一解析错误正文。"""
        return error.code, json.loads(error.read())

    def call(self, path, payload=None, token="", raw=None, headers=None, method=None):
        """发送测试 API 请求，并把正常及 HTTP 错误响应统一解析为状态码和正文。"""

        data = self._encode_payload(raw, payload)
        request = urllib.request.Request(self.base + path, data=data, method=method or ("POST" if data is not None else "GET"))
        request.add_header("Content-Type", "application/json" if raw is None else "application/octet-stream")
        if token:
            request.add_header("X-Session-Token", token)  # 会话令牌请求头
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, self._decode_response(response)
        except urllib.error.HTTPError as error:
            return self._decode_error(error)

    def wait_job(self, job_id):
        """短间隔轮询持久化任务，超时意味着后台任务生命周期发生回归。"""

        # 八十次乘五十毫秒覆盖合成小文件任务，同时让失败测试在约四秒内给出结果。
        for _ in range(80):
            status, payload = self.call(f"/api/jobs/{job_id}", token=self.admin)
            self.assertEqual(status, 200)  # 查询必须成功
            job = payload["job"]
            if job["status"] not in ("queued", "running"):
                return job  # 到达终态返回
            time.sleep(0.05)  # 短间隔轮询
        self.fail("任务未在测试时间内结束")
