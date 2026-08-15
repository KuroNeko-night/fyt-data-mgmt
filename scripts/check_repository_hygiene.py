"""检查源码仓库是否混入运行数据、生成物、凭据或编码残留。

检查对象包含 Git 已跟踪文件和未被忽略的新文件，因此不会读取 ``web-data``、本地密钥
或依赖目录，但能在新源码进入暂存区之前发现问题。脚本用于本地提交前检查和 CI；发现
问题时只输出文件路径和问题类型，不回显疑似凭据内容，避免诊断日志造成二次泄露。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]

# 这些目录只承载本地依赖、运行数据、缓存或可再生成产物，不应成为源码事实来源。
FORBIDDEN_PARTS = {
    ".codex-audit",
    ".hypothesis",
    ".mypy_cache",
    ".playwright-mcp",
    ".pytest_cache",
    ".reasonix",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "docker-data",
    "htmlcov",
    "node_modules",
    "target",
    "tmp",
    "web-data",
}

# 二进制美术资源和锁文件允许跟踪；这里只拦截运行产物、私密文件和交付压缩包后缀。
FORBIDDEN_SUFFIXES = {
    ".cer",
    ".crt",
    ".db",
    ".dmp",
    ".exe",
    ".key",
    ".log",
    ".p12",
    ".part",
    ".pem",
    ".pfx",
    ".pid",
    ".pyc",
    ".pyo",
    ".secret",
    ".sqlite",
    ".sqlite3",
    ".token",
    ".zip",
}

# 只对明确的文本后缀做 UTF-8 和内容扫描，避免把图片、字体或 Office 文件误判为乱码。
TEXT_SUFFIXES = {
    "",
    ".bat",
    ".cmd",
    ".css",
    ".dockerignore",
    ".editorconfig",
    ".env",
    ".example",
    ".gitattributes",
    ".gitignore",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

# 凭据检测坚持高精度。命中时只报告路径，不打印实际行内容。
SECRET_MARKERS = (
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN RSA " + "PRIVATE KEY-----",
    "-----BEGIN EC " + "PRIVATE KEY-----",
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    "github" + "_pat_",
    "gh" + "p_",
)


def _repository_files() -> list[str]:
    """读取已跟踪和未忽略的新文件，完整支持中文、空格和引号文件名。

    返回值：
        相对仓库根的路径字符串列表。
    副作用：
        启动 ``git ls-files`` 子进程，只读不修改工作区。
    异常：
        非零退出码时抛出 ``subprocess.CalledProcessError``；Git 缺失也表现为该异常。
    """

    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    # ``-z`` 用 NUL 分隔输出，文件名中的换行、引号和中文都能被完整还原。
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def _is_text(path: Path) -> bool:
    """按文件名和后缀判断是否需要执行 UTF-8 内容检查。

    参数：
        path: 仓库内的相对路径。
    返回值：
        需要做文本内容扫描时为 ``True``；二进制资源返回 ``False``，避免误报乱码。
    """

    if path.name.lower() in {"dockerfile", "license"}:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def _path_problem(relative: str) -> str | None:
    """返回已跟踪路径违反仓库边界的原因，没有问题时返回 ``None``。

    参数：
        relative: 相对仓库根的 POSIX 风格路径。
    返回值：
        问题描述字符串；路径合规时返回 ``None``。
    不变量：
        只做纯路径判断，不访问文件系统，因此可安全用于 CI 全量扫描。
    """

    # 使用 POSIX 路径语义并折叠大小写，保证 Windows 上 git 输出的斜杠与大小写差异不影响判定。
    path = PurePosixPath(relative)
    lowered_parts = {part.lower() for part in path.parts}
    forbidden = sorted(lowered_parts & FORBIDDEN_PARTS)
    if forbidden:
        return f"包含本地或生成目录：{forbidden[0]}"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"不应跟踪此类文件：{path.suffix.lower()}"
    return None


def _content_problems(relative: str) -> list[str]:
    """检查文本编码、凭据标记和历史乱码特征，不读取未跟踪文件。

    参数：
        relative: 相对仓库根的路径；调用方只传入仓库文件列表中的条目。
    返回值：
        问题描述列表；文件无可检内容或全部通过时返回空列表。
    副作用：
        只读文件内容，不修改任何文件；凭据命中只记录问题类型，不回显内容。
    """

    path = ROOT / relative
    if not path.is_file() or not _is_text(path):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ["文本文件不是有效 UTF-8"]

    problems: list[str] = []
    # U+FFFD 通常表示 GBK/UTF-8 转换失败；一旦出现在源码中，说明某次转换已不可逆地丢失原文。
    if "\ufffd" in text:
        problems.append("包含 Unicode 替换字符 U+FFFD")
    # 连续问号不一定是错误，但三个以上常由中文被错误当作 ASCII 替换而来，属于卫生线索。
    if "?" * 3 in text:
        problems.append("包含连续三个问号，疑似中文编码转换残留")
    if any(marker in text for marker in SECRET_MARKERS):
        problems.append("包含私钥或访问令牌特征")
    return problems


def check_repository() -> list[tuple[str, str]]:
    """返回全部仓库卫生问题，结果顺序稳定，便于本地与 CI 对照。

    返回值：
        ``(相对路径, 问题描述)`` 列表；按路径排序，路径问题优先于内容问题。
    副作用：
        读取 Git 索引并逐文件扫描文本内容；不修改仓库。
    异常：
        由 ``_repository_files`` 透传子进程异常，由调用方决定是否按基础设施失败处理。
    """

    problems: list[tuple[str, str]] = []
    for relative in sorted(_repository_files()):
        path_problem = _path_problem(relative)
        if path_problem:
            problems.append((relative, path_problem))
            continue
        for content_problem in _content_problems(relative):
            problems.append((relative, content_problem))
    return problems


def main() -> int:
    """运行检查并返回适合 CI 使用的退出码。

    返回值：
        0 表示通过；1 表示发现卫生问题；2 表示无法完成检查（如 Git 不可用）。
    副作用：
        仅打印结论与问题清单，不打印疑似凭据内容。
    """

    try:
        problems = check_repository()
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        print(f"[失败] 无法完成仓库卫生检查：{exc}", file=sys.stderr)
        return 2

    if problems:
        print(f"[失败] 发现 {len(problems)} 个仓库卫生问题：")
        for relative, reason in problems:
            print(f"- {relative}：{reason}")
        return 1

    print("[通过] 仓库未跟踪运行数据、生成物、敏感凭据或已知编码残留。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
