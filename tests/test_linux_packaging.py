# -*- coding: utf-8 -*-
"""Linux 部署脚本和 ZIP 元数据回归。"""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
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
        self.assertIn('bash "$APP_DIR/caddy-setup.sh" "$PORT"', install)  # 应用健康后自动尝试配置 Caddy

        caddy_setup = (LINUX_DIR / "caddy-setup.sh").read_text(encoding="utf-8")
        self.assertIn('FYT_CADDY_CERT_SEARCH_DIR:-/root', caddy_setup)  # 默认只扫描 root 上传目录
        self.assertIn("-maxdepth 1 -type f -size -2M", caddy_setup)  # 不递归扫描或读取大型业务文件
        self.assertIn("certificate_fingerprint", caddy_setup)  # 证书和私钥必须按公钥配对
        self.assertIn("openssl x509 -in \"$certificate\" -checkend 0", caddy_setup)  # 拒绝过期证书
        self.assertIn("subjectAltName", caddy_setup)  # 域名来自证书 SAN，不要求重复填写
        self.assertIn("caddyserver.com/api/download", caddy_setup)  # 软件源失败时只使用官方下载接口
        self.assertIn('systemctl enable "$CADDY_SERVICE"', caddy_setup)  # 注册开机启动服务
        self.assertIn("未在 $SEARCH_DIR 识别到完整的证书和私钥", caddy_setup)  # 缺少文件时安全跳过
        self.assertNotIn("BEGIN PRIVATE KEY-----\nMII", caddy_setup)  # 脚本不得内置真实私钥

        caddy_service = (LINUX_DIR / "fyt-caddy.service").read_text(encoding="utf-8")
        self.assertIn("User=caddy", caddy_service)  # 静态下载回退仍使用低权限账号
        self.assertIn("NoNewPrivileges=true", caddy_service)
        self.assertIn("CAP_NET_BIND_SERVICE", caddy_service)  # 只授予监听 80/443 所需能力

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

    def test_caddy_discovery_matches_real_certificate_key_and_san(self) -> None:
        """使用临时自签名材料验证真实公钥配对和 SAN 域名提取，不触碰系统 Caddy。"""

        bash = shutil.which("bash")
        openssl = shutil.which("openssl")
        if os.name == "nt":
            program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            git_bash = program_files / "Git" / "bin" / "bash.exe"
            if git_bash.is_file():
                bash = os.fspath(git_bash)
            git_openssl = program_files / "Git" / "usr" / "bin" / "openssl.exe"
            if git_openssl.is_file():
                openssl = os.fspath(git_openssl)
        if not bash or not openssl:
            self.skipTest("当前环境没有 Bash 或 openssl")

        with tempfile.TemporaryDirectory() as temp:
            cert_dir = Path(temp)
            command = [
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", os.fspath(cert_dir / "uploaded-private.key"),
                "-out", os.fspath(cert_dir / "uploaded-certificate.pem"),
                "-days", "1", "-subj", "/CN=fyt.example.com",
                "-addext", "subjectAltName=DNS:fyt.example.com,DNS:*.example.com",
            ]
            generated = subprocess.run(command, capture_output=True, text=True, check=False)
            if generated.returncode != 0:
                self.skipTest(f"当前 openssl 无法生成测试证书：{generated.stderr.strip()}")

            environment = os.environ.copy()
            search_dir = os.fspath(cert_dir)
            if os.name == "nt":
                drive, tail = os.path.splitdrive(search_dir)
                search_dir = f"/{drive[0].lower()}{tail.replace(os.sep, '/')}"
            environment["FYT_CADDY_CERT_SEARCH_DIR"] = search_dir
            environment["FYT_CADDY_VALIDATE_ONLY"] = "1"
            checked = subprocess.run(
                [bash, "packaging/linux/caddy-setup.sh", "8787"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn("识别测试通过", checked.stdout)
            self.assertIn("fyt.example.com", checked.stdout)
            self.assertIn("*.example.com", checked.stdout)

            # 用另一把私钥覆盖上传文件后必须安全跳过，不能把两个解析失败产生的空摘要误判为配对。
            replaced = subprocess.run(
                [
                    openssl,
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    "rsa_keygen_bits:2048",
                    "-out",
                    os.fspath(cert_dir / "uploaded-private.key"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            mismatched = subprocess.run(
                [bash, "packaging/linux/caddy-setup.sh", "8787"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(mismatched.returncode, 0, mismatched.stderr)
            self.assertNotIn("识别测试通过", mismatched.stdout)
            self.assertIn("没有识别到有效且相互匹配", mismatched.stderr)


if __name__ == "__main__":
    unittest.main()
