# -*- coding: utf-8 -*-
"""Web 服务端路径与持久化元数据的回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import web_server


class WebServerHardeningTests(unittest.TestCase):
    """保护路径归属判断和损坏 JSON 元数据的安全回退行为。"""

    def test_path_is_within_rejects_sibling_prefix(self) -> None:
        """字符串前缀相同的兄弟目录不能绕过基于真实父子关系的路径校验。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "reports"
            sibling = Path(temp_dir) / "reports-other" / "result.xlsx"  # 前缀相似但非子路径
            child = root / "2026" / "result.xlsx"
            root.mkdir()
            self.assertFalse(web_server.path_is_within(root, sibling))  # 兄弟前缀不能绕过
            self.assertTrue(web_server.path_is_within(root, child))  # 真实子路径放行

    def test_json_helpers_recover_damaged_metadata(self) -> None:
        """历史损坏 JSON 应回退为空容器或默认值，而不是中断整个 API 请求。"""

        self.assertEqual(web_server._json_list("损坏"), [])  # 损坏列表回退空数组
        self.assertEqual(web_server._json_object("损坏"), {})  # 损坏对象回退空字典
        self.assertEqual(web_server._json_value("损坏", "默认"), "默认")  # 损坏值回退默认
        self.assertEqual(web_server._json_list('[1, 2]'), [1, 2])  # 正常列表正常解析
        self.assertEqual(web_server._json_object('{"name":"模板"}'), {"name": "模板"})  # 正常对象正常解析


if __name__ == "__main__":
    unittest.main()
