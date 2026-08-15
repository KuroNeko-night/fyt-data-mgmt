# -*- coding: utf-8 -*-
"""峰运通 Web 服务与公网访问控制台。

控制台只使用 Python 标准库 Tkinter/ttk，不依赖第三方桌面 UI 运行时。它统一管理
``web_server.py`` 与 Cloudflare Tunnel；首次启动密码仅通过子进程环境传递，不显示或保存。

控制台既能管理自己启动的子进程，也能通过 PID 文件接管部署脚本此前启动的进程。后台
线程只读取服务日志，所有 Tk 控件更新都由主线程定时轮询完成。固定隧道令牌使用 Windows
DPAPI 绑定当前登录用户加密，启动 cloudflared 时只通过子进程环境传递。
"""

from __future__ import annotations

import ctypes
import os
import queue
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

# 密码策略与 Web 服务端共用 web_backend/passwords.py（纯标准库，不引入业务算法），
# 控制台只做预检提示；此处保留 ``_password_policy_error`` 旧名以兼容测试导入。
from web_backend.passwords import password_policy_error as _password_policy_error


ROOT = Path(__file__).resolve().parent
# 打包兼容：frozen 下 ROOT 指向部署包根目录（web-data、web-app/dist 与其同级），
# 平铺部署时回退到 exe 所在目录。
if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir.parent / "web-app" / "dist").is_dir():
        ROOT = exe_dir.parent
    else:
        ROOT = exe_dir
DATA_ROOT = Path(os.environ.get("FYT_WEB_DATA", ROOT / "web-data"))  # 与服务端使用同一数据根，PID、日志和账号库才能互相识别。
LOG_DIR = DATA_ROOT / "logs"
DB_PATH = DATA_ROOT / "accounts.sqlite3"
WEB_PID_PATH = LOG_DIR / "web-service.pid"
TUNNEL_PID_PATH = LOG_DIR / "cloudflare-tunnel.pid"
TUNNEL_URL_PATH = LOG_DIR / "cloudflare-tunnel.url"
TUNNEL_LOG_PATH = LOG_DIR / "cloudflare-tunnel.log"
TUNNEL_ERROR_LOG_PATH = LOG_DIR / "cloudflare-tunnel-error.log"
TUNNEL_TOKEN_PATH = DATA_ROOT / "private" / "cloudflare-tunnel-token.bin"
PUBLIC_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")  # Quick Tunnel 地址只接受 Cloudflare 官方随机域名。
TUNNEL_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._~+/=-]{80,4096}")  # 只校验令牌字符与合理长度，不尝试解析其内部格式。
# 隧道模式标签同时作为用户可读文案和状态机内部值，修改时必须同步更新控件文本比较。
TUNNEL_MODE_QUICK = "临时公网地址（每次启动可能变化）"
TUNNEL_MODE_NAMED = "固定命名隧道（需令牌）"
# 令牌文件头用于快速识别密文格式；旧明文或损坏文件会被视为未配置，而不是尝试解密。
_TOKEN_FILE_HEADER = b"FYT-DPAPI-TUNNEL\x00"
# 允许的 Web 服务映像名：冻结包用 web_server.exe，源码环境用 pythonw/python；避免 PID 被其他程序复用后误接管。
WEB_PROCESS_NAMES = ("web_server.exe", "pythonw.exe", "pythonw3.13.exe", "python.exe")


def _windowless_python() -> str:
    """返回当前环境的无控制台 Python 解释器。

    优先选择与当前解释器同目录的 ``pythonw.exe``，其次使用项目虚拟环境；都不存在时
    回退当前解释器。打包程序本身已使用无控制台模式，回退不会改变冻结部署行为。
    """
    executable = Path(sys.executable)
    candidates = [
        executable.with_name("pythonw.exe"),
        ROOT / ".venv" / "Scripts" / "pythonw.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return str(executable)


def _find_cloudflared() -> Path | None:
    """在 PATH、项目工具目录和常见安装目录中查找 cloudflared。

    一键部署包把客户端放在 ``tools``，手工安装则可能进入系统 PATH 或 Program Files；
    同时兼容官方下载文件尚未重命名的情况。
    """
    resolved = shutil.which("cloudflared")
    candidates = [Path(resolved)] if resolved else []
    tools_dir = ROOT / "tools"
    candidates.append(tools_dir / "cloudflared.exe")
    # 兼容直接下载未重命名的文件（cloudflared-windows-amd64.exe 等）
    if tools_dir.is_dir():
        candidates.extend(sorted(tools_dir.glob("cloudflared*.exe")))
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "cloudflared" / "cloudflared.exe")
    return next((item.resolve() for item in candidates if item.is_file()), None)


def _extract_public_url(*texts: str) -> str:
    """从标准输出或错误输出中提取最后一个 Quick Tunnel 地址。

    cloudflared 重连时日志可能包含多个旧地址，最后一次出现的地址才属于当前连接尝试。
    """
    matches = PUBLIC_URL_PATTERN.findall("\n".join(texts))
    return matches[-1] if matches else ""


def _tunnel_log_state(*texts: str) -> tuple[str, bool]:
    """解析公网地址，并判断最近一次连接事件是否为注册成功。

    仅看到 trycloudflare 地址不代表边缘连接已经建立；需要比较最后一次“已注册”和
    断开/重试事件的位置，避免用户复制一个尚未可用或已经失效的地址。
    """
    combined = "\n".join(texts)
    registered_at = combined.rfind("Registered tunnel connection")
    disconnected_at = max(  # ``rfind`` 未命中返回 -1，因此可直接取所有失败标记的最大位置。
        combined.rfind(marker)
        for marker in (
            "Unregistered tunnel connection",
            "Serve tunnel error",
            "Failed to serve tunnel connection",
            "connection dropped unexpectedly",
            "Retrying connection in up to",
        )
    )
    return _extract_public_url(combined), registered_at >= 0 and registered_at > disconnected_at


