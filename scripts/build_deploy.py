# -*- coding: utf-8 -*-
"""构建纯净源码包、Windows Web 服务包和 Linux 服务端包。

三个交付物采用彼此独立的内容白名单：源码包保留开发所需文件但排除运行数据与生成物；
Windows 包使用 PyInstaller 的 onedir 产物并附带静态前端和 Cloudflare 客户端；Linux 包
保留 Python 源码，通过安装脚本在目标机创建独立虚拟环境和 systemd 服务。

本脚本只在 ``dist`` 暂存和输出构建产物，不读取项目 ``web-data``。运行数据库、账号、
上传文件、日志、缓存、证书私钥和本地环境文件都由排除规则挡在发布包之外。Linux 包还会
显式写入 Unix 权限元数据，使其从 Windows 构建机解压到 Linux 后仍可直接执行安装脚本。

用法（项目根目录）：
    .venv\\Scripts\\python.exe scripts\\build_deploy.py
    .venv\\Scripts\\python.exe scripts\\build_deploy.py --linux-only

产物：
    dist/deploy/source/峰运通数据管理系统_源码_v<版本>/    （不含运行数据与构建缓存）
    dist/deploy/windows/峰运通服务端_windows_v<版本>/   （PyInstaller 免安装包）
    dist/deploy/linux/fyt-server-linux-v<版本>/       （源码 + 安装脚本，ASCII 路径）
    dist/峰运通数据管理系统_源码_v<版本>.zip
    dist/峰运通服务端_windows_v<版本>.zip
    dist/fyt-server-linux-v<版本>.zip
"""
from __future__ import annotations

import os
import argparse
import hashlib
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 构建路径锚定仓库，不依赖终端当前目录。
PYTHON = sys.executable  # 必须使用当前项目虚拟环境解释器，避免调用到全局 PyInstaller。
VENV_PYINSTALLER = [PYTHON, "-m", "PyInstaller"]

# Docker 与 Linux 包共用同一运行依赖锁文件，避免部署方式之间悄然出现版本差异。
RUNTIME_REQUIREMENTS_PATH = os.path.join(ROOT, "requirements-runtime.txt")

# Linux 安装与 systemd 单元模板的事实源；构建时只从该目录筛选，避免出现多份漂移副本。
LINUX_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packaging", "linux")

LINUX_README = """# 峰运通数据管理系统 —— Linux 服务端部署包

本包可从任意目录解压，包括中文目录；安装后会把程序复制到固定的 ASCII 路径，避免 Linux、systemd 和权限处理中文路径时出现问题。

## 环境要求
- Linux x86_64，支持 Alibaba Cloud Linux 3、Ubuntu 22.04+、Debian 12+、CentOS Stream 9+
- Python 3.10 及以上；Alibaba Cloud Linux 3 请保留系统 Python，并行安装 Python 3.11
- systemd、sudo、unzip、tar、curl

## 首次安装
```bash
sudo mkdir -p /opt/fyt
sudo unzip fyt-server-linux-v*.zip -d /opt/fyt
cd /opt/fyt/fyt-server-linux-v<VERSION>
sudo bash install.sh
```

安装器会自动创建独立虚拟环境、安装依赖、创建 `fyt-web` 低权限账号、初始化数据库、注册开机自启动服务并执行健康检查。初始管理员密码只在首次建库时显示一次。

## 固定目录
- 程序：`/opt/fyt/server`
- 配置：`/etc/fyt-web/fyt-web.env`
- 运行数据：`/var/lib/fyt-web`
- 安装备份：`/var/backups/fyt-web`
- systemd 服务：`fyt-web.service`

升级时只需解压新版包并重新执行 `sudo bash install.sh`。安装器会先备份数据，再切换程序目录；运行数据不会跟随新版程序覆盖。

## 常用命令
```bash
sudo bash /opt/fyt/server/status.sh
sudo bash /opt/fyt/server/restart.sh
sudo bash /opt/fyt/server/stop.sh
sudo bash /opt/fyt/server/logs.sh 100
sudo bash /opt/fyt/server/backup.sh
```

健康检查：
```bash
curl http://127.0.0.1:8787/api/health
```

## 可选配置
- `FYT_WEB_PORT`：服务端口，默认 `8787`
- `FYT_WEB_HOST`：监听地址，默认 `0.0.0.0`
- `FYT_ADMIN_PASSWORD`：首次安装时指定管理员密码，至少10位且包含字母和数字
- `FYT_PYTHON`：指定 Python 3.10+ 的绝对路径
- `PIP_INDEX_URL`：pip 镜像源
- `FYT_LEGACY_DATA_DIR`：从旧中文部署目录迁移 `web-data` 的路径
- `FYT_DATA_DIR`：自定义数据目录，必须是绝对 ASCII 路径

例如：
```bash
sudo env FYT_WEB_PORT=8787 PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ bash install.sh
```

## 公网访问
临时测试可在阿里云安全组和系统防火墙放行 TCP 8787；正式服务建议使用 Caddy/Nginx 监听 80/443 并反向代理到 `127.0.0.1:8787`，不长期暴露 8787。Cloudflare Tunnel 脚本仍随包提供，但需要单独授权与配置。

## 安全
程序使用专用低权限账号运行，配置文件为 root:fyt-web，运行数据为 fyt-web:fyt-web 且目录权限为700。不要将 `web-data`、管理员密码、证书私钥或日志加入发布包。
"""

