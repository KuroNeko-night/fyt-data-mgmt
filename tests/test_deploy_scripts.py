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
        self.assertIn("sudo unzip", source)
        self.assertIn("fyt-server-linux-v<VERSION>", source)
        self.assertNotIn("tar -xzf 峰运通服务端_linux_*.zip", source)

    def test_linux_service_runs_as_dedicated_user(self):
        """systemd 服务必须保持低权限账号、UTF-8 环境和数据目录写白名单。"""

        source = (ROOT / "packaging" / "linux" / "fyt-web.service").read_text(encoding="utf-8")
        self.assertIn("User=fyt-web", source)
        self.assertIn("NoNewPrivileges=true", source)
        self.assertIn("ReadWritePaths=__DATA_DIR__", source)
        self.assertIn("Environment=PYTHONUTF8=1", source)
        self.assertIn("Environment=HOME=__DATA_DIR__", source)

    def test_linux_installer_migrates_existing_service_home(self):
        """升级旧安装时应把服务账号 home 迁到正式数据目录，避免中文旧路径不可写。"""

        source = (ROOT / "packaging" / "linux" / "install.sh").read_text(encoding="utf-8")
        self.assertIn('usermod --home "$DATA_DIR" --shell "$NOLOGIN" fyt-web', source)

    def test_management_scripts_only_use_systemd(self):
        """启停脚本只能管理明确的 systemd 单元，不能按进程名误杀其他服务。"""

        source = "\n".join(
            (ROOT / "packaging" / "linux" / name).read_text(encoding="utf-8")
            for name in ("start.sh", "stop.sh", "restart.sh", "status.sh")
        )
        self.assertNotIn("pkill -f", source)
        self.assertNotIn("pgrep -f", source)
        self.assertNotIn("web-service.pid", source)
        self.assertIn("systemctl", source)
        self.assertIn("fyt_reexec_root", source)

    def test_web_bridge_does_not_depend_on_deployment_cwd(self):
        """Web 任务桥接应使用用户运行目录和显式环境，不能依赖部署包当前工作目录。"""

        # 桥接进程已从组合入口迁到独立任务模块；测试直接约束真正执行 Popen 的事实源，
        # 避免为了兼容旧文件位置而在 web_server.py 中保留无效实现或伪代码字符串。
        source = (ROOT / "web_backend" / "tasks" / "bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('environment["PYTHONPATH"]', source)
        self.assertIn("deps.data_root", source)
        self.assertIn('cwd=str(work_dir)', source)
        self.assertIn('"HOME": str(runtime_root)', source)
        self.assertIn('"FYT_CONFIG_PATH": str(runtime_root / "配置.json")', source)
        self.assertIn('"FYT_TASK_HISTORY_PATH": str(runtime_root / "任务历史.db")', source)
        self.assertNotIn("cwd=deps.root", source)

    def test_windows_launchers_use_managed_controller(self):
        """Windows 启停入口必须委托控制台维护 PID，禁止退回 taskkill 全局结束。"""

        source = (ROOT / "scripts" / "build_deploy.py").read_text(encoding="utf-8")
        self.assertIn('峰运通服务控制台.exe\\\" --start', source)
        self.assertIn('峰运通服务控制台.exe\\\" --stop', source)
        self.assertNotIn("taskkill /IM web_server.exe", source)

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

        self.assertIn('"web_backend",', build_source)
        self.assertIn('os.path.join(ROOT, "web_backend")', build_source)
        self.assertIn('ROOT / "web_backend"', patch_builder)
        self.assertIn('"$PAYLOAD_DIR/web_backend/__init__.py"', patch_script)
        self.assertIn('program_paths+=(web_backend)', patch_script)
        self.assertIn('collect_submodules("web_backend")', pyinstaller_spec)

    def test_smoke_script_targets_dist_bundle(self):
        """部署冒烟必须执行 dist 中的真实交付物，并覆盖新增对账单桥接动作。"""

        source = (ROOT / "scripts" / "smoke_deploy_package.py").read_text(encoding="utf-8")
        self.assertIn('"dist", "deploy", "windows"', source)
        self.assertIn("reconcile_statement.scan", source)


if __name__ == "__main__":
    unittest.main()