def _tunnel_arguments(port: int, named: bool = False) -> list[str]:
    """生成 Cloudflare Tunnel 参数；固定隧道令牌不进入命令行。

    Windows 进程命令行可能被其他本机用户或诊断工具读取，因此命名隧道只使用
    ``TUNNEL_TOKEN`` 环境变量；临时隧道则显式只代理本机回环地址。
    """
    if named:
        return ["tunnel", "--no-autoupdate", "run"]
    return ["tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]


def _extract_tunnel_token(value: str) -> str:
    """从裸令牌或 Cloudflare 安装命令中提取令牌，不记录原始内容。

    支持 ``--token`` 等号/空格两种写法和 ``service install`` 命令末尾令牌；只有匹配
    预期字符集和长度范围的值才会被接受，其余按未配置处理。
    """
    text = value.strip()
    if not text:
        return ""
    token_match = re.search(r"--token(?:=|\s+)([^\s\"']+)", text)
    if token_match:
        candidate = token_match.group(1)
    elif "service install" in text.lower():
        candidate = text.rsplit(maxsplit=1)[-1]
    else:
        candidate = text
    return candidate if TUNNEL_TOKEN_PATTERN.fullmatch(candidate) else ""


class _DataBlob(ctypes.Structure):
    """Windows DPAPI 使用的 ``DATA_BLOB`` 内存布局。

    结构体字段顺序必须与 Windows 头文件一致，供 CryptProtectData/CryptUnprotectData 读写。
    """

    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _bytes_blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    """把 Python 字节复制到稳定的 C 缓冲区，并返回阻止其提前回收的持有对象。

    返回的数组对象必须由调用方保存到 WinAPI 调用结束；若只保留指针，Python 可能提前
    回收缓冲内存导致访问已释放地址。
    """
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer  # 调用者必须保留 ``buffer`` 到 WinAPI 返回。


def _protect_tunnel_token(token: str) -> bytes:
    """使用 Windows DPAPI 绑定当前用户加密固定隧道令牌。

    ``CRYPTPROTECT_UI_FORBIDDEN`` 禁止系统弹出额外对话框，便于无人值守部署；输出缓冲区
    由 Windows ``LocalAlloc`` 分配，必须无论成功读取与否都调用 ``LocalFree``。
    """
    if not sys.platform.startswith("win"):
        raise OSError("固定隧道令牌加密仅支持 Windows")
    source, source_buffer = _bytes_blob(token.encode("utf-8"))
    output = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = (
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DataBlob),
    )
    crypt32.CryptProtectData.restype = ctypes.c_bool
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        "峰运通 Cloudflare Tunnel",
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN：加密失败时直接报错，不显示系统交互窗口。
        ctypes.byref(output),
    ):
        raise OSError(ctypes.get_last_error(), "无法加密固定隧道令牌")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))  # 释放 DPAPI 返回的本机堆内存。
        del source_buffer


def _unprotect_tunnel_token(payload: bytes) -> str:
    """解密由当前 Windows 用户保存的固定隧道令牌。

    DPAPI 用户绑定意味着复制令牌文件到另一台电脑或另一个 Windows 账号后无法解密；
    调用方会把这种情况当作“尚未配置”，而不是显示敏感错误详情。
    """
    if not sys.platform.startswith("win"):
        raise OSError("固定隧道令牌解密仅支持 Windows")
    source, source_buffer = _bytes_blob(payload)
    output = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = (
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DataBlob),
    )
    crypt32.CryptUnprotectData.restype = ctypes.c_bool
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output)
    ):
        raise OSError(ctypes.get_last_error(), "无法解密固定隧道令牌")
    try:
        return ctypes.string_at(output.data, output.size).decode("utf-8")
    finally:
        kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))
        del source_buffer


def _save_tunnel_token(token: str, path: Path = TUNNEL_TOKEN_PATH) -> None:
    """原子保存经当前 Windows 用户加密的固定隧道令牌。

    自定义文件头用于快速拒绝旧明文或损坏文件；先写 ``.part`` 再原子替换，避免断电时
    留下半份密文。Windows 不完全遵循 POSIX 权限，但 ``chmod(0600)`` 对兼容环境仍有益。
    """
    parsed = _extract_tunnel_token(token)
    if not parsed:
        raise ValueError("固定隧道令牌格式无效")
    encrypted = _TOKEN_FILE_HEADER + _protect_tunnel_token(parsed)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        temporary.write_bytes(encrypted)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)  # 同目录替换，读者只会看到旧文件或完整新文件。
    finally:
        temporary.unlink(missing_ok=True)


def _load_tunnel_token(path: Path = TUNNEL_TOKEN_PATH) -> str:
    """读取固定隧道令牌；无文件、损坏或非本用户数据均视为未配置。

    这里故意不把解密错误写进界面日志，避免泄露令牌文件状态并让普通用户误判为服务故障。
    """
    try:
        payload = path.read_bytes()
        if not payload.startswith(_TOKEN_FILE_HEADER):
            return ""
        token = _unprotect_tunnel_token(payload[len(_TOKEN_FILE_HEADER) :])
    except (OSError, UnicodeError):
        return ""
    return _extract_tunnel_token(token)