WINDOWS_README = """峰运通数据管理系统 —— Windows 服务端整合包
==============================================

本包用于在 Windows 电脑上部署峰运通 Web 服务（免安装 Python）。
局域网内所有电脑通过浏览器访问：http://<本机IP>:8787

一、启动服务
  双击「启动服务.bat」会打开控制台并自动启动服务；也可以直接打开
  「峰运通服务控制台.exe」后手动启动。

二、停止服务
  双击「停止服务.bat」，或在控制台界面点「停止」。

三、首次使用
  1. 首次启动时，控制台会要求两次输入管理员密码，不会在页面或日志显示。
  2. 启动服务后，浏览器打开 http://127.0.0.1:8787
  3. 管理员账号为 admin，密码是首次启动时设置的值。
  3. 登录后请立即在「账号安全」中修改密码；普通员工可自行注册，由管理员审核。

四、目录说明
  web-data\\   运行数据（账号、上传、输出、备份）——升级前请整体备份
  web-app\\    前端静态页面（勿删）
  服务端\\     Web 服务程序（web_server.exe）
  控制台\\     服务启停控制台（峰运通服务控制台.exe）
  桥接\\       任务处理程序（bridge_worker.exe）
  tools\\      已随包附带 Cloudflare Tunnel 客户端（cloudflared.exe）

五、升级
  停止服务 → 备份 web-data → 用新包覆盖程序文件（保留 web-data）→ 重新启动。

六、常见问题
  · 其他电脑访问不了：检查 Windows 防火墙是否放行 8787 端口，或改用 0.0.0.0 监听。
  · 公网访问：在服务控制台中选择临时或固定隧道并启动，无需另装 cloudflared。
  · 忘记管理员密码：停止服务后使用管理员密码重置工具，不要删除账号数据库。
  · 桌面端与服务器模式：桌面端可「连接服务器」直接使用本服务，或离线使用本地功能。
"""

SOURCE_README = """# 峰运通数据管理系统 —— 纯净源码包

本包包含桌面端、Web 端、Python 业务核心、服务端、打包脚本、测试与项目文档。

已排除：虚拟环境、node_modules、构建产物、运行数据库、账号与上传数据、日志、缓存、
临时文件、可执行文件、安装包和真实业务输出。解压后需自行安装依赖并重新构建。

## 开发环境

- Windows 10/11
- Python 3.13
- Node.js 与 npm
- Rust stable MSVC（构建 Tauri 桌面端时需要）

## 基础验证

```powershell
$env:PYTHONIOENCODING="utf-8"
.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"
npm --prefix web-app run build
npm --prefix tauri-app run build
```

服务端部署包使用 `scripts/build_deploy.py` 重新生成。
"""

