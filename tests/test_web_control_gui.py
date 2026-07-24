"""Web 服务控制台的无头 Qt 装配测试。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy.QtWidgets import QApplication

from web_control_gui import WebControlWindow, _windowless_python


class WebControlGuiTests(unittest.TestCase):
    """验证控制台控件装配和凭据不泄露。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_window_has_start_stop_controls_without_credentials(self):
        window = WebControlWindow()
        self.assertEqual(window.windowTitle(), "峰运通 Web 服务控制台")
        self.assertEqual(window._status.text(), "已停止")
        self.assertTrue(window._start.isEnabled())
        self.assertFalse(window._stop.isEnabled())
        self.assertNotIn("admin123456", window._log.toPlainText())
        self.assertNotIn("admin123456", window._address.text())
        window.close()

    @unittest.skipUnless(sys.platform.startswith("win"), "仅验证 Windows 无控制台解释器")
    def test_service_uses_windowless_python(self):
        self.assertTrue(_windowless_python().lower().endswith("pythonw.exe"))


if __name__ == "__main__":
    unittest.main()