def _admin_account_exists(path: Path = DB_PATH) -> bool:
    """只读判断数据库是否已有默认管理员账号。

    表尚未创建、数据库正迁移或文件损坏均返回 ``False``，随后服务端仍会执行权威初始化
    检查；控制台查询只用于决定是否显示首次密码输入框。
    """
    if not path.is_file():
        return False
    connection = None
    try:
        connection = sqlite3.connect(path)
        row = connection.execute(
            "SELECT 1 FROM users WHERE username = 'admin' AND role = 'admin' LIMIT 1"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        if connection is not None:
            connection.close()  # 只读查询也显式关闭，避免 Windows 上短暂占用数据库文件句柄。


from web_control_gui_process import (
    _process_exists, _read_live_pid, _remove_owned_pid, _terminate_pid,
    _windows_process_image, _write_pid,
)
class _TextValue:
    """给 Tk 标签提供与历史调用方相同的最小文本接口。

    这些轻量适配器让旧测试无需依赖具体 Tk 变量，同时不恢复已淘汰的 Qt 控制台。
    """

    def __init__(self, master, value: str = "", style: str = "Body.TLabel") -> None:
        """创建由 ``StringVar`` 驱动的标签，并暴露历史兼容的文本读写接口。

        ``master`` 决定 Tk 变量所属解释器，不能省略或改用全局默认根窗口，否则无界面测试
        和多个窗口实例会共享错误的 Tcl 生命周期。``style`` 只选择 ttk 外观，不参与状态。
        """
        self.variable = tk.StringVar(master, value=value)
        self.widget = ttk.Label(master, textvariable=self.variable, style=style)

    def text(self) -> str:
        """读取标签当前文本。"""
        return self.variable.get()

    def setText(self, value: str) -> None:
        """在 Tk 主线程中更新标签文本。"""
        self.variable.set(value)


class _EntryValue:
    """带文本读写和启用状态的输入控件。"""

    def __init__(self, master, value: str = "", width: int = 24, show: str = "") -> None:
        """创建可由状态机读取和禁用的单行输入框。

        ``show`` 由令牌输入框传入掩码字符；这里只把显示策略交给 Tk，真实值仍保存在
        当前进程的 ``StringVar`` 中，调用方不得把它写入日志或普通界面标签。
        """
        self.variable = tk.StringVar(master, value=value)
        self.widget = ttk.Entry(master, textvariable=self.variable, width=width, show=show)

    def text(self) -> str:
        """读取输入框当前文本。"""
        return self.variable.get()

    def setText(self, value: str) -> None:
        """替换输入框内容。"""
        self.variable.set(value)

    def setEnabled(self, enabled: bool) -> None:
        """切换普通或禁用状态。"""
        self.widget.configure(state="normal" if enabled else "disabled")


class _ChoiceValue:
    """只读选项控件，确保隧道模式只能从既定枚举中选择。"""

    def __init__(self, master, values: tuple[str, ...], value: str) -> None:
        """创建只允许从既定枚举中选择的组合框。

        初始值由控制台配置层校验；控件始终使用 ``readonly``，避免用户输入无法被服务
        启动逻辑识别的隧道模式文本。
        """
        self.variable = tk.StringVar(master, value=value)
        self.widget = ttk.Combobox(
            master,
            textvariable=self.variable,
            values=values,
            state="readonly",
        )

    def text(self) -> str:
        """返回当前选项文字。"""
        return self.variable.get()

    def setEnabled(self, enabled: bool) -> None:
        """保持可用时只读，防止用户输入不在枚举中的模式名称。"""
        self.widget.configure(state="readonly" if enabled else "disabled")


class _SpinValue(_EntryValue):
    """带范围限制的端口输入控件。"""

    def __init__(self, master, value: int, width: int = 10) -> None:
        """创建端口数值框，并把可输入范围限制为非特权 TCP 端口。"""
        self.variable = tk.StringVar(master, value=str(value))
        self.widget = ttk.Spinbox(master, from_=1024, to=65535, textvariable=self.variable, width=width)

    def value(self) -> int:
        """读取并钳制合法 TCP 端口，格式错误时回退默认端口。

        返回结果始终落在非特权端口范围内，调用方无需再防御负数或 65535 以上的值。
        """
        try:
            return max(1024, min(65535, int(self.variable.get())))
        except ValueError:
            return 8787


class _ButtonValue:
    """给按钮提供统一配色和启用状态接口。

    使用 ``tk.Button`` 而非主题按钮是为了在不同 Windows 主题下稳定控制背景色；按钮
    行为仍完全由 Tk 主线程驱动。
    """

    def __init__(self, master, text: str, command, style: str = "Secondary.TButton") -> None:
        """按语义样式创建原生 Tk 按钮并保存其启用态背景色。

        调用方仍以 ttk 风格名表达主操作、公网操作、危险操作或次要操作，本适配层把风格名
        映射为稳定的 Windows 配色。未知风格安全回退为次要按钮，不影响命令绑定。
        """
        palettes = {
            "Primary.TButton": ("#102d47", "#ffffff", "#174463"),
            "Public.TButton": ("#287fa8", "#ffffff", "#226d91"),
            "Danger.TButton": ("#fff4f4", "#b45d63", "#f8e5e6"),
            "Secondary.TButton": ("#ffffff", "#397e88", "#eef8f8"),
        }
        self._background, foreground, active_background = palettes.get(
            style, palettes["Secondary.TButton"]
        )
        self.widget = tk.Button(
            master,
            text=text,
            command=command,
            bg=self._background,
            fg=foreground,
            activebackground=active_background,
            activeforeground=foreground,
            disabledforeground="#a7b3bc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=13,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold" if style in {"Primary.TButton", "Public.TButton"} else "normal"),
        )

    def setEnabled(self, enabled: bool) -> None:
        """切换按钮状态，并使用中性色提示当前动作不可用。"""
        self.widget.configure(
            state="normal" if enabled else "disabled",
            bg=self._background if enabled else "#edf1f4",
        )

    def isEnabled(self) -> bool:
        """供测试和界面状态机读取按钮是否可操作。"""
        return str(self.widget.cget("state")) != "disabled"


class _LogValue:
    """带行数上限的只读运行记录文本框。

    这里只展示面向管理员的启动状态和必要错误，不显示令牌、初始密码或服务端绝对路径。
    """

    def __init__(self, master) -> None:
        """创建默认只读的深色运行记录区，写入时由方法短暂切换状态。"""
        self.widget = tk.Text(
            master,
            height=12,
            wrap="word",
            state="disabled",
            bg="#142b41",
            fg="#c9dce7",
            insertbackground="#ffffff",
            relief="flat",
            padx=12,
            pady=10,
            font=("Consolas", 10),
        )

    def appendPlainText(self, value: str) -> None:
        """追加一条非空记录，并把控件内存限制在最近约四百行。

        Tk 文本框只能在主线程操作；后台读取线程必须先把文本放入窗口队列。删除旧行后再
        滚动到底部，既保持当前状态可见，也防止长时间运行的控制台无限占用内存。
        """
        value = value.strip()
        if not value:
            return
        self.widget.configure(state="normal")
        self.widget.insert("end", value + "\n")
        lines = int(self.widget.index("end-1c").split(".")[0])
        if lines > 400:
            self.widget.delete("1.0", f"{lines - 400}.0")
        self.widget.see("end")
        self.widget.configure(state="disabled")

    def toPlainText(self) -> str:
        """返回当前可见记录，供复制操作和无界面回归测试读取。"""
        return self.widget.get("1.0", "end-1c")

    def clear(self) -> None:
        """清空运行记录，并在操作结束后恢复只读状态。"""
        self.widget.configure(state="normal")
        self.widget.delete("1.0", "end")
        self.widget.configure(state="disabled")


