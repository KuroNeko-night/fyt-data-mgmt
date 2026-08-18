# -*- coding: utf-8 -*-
"""部署脚本的固定路径、安全账号和 systemd 管理回归。"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptTests(unittest.TestCase):
    """以源码契约保护跨平台部署包中容易被误改的安全约束。"""

    def test_linux_readme_uses_zip_extractor(self):
        """Linux ZIP 的使用说明必须调用 unzip，并使用当前 ASCII 包目录名。"""

        source = (ROOT / "scripts" / "build_deploy.py").read_text(encoding="utf-8")
        self.assertIn("sudo unzip", source)  # 使用 unzip 解包
        self.assertIn("fyt-server-linux-v<VERSION>", source)  # 包目录为 ASCII 名
        self.assertNotIn("tar -xzf 峰运通服务端_linux_*.zip", source)

    def test_linux_service_runs_as_dedicated_user(self):
        """systemd 服务必须保持低权限账号、UTF-8 环境和数据目录写白名单。"""

        source = (ROOT / "packaging" / "linux" / "fyt-web.service").read_text(encoding="utf-8")
        self.assertIn("User=fyt-web", source)  # 专用低权限账号
        self.assertIn("NoNewPrivileges=true", source)  # 禁止提权
        self.assertIn("ReadWritePaths=__DATA_DIR__", source)  # 仅数据目录可写
        self.assertIn("Environment=PYTHONUTF8=1", source)  # 强制 UTF-8
        self.assertIn("Environment=HOME=__DATA_DIR__", source)  # HOME 指向数据目录

    def test_linux_installer_migrates_existing_service_home(self):
        """升级旧安装时应把服务账号 home 迁到正式数据目录，避免中文旧路径不可写。"""

        source = (ROOT / "packaging" / "linux" / "install.sh").read_text(encoding="utf-8")
        self.assertIn('usermod --home "$DATA_DIR" --shell "$NOLOGIN" fyt-web', source)  # 服务账号 home 迁移

    def test_linux_installer_only_configures_caddy_for_a_valid_uploaded_pair(self):
        """Caddy 自动化必须先配验证书和私钥，缺少上传文件时不得修改现有代理。"""

        source = (ROOT / "packaging" / "linux" / "caddy-setup.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("has_certificate_marker", source)  # 先做无副作用的 PEM 标记预检
        self.assertIn("has_private_key_marker", source)
        self.assertIn('if [ -z "$SELECTED_CERT" ] || [ -z "$SELECTED_KEY" ]', source)  # 未配对即退出
        self.assertIn('restore_file "$CADDYFILE"', source)  # 配置失败恢复旧 Caddyfile
        self.assertIn('"$CADDY_BIN" validate', source)  # 重载服务前先校验完整配置
        self.assertIn('reverse_proxy $UPSTREAM_HOST:$UPSTREAM_PORT', source)  # 只代理本机应用端口
        self.assertIn("FYT_CADDY_RECONFIGURE", source)  # 旧配置冲突时允许显式选择跳过或覆盖
        self.assertIn("find_redundant_forward_headers", source)  # 识别 Caddy 重复转发头警告
        self.assertIn("跳过 Caddy 重配置", source)  # 交互终端必须能保留现有配置
        self.assertIn("清理重复转发头", source)  # 覆盖选项应移除已由 Caddy 默认处理的规则
        self.assertNotIn("header_up X-Forwarded-For", source)  # 新生成的峰运通片段不再写入冗余规则
        self.assertNotIn("header_up X-Forwarded-Proto", source)

    def test_management_scripts_only_use_systemd(self):
        """启停脚本只能管理明确的 systemd 单元，不能按进程名误杀其他服务。"""

        source = "\n".join(
            (ROOT / "packaging" / "linux" / name).read_text(encoding="utf-8")
            for name in ("start.sh", "stop.sh", "restart.sh", "status.sh")
        )
        self.assertNotIn("pkill -f", source)  # 禁止进程名误杀
        self.assertNotIn("pgrep -f", source)
        self.assertNotIn("web-service.pid", source)  # 禁止旧 PID 文件
        self.assertIn("systemctl", source)  # 统一走 systemd
        self.assertIn("fyt_reexec_root", source)

    def test_web_bridge_does_not_depend_on_deployment_cwd(self):
        """Web 任务桥接应使用用户运行目录和显式环境，不能依赖部署包当前工作目录。"""

        # 桥接进程已从组合入口迁到独立任务模块；测试直接约束真正执行 Popen 的事实源，
        # 避免为了兼容旧文件位置而在 web_server.py 中保留无效实现或伪代码字符串。
        source = (ROOT / "web_backend" / "tasks" / "bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('environment["PYTHONPATH"]', source)  # 显式传入代码路径
        self.assertIn("deps.data_root", source)  # 使用数据根
        self.assertIn('cwd=str(work_dir)', source)  # 工作目录为任务运行目录
        self.assertIn('"HOME": str(runtime_root)', source)  # HOME 隔离到运行目录
        self.assertIn('"FYT_CONFIG_PATH": str(runtime_root / "配置.json")', source)  # 配置按账号隔离
        self.assertIn('"FYT_TASK_HISTORY_PATH": str(runtime_root / "任务历史.db")', source)  # 任务历史隔离
        self.assertNotIn("cwd=deps.root", source)  # 禁止依赖部署包 cwd

    def test_windows_launchers_use_managed_controller(self):
        """Windows 启停入口必须委托控制台维护 PID，禁止退回 taskkill 全局结束。"""

        source = (ROOT / "scripts" / "build_deploy.py").read_text(encoding="utf-8")
        self.assertIn('峰运通服务控制台.exe\\\" --start', source)  # 启动委托控制台
        self.assertIn('峰运通服务控制台.exe\\\" --stop', source)  # 停止委托控制台
        self.assertNotIn("taskkill /IM web_server.exe", source)  # 禁止全局强杀

    def test_split_web_backend_is_included_in_all_deployment_paths(self):
        """服务端拆分后的 web_backend 必须同时进入完整包、增量补丁和 PyInstaller。"""

        build_source = (ROOT / "scripts" / "build_deploy.py").read_text(encoding="utf-8")
        patch_builder = (ROOT / "scripts" / "build_linux_upgrade_patch.py").read_text(
            encoding="utf-8"
        )
        patch_script = (ROOT / "packaging" / "linux" / "apply-upgrade-patch.sh").read_text(
            encoding="utf-8"
        )
        pyinstaller_spec = (ROOT / "packaging" / "web_server.spec").read_text(encoding="utf-8")

        self.assertIn('"web_backend",', build_source)  # 完整包白名单含 web_backend
        self.assertIn('os.path.join(ROOT, "web_backend")', build_source)
        self.assertIn('ROOT / "web_backend"', patch_builder)  # 增量补丁包含
        self.assertIn('"$PAYLOAD_DIR/web_backend/__init__.py"', patch_script)
        self.assertIn('program_paths+=(web_backend)', patch_script)
        self.assertIn('collect_submodules("web_backend")', pyinstaller_spec)  # PyInstaller 收集

    def test_linux_upgrade_patch_uses_runtime_requirements_only(self):
        """增量补丁必须与完整 Linux 包一致，只部署锁定的运行依赖。"""

        source = (ROOT / "scripts" / "build_linux_upgrade_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('RUNTIME_REQUIREMENTS = ROOT / "requirements-runtime.txt"', source)  # 运行依赖锁文件
        self.assertIn('shutil.copy2(RUNTIME_REQUIREMENTS, payload / "requirements.txt")', source)  # 只复制运行依赖
        self.assertNotIn(
            'shutil.copy2(ROOT / "requirements.txt", payload / "requirements.txt")',
            source,
        )

    def test_smoke_script_targets_dist_bundle(self):
        """部署冒烟必须执行 dist 中的真实交付物，并覆盖新增对账单桥接动作。"""

        source = (ROOT / "scripts" / "smoke_deploy_package.py").read_text(encoding="utf-8")
        self.assertIn('"dist", "deploy", "windows"', source)  # 冒烟面向 dist 产物
        self.assertIn("reconcile_statement.scan", source)  # 覆盖对账单动作

    def test_dockerfile_keeps_portable_defaults_and_non_root_runtime(self):
        """标准 Dockerfile 应使用通用默认源，并以固定低权限用户运行最终镜像。"""

        source = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG NODE_IMAGE=node:22-bookworm-slim", source)  # 基础镜像可配置
        self.assertIn("ARG PYTHON_IMAGE=python:3.13-slim-bookworm", source)
        self.assertIn("ARG NPM_REGISTRY=https://registry.npmjs.org", source)  # 默认公开源
        self.assertIn("ARG PIP_INDEX_URL=https://pypi.org/simple", source)
        self.assertIn("useradd --system --uid 10001", source)  # 低权限系统账号
        self.assertIn("USER fyt", source)  # 运行时降权
        self.assertIn("FYT_WEB_DATA=/data", source)  # 数据根在卷内
        self.assertIn("/api/health", source)

    def test_compose_preserves_data_and_hardens_runtime(self):
        """Compose 必须把运行数据留在卷中，并保持只读、降权和日志限制。"""

        source = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('FYT_ADMIN_PASSWORD_FILE: "/run/secrets/fyt_admin_password"', source)  # 密码走 secret 文件
        self.assertIn('${FYT_DATA_DIR:-fyt-data}:/data', source)  # 数据保留在卷
        self.assertIn("read_only: true", source)  # 根文件系统只读
        self.assertIn("no-new-privileges:true", source)  # 禁止提权
        self.assertIn("cap_drop:\n      - ALL", source)  # 丢弃全部能力
        self.assertIn("pids_limit: 256", source)  # 限制进程数
        self.assertIn("stop_grace_period: 30s", source)  # 优雅停机窗口
        self.assertIn('max-size: "10m"', source)  # 日志单文件上限
        self.assertIn('max-file: "3"', source)  # 日志文件数上限
        self.assertNotIn("/var/run/docker.sock", source)  # 不挂载 Docker socket

    def test_docker_build_sources_are_configurable_without_credentials(self):
        """受限网络可覆盖公开镜像地址，但示例不能携带用户名、密码或 Token。"""

        compose = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in (
            "FYT_DOCKER_NODE_IMAGE",
            "FYT_DOCKER_PYTHON_IMAGE",
            "FYT_DOCKER_NPM_REGISTRY",
            "FYT_DOCKER_PIP_INDEX_URL",
        ):
            self.assertIn(name, compose)  # 镜像与源均可配置
            self.assertIn(name, example)
        self.assertNotIn("github" + "_pat_", example)  # 示例不含 PAT
        self.assertNotIn("gh" + "p_", example)
        self.assertNotIn("token=", example.lower())  # 示例不含 token


if __name__ == "__main__":
    unittest.main()
