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
    """流式计算文件 SHA-256，避免把大型压缩包一次性读入内存。

    参数：
        path: 待哈希文件的路径。
    返回值：
        十六进制摘要字符串。
    异常：
        文件不存在或读取失败时抛出 ``OSError``。
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        # 一兆字节分块兼顾磁盘吞吐和构建机内存占用，哈希结果不受分块大小影响。
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)  # 逐块更新摘要
    return digest.hexdigest()


def read_version() -> str:
    """从项目版本单一事实源读取版本号，缺失时终止打包。

    仅用 AST 解析 ``VERSION`` 的字符串字面量赋值，不执行版本文件，避免版本文件被污染
    时给构建脚本引入任意代码执行面（构建常在 CI/自动化环境以高权限运行）。

    参数：
        无。
    返回值：
        去除首尾空白后的非空版本字符串。
    异常：
        ``RuntimeError``：找不到字符串类型的 ``VERSION`` 赋值；版本文件缺失或语法损坏
        时由 ``Path.read_text``/``ast.parse`` 抛出对应异常。
    """
    version_file = ROOT / "core" / "version.py"
    tree = ast.parse(version_file.read_text(encoding="utf-8"))  # 仅解析语法，不执行代码
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue  # 跳过 import/函数等非赋值语句
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "VERSION":
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    version = value.value.strip()  # 去除空白，确保版本可写入文件名
                    if version:
                        return version
    raise RuntimeError("无法从 core/version.py 读取版本号")


def copy_runtime_payload(payload: Path) -> None:
    """把 Linux 服务运行所需的白名单内容复制到暂存载荷目录。

    这里有意逐类复制而不是复制整个仓库：这样 ``web-data``、开发虚拟环境、测试样本、
    构建缓存和桌面端产物不会因为新增目录而被意外纳入升级包。

    参数：
        payload: 补丁包内的载荷目录，函数只向该目录写入运行白名单文件。
    返回值：
        无。
    副作用：
        向 ``payload`` 写入 ``web_server.py``、``web_backend``、``core``、前端 ``dist``
        与 ``requirements.txt``；不读取、不覆盖、不删除 ``/var/lib/fyt-web``。
    异常：
        前端未构建时抛出 ``RuntimeError``；源目录缺失或复制失败时由文件操作抛出 ``OSError``。
    """

    shutil.copy2(ROOT / "web_server.py", payload / "web_server.py")  # 服务入口单独复制
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
        shutil.copy2(source, core_target / source.name)  # 排序复制保证载荷可重复

    dist_source = ROOT / "web-app" / "dist"
    if not (dist_source / "index.html").is_file():  # index.html 是前端构建完成的最低可验证标志。
        raise RuntimeError("web-app/dist 尚未构建，请先执行 npm --prefix web-app run build")
    shutil.copytree(dist_source, payload / "web-app" / "dist")  # 前端产物直接进包


def validate_tree(package_root: Path) -> list[Path]:
    """递归验证暂存树并返回允许写入校验清单的普通文件。

    检查覆盖任意层级的禁止目录名、运行数据后缀和符号链接。符号链接即使当前指向安全
    文件，也可能在解压主机上越出补丁目录，因此这里直接拒绝，而不是尝试解析其目标。

    参数：
        package_root: 待验证的补丁暂存根目录。
    返回值：
        通过检查的普通文件路径列表，按遍历顺序排序，供生成 ``SHA256SUMS`` 使用。
    异常：
        ``RuntimeError``：出现禁止目录/文件名、禁止后缀或符号链接。
    不变量：
        只读检查，不修改任何文件；清单生成前后使用同一规则，确保最终树与首次检查边界一致。
    """

    files: list[Path] = []
    for path in sorted(package_root.rglob("*")):
        relative = path.relative_to(package_root)
        lowered_parts = {part.casefold() for part in relative.parts}  # casefold 同时覆盖不同平台的大小写差异。
        blocked = lowered_parts & FORBIDDEN_NAMES
        if blocked:
            raise RuntimeError(f"补丁中出现禁止目录或文件：{relative}")  # 发现禁止目录立即终止
        if path.is_symlink():
            raise RuntimeError(f"补丁中不允许出现符号链接：{relative}")  # 拒绝符号链接防越界
        if path.is_file():
            if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
                raise RuntimeError(f"补丁中出现运行数据或日志：{relative}")  # 拒绝数据库与日志
            files.append(path)
    return files


def write_readme(path: Path, archive_name: str) -> None:
    """写入面向运维人员的升级说明，并明确运行数据保护边界。

    参数：
        path: 说明文件写入位置。
        archive_name: 最终压缩包文件名，用于生成对运维人员可直接执行的解包命令。
    返回值：
        无。
    副作用：
        覆盖 ``path`` 并写入 UTF-8/LF 文本；内容声明补丁不接触 ``/var/lib/fyt-web``。
    异常：
        写入失败时抛出 ``OSError``。
    """

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

    参数：
        archive: 已打开的 tar 文件。
        source: 要归档的源路径。
        arcname: 包内相对路径名。
    返回值：
        无。
    副作用：
        向 ``archive`` 写入归一化条目；不会改动源文件权限或属主。
    异常：
        归档失败时由 ``tarfile`` 抛出 ``OSError``。
    """

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        """把单个 tar 条目的属主及权限归一化为 Linux 部署约定。"""

        info.uid = 0
        info.gid = 0
        info.uname = "root"
        info.gname = "root"
        if info.isdir():
            info.mode = 0o755  # 目录保留进入权限
        elif info.name.endswith(".sh"):
            info.mode = 0o755  # 脚本保留执行位
        else:
            info.mode = 0o644  # 普通文件只读即可
        return info

    archive.add(source, arcname=arcname, recursive=True, filter=normalize)


