# -*- coding: utf-8 -*-
"""
桌面端安全更新检查与安装器下载
================================
更新源统一由 ``core.version`` 配置：显式清单 URL 优先，否则根据 GitHub 仓库拼接
latest release 的 ``latest.json``。两种配置都为空时，检查入口返回 ``None``，界面可
隐藏更新功能而不显示错误。

更新清单(manifest) 约定为一个 JSON：
    {
      "version": "1.1.0",
      "notes": "本次更新说明...",
      "url": "https://.../峰运通数据管理系统_安装_1.1.0.exe",  # 安装包直链
      "mandatory": false
    }

``check_update`` 返回：
    None                         —— 未配置更新源（不显示任何东西）
    {"status": "latest"}         —— 已是最新
    {"status": "update", ...}    —— 有新版本，附带 version/notes/url
    {"status": "error", "msg"}   —— 检查失败（网络等）

安全边界：清单和安装包地址都必须是 HTTPS；清单必须提供 64 位 SHA-256。清单本身
始终从原始可信地址获取，不能经过第三方加速镜像，因为代理若同时篡改安装包地址和
哈希就会绕过完整性校验。安装包下载可使用配置的 GitHub 加速前缀，但最终字节必须与
原清单哈希一致，并在启动前通过旁路 ``.sha256`` 文件再次验证。

下载先写 ``.part``，连接、读取、长度或哈希失败都会清理半包，校验通过后才原子改成
exe。Windows 安装通过无窗口批处理等待当前进程退出、启动并等待安装器、再清理临时
文件；模块只使用标准库，不负责发布清单或替换版本号。
"""
import json
import ssl
import hashlib
import re
import contextlib
import urllib.request

from . import version

# 界面历史协议只把下载 URL 传给下载函数，因此进程内缓存把“实际下载地址”关联到
# 清单哈希。缓存不落盘、不跨重启；下载函数仍允许显式传入哈希并优先使用。
_SHA_CACHE = {}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def manifest_url():
    """按显式 URL、GitHub 仓库、未配置的优先级返回更新清单地址。"""
    if version.UPDATE_MANIFEST_URL:
        return version.UPDATE_MANIFEST_URL
    if version.GITHUB_OWNER and version.GITHUB_REPO:
        # 发布流程把 latest.json 作为最新 Release 的固定名称资产，版本 tag 可自由变化。
        return ("https://github.com/%s/%s/releases/latest/download/latest.json"
                % (version.GITHUB_OWNER, version.GITHUB_REPO))
    return ""


def accelerate(url):
    """为 GitHub 安装包链接添加可选下载加速前缀。

    只处理 ``github.com`` 和 ``raw.githubusercontent.com`` 的 HTTPS 风格链接；非 GitHub
    地址或空前缀原样返回。已经加过前缀的 URL 不会再次套用。此函数只用于安装包，
    更新清单必须直接访问可信源。
    """
    prefix = (getattr(version, "DOWNLOAD_ACCEL_PREFIX", "") or "").strip()
    if not url or not prefix:
        return url
    low = url.lower()
    if not (low.startswith("https://github.com/")
            or low.startswith("https://raw.githubusercontent.com/")):
        return url  # 企业对象存储等非 GitHub 下载源不应被错误改写。
    if not prefix.endswith("/"):
        prefix += "/"
    if url.startswith(prefix):
        return url
    return prefix + url


def _parse_ver(s):
    """把宽松版本文本转换为可比较的三段整数元组。

    允许前导 ``v``/``V``，每个无法转整数的段按零，少于三段补零，多于三段截断。
    这不是完整语义化版本解析器，发布清单应使用纯数字 ``主.次.修订`` 格式。
    """
    parts = []
    for x in str(s).strip().lstrip("vV").split("."):
        try:
            parts.append(int(x))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_update(timeout=8):
    """获取可信更新清单并返回最新、可更新或错误状态，绝不抛异常。

    未配置返回 ``None``。清单 URL、安装包 URL 和 SHA-256 都经过严格校验；只有远端
    三段版本大于本地 ``VERSION_TUPLE`` 才返回更新。下载哈希同时缓存到加速后的实际
    URL，供后续旧界面协议调用 ``download_installer``。
    """
    url = manifest_url()
    if not url:
        return None
    if not url.lower().startswith("https://"):
        return {"status": "error", "msg": "更新清单地址必须使用 HTTPS"}
    # 清单决定“下载什么”和“正确哈希是什么”，必须直接从配置的可信 HTTPS 源获取。
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": version.APP_ID})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            # 清单体积应很小，一次读取后按 UTF-8 JSON 解析即可。
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "msg": str(e)}
    remote = _parse_ver(data.get("version", "0.0.0"))
    if remote > version.VERSION_TUPLE:
        dl_url = data.get("url", "")
        sha256 = (data.get("sha256", "") or "").strip().lower()
        if not (isinstance(dl_url, str) and dl_url.lower().startswith("https://")):
            return {"status": "error", "msg": "更新清单中的安装包地址必须为 HTTPS"}
        if not _SHA256_RE.fullmatch(sha256):
            return {"status": "error", "msg": "更新清单缺少有效 SHA-256，已拒绝下载"}
        # 下载入口先套加速地址再查缓存，因此缓存键必须使用同一实际 URL。
        _SHA_CACHE[accelerate(dl_url)] = sha256
        return {"status": "update",
                "version": data.get("version", ""),
                "notes": data.get("notes", ""),
                "url": dl_url,
                "sha256": sha256,
                "mandatory": bool(data.get("mandatory", False))}
    return {"status": "latest"}