# URL 指向 Cloudflare 官方 latest 发行资源；实际版本会在打包时执行 --version 并写入来源说明。
CLOUDFLARED_WINDOWS_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-windows-amd64.exe"
)

# 源码包根文件采用显式白名单，新出现的敏感配置不会因为位于根目录而自动进入包中。
SOURCE_ROOT_FILES = (
    ".editorconfig",
    ".dockerignore",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-runtime.txt",
    "web_control_gui.py",
    "web_server.py",
)

# 这里只列出项目维护源码和文档目录；web-data、dist 与依赖目录不在候选范围内。
SOURCE_DIRS = (
    ".github",
    "assets",
    "core",
    "design-system",
    "docker",
    "docs",
    "packaging",
    "scripts",
    "secrets",
    "tauri-app",
    "tests",
    "web-app",
    "web_backend",
)

# 即使某个候选源码目录内部嵌套了运行数据或生成目录，也会在 copytree 回调中再次排除。
SOURCE_IGNORED_DIRS = {
    ".codex-audit",
    ".playwright-mcp",
    ".pytest_cache",
    ".reasonix",
    ".venv",
    "__pycache__",
    "art-generation",
    "build",
    "dist",
    "gen",
    "node_modules",
    "target",
    "tmp",
    "web-data",
}


def run(command: list[str]) -> None:
    """在仓库根目录执行构建命令，失败时立即停止后续打包。

    参数：
        command: 要执行的命令及参数列表；执行前会打印，便于人工核对打包动作。
    返回值：
        无。
    副作用：
        在仓库根目录启动子进程，标准输出与错误直接继承当前控制台。
    异常：
        命令非零退出时抛出 ``subprocess.CalledProcessError``，用于快速终止整条打包链。
    """

    print(">>", " ".join(str(item) for item in command))  # 回显命令，便于核对构建步骤
    subprocess.run(command, cwd=ROOT, check=True)  # 固定仓库根执行，失败即终止打包链


def build_web_dist() -> None:
    """构建 Web 静态文件；Windows 通过 cmd 解析 npm.cmd，其他平台直接调用 npm。

    返回值：
        无。
    副作用：
        在 ``web-app/dist`` 生成或覆盖静态文件。
    不变量：
        任何部署包复制前端产物前都必须先调用本函数，保证页面与当前源码版本一致。
    异常：
        由 ``run`` 透传的 ``subprocess.CalledProcessError``。
    """

    if sys.platform.startswith("win"):
        run(["cmd", "/c", "npm", "--prefix", "web-app", "run", "build"])  # Windows 需经 cmd 解析 npm.cmd
    else:
        run(["npm", "--prefix", "web-app", "run", "build"])  # 类 Unix 直接调用 npm


# 保留该映射以兼容既有构建脚本导入接口；当前三类包均通过明确函数组装内容。
CONTENT_DIRS: dict[str, str] = {}


