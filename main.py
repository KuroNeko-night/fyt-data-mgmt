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


def _single_instance_guard():
    """单实例守卫。

    用具名互斥量判断是否已有本程序在运行：
      · 首个实例：建互斥量 + 具名事件，返回 (True, mutex, event)；
      · 已有实例：SetEvent 唤醒那个实例（让它从托盘/最小化还原），
        返回 (False, mutex, event)，调用方据此直接退出本进程。
    互斥量名须与 installer.iss 的 AppMutex 完全一致（供安装器识别程序在运行）。
    句柄须持有到进程结束，不能被回收。非 Windows 或失败时返回 (True, None, None)，
    不阻断启动。
    """
    try:
        import ctypes
        from ctypes import wintypes
        from core import version
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateEventW.restype = wintypes.HANDLE
        k.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL,
                                   wintypes.BOOL, wintypes.LPCWSTR]
        k.SetEvent.argtypes = [wintypes.HANDLE]

        mutex_name = version.APP_ID + "_SingleInstance"   # 须与 installer.iss 一致
        event_name = version.APP_ID + "_ShowEvent"
        ERROR_ALREADY_EXISTS = 183

        mutex = k.CreateMutexW(None, False, mutex_name)
        # 关键修复：CreateMutexW 对已存在的具名对象仍返回句柄，须查错误码判定
        already = (ctypes.get_last_error() == ERROR_ALREADY_EXISTS)
        # 具名事件：首个实例建、后续实例开同一个内核对象（自动重置、初始无信号）
        event = k.CreateEventW(None, False, False, event_name)
        if already:
            if event:
                k.SetEvent(event)          # 唤醒已在运行的实例
            return (False, mutex, event)
        return (True, mutex, event)
    except Exception:
        return (True, None, None)


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
    # 单实例守卫须在建 QApplication 前判定：非首个实例直接唤醒老窗口并退出，
    # 不再白建一套界面（这正是"隐藏到托盘后再启动会冒出第二个进程"的根因）。
    is_first, mutex, show_event = _single_instance_guard()
    if not is_first:
        return                            # 已唤醒运行中的实例，本进程直接退出

    _setup_high_dpi()
    from PySide2.QtWidgets import QApplication
    from PySide2.QtGui import QFont, QIcon
    from ui import theme
    from ui.main_window import MainWindow
    from core import version, settings as settings_mod, paths

    sys.excepthook = _write_crash
    app = QApplication(sys.argv)
    app._mutex = mutex                    # 持有句柄至进程结束，供更新安装器识别
    app._show_event = show_event          # 同上，防句柄被回收
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
    win.attach_show_event(show_event)     # 监听"再次启动"唤醒信号，从托盘还原
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
