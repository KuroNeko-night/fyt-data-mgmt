# -*- coding: utf-8 -*-
"""生成不包含任何运行数据的 Linux 增量升级补丁。

补丁只收集服务端程序、业务核心、依赖清单和已经构建好的 Web 静态文件，随后生成
包内文件校验清单及压缩包校验值。生产数据位于 ``/var/lib/fyt-web``，本脚本既不读取
该目录，也不接受调用方把运行数据库、日志或符号链接混入补丁。

实际升级、备份、健康检查与失败回滚由随包分发的 ``apply-upgrade.sh`` 完成；本模块
只负责在本机临时目录中组装可审计、权限一致且可跨 Linux 主机解压的交付物。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import shutil
import tarfile
import tempfile
from datetime import date
from pathlib import Path


# 从脚本文件定位仓库根目录，避免构建结果依赖调用命令时所在的工作目录。
ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
APPLY_SCRIPT = ROOT / "packaging" / "linux" / "apply-upgrade-patch.sh"
RUNTIME_REQUIREMENTS = ROOT / "requirements-runtime.txt"
# 目录名按大小写不敏感方式检查，防止 Windows 上生成的补丁绕过 Linux 数据保护规则。
FORBIDDEN_NAMES = {
    "web-data",
    ".venv",
    "node_modules",
    "__pycache__",
    "target",
    "logs",
}
FORBIDDEN_SUFFIXES = {".sqlite3", ".db", ".log", ".pid"}  # 运行数据库、日志和进程标记一律不得进入补丁。


def sha256(path: Path) -> str:
    """流式计算文件 SHA-256，避免把大型压缩包一次性读入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        # 一兆字节分块兼顾磁盘吞吐和构建机内存占用，哈希结果不受分块大小影响。
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_version() -> str:
    """从项目版本单一事实源读取版本号，缺失时终止打包。

    仅用 AST 解析 ``VERSION`` 的字符串字面量赋值，不执行版本文件，避免版本文件被污染
    时给构建脚本引入任意代码执行面（构建常在 CI/自动化环境以高权限运行）。
    """
    version_file = ROOT / "core" / "version.py"
    tree = ast.parse(version_file.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "VERSION":
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    version = value.value.strip()
                    if version:
                        return version
    raise RuntimeError("无法从 core/version.py 读取版本号")


def copy_runtime_payload(payload: Path) -> None:
    """把 Linux 服务运行所需的白名单内容复制到暂存载荷目录。

    这里有意逐类复制而不是复制整个仓库：这样 ``web-data``、开发虚拟环境、测试样本、
    构建缓存和桌面端产物不会因为新增目录而被意外纳入升级包。
    """

    shutil.copy2(ROOT / "web_server.py", payload / "web_server.py")
    # Linux 服务器只安装运行依赖。仓库根 requirements.txt 还包含 PyInstaller 等开发、
    # 打包依赖，并通过 ``-r requirements-runtime.txt`` 间接引用运行清单；如果直接复制
    # 前者，补丁暂存目录会因缺少被引用文件而安装失败，也会给服务器引入无关工具。
    # 与完整 Linux 部署包保持一致，把锁定的运行清单作为包内 requirements.txt。
    shutil.copy2(RUNTIME_REQUIREMENTS, payload / "requirements.txt")
    shutil.copytree(
        ROOT / "web_backend",
        payload / "web_backend",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    core_target = payload / "core"
    core_target.mkdir()
    # core 当前是平铺 Python 模块；逐个复制只允许正式源码，不携带字节码缓存。
    for source in sorted((ROOT / "core").glob("*.py")):
        shutil.copy2(source, core_target / source.name)

    dist_source = ROOT / "web-app" / "dist"
    if not (dist_source / "index.html").is_file():  # index.html 是前端构建完成的最低可验证标志。
        raise RuntimeError("web-app/dist 尚未构建，请先执行 npm --prefix web-app run build")
    shutil.copytree(dist_source, payload / "web-app" / "dist")


def validate_tree(package_root: Path) -> list[Path]:
    """递归验证暂存树并返回允许写入校验清单的普通文件。

    检查覆盖任意层级的禁止目录名、运行数据后缀和符号链接。符号链接即使当前指向安全
    文件，也可能在解压主机上越出补丁目录，因此这里直接拒绝，而不是尝试解析其目标。
    """

    files: list[Path] = []
    for path in sorted(package_root.rglob("*")):
        relative = path.relative_to(package_root)
        lowered_parts = {part.casefold() for part in relative.parts}  # casefold 同时覆盖不同平台的大小写差异。
        blocked = lowered_parts & FORBIDDEN_NAMES
        if blocked:
            raise RuntimeError(f"补丁中出现禁止目录或文件：{relative}")
        if path.is_symlink():
            raise RuntimeError(f"补丁中不允许出现符号链接：{relative}")
        if path.is_file():
            if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
                raise RuntimeError(f"补丁中出现运行数据或日志：{relative}")
            files.append(path)
    return files


def write_readme(path: Path, archive_name: str) -> None:
    """写入面向运维人员的升级说明，并明确运行数据保护边界。"""

    path.write_text(
        "峰运通数据管理系统 Linux 增量升级补丁\n"
        "\n"
        "适用目录：/opt/fyt/server\n"
        "适用服务：fyt-web.service\n"
        "\n"
        "本补丁只更新 web_server.py、web_backend、core、web-app/dist 和 requirements.txt。\n"
        "它不会打包、读取、复制、删除或覆盖 web-data，也不会操作 /var/lib/fyt-web。\n"
        "升级前会把现有程序文件备份到 /var/backups/fyt-web，健康检查失败会自动回滚。\n"
        "\n"
        "上传到服务器 /root 后执行：\n"
        f"cd /root && tar -xzf {archive_name} && bash "
        f"{archive_name.removesuffix('.tar.gz')}/apply-upgrade.sh\n"
        "\n"
        "如安装目录或服务名不同，可在命令前设置 FYT_INSTALL_DIR、FYT_SERVICE_NAME。\n",
        encoding="utf-8",
        newline="\n",
    )


def add_to_tar(archive: tarfile.TarFile, source: Path, arcname: str) -> None:
    """以固定属主和权限写入 tar，消除构建机账户信息与权限差异。

    压缩包内记录 root 属主只是为了得到可预测的元数据；安装脚本仍会在部署时根据正式
    服务账户重新设置属主。Shell 脚本保留执行位，普通源码和静态资源保持只读文件权限。
    """

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        """把单个 tar 条目的属主及权限归一化为 Linux 部署约定。"""

        info.uid = 0
        info.gid = 0
        info.uname = "root"
        info.gname = "root"
        if info.isdir():
            info.mode = 0o755
        elif info.name.endswith(".sh"):
            info.mode = 0o755
        else:
            info.mode = 0o644
        return info

    archive.add(source, arcname=arcname, recursive=True, filter=normalize)


def build(output_dir: Path, build_date: str, revision: str = "") -> tuple[Path, Path]:
    """在隔离临时目录中组装补丁，返回压缩包与外部校验文件路径。

    包内 ``SHA256SUMS`` 用于升级前逐文件验真；同名 ``.sha256`` 文件用于上传后验证整个
    压缩包。只有全部内容验证完成后才把最终归档写入输出目录。
    """

    version = read_version()
    revision_suffix = f"-{revision}" if revision else ""
    package_name = f"fyt-linux-upgrade-patch-v{version}-{build_date}{revision_suffix}"
    archive_path = output_dir / f"{package_name}.tar.gz"
    checksum_path = output_dir / f"{package_name}.tar.gz.sha256"

    # 暂存目录退出上下文后自动删除，避免残留旧版本文件污染下一次补丁。
    with tempfile.TemporaryDirectory(prefix="fyt-linux-patch-") as temp_dir:
        package_root = Path(temp_dir) / package_name
        payload = package_root / "payload"
        payload.mkdir(parents=True)

        shutil.copy2(APPLY_SCRIPT, package_root / "apply-upgrade.sh")
        copy_runtime_payload(payload)
        write_readme(package_root / "README.txt", archive_path.name)

        files = validate_tree(package_root)  # 先验证再生成清单，禁止内容不会被哈希后继续打包。
        manifest_lines = [
            f"{sha256(path)}  {path.relative_to(package_root).as_posix()}"
            for path in files
            if path.name != "SHA256SUMS"  # 清单不能包含自身，否则无法得到稳定的递归校验值。
        ]
        (package_root / "SHA256SUMS").write_text(
            "\n".join(manifest_lines) + "\n",
            encoding="ascii",
            newline="\n",
        )
        validate_tree(package_root)  # 清单写入后再次验证，确保最终树与首次检查边界一致。

        output_dir.mkdir(parents=True, exist_ok=True)
        archive_path.unlink(missing_ok=True)
        checksum_path.unlink(missing_ok=True)
        with tarfile.open(archive_path, "w:gz", compresslevel=9) as archive:
            add_to_tar(archive, package_root, package_name)

    checksum_path.write_text(
        f"{sha256(archive_path)}  {archive_path.name}\n",
        encoding="ascii",
        newline="\n",
    )
    return archive_path, checksum_path


def main() -> int:
    """解析命令行参数、校验日期格式并输出可人工核对的构建摘要。"""

    parser = argparse.ArgumentParser(description="生成 Linux 增量升级补丁")
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y%m%d"),
        help="补丁日期，默认使用当天日期",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DIST_DIR,
        help="输出目录，默认使用项目 dist",
    )
    parser.add_argument(
        "--revision",
        default="",
        help="同日重新发布时使用的 ASCII 修订标记，例如 r2",
    )
    args = parser.parse_args()
    if len(args.date) != 8 or not args.date.isdigit():
        parser.error("--date 必须是 YYYYMMDD 格式")
    if args.revision and not args.revision.replace("-", "").replace("_", "").isalnum():
        parser.error("--revision 只能包含字母、数字、短横线和下划线")

    archive_path, checksum_path = build(
        args.output_dir.resolve(), args.date, args.revision,
    )
    print(f"补丁包：{archive_path}")
    print(f"校验文件：{checksum_path}")
    print(f"SHA-256：{sha256(archive_path)}")
    print(f"大小：{archive_path.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
