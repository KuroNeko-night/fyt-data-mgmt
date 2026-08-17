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

    def test_local_ops_guides_are_excluded_from_source_bundle(self) -> None:
        """本地部署和 AI 排错资料不得被纯净源码包重新带入公开交付物。"""

        module_path = ROOT / "scripts" / "build_deploy.py"
        spec = importlib.util.spec_from_file_location("build_deploy_docs_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        local_guides = {
            "AI协作排错指南.md",
            "Git源码自动部署指南.md",
            "运维部署完全指南.md",
        }
        ignored = module._source_ignore(os.fspath(ROOT / "docs"), sorted(local_guides))
        self.assertEqual(local_guides, ignored)  # 三份本地资料必须全部命中源码包排除规则

    def test_scripts_are_utf8_lf_and_use_fixed_ascii_paths(self) -> None:
        """Shell 必须使用 UTF-8/LF，并把程序、数据和服务 home 固定到安全 ASCII 路径。"""

        for path in LINUX_DIR.glob("*.sh"):
            content = path.read_bytes()
            self.assertNotIn(b"\r\n", content, path.name)  # 脚本必须 LF 换行
            content.decode("utf-8")  # 必须为合法 UTF-8

        install = (LINUX_DIR / "install.sh").read_text(encoding="utf-8")
        self.assertIn('APP_DIR="${FYT_INSTALL_DIR:-$INSTALL_ROOT/server}"', install)  # 程序固定到 ASCII 路径
        self.assertIn('DATA_DIR="${FYT_DATA_DIR:-/var/lib/fyt-web}"', install)  # 数据固定路径
        self.assertIn("python3.11", install)  # 使用并行安装的 Python 3.11
        self.assertIn("web_server.py web_backend core web-app/dist", install)  # 载荷白名单齐全
        self.assertIn('cp -a "$SOURCE_DIR/web_backend" "$STAGE/"', install)  # Web 后端整目录复制
        self.assertIn('(root / "web_backend").rglob("*.py")', install)  # Python 源码校验
        self.assertNotIn('WorkingDirectory=__DIR__', install)  # 不得使用相对工作目录
        self.assertIn("SOURCE_COMMIT SOURCE_REF", install)  # Git 部署元数据随正式程序保留

        git_deploy = (LINUX_DIR / "deploy-from-git.sh").read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/KuroNeko-night/fyt-data-mgmt.git",
            git_deploy,
        )  # 公开仓库是默认来源
        self.assertIn('GIT_REF="${FYT_GIT_REF:-main}"', git_deploy)  # 默认部署 main，可覆盖为标签
        self.assertIn("FYT_GIT_EXPECTED_COMMIT", git_deploy)  # 支持固定期望提交，防止引用漂移
        self.assertIn('mktemp -d "$INSTALL_ROOT/.git-deploy.XXXXXX"', git_deploy)  # 克隆只落临时目录
        self.assertIn('"$NPM_BIN" --prefix "$CHECKOUT_DIR/web-app" run build', git_deploy)  # Git 源码现场构建前端
        self.assertIn('bash "$BUNDLE_DIR/install.sh"', git_deploy)  # 复用现有备份与回滚安装器
        self.assertNotIn("/var/lib/fyt-web/*", git_deploy)  # Git 部署脚本不得清理运行数据

        service = (LINUX_DIR / "fyt-web.service").read_text(encoding="utf-8")
        self.assertIn("WorkingDirectory=__APP_DIR__", service)  # systemd 使用安装占位符
        self.assertIn("Environment=PYTHONUTF8=1", service)  # 强制 UTF-8 模式
        self.assertIn("Environment=HOME=__DATA_DIR__", service)  # 服务 HOME 指向数据目录
        self.assertIn("ReadWritePaths=__DATA_DIR__", service)  # 只授权数据目录写
        self.assertIn('usermod --home "$DATA_DIR" --shell "$NOLOGIN" fyt-web', install)  # 低权限账号落位

    def test_linux_zip_uses_ascii_root_and_unix_modes(self) -> None:
        """ZIP 顶层不得含中文，且 Shell 执行位和禁止全局写权限必须写入元数据。"""

        module_path = ROOT / "scripts" / "build_deploy.py"
        # 动态加载构建脚本后只把 ROOT 指向临时目录，测试不会写项目 dist 或读取 web-data。
        spec = importlib.util.spec_from_file_location("build_deploy_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # 动态加载后 ROOT 可被覆盖

        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            package = temp_root / "fyt-server-linux-v1.3.0"
            package.mkdir()
            (package / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8", newline="\n")
            (package / "README.md").write_text("中文说明\n", encoding="utf-8", newline="\n")
            module.ROOT = os.fspath(temp_root)  # 重定向输出到临时目录
            target = module.make_linux_zip(os.fspath(package), "fyt-server-linux-v1.3.0")
            self.assertTrue(Path(target + ".sha256").is_file())  # 校验文件同时生成

            with zipfile.ZipFile(target) as archive:
                # external_attr 的高十六位是 Unix mode；这里直接检查实际归档而非实现变量。
                names = archive.namelist()
                self.assertTrue(all(name.isascii() for name in names))  # 包内路径全 ASCII
                mode = archive.getinfo("fyt-server-linux-v1.3.0/install.sh").external_attr >> 16
                self.assertTrue(mode & stat.S_IXUSR)  # 脚本保留执行位
                self.assertFalse(mode & stat.S_IWOTH)  # 禁止他人写权限


if __name__ == "__main__":
    unittest.main()