def is_configured():
    """返回是否能解析出更新清单地址，供界面决定是否显示检查入口。"""
    return bool(manifest_url())


def _download_name(url):
    """从 URL 路径提取安全 exe 文件名，无法使用时回退应用固定名称。

    查询参数不属于文件名；只允许 ASCII 字母、数字、点、下划线和连字符，避免远端
    名称注入目录分隔符或命令特殊字符。非 exe URL 统一使用默认 exe 名。
    """
    import os
    base = os.path.basename(url.split("?")[0]) or ""
    if base.lower().endswith(".exe"):
        safe = re.sub(r'[^A-Za-z0-9._-]', "_", base)
        return safe or (version.APP_ID + "_Update.exe")
    return "%s_Update.exe" % version.APP_ID


def _file_sha256(path, chunk=1048576):
    """按默认 1 MiB 分块计算文件 SHA-256，返回小写十六进制串。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def download_installer(url, dest_dir=None, progress=None, log=None, timeout=30,
                       sha256=None):
    """下载、校验并提交安装包到临时或指定目录。

    ``progress`` 接收 0 到 100；服务器没有 Content-Length 时先传 ``-1`` 请求界面切换
    不确定态。``sha256`` 显式值优先，否则读取本进程清单缓存；缺失或格式错误直接
    拒绝下载。网络与校验异常向上抛出，由 Worker 转成友好提示。

    下载写入 ``.part``，已知长度时必须精确吻合，随后计算强制 SHA-256。全部验证通过
    才原子替换正式 exe，并写入 ASCII 哈希旁路文件供 ``run_installer`` 二次验证。
    """
    import os
    import ssl
    import tempfile
    import urllib.request

    if not url:
        raise ValueError("下载地址为空，无法下载安装包。")
    if not url.lower().startswith("https://"):
        raise ValueError("更新下载地址必须使用 HTTPS。")
    url = accelerate(url)
    # 显式哈希支持调用方绕过进程缓存；否则按实际加速后地址取清单阶段缓存。
    expect_sha = (sha256 or _SHA_CACHE.get(url) or "").strip().lower()
    if not _SHA256_RE.fullmatch(expect_sha):
        raise ValueError("缺少有效 SHA-256，已拒绝下载未认证安装包。")
    dest_dir = dest_dir or os.path.join(tempfile.gettempdir(), version.APP_ID + "_update")
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    dest = os.path.join(dest_dir, _download_name(url))
    part = dest + ".part"
    try:
        if os.path.exists(part):
            os.remove(part)
    except OSError:
        # 旧半包无法删除时后续打开写入会给出更具体错误，这里不掩盖主流程。
        pass
    if log:
        log("正在连接下载服务器…")
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": version.APP_ID})
    try:
        response_cm = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except Exception:
        # 当前实现不支持断点续传，连接失败时必须清掉旧半包，避免误认成完整文件。
        try:
            if os.path.exists(part):
                os.remove(part)
        except OSError:
            pass
        raise
    @contextlib.contextmanager
    def _response_with_cleanup():
        """包装 HTTP 响应，确保读取或关闭异常时删除不完整的 ``.part``。"""
        try:
            with response_cm as resp:
                yield resp
        except Exception:
            # 读取中断、响应关闭失败等异常同样不能残留半包。
            try:
                if os.path.exists(part):
                    os.remove(part)
            except OSError:
                pass
            raise

    with _response_with_cleanup() as resp:
        total = int(resp.headers.get("Content-Length", 0) or 0)
        done = 0
        indeterminate_notified = False
        with open(part, "wb") as f:
            while True:
                # 64 KiB 块在进度更新频率和磁盘吞吐之间取得平衡。
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total > 0:
                    if progress:
                        # 校验完成前最多报告 99%，100% 只在哈希与原子替换成功后发送。
                        progress(min(99, done * 100 // total))
                    if log and done % (2 * 1024 * 1024) < 65536:
                        log("已下载 %.1f / %.1f MB" % (done / 1048576.0, total / 1048576.0))
                else:
                    # 未知总长只通知一次不确定态，并每约 2 MiB 提供文字进度。
                    if progress and not indeterminate_notified:
                        progress(-1)
                        indeterminate_notified = True
                    if log and done % (2 * 1024 * 1024) < 65536:
                        log("已下载 %.1f MB…" % (done / 1048576.0))
    # 第一层完整性：服务器声明长度时，实际字节数必须精确一致。
    if total > 0 and done != total:
        try:
            os.remove(part)
        except OSError:
            pass
        raise IOError("下载不完整，请重试（已收 %d/%d 字节）。" % (done, total))
    # 第二层完整性与来源约束：强制匹配可信清单中的 SHA-256。
    actual = _file_sha256(part)
    if actual.lower() != expect_sha:
        try:
            os.remove(part)
        except OSError:
            pass
        raise IOError("安装包校验失败（哈希不匹配），已拒绝运行，请重试或联系管理员。")
    if log:
        log("哈希校验通过。")
    os.replace(part, dest)
    # 旁路哈希不用于下载验证，只用于安装启动前确认文件在下载后未被替换。
    with open(dest + ".sha256", "w", encoding="ascii") as file_obj:
        file_obj.write(expect_sha)
    if progress:
        progress(100)
    if log:
        log("下载完成：%s" % dest)
    return dest


# 批处理助手必须等当前程序退出后再启动安装器。无窗口 cmd 的管道在此场景不稳定，
# 因而用 tasklist 重定向文件再 findstr；start /wait 等整个安装向导结束后才清理 exe、
# 哈希旁路文件和助手自身，避免安装器仍占用文件时过早删除。
_HELPER_BAT = (
    "@echo off\r\n"
    ":wait\r\n"
    "tasklist /FI \"PID eq __PID__\" /NH > \"__CK__\" 2>nul\r\n"
    "findstr /I /C:\"__EXE__\" \"__CK__\" >nul\r\n"
    "if not errorlevel 1 (\r\n"
    "  ping -n 2 127.0.0.1 >nul\r\n"
    "  goto wait\r\n"
    ")\r\n"
    "del \"__CK__\" 2>nul\r\n"
    "start \"\" /wait \"__INST__\"\r\n"
    "del \"__INST__\" 2>nul\r\n"
    "del \"__INST__.sha256\" 2>nul\r\n"
    "del \"%~f0\"\r\n"
)


def run_installer(path):
    """二次校验并在当前程序退出后启动安装器。

    调用方在函数返回后应立即退出应用并释放旧程序文件。启动前要求同目录存在下载阶段
    写入的 ``.sha256``，并重新计算安装包哈希。Windows 创建无窗口批处理助手轮询当前
    PID，父进程退出后再启动安装器并等待完成；助手创建失败时回退 ``os.startfile``。
    非 Windows 环境直接 ``Popen``，主要供兼容测试，不承担 Linux 服务端升级。
    """
    import os
    import sys
    import subprocess

    if not path or not os.path.isfile(path):
        raise FileNotFoundError("安装包不存在：%s" % path)
    if not path.lower().endswith(".exe"):
        raise ValueError("更新安装包必须是 .exe 文件")
    try:
        with open(path + ".sha256", "r", encoding="ascii") as file_obj:
            expected = file_obj.read().strip().lower()
        if not _SHA256_RE.fullmatch(expected) or _file_sha256(path) != expected:
            raise ValueError("安装包校验失败，已拒绝启动")
    except OSError as error:
        raise ValueError("找不到已验证的安装包校验记录，已拒绝启动") from error
    if not sys.platform.startswith("win"):
        # 哈希已在平台分支前验证；非 Windows 不使用批处理等待机制。
        subprocess.Popen([path]); return

    try:
        exe = os.path.basename(sys.executable) or (version.APP_ID + ".exe")
        work = os.path.dirname(os.path.abspath(path))
        ck = os.path.join(work, "_upd_check.txt")
        # 替换固定占位符而非拼接命令行片段，批处理模板的执行顺序保持可审计。
        bat = (_HELPER_BAT.replace("__PID__", str(os.getpid()))
               .replace("__EXE__", exe).replace("__INST__", os.path.abspath(path))
               .replace("__CK__", ck))
        bat_path = os.path.join(work, "_run_update.bat")
        # cmd 在中文 Windows 下使用系统 ANSI，mbcs 可正确表达中文用户名路径。
        with open(bat_path, "w", encoding="mbcs") as f:
            f.write(bat)
        # CREATE_NO_WINDOW 防止桌面更新时闪出额外命令窗口。
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(["cmd", "/c", bat_path], close_fds=True,
                         creationflags=CREATE_NO_WINDOW)
    except Exception:
        # 回退仍启动经过双重哈希校验的同一安装包，不降低完整性要求。
        os.startfile(path)
