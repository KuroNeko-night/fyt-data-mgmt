# -*- coding: utf-8 -*-
"""
更新检查（为 GitHub Releases 预留，仓库暂未创建）
==================================================
设计目标：仓库还没建时也不报错；日后在 version.py 填好 OWNER/REPO 或
UPDATE_MANIFEST_URL 即可自动生效，无需改动本文件或界面。

更新清单(manifest) 约定为一个 JSON：
    {
      "version": "1.1.0",
      "notes": "本次更新说明...",
      "url": "https://.../峰运通数据管理系统_安装_1.1.0.exe",  # 安装包直链
      "mandatory": false
    }

check_update() 返回：
    None                         —— 未配置更新源（不显示任何东西）
    {"status": "latest"}         —— 已是最新
    {"status": "update", ...}    —— 有新版本，附带 version/notes/url
    {"status": "error", "msg"}   —— 检查失败（网络等）

仅用标准库(urllib)，不引入额外依赖，兼容 Win7 + Python 3.8。
"""
import json
import ssl
import hashlib
import urllib.request

from . import version

# 清单里 url→sha256 的缓存：check_update 解析清单时填入，download_installer
# 校验时按下载地址取回。因界面层(about_page)只把 url 传给下载函数、拿不到
# sha256，故用本进程内缓存搭桥；不影响向后兼容(清单无 sha256 则不缓存)。
_SHA_CACHE = {}


def manifest_url():
    """解析实际使用的清单地址：显式 URL 优先，其次由 OWNER/REPO 拼 GitHub latest。"""
    if version.UPDATE_MANIFEST_URL:
        return version.UPDATE_MANIFEST_URL
    if version.GITHUB_OWNER and version.GITHUB_REPO:
        # GitHub Releases 约定：把 latest.json 作为 release asset 上传到 latest tag
        return ("https://github.com/%s/%s/releases/latest/download/latest.json"
                % (version.GITHUB_OWNER, version.GITHUB_REPO))
    return ""


def accelerate(url):
    """给 GitHub 链接套上加速镜像前缀（若已配置）。

    只对 github.com / raw.githubusercontent.com 生效，其余地址原样返回。
    前缀为空则不加速。幂等：不会重复套用。
    """
    prefix = (getattr(version, "DOWNLOAD_ACCEL_PREFIX", "") or "").strip()
    if not url or not prefix:
        return url
    low = url.lower()
    if not (low.startswith("https://github.com/")
            or low.startswith("https://raw.githubusercontent.com/")):
        return url                       # 非 GitHub 链接不动
    if not prefix.endswith("/"):
        prefix += "/"
    if url.startswith(prefix):
        return url                       # 已套过，避免重复
    return prefix + url


def _parse_ver(s):
    """'1.2.3' -> (1,2,3)；解析失败返回 (0,0,0)。"""
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
    """检查是否有新版本。见模块文档的返回约定。绝不抛异常。"""
    url = manifest_url()
    if not url:
        return None                      # 未配置更新源
    url = accelerate(url)                # 清单拉取也走加速，防 GitHub 被墙时连清单都读不到
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": version.APP_ID})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "msg": str(e)}
    remote = _parse_ver(data.get("version", "0.0.0"))
    if remote > version.VERSION_TUPLE:
        dl_url = data.get("url", "")
        sha256 = (data.get("sha256", "") or "").strip().lower()   # 可选:清单提供才有
        if dl_url and sha256:
            # 缓存到"实际下载地址(套加速后)"下,供 download_installer 校验取回
            _SHA_CACHE[accelerate(dl_url)] = sha256
        return {"status": "update",
                "version": data.get("version", ""),
                "notes": data.get("notes", ""),
                "url": dl_url,
                "sha256": sha256,
                "mandatory": bool(data.get("mandatory", False))}
    return {"status": "latest"}


def is_configured():
    """更新源是否已配置（界面据此决定"检查更新"按钮是否可用）。"""
    return bool(manifest_url())


def _download_name(url):
    """从下载地址推断安装包文件名，取不到就用默认名。"""
    import os
    base = os.path.basename(url.split("?")[0]) or ""
    if base.lower().endswith(".exe"):
        return base
    return "%s_Update.exe" % version.APP_ID