def build(output_dir: Path, build_date: str, revision: str = "") -> tuple[Path, Path]:
    """在隔离临时目录中组装补丁，返回压缩包与外部校验文件路径。

    包内 ``SHA256SUMS`` 用于升级前逐文件验真；同名 ``.sha256`` 文件用于上传后验证整个
    压缩包。只有全部内容验证完成后才把最终归档写入输出目录。

    参数：
        output_dir: 最终压缩包与校验文件的输出目录。
        build_date: YYYYMMDD 日期，写入包名以便按日追踪。
        revision: 可选的同日修订标记；默认空串表示当日首次发布。
    返回值：
        ``(压缩包路径, 外部校验文件路径)`` 元组。
    副作用：
        在系统临时目录组装并在退出后自动清理；在 ``output_dir`` 写入最终交付物。
    异常：
        版本读取失败、内容验证失败或归档失败时向上抛出，不留下半成品压缩包。
    """

    version = read_version()
    revision_suffix = f"-{revision}" if revision else ""  # 同日修订标记拼入包名
    package_name = f"fyt-linux-upgrade-patch-v{version}-{build_date}{revision_suffix}"
    archive_path = output_dir / f"{package_name}.tar.gz"
    checksum_path = output_dir / f"{package_name}.tar.gz.sha256"

    # 暂存目录退出上下文后自动删除，避免残留旧版本文件污染下一次补丁。
    with tempfile.TemporaryDirectory(prefix="fyt-linux-patch-") as temp_dir:
        package_root = Path(temp_dir) / package_name
        payload = package_root / "payload"
        payload.mkdir(parents=True)  # 载荷目录用于放运行白名单

        shutil.copy2(APPLY_SCRIPT, package_root / "apply-upgrade.sh")  # 升级脚本放包根
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
        archive_path.unlink(missing_ok=True)  # 覆盖同名旧包
        checksum_path.unlink(missing_ok=True)
        with tarfile.open(archive_path, "w:gz", compresslevel=9) as archive:
            add_to_tar(archive, package_root, package_name)  # 打包时归一化权限与属主

    checksum_path.write_text(
        f"{sha256(archive_path)}  {archive_path.name}\n",
        encoding="ascii",
        newline="\n",
    )
    return archive_path, checksum_path


def main() -> int:
    """解析命令行参数、校验日期格式并输出可人工核对的构建摘要。

    返回值：
        0 表示成功；参数非法时 ``argparse`` 以非零码退出；构建失败异常向上传播。
    副作用：
        调用 ``build`` 生成补丁；仅在标准输出打印构建摘要。
    """

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
        parser.error("--date 必须是 YYYYMMDD 格式")  # 日期格式错误直接提示退出
    # revision 只用于文件名后缀拼接；限制字符集可防止路径分隔符或特殊字符混入包名。
    if args.revision and not args.revision.replace("-", "").replace("_", "").isalnum():
        parser.error("--revision 只能包含字母、数字、短横线和下划线")

    archive_path, checksum_path = build(
        args.output_dir.resolve(), args.date, args.revision,
    )
    print(f"补丁包：{archive_path}")
    print(f"校验文件：{checksum_path}")
    print(f"SHA-256：{sha256(archive_path)}")  # 外部校验值便于上传后核对
    print(f"大小：{archive_path.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
