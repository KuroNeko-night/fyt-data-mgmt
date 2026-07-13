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
import urllib.request

from . import version


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
        return {"status": "update",
                "version": data.get("version", ""),
                "notes": data.get("notes", ""),
                "url": data.get("url", ""),
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


def download_installer(url, dest_dir=None, progress=None, log=None, timeout=30):
    """下载安装包到临时目录，返回本地路径。

    progress(pct): 可选回调，报告 0~100 进度百分比（供界面进度条）。
    log(msg):      可选回调，输出文字日志。
    出错抛异常（由上层 Worker 捕获转成友好提示）。
    """
    import os
    import ssl
    import tempfile
    import urllib.request

    if not url:
        raise ValueError("下载地址为空，无法下载安装包。")
    url = accelerate(url)                # 安装包下载套加速镜像
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
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(99, done * 100 // total))
                if log and total and done % (2 * 1024 * 1024) < 65536:
                    log("已下载 %.1f / %.1f MB" % (done / 1048576.0, total / 1048576.0))
    if progress:
        progress(100)
    if log:
        log("下载完成：%s" % dest)
    return dest


def run_installer(path):
    """启动安装包（会触发 UAC 提权、弹出安装向导）。

    调用方在本函数返回后应立即退出本程序，释放对旧文件的占用，
    安装向导才能顺利覆盖更新。
    """
    import os
    import sys
    import subprocess

    if not path or not os.path.exists(path):
        raise FileNotFoundError("安装包不存在：%s" % path)
    if sys.platform.startswith("win"):
        os.startfile(path)          # 用系统默认方式运行 exe，manifest 会自动请求管理员权限
    else:
        subprocess.Popen([path])