def _file_sha256(path, chunk=1048576):
    """分块读取计算文件 SHA256(大文件不占内存)。返回小写十六进制串。"""
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
    """下载安装包到临时目录，返回本地路径。

    progress(pct): 可选回调，报告 0~100 进度百分比（供界面进度条）；
                   服务器不返回 Content-Length 时传 -1 表示"不确定进度"，
                   调用方可据此切进度条为不确定态(此处同时按 KB 周期性 log)。
    log(msg):      可选回调，输出文字日志。
    sha256:        可选期望哈希；未显式传入则回退到清单缓存(_SHA_CACHE)。
                   校验不通过将删文件并抛错，绝不返回可疑安装包。
    出错抛异常（由上层 Worker 捕获转成友好提示）。
    """
    import os
    import ssl
    import tempfile
    import urllib.request

    if not url:
        raise ValueError("下载地址为空，无法下载安装包。")
    url = accelerate(url)                # 安装包下载套加速镜像
    # 期望哈希：优先用显式入参，否则取清单缓存(按套加速后的地址)
    expect_sha = (sha256 or _SHA_CACHE.get(url) or "").strip().lower()
    dest_dir = dest_dir or os.path.join(tempfile.gettempdir(), version.APP_ID + "_update")
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    dest = os.path.join(dest_dir, _download_name(url))
    if log:
        log("正在连接下载服务器…")
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": version.APP_ID})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        total = int(resp.headers.get("Content-Length", 0) or 0)
        done = 0
        indeterminate_notified = False
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total > 0:
                    if progress:
                        progress(min(99, done * 100 // total))
                    if log and done % (2 * 1024 * 1024) < 65536:
                        log("已下载 %.1f / %.1f MB" % (done / 1048576.0, total / 1048576.0))
                else:
                    # 服务器未给 Content-Length：切不确定态(progress=-1)，
                    # 并按已下载 KB 周期性 log，避免进度条永远卡在 0。
                    if progress and not indeterminate_notified:
                        progress(-1)
                        indeterminate_notified = True
                    if log and done % (2 * 1024 * 1024) < 65536:
                        log("已下载 %.1f MB…" % (done / 1048576.0))
    # 完整性校验一：total 已知时字节数必须吻合，截断包一律拒绝
    if total > 0 and done != total:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise IOError("下载不完整，请重试（已收 %d/%d 字节）。" % (done, total))
    # 完整性校验二：清单提供了 sha256 时校验哈希，不匹配则删包拒绝，
    # 绝不把来路不明的 exe 交给 run_installer 以管理员权限执行。
    if expect_sha:
        actual = _file_sha256(dest)
        if actual.lower() != expect_sha:
            try:
                os.remove(dest)
            except OSError:
                pass
            raise IOError("安装包校验失败（哈希不匹配），已拒绝运行，请重试或联系管理员。")
        if log:
            log("哈希校验通过。")
    if progress:
        progress(100)
    if log:
        log("下载完成：%s" % dest)
    return dest


# 等本程序进程退出后再拉起安装器，装完自动清理安装包。
# 关键点：
#  1) 无窗口 cmd 下管道 `|` 不可靠(第二段拿不到 stdin)，故用「tasklist 重定向到文件
#     + findstr 查文件」替代 `tasklist | find`；findstr 命中返回 0、未命中返回 1，判断进程是否还在。
#  2) start 加 /wait：Inno 引导进程会等提权副本装完才退出，故本行会阻塞到安装向导整个结束，
#     其后再删安装包才安全(此时新程序已装到 Program Files，不再占用临时目录里的安装包)。
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
    "del \"%~f0\"\r\n"
)


def run_installer(path):
    """启动安装包（会触发 UAC 提权、弹出安装向导）。

    调用方在本函数返回后应立即退出本程序，释放对旧文件的占用。
    Win 上通过 detached 批处理助手在“本进程退出后”再拉起安装器：
    助手全程存活，提权由存活进程发起，规避 Win7 下父进程提前退出
    导致提权请求被系统丢弃、安装器不打开的问题。安装向导结束后，
    助手会自动删除临时目录里的安装包与自身。失败则回退到 os.startfile。
    """
    import os
    import sys
    import subprocess

    if not path or not os.path.exists(path):
        raise FileNotFoundError("安装包不存在：%s" % path)
    if not sys.platform.startswith("win"):
        subprocess.Popen([path]); return

    try:
        exe = os.path.basename(sys.executable) or (version.APP_ID + ".exe")
        work = os.path.dirname(os.path.abspath(path))
        ck = os.path.join(work, "_upd_check.txt")
        bat = (_HELPER_BAT.replace("__PID__", str(os.getpid()))
               .replace("__EXE__", exe).replace("__INST__", os.path.abspath(path))
               .replace("__CK__", ck))
        bat_path = os.path.join(work, "_run_update.bat")
        with open(bat_path, "w", encoding="mbcs") as f:   # mbcs=系统 ANSI，兼容中文用户名路径
            f.write(bat)
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(["cmd", "/c", bat_path], close_fds=True,
                         creationflags=CREATE_NO_WINDOW)
    except Exception:
        os.startfile(path)          # 回退：manifest 仍会请求管理员权限（Win10/11 一般可用）
