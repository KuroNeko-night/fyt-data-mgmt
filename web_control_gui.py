# -*- coding: utf-8 -*-
"""峰运通 Web 服务控制台。

运行于 Windows 10/11 + Python 3.13 + PySide6(Qt6)。本窗口只管理由自己启动的
``web_server.py`` 子进程，不读取或展示管理员账号、密码。
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from qtpy.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from qtpy.QtGui import QFont, QIcon
from qtpy.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


ROOT = Path(__file__).resolve().parent


def _windowless_python() -> str:
    """返回当前环境的无控制台 Python 解释器。"""
    executable = Path(sys.executable)
    candidates = [
        executable.with_name("pythonw.exe"),
        ROOT / ".venv" / "Scripts" / "pythonw.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return str(executable)


class WebControlWindow(QMainWindow):
    """提供 Web 服务启动、停止和状态查看。"""

    def __init__(self) -> None:
        super().__init__()
        self._process = QProcess(self)
        self._stopping = False
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.readyReadStandardOutput.connect(self._read_output)

        self.setWindowTitle("峰运通 Web 服务控制台")
        self.setMinimumSize(620, 470)
        self.resize(700, 530)
        icon_path = ROOT / "assets" / "icon.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._build_ui()
        self._refresh_ui()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Web 服务控制台")
        title.setObjectName("Title")
        subtitle = QLabel("一键启动或关闭局域网浏览器入口")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch(1)
        self._status = QLabel("已停止")
        self._status.setObjectName("Status")
        heading.addWidget(self._status, 0, Qt.AlignTop)
        layout.addLayout(heading)

        settings = QFrame()
        settings.setObjectName("Card")
        form = QFormLayout(settings)
        form.setContentsMargins(18, 15, 18, 15)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)

        self._host = QLineEdit("0.0.0.0")
        self._host.setPlaceholderText("例如：0.0.0.0")
        self._port = QSpinBox()
        self._port.setRange(1024, 65535)
        self._port.setValue(int(os.environ.get("FYT_WEB_PORT", "8787")))
        self._port.setButtonSymbols(QSpinBox.PlusMinus)
        form.addRow("监听地址", self._host)
        form.addRow("端口", self._port)
        layout.addWidget(settings)

        address_card = QFrame()
        address_card.setObjectName("AddressCard")
        address_layout = QVBoxLayout(address_card)
        address_layout.setContentsMargins(18, 14, 18, 14)
        address_title = QLabel("访问地址")
        address_title.setObjectName("SmallTitle")
        self._address = QLabel(self._address_text())
        self._address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._address.setObjectName("Address")
        address_actions = QHBoxLayout()
        address_actions.addWidget(self._address)
        address_actions.addStretch(1)
        copy_button = QPushButton("复制地址")
        copy_button.setObjectName("Secondary")
        copy_button.clicked.connect(self._copy_address)
        address_actions.addWidget(copy_button)
        address_layout.addWidget(address_title)
        address_layout.addLayout(address_actions)
        layout.addWidget(address_card)

        actions = QHBoxLayout()
        self._start = QPushButton("启动 Web 服务")
        self._start.setObjectName("Primary")
        self._start.clicked.connect(self.start_service)
        self._stop = QPushButton("关闭 Web 服务")
        self._stop.setObjectName("Danger")
        self._stop.clicked.connect(self.stop_service)
        actions.addWidget(self._start)
        actions.addWidget(self._stop)
        actions.addStretch(1)
        layout.addLayout(actions)

        log_title = QLabel("运行日志")
        log_title.setObjectName("SmallTitle")
        layout.addWidget(log_title)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(400)
        self._log.setPlaceholderText("服务启动后会在这里显示状态和错误信息")
        layout.addWidget(self._log, 1)

        self._host.textChanged.connect(self._refresh_address)
        self._port.valueChanged.connect(self._refresh_address)

    def _address_text(self) -> str:
        host = self._host.text().strip() if hasattr(self, "_host") else "0.0.0.0"
        port = self._port.value() if hasattr(self, "_port") else 8787
        if host in ("", "0.0.0.0", "::"):
            try:
                host = socket.gethostbyname(socket.gethostname())
            except OSError:
                host = "本机 IP"
        return f"http://{host}:{port}/"

    def _refresh_address(self) -> None:
        self._address.setText(self._address_text())

    def _append_log(self, text: str) -> None:
        text = text.strip()
        if text:
            self._log.appendPlainText(text)

    def _refresh_ui(self) -> None:
        running = self._process.state() != QProcess.NotRunning
        self._start.setEnabled(not running)
        self._stop.setEnabled(running)
        self._host.setEnabled(not running)
        self._port.setEnabled(not running)
        self._status.setProperty("running", running)
        self._status.setText("运行中" if running else "已停止")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _read_output(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        if data:
            self._append_log(data.decode("utf-8", errors="replace"))

    def _on_started(self) -> None:
        self._append_log(f"[完成] Web 服务已启动：{self._address_text()}")
        self._refresh_ui()

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._read_output()
        if self._stopping:
            self._append_log("[完成] Web 服务已停止。")
        elif exit_status == QProcess.CrashExit:
            self._append_log(f"[错误] 服务进程异常退出（代码 {exit_code}）")
        else:
            self._append_log(f"[完成] Web 服务已停止（代码 {exit_code}）")
        self._stopping = False
        self._refresh_ui()

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.FailedToStart:
            return
        self._append_log("[错误] 无法启动 Python Web 服务，请检查 .venv 或端口设置。")
        self._refresh_ui()

    def start_service(self) -> None:
        if self._process.state() != QProcess.NotRunning:
            return
        host = self._host.text().strip() or "0.0.0.0"
        port = str(self._port.value())
        env = QProcessEnvironment.systemEnvironment()
        env.insert("FYT_WEB_HOST", host)
        env.insert("FYT_WEB_PORT", port)
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(str(ROOT))
        self._log.clear()
        self._stopping = False
        self._append_log(f"[启动] 正在启动 {host}:{port} …")
        self._process.start(_windowless_python(), [str(ROOT / "web_server.py")])
        self._refresh_ui()

    def stop_service(self) -> None:
        if self._process.state() == QProcess.NotRunning:
            return
        self._append_log("[停止] 正在关闭 Web 服务 …")
        self._stopping = True
        self._process.terminate()
        if not self._process.waitForFinished(500):
            self._append_log("[提示] 正在结束服务进程。")
            self._process.kill()
            self._process.waitForFinished(1000)
        self._refresh_ui()

    def _copy_address(self) -> None:
        QApplication.clipboard().setText(self._address_text())
        self._append_log("[完成] 访问地址已复制。")

    def closeEvent(self, event) -> None:
        if self._process.state() != QProcess.NotRunning:
            answer = QMessageBox.question(
                self,
                "Web 服务仍在运行",
                "关闭控制台时是否同时关闭 Web 服务？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Yes:
                self.stop_service()
        event.accept()


def _style(app: QApplication) -> None:
    """应用控制台专用的浅色 QSS，避免依赖主程序窗口状态。"""
    app.setStyleSheet(
        """
        QWidget#Root { background: #f4f7fb; color: #17324b; }
        QLabel#Title { color: #17324b; font-size: 23px; font-weight: 700; }
        QLabel#Subtitle { color: #7b8c9c; font-size: 12px; margin-top: 4px; }
        QLabel#Status { color: #8a99a5; background: #edf1f4; border-radius: 12px; padding: 6px 14px; font-size: 11px; }
        QLabel#Status[running="true"] { color: #1d8b72; background: #e6f7f1; }
        QFrame#Card, QFrame#AddressCard { background: #ffffff; border: 1px solid #dfe8f1; border-radius: 10px; }
        QFrame#AddressCard { background: #eef9f8; border-color: #cfe9e8; }
        QLabel#SmallTitle { color: #728798; font-size: 11px; font-weight: 700; }
        QLabel#Address { color: #2b8d99; font-size: 14px; font-weight: 700; }
        QLineEdit, QSpinBox { min-height: 34px; padding: 0 9px; border: 1px solid #d7e2eb; border-radius: 7px; background: #fbfdfe; color: #17324b; }
        QLineEdit:focus, QSpinBox:focus { border-color: #20b9c9; }
        QPushButton { min-height: 38px; padding: 0 15px; border-radius: 7px; font-size: 12px; }
        QPushButton#Primary { color: #ffffff; background: #102d47; border: 0; font-weight: 700; }
        QPushButton#Primary:hover { background: #174463; }
        QPushButton#Danger { color: #b45d63; background: #fff4f4; border: 1px solid #f0c8cb; }
        QPushButton#Secondary { min-height: 30px; color: #397e88; background: #ffffff; border: 1px solid #c6e2e4; }
        QPlainTextEdit { border: 1px solid #dfe8f1; border-radius: 8px; padding: 9px; background: #152c42; color: #c9dce7; font-family: Consolas, monospace; font-size: 11px; }
        """
    )


def main() -> int:
    """启动 Web 服务控制台。"""
    os.environ.setdefault("QT_API", "pyside6")
    app = QApplication(sys.argv)
    app.setApplicationName("峰运通 Web 服务控制台")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    _style(app)
    window = WebControlWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
