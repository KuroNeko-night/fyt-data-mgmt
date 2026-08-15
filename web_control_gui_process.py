# -*- coding: utf-8 -*-
"""Web 控制台的进程发现、验证与受控终止辅助函数。

本模块从 ``web_control_gui.py`` 拆出，只处理 PID 文件、Windows 映像名和进程终止，
不导入 Tkinter，也不依赖图形界面状态。控制台主类通过导入复用这些函数，测试可独立覆盖。
"""
import ctypes
import os
import signal
import sys
from pathlib import Path

def _windows_process_image(pid: int) -> str:
    """尽力读取 Windows 进程完整路径；权限不足时返回空字符串。

    读取映像名用于验证 PID 文件没有因系统重用 PID 而指向无关进程，不能单靠“PID 存在”
    就允许控制台终止它。
    """
    if not sys.platform.startswith("win") or pid <= 0:
        return ""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION 足够读取映像路径。
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _process_exists(pid: int) -> bool:
    """判断进程是否仍存在；权限不足时按“可能仍运行”处理。

    保守判断可以避免误删仍有效的 PID 文件，真正终止时仍会执行权限和映像名校验。
    """
    if pid <= 0:
        return False
    if _windows_process_image(pid):
        return True
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True  # 无权发送信号不等于进程不存在。
    except (OSError, ProcessLookupError):
        return False


def _read_live_pid(path: Path, expected_names: tuple[str, ...]) -> int | None:
    """读取 PID 文件并校验进程名称，过期或已被重用的记录会被清理。

    必须先验证映像名才能返回 PID：系统会重用 PID，文件里记录的旧号可能已指向无关进程，
    直接交给调用方终止会误杀其他程序。
    """
    try:
        value = path.read_text(encoding="ascii", errors="ignore").strip().splitlines()[0]
        pid = int(value)
    except (FileNotFoundError, IndexError, ValueError):
        return None
    if not _process_exists(pid):
        path.unlink(missing_ok=True)
        return None
    image = Path(_windows_process_image(pid)).name.lower()
    if image and image not in expected_names:
        path.unlink(missing_ok=True)
        return None
    return pid


def _terminate_pid(pid: int) -> None:
    """直接终止已验证的进程，不启动 taskkill 等可见命令窗口。

    Windows 使用最小的 ``PROCESS_TERMINATE`` 权限打开进程；非 Windows 路径主要服务测试，
    发送 SIGTERM 让目标有机会自行退出。
    """
    if not sys.platform.startswith("win"):
        os.kill(pid, signal.SIGTERM)
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE。
    if not handle:
        raise OSError(ctypes.get_last_error(), "没有权限关闭该进程")
    try:
        if not kernel32.TerminateProcess(handle, 0):
            raise OSError(ctypes.get_last_error(), "关闭进程失败")
    finally:
        kernel32.CloseHandle(handle)


def _write_pid(path: Path, pid: int) -> None:
    """把控制台拥有的进程号写入 ASCII PID 文件，供重启后的控制台重新发现。

    PID 文件只写 ASCII，避免 Windows 默认代码页把内容写成 GBK；读取方也按 ASCII 容错。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="ascii")


def _remove_owned_pid(path: Path, pid: int) -> None:
    """仅当 PID 文件仍指向本进程时删除，避免覆盖后误删新进程的所有权记录。"""
    try:
        recorded = int(path.read_text(encoding="ascii").strip())
    except (FileNotFoundError, ValueError):
        return
    if recorded == pid:
        path.unlink(missing_ok=True)