def _source_ignore(directory: str, names: list[str]) -> set[str]:
    """返回源码包中应排除的本地数据、缓存、密钥候选和生成文件。

    此函数由 ``shutil.copytree`` 对每一级目录调用，因此判断既要考虑当前文件名，也要
    结合相对目录处理资源源图等特殊情况。返回值只影响源码副本，不删除仓库中的文件。
    """

    ignored: set[str] = set()  # 收集本层需排除的候选名
    # 统一为 POSIX 相对路径，保证 Windows 构建机上逐级目录比较与白名单书写一致。
    relative_dir = os.path.relpath(directory, ROOT).replace("\\", "/")  # 路径统一为斜杠，便于规则比对
    for name in names:
        path = os.path.join(directory, name)  # 拼出完整路径供目录判断
        lower = name.lower()  # 统一小写，锁定扩展名匹配
        if os.path.isdir(path) and name in SOURCE_IGNORED_DIRS:
            ignored.add(name)  # 排除运行数据与生成目录
            continue
        if relative_dir == "assets/generated" and name == "_source":
            # 对话生成的原始大图不属于运行资产，正式资源只取 manifest 中已验收的输出。
            ignored.add(name)
            continue
        if relative_dir == "secrets" and name != "admin-password.example.txt":
            # Docker secret 目录只允许公开空示例，真实初始密码文件永不进入源码包。
            ignored.add(name)
            continue
        if lower.startswith(".env") and lower != ".env.example":
            # 仅示例配置可公开；实际 .env 可能包含密码、令牌或部署地址。
            ignored.add(name)
            continue
        if lower.endswith((
            ".bak", ".cer", ".crt", ".db", ".db-shm", ".db-wal", ".exe",
            ".key", ".log", ".msi", ".part", ".pem", ".pfx", ".p12",
            ".pid", ".pyc", ".pyo", ".secret", ".sqlite", ".sqlite3",
            ".token", ".tsbuildinfo", ".zip",
        )):
            ignored.add(name)
            continue
        if lower in {"vite.config.js", "vite.config.d.ts"}:
            ignored.add(name)
    return ignored


