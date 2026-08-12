"""Web 服务控制台的标准库界面与运行逻辑测试。"""

from __future__ import annotations

import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from web_control_gui import (
    WebControlWindow,
    _extract_public_url,
    _extract_tunnel_token,
    _load_tunnel_token,
    _password_policy_error,
    _save_tunnel_token,
    _tunnel_arguments,
    _tunnel_log_state,
    _windowless_python,
)


class WebControlGuiTests(unittest.TestCase):
    """验证控制台控件装配和凭据不泄露。"""

    def test_window_has_start_stop_controls_without_credentials(self):
        """控制台初始态必须可管理服务，同时不展示默认或历史管理员凭据。"""

        try:
            window = WebControlWindow(manage_existing=False)
        except tk.TclError as exc:
            self.skipTest(f"当前运行环境没有可用桌面：{exc}")
        self.assertEqual(window.windowTitle(), "峰运通 Web 服务控制台")
        self.assertEqual(window._status.text(), "已停止")
        self.assertTrue(window._start.isEnabled())
        self.assertTrue(window._tunnel_start.isEnabled())
        self.assertFalse(window._tunnel_stop.isEnabled())
        self.assertFalse(window._stop.isEnabled())
        self.assertIn(
            window._public_address.text(),
            {"启动公网访问后显示", "固定隧道已配置，绑定域名后可访问"},
        )
        self.assertEqual(window._tunnel_token.text(), "")
        self.assertNotIn("admin123456", window._log.toPlainText())
        self.assertNotIn("admin123456", window._address.text())
        self.assertNotIn("admin123456", window._public_address.text())
        window.closeEvent()

    def test_extracts_quick_tunnel_url_from_both_output_streams(self):
        """快速隧道地址可能出现在任一输出流，应选择最近一次分配值。"""

        value = _extract_public_url(
            "普通启动信息",
            "访问地址 https://first.trycloudflare.com\n"
            "重新连接 https://latest.trycloudflare.com",
        )
        self.assertEqual(value, "https://latest.trycloudflare.com")

    def test_builds_quick_and_token_tunnel_arguments(self):
        """快速与命名隧道必须生成彼此独立且不混入凭据的参数列表。"""

        self.assertEqual(
            _tunnel_arguments(8787),
            ["tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8787"],
        )
        self.assertEqual(
            _tunnel_arguments(8787, named=True),
            ["tunnel", "--no-autoupdate", "run"],
        )

    def test_extracts_token_without_retaining_install_command(self):
        """只保存长令牌本体，不把用户粘贴的安装命令或登录命令持久化。"""

        token = "eyJ" + "a" * 120
        self.assertEqual(_extract_tunnel_token(token), token)
        self.assertEqual(
            _extract_tunnel_token(f"cloudflared.exe service install {token}"), token
        )
        self.assertEqual(
            _extract_tunnel_token(f"cloudflared tunnel run --token {token}"), token
        )
        self.assertEqual(_extract_tunnel_token("cloudflared tunnel login"), "")

    @unittest.skipUnless(sys.platform.startswith("win"), "仅验证 Windows DPAPI")
    def test_tunnel_token_is_encrypted_for_current_windows_user(self):
        """Windows 固定隧道令牌必须由当前用户 DPAPI 加密后再落盘。"""

        token = "eyJ" + "b" * 120
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "token.bin"
            _save_tunnel_token(token, path)
            self.assertEqual(_load_tunnel_token(path), token)
            self.assertNotIn(token.encode("ascii"), path.read_bytes())

    def test_tunnel_url_is_not_ready_before_connection_registration(self):
        """日志出现临时网址但尚未注册边缘连接时，界面不能提前宣告可用。"""

        url, connected = _tunnel_log_state(
            "Your quick Tunnel has been created: "
            "https://pending.trycloudflare.com"
        )
        self.assertEqual(url, "https://pending.trycloudflare.com")
        self.assertFalse(connected)

    def test_tunnel_connection_state_follows_latest_event(self):
        """连接状态应服从最后一个成功或失败事件，而不是历史成功日志。"""

        url, connected = _tunnel_log_state(
            "https://ready.trycloudflare.com\nRegistered tunnel connection"
        )
        self.assertEqual(url, "https://ready.trycloudflare.com")
        self.assertTrue(connected)
        _, connected = _tunnel_log_state(
            "https://ready.trycloudflare.com\nRegistered tunnel connection\n"
            "ERR Serve tunnel error"
        )
        self.assertFalse(connected)

    @unittest.skipUnless(sys.platform.startswith("win"), "仅验证 Windows 无控制台解释器")
    def test_service_uses_windowless_python(self):
        """源码 GUI 启动服务时必须选择 pythonw，防止额外命令窗口出现。"""

        self.assertTrue(_windowless_python().lower().endswith("pythonw.exe"))

    def test_initial_admin_password_policy_matches_server(self):
        """控制台首次密码校验要与服务端长度及字母数字规则保持一致。"""

        self.assertTrue(_password_policy_error("short1"))
        self.assertTrue(_password_policy_error("只有中文没有数字"))
        self.assertEqual(_password_policy_error("安全密码2026abc"), "")

    def test_tauri_sidecar_is_built_without_console_window(self):
        """桌面 sidecar 的 spec 必须保持无控制台子系统配置。"""

        spec = Path(__file__).resolve().parents[1] / "packaging" / "tauri_bridge.spec"
        source = spec.read_text(encoding="utf-8")
        self.assertIn("console=False", source)
        self.assertNotIn("console=True", source)

    def test_dependency_manifests_do_not_restore_removed_ui_runtime(self):
        """依赖与启动脚本不得重新引入已移除的 PySide/Qt 运行时和旧生成器。"""

        root = Path(__file__).resolve().parents[1]
        source = "\n".join(
            (root / name).read_text(encoding="utf-8")
            for name in ("requirements.txt", "pyproject.toml", "run-web-gui.ps1")
        ).lower()
        self.assertNotIn("py" + "side", source)
        self.assertNotIn("qt" + "py", source)
        self.assertFalse((root / "assets" / "_gen_logo.py").exists())

    def test_tauri_release_app_uses_windows_gui_subsystem(self):
        """Rust 正式入口必须使用 Windows GUI 子系统，避免安装版启动时弹出终端。"""

        main_rs = (
            Path(__file__).resolve().parents[1]
            / "tauri-app"
            / "src-tauri"
            / "src"
            / "main.rs"
        )
        source = main_rs.read_text(encoding="utf-8")
        self.assertIn('windows_subsystem = "windows"', source)


if __name__ == "__main__":
    unittest.main()
