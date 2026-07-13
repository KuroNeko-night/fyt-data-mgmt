# -*- coding: utf-8 -*-
"""
峰运通数据管理系统 —— 程序入口
==============================
· 高 DPI 自适应（Win7 上也能清晰）；
· 统一崩溃日志（写到数据目录，弹窗告知，不再白屏退出）；
· 加载主题与中文字体，启动主窗口。
兼容 Windows 7 + Python 3.8 + PySide2(Qt5.15)。
"""
import os
import sys
import traceback
import datetime

# 让 "from core ... / from ui ..." 在任意工作目录下都可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_high_dpi():
    """必须在创建 QApplication 之前设置。"""
    from PySide2.QtCore import Qt, QCoreApplication
    try:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")


def _create_app_mutex():
    """创建具名互斥量，供 Inno Setup 安装器识别"程序正在运行"并自动关闭它。

    名字须与 installer.iss 的 AppMutex 完全一致。返回句柄(须持有到进程结束，
    不能被回收)；非 Windows 或失败时返回 None，不影响正常运行。
    """
    try:
        import ctypes
        from core import version
        name = version.APP_ID + "_SingleInstance"
        return ctypes.windll.kernel32.CreateMutexW(None, False, name)
    except Exception:
        return None


def _write_crash(exc_type, exc_value, tb):
    """全局异常兜底：写日志 + 弹窗，避免程序静默崩溃。"""
    from core import paths
    text = "".join(traceback.format_exception(exc_type, exc_value, tb))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(paths.crash_log_path(), "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n%s\n" % (stamp, text))
    except Exception:
        pass
    try:
        from PySide2.QtWidgets import QMessageBox, QApplication
        if QApplication.instance():
            QMessageBox.critical(None, "程序遇到错误",
                                 "发生未预期错误，已记录到日志：\n%s\n\n%s"
                                 % (paths.crash_log_path(), str(exc_value)))
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, tb)


def main():
    _setup_high_dpi()
    from PySide2.QtWidgets import QApplication
    from PySide2.QtGui import QFont, QIcon
    from ui import theme
    from ui.main_window import MainWindow
    from core import version, settings as settings_mod, paths

    sys.excepthook = _write_crash
    app = QApplication(sys.argv)
    app._mutex = _create_app_mutex()      # 持有句柄至进程结束，供更新安装器识别
    app.setApplicationName(version.APP_NAME)
    app.setApplicationDisplayName(version.APP_NAME)
    _icon = os.path.join(paths.assets_dir(), "icon.ico")
    if os.path.exists(_icon):
        app.setWindowIcon(QIcon(_icon))
    app.setFont(QFont(theme.pick_font(), 10))
    theme.set_mode(settings_mod.get_settings().theme_mode)   # 解析跟随系统/浅/深
    theme.apply_palette(app)                                 # 先染调色板：杜绝原生白底擦除
    app.setStyleSheet(theme.stylesheet())

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