def build_source_bundle(version: str) -> str:
    """按根文件和目录白名单组装可公开上传的纯净源码副本。

    同版本暂存目录会被重建，但删除范围严格限定在 ``dist/deploy/source`` 下。维护规范
    现在属于仓库根文件；仅在兼容旧工作区布局时，才从仓库上一级补充 ``AGENTS.md``。

    参数：
        version: ``core/version.py`` 中的版本号，只用于命名暂存目录。
    返回值：
        组装完成的暂存目录绝对路径。
    副作用：
        重建 ``dist/deploy/source/<版本>`` 并写入 ``源码包说明.md``；不触碰仓库源文件。
    异常：
        源目录缺失或复制失败时由 ``shutil.copy2``/``copytree`` 抛出 ``OSError``。
    """

    work = os.path.join(ROOT, "dist", "deploy", "source")
    staging = os.path.join(work, f"峰运通数据管理系统_源码_v{version}")  # 暂存目录按版本命名
    if os.path.isdir(staging):
        shutil.rmtree(staging)  # 重建前清掉同版本旧副本
    os.makedirs(staging)

    for name in SOURCE_ROOT_FILES:
        source = os.path.join(ROOT, name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(staging, name))  # 按白名单复制根文件
    for name in SOURCE_DIRS:
        source = os.path.join(ROOT, name)
        if os.path.isdir(source):
            shutil.copytree(
                source,
                os.path.join(staging, name),
                ignore=_source_ignore,
            )
    staged_agents = os.path.join(staging, "AGENTS.md")
    legacy_agents = os.path.join(os.path.dirname(ROOT), "AGENTS.md")
    if not os.path.isfile(staged_agents) and os.path.isfile(legacy_agents):
        # 旧工作区曾把维护规范放在中文项目目录上一级；保留只读回退，避免历史源码包缺文件。
        shutil.copy2(legacy_agents, staged_agents)  # 回退复制旧布局的维护规范
    # 说明文件统一 LF 换行，兼容 Linux 预览与 Windows 记事本，避免 CRLF 混入源码包。
    with open(os.path.join(staging, "源码包说明.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(SOURCE_README)
    return staging


def _find_windows_cloudflared() -> str | None:
    """按显式环境变量、PATH、仓库工具目录和标准安装目录查找 cloudflared。

    返回值：
        第一个实际存在的候选程序路径；全部未命中时返回 ``None``，由调用方决定是否下载。
    不变量：
        只做路径探测与 ``os.path.isfile`` 检查，不下载、不执行、不修改环境变量。
    """

    candidates = [
        os.environ.get("FYT_CLOUDFLARED_EXE"),  # 优先尊重显式环境变量
        shutil.which("cloudflared"),  # 其次搜索 PATH 中的客户端
        os.path.join(ROOT, "tools", "cloudflared.exe"),  # 再查仓库工具目录
    ]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            candidates.append(os.path.join(base, "cloudflared", "cloudflared.exe"))  # 最后查标准安装目录
    # 显式环境变量优先于 PATH 与标准安装目录；只返回确实存在的文件，避免把无效路径交给复制步骤。
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def bundle_windows_cloudflared(staging: str, work: str) -> str:
    """把可执行的 Cloudflare Tunnel 客户端放入 Windows 包并记录来源版本。

    优先复用管理员显式指定或本机已安装的程序；都不存在时才从官方发行地址下载。复制后
    必须成功执行 ``--version``，从而在交付前拦截错误架构、损坏下载或不可执行文件。

    参数：
        staging: Windows 交付目录根，函数在其中创建 ``tools`` 子目录。
        work: PyInstaller 工作目录，下载候选放在其 ``_downloads`` 子目录。
    返回值：
        ``tools/cloudflared.exe`` 的最终路径。
    副作用：
        可能访问外网下载客户端；在 ``staging/tools`` 写入可执行文件与版本来源说明。
    异常：
        下载失败、复制失败或 ``--version`` 非零退出都会抛出对应异常并终止打包。
    """

    source = _find_windows_cloudflared()  # 优先复用本机已安装客户端
    if source is None:
        download_dir = os.path.join(work, "_downloads")
        os.makedirs(download_dir, exist_ok=True)
        source = os.path.join(download_dir, "cloudflared.exe")
        print("[下载] 本机未找到 cloudflared，正在下载官方 Windows amd64 客户端")
        # urlretrieve 已弃用且无超时；改用带超时的 urlopen 分块写入，避免网络挂起无限阻塞打包。
        with urllib.request.urlopen(CLOUDFLARED_WINDOWS_URL, timeout=120) as response, open(source, "wb") as handle:
            shutil.copyfileobj(response, handle)  # 分块落盘，超时会抛异常终止打包

    # 无论复用本地文件还是新下载，都先复制到包内再验证，确保验证对象与交付文件完全一致。
    tools_dir = os.path.join(staging, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    target = os.path.join(tools_dir, "cloudflared.exe")
    shutil.copy2(source, target)  # 复制到交付目录后再做版本验证
    checked = subprocess.run(
        [target, "--version"],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,  # 版本检查失败即终止打包，不能交付一个仅“文件存在”的客户端。
    )
    version_text = checked.stdout.strip()  # 去掉换行，便于写入说明
    with open(os.path.join(tools_dir, "cloudflared-版本与来源.txt"), "w", encoding="utf-8") as handle:
        handle.write(version_text + "\n")
        handle.write("官方来源：" + CLOUDFLARED_WINDOWS_URL + "\n")
        handle.write("项目与许可证：https://github.com/cloudflare/cloudflared\n")
    print(f"[完成] 已附带 Cloudflare Tunnel 客户端：{version_text}")
    return target


def build_windows_bundle(version: str) -> str:
    """构建免安装 Windows Web 服务目录并返回暂存路径。

    服务端、任务桥接和 Tkinter 控制台分别保留各自 ``_internal``，避免多个 PyInstaller
    onedir 目录合并后同名动态库相互覆盖。spec 文件负责 GUI/控制台窗口策略，本函数只做
    产物编排、静态前端、辅助脚本及 Cloudflare 客户端装配。

    参数：
        version: 用于命名暂存目录和最终压缩包。
    返回值：
        组装完成的 Windows 暂存目录路径。
    副作用：
        重建 ``dist/deploy/windows/<版本>``，执行三次 PyInstaller 打包，并写入 BAT、
        使用说明、Cloudflare 客户端与辅助脚本。
    异常：
        任一步骤失败都会向上抛出（通常为 ``subprocess.CalledProcessError`` 或 ``OSError``），
        不会交付半成品目录。
    """

    work = os.path.join(ROOT, "dist", "deploy", "windows")
    staging = os.path.join(work, f"峰运通服务端_windows_v{version}")  # 暂存目录按版本命名
    if os.path.isdir(staging):
        shutil.rmtree(staging)  # 重建前清掉同版本旧副本
    os.makedirs(staging)

    specs = ["web_server.spec", "bridge_worker.spec", "web_control_gui.spec"]  # 三个 EXE 的 PyInstaller 描述
    for spec in specs:
        run(
            VENV_PYINSTALLER
            + [
                "--noconfirm",
                "--distpath", work, "--workpath",
                os.path.join(work, "_build"), os.path.join("packaging", spec),
            ]
        )
    # 三个 onedir 产物按子目录部署，各自保留 _internal，避免内容目录合并冲突。
    for source, destination in (
        ("web_server", "服务端"),
        ("bridge_worker", "桥接"),
        ("峰运通服务控制台", "控制台"),
    ):
        shutil.move(
            os.path.join(work, source),
            os.path.join(staging, destination),
        )
    # 静态文件与 EXE 分离，服务端按部署根目录解析，升级时也能单独替换前端。
    shutil.copytree(
        os.path.join(ROOT, "web-app", "dist"),
        os.path.join(staging, "web-app", "dist"),
    )
    # BAT 使用 GBK，确保中文 Windows 默认记事本和 cmd 能正确读取路径与文件名。
    with open(os.path.join(staging, "启动服务.bat"), "w", encoding="gbk") as handle:
        handle.write("@echo off\r\nstart \"\" \"%~dp0控制台\\峰运通服务控制台.exe\" --start\r\n")
    with open(os.path.join(staging, "停止服务.bat"), "w", encoding="gbk") as handle:
        handle.write("@echo off\r\n\"%~dp0控制台\\峰运通服务控制台.exe\" --stop\r\n")
    with open(os.path.join(staging, "使用说明.txt"), "w", encoding="utf-8") as handle:
        handle.write(WINDOWS_README)
    shutil.copy2(
        os.path.join(ROOT, "scripts", "reset-web-admin-password.ps1"),
        os.path.join(staging, "重置管理员密码.ps1"),
    )
    shutil.copy2(
        os.path.join(ROOT, "scripts", "install-cloudflared.ps1"),
        os.path.join(staging, "重新安装Cloudflare客户端.ps1"),
    )
    bundle_windows_cloudflared(staging, work)  # 最后装配 Cloudflare 客户端
    return staging


def build_linux_bundle(version: str) -> str:
    """组装 Linux 源码部署目录，不包含虚拟环境或任何运行数据。

    包目录与安装目标均使用 ASCII 名称，规避部分 systemd、旧 shell 和运维工具处理中文
    工作路径时的兼容问题。目标机的 Python 选择、依赖安装、数据迁移、服务切换与回滚由
    ``packaging/linux/install.sh`` 负责，本函数只复制其唯一事实源和运行所需代码。

    参数：
        version: 用于命名包目录和 ``VERSION`` 文件。
    返回值：
        组装完成的 Linux 暂存目录路径。
    副作用：
        仅清理并重建 ``dist/deploy/linux`` 下的历史暂存目录；不读取、不覆盖、不删除
        目标机 ``/var/lib/fyt-web``。包内写入 ``VERSION``、``README.md`` 与运行依赖。
    异常：
        依赖清单或前端 ``dist`` 缺失时由文件操作抛出 ``OSError``，终止打包。
    """

    work = os.path.join(ROOT, "dist", "deploy", "linux")
    staging = os.path.join(work, f"fyt-server-linux-v{version}")  # 暂存目录按版本命名
    os.makedirs(work, exist_ok=True)
    # 只清理 dist/deploy/linux 下的历史暂存目录，绝不接触目标机 /var/lib/fyt-web。
    for name in os.listdir(work):
        if name.startswith(("峰运通服务端_linux_v", "fyt-server-linux-v")):
            old = os.path.join(work, name)
            if old != staging and os.path.isdir(old):
                shutil.rmtree(old)  # 删除旧版本暂存目录
    if os.path.isdir(staging):
        shutil.rmtree(staging)  # 重建前清掉同版本旧副本
    os.makedirs(staging)
    # 服务端入口、HTTP 后端与业务核心采用白名单复制，不把 tests、web-data 或桌面端带入包中。
    shutil.copy2(os.path.join(ROOT, "web_server.py"), staging)
    shutil.copytree(
        os.path.join(ROOT, "web_backend"),
        os.path.join(staging, "web_backend"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    core_out = os.path.join(staging, "core")
    os.makedirs(core_out)
    for name in os.listdir(os.path.join(ROOT, "core")):
        if name.endswith(".py"):
            shutil.copy2(os.path.join(ROOT, "core", name), os.path.join(core_out, name))  # 只复制核心 Python 源码
    # 前端必须预先构建；复制 dist 能让目标机无需安装 Node.js。
    shutil.copytree(
        os.path.join(ROOT, "web-app", "dist"),
        os.path.join(staging, "web-app", "dist"),
    )
    # Linux 包沿用容器和源码服务的统一运行依赖锁文件，不携带 PyInstaller 等开发工具。
    shutil.copy2(RUNTIME_REQUIREMENTS_PATH, os.path.join(staging, "requirements.txt"))
    # 只挑选安装、升级、服务控制脚本与 systemd 模板；排序后复制保证构建结果可重复比对。
    for name in sorted(os.listdir(LINUX_SCRIPTS_DIR)):
        if name.endswith((".sh", ".service")):
            shutil.copy2(os.path.join(LINUX_SCRIPTS_DIR, name), os.path.join(staging, name))  # 只收脚本与 systemd 模板
    with open(os.path.join(staging, "VERSION"), "w", encoding="ascii", newline="\n") as handle:
        handle.write(version + "\n")
    with open(os.path.join(staging, "README.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(LINUX_README.replace("<VERSION>", version))  # 替换包内 README 版本占位符
    return staging


def make_zip(folder: str, name: str) -> str:
    """把 Windows 或源码暂存目录压缩为普通 ZIP，并返回最终路径。

    参数：
        folder: 已组装好的暂存目录。
        name: ZIP 文件名（不含 ``.zip``），同时决定 ``dist`` 下的输出路径。
    返回值：
        压缩包完整路径。
    副作用：
        覆盖同路径旧压缩包；遍历目录读取每个文件。
    异常：
        文件读取或写入失败时抛出 ``OSError``。
    """

    target = os.path.join(ROOT, "dist", f"{name}.zip")
    if os.path.isfile(target):
        os.remove(target)  # 覆盖同名旧包前先删除
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(folder):
            for file in files:
                full = os.path.join(root, file)
                # 保留顶层包目录，用户解压多个交付物时不会把文件散落到当前目录。
                archive.write(full, os.path.relpath(full, os.path.dirname(folder)))
    return target


def make_linux_zip(folder: str, name: str) -> str:
    """生成带 UTF-8 文件名、Unix 权限元数据和外部 SHA-256 的 Linux ZIP。

    Python 在 Windows 上写 ZIP 时默认不会附带 Linux 执行位，因此这里为 Shell 脚本设置
    ``0755``，其余普通文件设置 ``0644``。这样解压工具若尊重外部属性，安装脚本可直接
    执行；即使不尊重，README 仍统一建议使用 ``bash install.sh``。

    参数：
        folder: Linux 暂存目录。
        name: ZIP 文件名（不含 ``.zip``）。
    返回值：
        压缩包完整路径；相邻位置还会生成同名 ``.sha256`` 校验文件。
    副作用：
        删除旧同目标压缩包与旧中文命名 Linux 压缩包；写入 ``dist/<name>.zip`` 与
        ``dist/<name>.zip.sha256``。
    异常：
        任一文件读取或写入失败均向上抛出 ``OSError``。
    """

    target = os.path.join(ROOT, "dist", f"{name}.zip")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    # 删除旧中文命名压缩包，防止运维人员误上传已经淘汰的 Linux 交付物。
    legacy_name = name.replace("fyt-server-linux-v", "峰运通服务端_linux_v", 1)
    legacy_target = os.path.join(ROOT, "dist", f"{legacy_name}.zip")
    if legacy_target != target and os.path.isfile(legacy_target):
        os.remove(legacy_target)  # 清理已淘汰的中文命名包
    if os.path.isfile(target):
        os.remove(target)  # 覆盖同名旧包前先删除
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for directory, _, files in os.walk(folder):
            for file in files:
                full = os.path.join(directory, file)
                relative = os.path.relpath(full, os.path.dirname(folder)).replace(os.sep, "/")  # ZIP 内统一斜杠路径
                # 显式使用源文件 mtime 并声明 Unix 创建系统，避免继承构建机时间与平台差异。
                info = zipfile.ZipInfo(relative, time.localtime(os.path.getmtime(full))[:6])
                info.create_system = 3  # 3 表示 Unix，解压器才会解释 external_attr 中的权限位。
                mode = stat.S_IFREG | (0o755 if file.endswith(".sh") else 0o644)  # Shell 脚本保留执行位
                info.external_attr = (mode & 0xFFFF) << 16  # 权限位写入 Unix 高 16 位
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as source:
                    archive.writestr(info, source.read())
    digest = hashlib.sha256()
    with open(target, "rb") as archive_file:
        for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
            digest.update(chunk)  # 分块计算校验和，避免整包读入内存
    with open(target + ".sha256", "w", encoding="ascii", newline="\n") as checksum:
        checksum.write(f"{digest.hexdigest()}  {os.path.basename(target)}\n")
    return target


def main() -> None:
    """根据命令行模式构建交付物，并以版本单一事实源命名所有产物。

    参数：
        命令行参数：``--linux-only`` 只构建 Linux 包。
    返回值：
        无。
    副作用：
        在 ``dist`` 下生成源码包、Windows 包、Linux 包及对应压缩包。
    异常：
        构建或网络失败时向上抛出，未捕获异常会让进程以非零退出码结束。
    """

    parser = argparse.ArgumentParser(description="构建峰运通服务端交付包")
    parser.add_argument(
        "--linux-only",
        action="store_true",
        help="只构建 Linux Web 服务端包，跳过源码包和 Windows PyInstaller 打包",
    )
    args = parser.parse_args()
    sys.path.insert(0, ROOT)  # 延迟导入使脚本在解析帮助参数时不必加载业务模块。
    from core.version import VERSION  # noqa: E402

    version = VERSION  # 统一从 core.version 读取版本事实源
    if args.linux_only:
        # Linux 单包模式仍先构建 Web dist，保证包中页面与当前源码版本一致。
        print(f"[开始] 只构建 Linux 服务端包 v{version}")
        build_web_dist()  # 先构建前端产物
        linux_folder = build_linux_bundle(version)
        linux_zip = make_linux_zip(linux_folder, f"fyt-server-linux-v{version}")
        print(f"[完成] Linux 整合包：{linux_zip}")
        return

    print(f"[开始] 构建源码与部署整合包 v{version}")
    print("[开始] 组装纯净源码包")
    source_folder = build_source_bundle(version)  # 先复制源码白名单
    build_web_dist()
    print("[开始] 构建 Windows 免安装包（PyInstaller，约需数分钟）")
    windows_folder = build_windows_bundle(version)
    print("[开始] 组装 Linux 源码部署包")
    linux_folder = build_linux_bundle(version)
    windows_zip = make_zip(windows_folder, f"峰运通服务端_windows_v{version}")  # 普通 ZIP 适合 Windows 分发
    linux_zip = make_linux_zip(linux_folder, f"fyt-server-linux-v{version}")  # Linux ZIP 带权限与校验
    source_zip = make_zip(source_folder, f"峰运通数据管理系统_源码_v{version}")
    print(f"[完成] 纯净源码包：{source_zip}")
    print(f"[完成] Windows 整合包：{windows_zip}")
    print(f"[完成] Linux 整合包：{linux_zip}")


if __name__ == "__main__":
    main()