class WebControlWindow(tk.Tk):
    """提供局域网 Web 服务和 Cloudflare Tunnel 的统一控制。

    ``_process``/``_tunnel_process`` 表示本窗口启动并持有句柄的进程；``_external_*_pid``
    表示通过 PID 文件发现、但没有 ``Popen`` 句柄的已有进程。两种状态分开记录，停止和
    日志读取策略因此不同。
    """

    def __init__(self, manage_existing: bool = True) -> None:
        """初始化服务、隧道和界面状态，并按需接管已登记进程。

        ``manage_existing`` 为真时，窗口会读取 PID 文件识别本部署已运行的服务；测试可将其
        关闭以避免访问本机进程。构造阶段只建立状态和控件，服务与隧道仍需用户显式启动，
        因此打开控制台不会意外改变公网暴露状态。
        """
        super().__init__()
        self._manage_existing = manage_existing
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._output_queue: queue.Queue[str] = queue.Queue()  # 后台线程只入队，Tk 主线程负责更新控件。
        self._stopping = False
        self._external_web_pid: int | None = None
        self._external_tunnel_pid: int | None = None
        self._owned_web_pid: int | None = None
        self._tunnel_process: subprocess.Popen[bytes] | None = None
        self._tunnel_stdout = None
        self._tunnel_stderr = None
        self._public_url = ""
        self._pending_public_url = ""
        self._tunnel_connected_logged = False
        self._last_running_state: tuple[bool, bool] | None = None
        self._tunnel_token_configured = bool(_load_tunnel_token())

        self.title("峰运通 Web 服务控制台")
        self.geometry("840x780")
        self.minsize(720, 680)
        icon_path = ROOT / "assets" / "icon.ico"
        if icon_path.is_file() and sys.platform.startswith("win"):
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
                pass
        self._configure_style()
        self._build_ui()
        self._discover_existing_processes()
        self.protocol("WM_DELETE_WINDOW", self.closeEvent)
        self.after(600, self._poll_runtime)  # 定时器同时泵送日志、进程状态和隧道连接状态。
        self._refresh_ui()

    def windowTitle(self) -> str:
        """兼容旧测试和调用方的窗口标题读取接口。"""
        return str(self.title())

    def _configure_style(self) -> None:
        """配置控制台的 ttk 颜色与字体；主题不可用时保留 Tk 默认主题。

        主题选择失败不能阻止控制台打开，因此只捕获 ``TclError`` 并继续使用默认外观。
        """
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if sys.platform.startswith("win") else "clam")
        except tk.TclError:
            pass
        style.configure("Root.TFrame", background="#f4f7fb")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("Address.TFrame", background="#eef9f8", relief="solid", borderwidth=1)
        style.configure("Public.TFrame", background="#f1f6fb", relief="solid", borderwidth=1)
        style.configure("Title.TLabel", background="#f4f7fb", foreground="#17324b", font=("Microsoft YaHei UI", 23, "bold"))
        style.configure("Subtitle.TLabel", background="#f4f7fb", foreground="#7b8c9c", font=("Microsoft YaHei UI", 11))
        style.configure("SmallTitle.TLabel", background="#ffffff", foreground="#728798", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("AddressTitle.TLabel", background="#eef9f8", foreground="#477b83", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("PublicTitle.TLabel", background="#f1f6fb", foreground="#5f7e9a", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#17324b", font=("Microsoft YaHei UI", 10))
        style.configure("Address.TLabel", background="#eef9f8", foreground="#2b8d99", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("PublicAddress.TLabel", background="#f1f6fb", foreground="#327da8", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#718795", font=("Microsoft YaHei UI", 10))
        style.configure("Status.TLabel", background="#edf1f4", foreground="#8a99a5", padding=(12, 6), font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Running.TLabel", background="#e6f7f1", foreground="#1d8b72", padding=(12, 6), font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TunnelStatus.TLabel", background="#e7edf2", foreground="#8a99a5", padding=(9, 4), font=("Microsoft YaHei UI", 9))
        style.configure("TunnelRunning.TLabel", background="#e3f1f8", foreground="#287ca8", padding=(9, 4), font=("Microsoft YaHei UI", 9))
        style.configure("TEntry", padding=7, font=("Microsoft YaHei UI", 10))
        style.configure("TSpinbox", padding=7, font=("Microsoft YaHei UI", 10))

    def _build_ui(self) -> None:
        """构建设置、地址、操作和日志区域，并绑定地址与隧道模式联动。

        控件创建后不自动启动服务或隧道；监听地址与端口变化只刷新展示地址，实际监听
        参数以用户点击启动时的值为准。
        """
        root = ttk.Frame(self, style="Root.TFrame", padding=(28, 24))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(6, weight=1)

        heading = ttk.Frame(root, style="Root.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Web 服务控制台", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="统一管理局域网服务与公网访问", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._status = _TextValue(heading, "已停止", "Status.TLabel")
        self._status.widget.grid(row=0, column=1, rowspan=2, sticky="ne")

        settings = ttk.Frame(root, style="Card.TFrame", padding=(18, 15))
        settings.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        settings.columnconfigure(1, weight=1)
        self._host = _EntryValue(settings, "0.0.0.0")
        self._port = _SpinValue(settings, int(os.environ.get("FYT_WEB_PORT", "8787")))
        default_mode = TUNNEL_MODE_NAMED if self._tunnel_token_configured else TUNNEL_MODE_QUICK
        self._tunnel_mode = _ChoiceValue(
            settings, (TUNNEL_MODE_QUICK, TUNNEL_MODE_NAMED), default_mode
        )
        token_controls = ttk.Frame(settings, style="Card.TFrame")
        token_controls.columnconfigure(0, weight=1)
        self._tunnel_token = _EntryValue(token_controls, "", show="*")
        self._tunnel_token.widget.grid(row=0, column=0, sticky="ew")
        self._save_token_button = _ButtonValue(token_controls, "保存令牌", self._save_token)
        self._save_token_button.widget.grid(row=0, column=1, padx=(8, 0))
        self._clear_token_button = _ButtonValue(token_controls, "清除", self._clear_token)
        self._clear_token_button.widget.grid(row=0, column=2, padx=(8, 0))
        self._token_state = _TextValue(
            settings,
            "已安全保存" if self._tunnel_token_configured else "尚未配置",
            "Muted.TLabel",
        )
        cloudflared = _find_cloudflared()
        self._client_state = _TextValue(settings, "客户端已就绪" if cloudflared else "未找到客户端，请运行 scripts\\install-cloudflared.ps1")
        for row, (label, value) in enumerate(
            (
                ("监听地址", self._host),
                ("端口", self._port),
                ("公网连接模式", self._tunnel_mode),
            )
        ):
            ttk.Label(settings, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 18), pady=5)
            value.widget.grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Label(settings, text="固定隧道令牌", style="Body.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, 18), pady=5
        )
        token_controls.grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(settings, text="令牌状态", style="Body.TLabel").grid(
            row=4, column=0, sticky="w", padx=(0, 18), pady=5
        )
        self._token_state.widget.grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(settings, text="Cloudflare", style="Body.TLabel").grid(
            row=5, column=0, sticky="w", padx=(0, 18), pady=5
        )
        self._client_state.widget.grid(row=5, column=1, sticky="w", pady=5)
        self._host.variable.trace_add("write", lambda *_: self._refresh_address())  # 输入变化立即刷新可复制的局域网地址。
        self._port.variable.trace_add("write", lambda *_: self._refresh_address())
        self._tunnel_mode.widget.bind(
            "<<ComboboxSelected>>", lambda _event: self._on_tunnel_mode_changed()
        )

        local = ttk.Frame(root, style="Address.TFrame", padding=(18, 13))
        local.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        local.columnconfigure(0, weight=1)
        ttk.Label(local, text="局域网访问地址", style="AddressTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self._address = _TextValue(local, self._address_text(), "Address.TLabel")
        self._address.widget.grid(row=1, column=0, sticky="w", pady=(8, 0))
        _ButtonValue(local, "复制", self._copy_address).widget.grid(row=1, column=1, sticky="e", pady=(8, 0))

        public = ttk.Frame(root, style="Public.TFrame", padding=(18, 13))
        public.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        public.columnconfigure(0, weight=1)
        ttk.Label(public, text="公网访问地址", style="PublicTitle.TLabel").grid(row=0, column=0, sticky="w")
        self._tunnel_status = _TextValue(public, "未连接", "TunnelStatus.TLabel")
        self._tunnel_status.widget.grid(row=0, column=1, sticky="e")
        self._public_address = _TextValue(public, "启动公网访问后显示", "PublicAddress.TLabel")
        self._public_address.widget.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._copy_public = _ButtonValue(public, "复制", self._copy_public_address)
        self._copy_public.widget.grid(row=1, column=1, sticky="e", pady=(8, 0))

        actions = ttk.Frame(root, style="Root.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(0, 14))
        self._start = _ButtonValue(actions, "启动局域网服务", self.start_service, "Primary.TButton")
        self._tunnel_start = _ButtonValue(actions, "启动公网访问", self.start_tunnel, "Public.TButton")
        self._tunnel_stop = _ButtonValue(actions, "关闭公网访问", self.stop_tunnel)
        self._stop = _ButtonValue(actions, "全部关闭", self.stop_service, "Danger.TButton")
        for index, button in enumerate((self._start, self._tunnel_start, self._tunnel_stop, self._stop)):
            button.widget.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0))
            actions.columnconfigure(index, weight=1)

        ttk.Label(root, text="运行记录", style="SmallTitle.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 7))
        self._log = _LogValue(root)
        self._log.widget.grid(row=6, column=0, sticky="nsew")
        self._on_tunnel_mode_changed()

    def _discover_existing_processes(self) -> None:
        """从 PID 文件发现已有服务，使控制台重开后仍可显示和关闭它们。

        只有通过 PID 文件校验的进程才会被接管；发现外部隧道时只加载待确认地址，真正的
        连接状态要等扫描日志确认。
        """
        if not self._manage_existing:
            return
        self._external_web_pid = _read_live_pid(WEB_PID_PATH, WEB_PROCESS_NAMES)
        self._external_tunnel_pid = _read_live_pid(TUNNEL_PID_PATH, ("cloudflared.exe",))
        if self._external_web_pid:
            self._append_log(f"[提示] 已检测到运行中的 Web 服务，进程号：{self._external_web_pid}")
        if self._external_tunnel_pid:
            self._append_log(f"[提示] 已检测到运行中的公网隧道，进程号：{self._external_tunnel_pid}")
            self._load_saved_public_url()

    def _address_text(self) -> str:
        """生成局域网访问地址；监听所有网卡时尽力替换为本机可访问 IPv4。

        实际监听地址不因展示值改变；解析失败回退为“本机 IP”，避免控制台直接报错。
        """
        host = self._host.text().strip() if hasattr(self, "_host") else "0.0.0.0"
        port = self._port.value() if hasattr(self, "_port") else 8787
        if host in ("", "0.0.0.0", "::"):
            try:
                host = socket.gethostbyname(socket.gethostname())  # 仅用于展示，不改变实际监听地址。
            except OSError:
                host = "本机 IP"
        return f"http://{host}:{port}/"

    def _refresh_address(self) -> None:
        """在地址标签已经创建后刷新显示值。"""
        if hasattr(self, "_address"):
            self._address.setText(self._address_text())

    def _append_log(self, text: str) -> None:
        """把一条已脱敏状态写入界面日志。

        调用方必须保证传入文本已移除密码、令牌和服务端绝对路径；本方法不执行二次过滤。
        """
        self._log.appendPlainText(text)

    def _using_named_tunnel(self) -> bool:
        """判断当前选择是否为固定命名隧道。"""
        return self._tunnel_mode.text() == TUNNEL_MODE_NAMED

    def _idle_public_text(self) -> str:
        """根据隧道模式和令牌状态生成未连接时的客户提示。"""
        if self._using_named_tunnel():
            if self._tunnel_token_configured:
                return "固定隧道已配置，绑定域名后可访问"
            return "请先粘贴并保存固定隧道令牌"
        return "启动公网访问后显示"

    def _on_tunnel_mode_changed(self) -> None:
        """切换模式后刷新令牌控件、空闲提示和按钮状态。

        未连接时同时更新空闲提示，避免界面停留在上一个模式的旧地址。
        """
        if not self._tunnel_running() and not self._public_url:
            self._public_address.setText(self._idle_public_text())
        self._refresh_ui()

    def _save_token(self) -> None:
        """校验、DPAPI 加密并保存固定隧道令牌，随后清空输入框和局部变量。

        保存失败也不回显令牌；finally 中清空输入框，避免令牌在 Tk 控件或本方法局部变量中
        继续存活。
        """
        token = _extract_tunnel_token(self._tunnel_token.text())
        if not token:
            messagebox.showwarning(
                "令牌格式无效",
                "请粘贴 Cloudflare 提供的连接器令牌或完整安装命令。",
                parent=self,
            )
            return
        try:
            _save_tunnel_token(token)
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", f"无法安全保存固定隧道令牌：{exc}", parent=self)
            return
        finally:
            token = ""
            self._tunnel_token.setText("")  # 无论保存成功与否都不让令牌继续留在可见控件中。
        self._tunnel_token_configured = True
        self._token_state.setText("已安全保存")
        self._tunnel_mode.variable.set(TUNNEL_MODE_NAMED)
        self._public_address.setText(self._idle_public_text())
        self._append_log("[完成] 固定隧道令牌已安全保存，仅当前 Windows 用户可解密。")
        self._refresh_ui()

    def _clear_token(self) -> None:
        """经用户确认后删除加密令牌，并切回无需令牌的临时隧道模式。

        删除操作不要求提供旧令牌；DPAPI 加密文件已绑定当前 Windows 用户，其他人无法使用。
        """
        if not self._tunnel_token_configured:
            return
        if not messagebox.askyesno(
            "清除固定隧道令牌",
            "清除后将无法启动固定命名隧道，是否继续？",
            parent=self,
        ):
            return
        TUNNEL_TOKEN_PATH.unlink(missing_ok=True)
        self._tunnel_token_configured = False
        self._token_state.setText("尚未配置")
        self._tunnel_token.setText("")
        self._tunnel_mode.variable.set(TUNNEL_MODE_QUICK)
        self._public_address.setText(self._idle_public_text())
        self._append_log("[完成] 固定隧道令牌已清除。")
        self._refresh_ui()

    def _web_running(self) -> bool:
        """综合自有子进程和外部 PID 判断 Web 服务是否运行。

        自有进程以 ``poll()`` 为准，外部进程每次重新探测，避免把已回收 PID 当作存活。
        """
        owned = self._process is not None and self._process.poll() is None
        return owned or bool(self._external_web_pid and _process_exists(self._external_web_pid))

    def _tunnel_running(self) -> bool:
        """综合自有子进程和外部 PID 判断隧道是否运行。

        cloudflared 进程存在不代表公网已连接；连接状态由日志扫描单独判定。
        """
        owned = self._tunnel_process is not None and self._tunnel_process.poll() is None
        external = bool(self._external_tunnel_pid and _process_exists(self._external_tunnel_pid))
        return owned or external

    def _set_label_style(self, label: _TextValue, style: str) -> None:
        """切换状态标签的 ttk 样式。"""
        label.widget.configure(style=style)

    def _apply_runtime_controls(self, web_running: bool, tunnel_running: bool, named: bool) -> None:
        """按运行状态启停控件，运行期间锁定监听地址和端口。"""
        any_running = web_running or tunnel_running
        self._start.setEnabled(not web_running)
        self._tunnel_start.setEnabled(not tunnel_running)
        self._tunnel_stop.setEnabled(tunnel_running)
        self._stop.setEnabled(any_running)
        self._host.setEnabled(not any_running)
        self._port.setEnabled(not any_running)
        self._tunnel_mode.setEnabled(not tunnel_running)
        self._tunnel_token.setEnabled(not tunnel_running and named)
        self._save_token_button.setEnabled(not tunnel_running and named)
        self._clear_token_button.setEnabled(
            not tunnel_running and self._tunnel_token_configured
        )
        self._copy_public.setEnabled(bool(self._public_url))

    def _apply_status_labels(self, web_running: bool, tunnel_running: bool) -> None:
        """刷新运行状态与公网连接状态两处文本和样式。"""
        status = "公网运行中" if tunnel_running else "局域网运行中" if web_running else "已停止"
        self._status.setText(status)
        self._set_label_style(
            self._status,
            "Running.TLabel" if web_running or tunnel_running else "Status.TLabel",
        )
        tunnel_connected = tunnel_running and (self._public_url or self._tunnel_connected_logged)  # 命名隧道可能没有可解析的 Quick URL。
        self._tunnel_status.setText(
            "已连接" if tunnel_connected else "连接中" if tunnel_running else "未连接"
        )
        self._set_label_style(
            self._tunnel_status,
            "TunnelRunning.TLabel" if tunnel_connected else "TunnelStatus.TLabel",
        )

    def _refresh_ui(self) -> None:
        """根据两个进程和连接确认状态统一刷新全部控件。

        服务或隧道运行期间锁定监听地址和端口，避免界面显示值与真实进程参数不一致；
        “隧道运行”与“公网已连接”分开表达，前者仅表示 cloudflared 进程仍存在。
        """
        web_running = self._web_running()
        tunnel_running = self._tunnel_running()
        named = self._using_named_tunnel()
        self._apply_runtime_controls(web_running, tunnel_running, named)
        self._apply_status_labels(web_running, tunnel_running)
        self._last_running_state = (web_running, tunnel_running)

    def _drain_web_output(self) -> None:
        """在 Tk 主线程中清空后台日志队列，避免跨线程操作控件。

        Tk 控件只能由主线程操作，后台日志线程只入队；这里每次轮询把队列全部取完。
        """
        while True:
            try:
                self._append_log(self._output_queue.get_nowait())
            except queue.Empty:
                return

    def _start_web_reader(self, process: subprocess.Popen[str]) -> None:
        """启动守护线程持续读取 Web 标准输出并写入线程安全队列。

        守护线程不访问 Tk 控件，主线程轮询队列后再更新运行记录。
        """

        def read_output() -> None:
            """只执行阻塞管道读取，不直接访问任何 Tk 对象。"""
            if process.stdout is None:
                return
            for line in process.stdout:
                self._output_queue.put(line.rstrip())

        self._reader_thread = threading.Thread(target=read_output, name="fyt-web-log", daemon=True)
        self._reader_thread.start()

    def _finalize_web_process(self) -> None:
        """收尾已退出的自有 Web 子进程，清理句柄、PID 文件和界面状态。

        清理前先排空输出队列，尽量把退出前的日志展示完整；PID 文件只在仍指向本进程时删除。
        """
        if self._process is None or self._process.poll() is None:
            return
        process = self._process
        self._drain_web_output()
        exit_code = process.returncode
        process.stdout.close() if process.stdout else None
        self._process = None
        if self._owned_web_pid:
            _remove_owned_pid(WEB_PID_PATH, self._owned_web_pid)
            self._owned_web_pid = None
        if self._stopping:
            self._append_log("[完成] 局域网服务已停止。")
        elif exit_code:
            self._append_log(f"[错误] Web 服务异常退出（代码 {exit_code}）")
        else:
            self._append_log("[完成] Web 服务已停止。")
        self._stopping = False

    def start_service(self) -> None:
        """以隐藏控制台方式启动 Web 服务，并接管日志与 PID 生命周期。

        冻结包直接运行随包 ``web_server.exe``；源码环境使用 ``pythonw.exe``。首次管理员
        密码只加入这一份子进程环境，启动调用结束后立即清空局部变量。
        """
        if self._web_running():
            self._append_log("[提示] Web 服务已经运行。")
            return
        host = self._host.text().strip() or "0.0.0.0"
        port = str(self._port.value())
        env = os.environ.copy()
        env.update({"FYT_WEB_HOST": host, "FYT_WEB_PORT": port, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
        initial_password = self._initial_admin_password()
        if initial_password is None:
            self._append_log("[提示] 已取消启动：尚未设置管理员密码。")
            return
        if initial_password:
            env["FYT_ADMIN_PASSWORD"] = initial_password
        if not self._tunnel_running():
            self._log.clear()
        self._stopping = False
        self._append_log(f"[启动] 正在启动局域网服务 {host}:{port}")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows 下阻止服务弹出 CMD 窗口，其他平台为 0。
        try:
            if getattr(sys, "frozen", False):
                web_server_exe = ROOT / "服务端" / "web_server.exe"
                if not web_server_exe.is_file():
                    web_server_exe = ROOT / "web_server.exe"
                self._process = subprocess.Popen(
                    [str(web_server_exe)],
                    cwd=ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",  # 服务依赖输出异常字节时仍保持日志线程存活。
                    creationflags=creation_flags,
                )
            else:
                self._process = subprocess.Popen(
                    [_windowless_python(), str(ROOT / "web_server.py")],
                    cwd=ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creation_flags,
                )
        except OSError as exc:
            self._process = None
            self._append_log(f"[错误] 无法启动 Web 服务：{exc}")
            self._refresh_ui()
            return
        finally:
            initial_password = ""  # 缩短明文密码在 Python 对象中的存活时间；服务端不会回显它。
        self._owned_web_pid = self._process.pid
        _write_pid(WEB_PID_PATH, self._process.pid)
        self._external_web_pid = None
        self._start_web_reader(self._process)
        self._append_log(f"[完成] 局域网服务已启动：{self._address_text()}")
        self._refresh_ui()

    def _initial_admin_password(self) -> str | None:
        """首次启动时安全采集管理员密码；已有账号返回空串，取消返回 ``None``。

        两次密码输入均使用掩码，策略与服务端保持一致；服务端建库时仍会再次执行权威校验。
        """
        if _admin_account_exists() or os.environ.get("FYT_ADMIN_PASSWORD"):
            return ""
        while True:
            password = simpledialog.askstring(
                "设置管理员密码",
                "首次启动需要设置管理员密码（至少 10 位，同时包含字母和数字）：",
                show="*",
                parent=self,
            )
            if password is None:
                return None
            policy_error = _password_policy_error(password)
            if policy_error:
                messagebox.showwarning("密码不符合要求", policy_error, parent=self)
                continue
            confirmation = simpledialog.askstring(
                "确认管理员密码", "请再次输入管理员密码：", show="*", parent=self)
            if confirmation is None:
                return None
            if confirmation != password:
                messagebox.showwarning("两次输入不一致", "请重新设置管理员密码。", parent=self)
                continue
            return password

    def _ensure_web_for_tunnel(self) -> bool:
        """确保隧道上游 Web 服务已启动，最多等待五秒确认进程仍存活。

        公网入口必须指向本机回环地址，因此启动前把监听地址改为 127.0.0.1；短等待期间
        继续处理 Tk 事件，防止窗口无响应。
        """
        if self._web_running():
            return True
        self._host.setText("127.0.0.1")
        self.start_service()
        deadline = time.monotonic() + 5  # 单调时钟不受系统时间校准影响。
        while time.monotonic() < deadline:
            self._drain_web_output()
            if self._process is not None and self._process.poll() is None:
                return True
            self.update()  # 短等待期间继续处理 Tk 事件，避免窗口假死。
            time.sleep(0.05)
        self._append_log("[错误] Web 服务未能启动，已取消公网连接。")
        return False

    def start_tunnel(self) -> None:
        """启动临时或固定 Cloudflare Tunnel，并把输出写入诊断日志。

        固定令牌仅放入专用子进程环境；启动前移除父环境可能遗留的令牌变量，避免临时
        模式意外使用旧配置。公网地址只有在日志确认连接注册成功后才会开放复制。
        """
        if self._tunnel_running():
            self._append_log("[提示] 公网隧道已经运行。")
            return
        cloudflared = _find_cloudflared()
        if cloudflared is None:
            self._client_state.setText("未找到客户端，请运行 scripts\\install-cloudflared.ps1")
            messagebox.showwarning(
                "缺少 Cloudflare 客户端",
                "请运行 scripts\\install-cloudflared.ps1 自动安装；\n"
                "或手动把 cloudflared.exe 放到：\n%s" % (ROOT / "tools"),
                parent=self,
            )
            return
        self._client_state.setText("客户端已就绪")
        if not _admin_account_exists() and not os.environ.get("FYT_ADMIN_PASSWORD"):
            messagebox.showwarning("需要设置管理员密码", "首次开放公网访问前，请先运行 scripts\\reset-web-admin-password.ps1 设置管理员密码。", parent=self)
            self._append_log("[提示] 已取消公网连接：首次启动需要先设置管理员密码。")
            return
        named = self._using_named_tunnel()
        token = _load_tunnel_token() if named else ""
        if named and not token:
            self._tunnel_token_configured = False
            self._token_state.setText("尚未配置")
            self._public_address.setText(self._idle_public_text())
            messagebox.showwarning(
                "尚未配置固定隧道",
                "请先粘贴并保存 Cloudflare 连接器令牌。",
                parent=self,
            )
            self._append_log("[提示] 已取消固定隧道连接：尚未保存有效令牌。")
            self._refresh_ui()
            return
        if not self._ensure_web_for_tunnel():
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._close_tunnel_files()
        self._tunnel_stdout = TUNNEL_LOG_PATH.open("wb")  # 使用二进制流避免 cloudflared 输出编码影响父进程。
        self._tunnel_stderr = TUNNEL_ERROR_LOG_PATH.open("wb")
        TUNNEL_URL_PATH.unlink(missing_ok=True)
        self._public_url = ""
        self._pending_public_url = ""
        self._public_address.setText("正在连接固定隧道" if named else "正在获取公网地址")
        self._tunnel_connected_logged = False
        command = [str(cloudflared), *_tunnel_arguments(self._port.value(), named)]
        tunnel_env = os.environ.copy()
        tunnel_env.pop("TUNNEL_TOKEN", None)  # 清除服务账号环境中的历史值，模式选择才是唯一来源。
        tunnel_env.pop("TUNNEL_TOKEN_FILE", None)
        if named:
            tunnel_env["TUNNEL_TOKEN"] = token
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._tunnel_process = subprocess.Popen(command, cwd=ROOT, env=tunnel_env, stdin=subprocess.DEVNULL, stdout=self._tunnel_stdout, stderr=self._tunnel_stderr, creationflags=creation_flags)
        except OSError as exc:
            self._close_tunnel_files()
            self._append_log(f"[错误] 公网隧道启动失败：{exc}")
            self._tunnel_process = None
            self._refresh_ui()
            return
        finally:
            token = ""  # 不在窗口实例或日志中长期保留解密后的令牌。
        _write_pid(TUNNEL_PID_PATH, self._tunnel_process.pid)
        self._external_tunnel_pid = None
        mode = "固定命名隧道" if named else "临时公网隧道"
        self._append_log(f"[启动] 正在连接{mode}。")
        self._refresh_ui()

    def _load_saved_public_url(self) -> None:
        """读取上次记录的临时地址，但必须重新扫描日志确认当前连接后才启用。

        文件里的旧地址可能是上次进程留下的，直接展示会误导用户复制失效链接；先置为
        待确认状态，等日志显示注册成功后才开放复制。
        """
        try:
            value = TUNNEL_URL_PATH.read_text(encoding="utf-8-sig").strip()
        except OSError:
            return
        if PUBLIC_URL_PATTERN.fullmatch(value):
            self._pending_public_url = value
            self._public_address.setText("正在确认公网连接")
            self._scan_tunnel_logs()

    def _set_public_url(self, value: str) -> None:
        """确认并公布当前临时公网地址，同时持久化供控制台重开后恢复。

        地址只在匹配 Cloudflare 官方域名模式后才会进入这里，持久化文件同样只保存该地址。
        """
        if not value or value == self._public_url:
            return
        self._public_url = value
        self._public_address.setText(value)
        TUNNEL_URL_PATH.parent.mkdir(parents=True, exist_ok=True)
        TUNNEL_URL_PATH.write_text(f"{value}\n", encoding="utf-8")
        self._append_log(f"[访问] 公网地址：{value}")
        self._refresh_ui()

    def _clear_public_url(self) -> None:
        """清除已确认和待确认地址，并恢复当前模式对应的空闲提示。"""
        self._public_url = ""
        self._pending_public_url = ""
        self._tunnel_connected_logged = False
        self._public_address.setText(self._idle_public_text())
        TUNNEL_URL_PATH.unlink(missing_ok=True)

    def _scan_tunnel_logs(self) -> None:
        """解析 cloudflared 日志并推进“连接中/已连接/重连中”状态机。"""
        texts = []
        for path in (TUNNEL_LOG_PATH, TUNNEL_ERROR_LOG_PATH):
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                texts.append("")
        value, connected = _tunnel_log_state(*texts)
        if value and value != self._public_url:
            self._pending_public_url = value
            if not connected:
                self._public_address.setText("正在确认公网连接")
        if connected and not self._tunnel_connected_logged:
            self._tunnel_connected_logged = True
            if self._pending_public_url:
                self._set_public_url(self._pending_public_url)
            elif self._using_named_tunnel():
                self._public_address.setText("固定隧道已连接，尚未绑定公网域名")
            self._append_log("[完成] 公网隧道已连接。")
            self._refresh_ui()
        elif not connected and self._tunnel_connected_logged:
            self._tunnel_connected_logged = False
            self._public_url = ""
            self._public_address.setText("公网连接中断，正在重连")
            TUNNEL_URL_PATH.unlink(missing_ok=True)
            self._append_log("[提示] 公网连接中断，正在自动重连。")
            self._refresh_ui()

    def _poll_runtime(self) -> None:
        """每 600 毫秒轮询进程、日志和外部 PID，并安排下一次轮询。

        定时轮询避免后台线程触碰 Tk；窗口销毁时 ``after`` 可能抛 ``TclError``，此时静默
        停止调度即可。
        """
        self._drain_web_output()
        if self._process is not None:
            if self._process.poll() is None:
                pass
            else:
                self._finalize_web_process()
        if self._tunnel_process is not None:
            exit_code = self._tunnel_process.poll()
            if exit_code is None:
                self._scan_tunnel_logs()
            else:
                pid = self._tunnel_process.pid
                self._scan_tunnel_logs()
                _remove_owned_pid(TUNNEL_PID_PATH, pid)
                self._close_tunnel_files()
                self._tunnel_process = None
                if exit_code != 0:
                    self._append_log(f"[错误] 公网隧道已断开（代码 {exit_code}），请查看诊断日志。")
                else:
                    self._append_log("[完成] 公网隧道已停止。")
                self._clear_public_url()
        elif self._manage_existing:
            previous_pid = self._external_tunnel_pid
            self._external_tunnel_pid = _read_live_pid(TUNNEL_PID_PATH, ("cloudflared.exe",))
            if self._external_tunnel_pid:
                self._load_saved_public_url()
            elif previous_pid:
                self._clear_public_url()
                self._append_log("[提示] 公网隧道已断开。")
        if self._manage_existing and self._process is None:
            self._external_web_pid = _read_live_pid(WEB_PID_PATH, WEB_PROCESS_NAMES)
        state = (self._web_running(), self._tunnel_running())  # 仅状态变化时重绘，减少无意义控件配置。
        if state != self._last_running_state:
            self._refresh_ui()
        try:
            self.after(600, self._poll_runtime)
        except tk.TclError:
            pass

    def _close_tunnel_files(self) -> None:
        """关闭隧道日志文件句柄，并清空引用以允许后续重新启动。

        父进程关闭自己的文件引用不会中断已继承句柄的子进程写入；下次启动会重新打开新的
        日志文件。
        """
        for stream in (self._tunnel_stdout, self._tunnel_stderr):
            if stream is not None and not stream.closed:
                stream.close()
        self._tunnel_stdout = None
        self._tunnel_stderr = None

    def stop_tunnel(self) -> None:
        """优雅停止自有隧道，超时后强制结束；外部进程则按已验证 PID 终止。"""
        stopped = False
        if self._tunnel_process is not None and self._tunnel_process.poll() is None:
            pid = self._tunnel_process.pid
            self._append_log("[停止] 正在关闭公网隧道。")
            self._tunnel_process.terminate()
            try:
                self._tunnel_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._tunnel_process.kill()
                self._tunnel_process.wait(timeout=2)
            _remove_owned_pid(TUNNEL_PID_PATH, pid)
            self._close_tunnel_files()
            self._tunnel_process = None
            stopped = True
        elif self._external_tunnel_pid:
            pid = self._external_tunnel_pid
            try:
                _terminate_pid(pid)
            except OSError as exc:
                self._append_log(f"[错误] 无法关闭公网隧道：{exc}")
            else:
                TUNNEL_PID_PATH.unlink(missing_ok=True)
                self._external_tunnel_pid = None
                stopped = True
        if stopped:
            self._append_log("[完成] 公网访问已关闭。")
            self._clear_public_url()
        self._refresh_ui()

    def stop_service(self) -> None:
        """先关闭公网入口，再停止 Web 服务，避免隧道继续指向已离线上游。"""
        if self._tunnel_running():
            self.stop_tunnel()
        if self._process is not None and self._process.poll() is None:
            self._append_log("[停止] 正在关闭局域网服务。")
            self._stopping = True
            self._process.terminate()
            try:
                self._process.wait(timeout=0.8)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1.5)
            self._finalize_web_process()
        elif self._external_web_pid:
            pid = self._external_web_pid
            try:
                _terminate_pid(pid)
            except OSError as exc:
                self._append_log(f"[错误] 无法关闭 Web 服务：{exc}")
            else:
                WEB_PID_PATH.unlink(missing_ok=True)
                self._external_web_pid = None
                self._append_log("[完成] 局域网服务已停止。")
        self._refresh_ui()

    def _copy_address(self) -> None:
        """复制当前局域网地址并立即刷新剪贴板所有权。

        立即 ``update()`` 使剪贴板在所有权仍在窗口时完成写入，避免窗口退出后剪贴板失效。
        """
        self.clipboard_clear()
        self.clipboard_append(self._address_text())
        self.update()
        self._append_log("[完成] 局域网地址已复制。")

    def _copy_public_address(self) -> None:
        """仅在地址已经确认可用时复制公网地址。

        未确认或已断开的地址不会被复制，防止管理员把失效链接发给现场人员。
        """
        if not self._public_url:
            return
        self.clipboard_clear()
        self.clipboard_append(self._public_url)
        self.update()
        self._append_log("[完成] 公网地址已复制。")

    def closeEvent(self) -> None:
        """处理窗口关闭：由用户决定保留后台服务、全部停止或取消关闭。

        选择“否”时只销毁窗口并保留后台服务，后续仍可通过 PID 文件重新接管。
        """
        if self._web_running() or self._tunnel_running():
            answer = messagebox.askyesnocancel("服务仍在运行", "关闭控制台时是否同时关闭 Web 服务和公网隧道？", parent=self)
            if answer is None:
                return
            if answer:
                self.stop_service()
        self._close_tunnel_files()
        self.destroy()


def _stop_managed_processes() -> int:
    """供部署包停止入口使用，只关闭 PID 文件记录且映像名匹配的进程。

    返回值遵循命令行约定：全部成功或本就未运行返回 0，任一进程无权终止返回 1。
    """
    failed = False
    for path, names in (
        (TUNNEL_PID_PATH, ("cloudflared.exe",)),
        (WEB_PID_PATH, WEB_PROCESS_NAMES),
    ):
        pid = _read_live_pid(path, names)
        if pid is None:
            continue
        try:
            _terminate_pid(pid)
        except OSError:
            failed = True
        else:
            path.unlink(missing_ok=True)
    return 1 if failed else 0


def main() -> int:
    """解析轻量命令参数并启动 Web 服务控制台。

    ``--stop`` 不创建窗口，适合部署脚本；``--start`` 在窗口事件循环建立后异步启动服务，
    避免构造函数内弹出首次密码对话框导致窗口尚未完成绘制。
    """
    if "--stop" in sys.argv[1:]:
        return _stop_managed_processes()
    window = WebControlWindow()
    if "--start" in sys.argv[1:]:
        window.after(250, window.start_service)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
