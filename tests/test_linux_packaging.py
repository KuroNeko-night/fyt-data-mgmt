# -*- coding: utf-8 -*-
"""Linux 部署脚本和 ZIP 元数据回归。"""

from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINUX_DIR = ROOT / "packaging" / "linux"


class LinuxPackagingTests(unittest.TestCase):
    """验证从 Windows 构建的 Linux 包仍满足编码、路径和 Unix 权限要求。"""

    def test_scripts_are_utf8_lf_and_use_fixed_ascii_paths(self) -> None:
        """Shell 必须使用 UTF-8/LF，并把程序、数据和服务 home 固定到安全 ASCII 路径。"""

        for path in LINUX_DIR.glob("*.sh"):
            content = path.read_bytes()
            self.assertNotIn(b"\r\n", content, path.name)
            content.decode("utf-8")

        install = (LINUX_DIR / "install.sh").read_text(encoding="utf-8")
        self.assertIn('APP_DIR="${FYT_INSTALL_DIR:-$INSTALL_ROOT/server}"', install)
        self.assertIn('DATA_DIR="${FYT_DATA_DIR:-/var/lib/fyt-web}"', install)
        self.assertIn("python3.11", install)
        self.assertIn("web_server.py web_backend core web-app/dist", install)
        self.assertIn('cp -a "$SOURCE_DIR/web_backend" "$STAGE/"', install)
        self.assertIn('(root / "web_backend").rglob("*.py")', install)
        self.assertNotIn('WorkingDirectory=__DIR__', install)

        service = (LINUX_DIR / "fyt-web.service").read_text(encoding="utf-8")
        self.assertIn("WorkingDirectory=__APP_DIR__", service)
        self.assertIn("Environment=PYTHONUTF8=1", service)
        self.assertIn("Environment=HOME=__DATA_DIR__", service)
        self.assertIn("ReadWritePaths=__DATA_DIR__", service)
        self.assertIn('usermod --home "$DATA_DIR" --shell "$NOLOGIN" fyt-web', install)

    def test_linux_zip_uses_ascii_root_and_unix_modes(self) -> None:
        """ZIP 顶层不得含中文，且 Shell 执行位和禁止全局写权限必须写入元数据。"""

        module_path = ROOT / "scripts" / "build_deploy.py"
        # 动态加载构建脚本后只把 ROOT 指向临时目录，测试不会写项目 dist 或读取 web-data。
        spec = importlib.util.spec_from_file_location("build_deploy_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            package = temp_root / "fyt-server-linux-v1.3.0"
            package.mkdir()
            (package / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8", newline="\n")
            (package / "README.md").write_text("中文说明\n", encoding="utf-8", newline="\n")
            module.ROOT = os.fspath(temp_root)
            target = module.make_linux_zip(os.fspath(package), "fyt-server-linux-v1.3.0")
            self.assertTrue(Path(target + ".sha256").is_file())

            with zipfile.ZipFile(target) as archive:
                # external_attr 的高十六位是 Unix mode；这里直接检查实际归档而非实现变量。
                names = archive.namelist()
                self.assertTrue(all(name.isascii() for name in names))
                mode = archive.getinfo("fyt-server-linux-v1.3.0/install.sh").external_attr >> 16
                self.assertTrue(mode & stat.S_IXUSR)
                self.assertFalse(mode & stat.S_IWOTH)


if __name__ == "__main__":
    unittest.main()
