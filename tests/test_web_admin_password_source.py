"""首次管理员密码来源的容器与传统部署兼容回归。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_backend.database.initializer import _load_initial_admin_password


class InitialAdminPasswordSourceTests(unittest.TestCase):
    """验证环境变量优先级、Docker secret 读取和多行输入拒绝规则。"""

    def test_environment_value_has_priority(self):
        """传统 Windows/Linux 部署继续优先使用现有环境变量。"""
        with patch.dict(os.environ, {
            "FYT_ADMIN_PASSWORD": "EnvPassword123",
            "FYT_ADMIN_PASSWORD_FILE": "Z:/不存在/secret.txt",
        }, clear=False):
            self.assertEqual(_load_initial_admin_password(), "EnvPassword123")

    def test_password_can_be_read_from_secret_file(self):
        """Docker secret 末尾允许一个文本换行，但不把换行作为密码内容。"""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "admin-password.txt"
            source.write_text("DockerPassword123\n", encoding="utf-8")
            with patch.dict(os.environ, {
                "FYT_ADMIN_PASSWORD": "",
                "FYT_ADMIN_PASSWORD_FILE": str(source),
            }, clear=False):
                self.assertEqual(_load_initial_admin_password(), "DockerPassword123")

    def test_multiline_secret_is_rejected(self):
        """拒绝多行 secret，避免编辑器意外附加内容进入管理员密码。"""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "admin-password.txt"
            source.write_text("DockerPassword123\nSecondLine456", encoding="utf-8")
            with patch.dict(os.environ, {
                "FYT_ADMIN_PASSWORD": "",
                "FYT_ADMIN_PASSWORD_FILE": str(source),
            }, clear=False):
                with self.assertRaisesRegex(RuntimeError, "只包含一行"):
                    _load_initial_admin_password()


if __name__ == "__main__":
    unittest.main()
