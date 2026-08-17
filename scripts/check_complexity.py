# -*- coding: utf-8 -*-
"""圈复杂度检查与函数评级。

按仓库约定的复杂度阈值扫描 Python 函数与方法，输出每个函数的 A-F 评级表；配合
Git 基线时只对本次变更新增或变得更复杂的超标函数报错，避免历史代码阻塞新提交。
脚本供本地提交前检查和 CI 使用，评级与行数只用于提示，不替代人工拆分判断。

用法（仓库根目录）：:

    python scripts/check_complexity.py                    # 扫描全仓并打印评级表
    python scripts/check_complexity.py --base HEAD        # 只检查相对 HEAD 的变更
    python scripts/check_complexity.py --strict           # 任何超标函数都导致失败

阈值取 ``docs/源码注释与编码风格规范.md`` 第八章的约束：单个函数圈复杂度超过
``COMPLEXITY_THRESHOLD``（默认 15）时应拆分为语义清晰的辅助函数。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

# 默认全仓扫描范围；这些路径是项目自行维护的 Python 源码。
DEFAULT_PATHS = (
    "core",
    "scripts",
    "tests",
    "web_backend",
    "web_control_gui.py",
    "web_control_gui_process.py",
    "web_server.py",
)

# 圈复杂度超过该值就需要拆分（与代码风格规范第八章保持一致）。
COMPLEXITY_THRESHOLD = 15

# 扫描目录时跳过的本地依赖、运行数据和生成产物。
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "outputs",
    "web-data",
}

# 相对路径命中这些片段时不参与分析，避免把发布副本或外部依赖当成源码事实来源。
SKIP_PATH_PARTS = {
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "outputs",
    "web-data",
}


@dataclass(frozen=True)
class BlockReport:
    """一个可分析代码块的评级快照。"""

    path: str
    fullname: str
    name: str
    kind: str
    complexity: int
    rank: str
    lineno: int
    lines: int
    is_function: bool


def _load_radon():
    """惰性加载 radon，使未安装依赖时只运行纯路径判断仍可导入脚本。"""
    try:
        from radon.complexity import cc_visit
    except ImportError as exc:
        print("缺少圈复杂度工具 radon，请先执行：python -m pip install radon==6.0.1")
        raise SystemExit(2) from exc
    return cc_visit


def _is_python_source(relative: str) -> bool:
    """判断相对路径是否属于应分析的 Python 源码。"""
    path = PurePosixPath(relative.replace("\\", "/"))
    if path.suffix.lower() != ".py":
        return False
    return not (SKIP_PATH_PARTS & {part.lower() for part in path.parts})


def _iter_python_files(paths) -> list[str]:
    """递归收集指定路径下的 Python 文件，返回相对仓库根的 POSIX 路径。"""
    files: set[str] = set()
    for item in paths:
        path = Path(item)
        if not path.exists():
            continue
        if path.is_file():
            files.add(path.resolve().relative_to(ROOT).as_posix())
            continue
        for current, dirs, names in os.walk(path):
            dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
            for name in names:
                candidate = Path(current) / name
                files.add(candidate.resolve().relative_to(ROOT).as_posix())
    return sorted(relative for relative in files if _is_python_source(relative))


def _rank_for(complexity: int) -> str:
    """按 radon 默认阈值把圈复杂度映射为 A-F 评级。"""
    if complexity <= 5:
        return "A"
    if complexity <= 10:
        return "B"
    if complexity <= 20:
        return "C"
    if complexity <= 30:
        return "D"
    if complexity <= 40:
        return "E"
    return "F"


def _block_report(path: str, block) -> BlockReport:
    """把 radon 分析块转换为便于排序和展示的记录。"""
    endline = int(getattr(block, "endline", block.lineno) or block.lineno)
    complexity = int(block.complexity)
    return BlockReport(
        path=path,
        fullname=str(block.fullname or block.name),
        name=str(block.name),
        kind=type(block).__name__,
        complexity=complexity,
        rank=_rank_for(complexity),
        lineno=int(block.lineno),
        lines=max(1, endline - int(block.lineno) + 1),
        is_function=type(block).__name__ == "Function",
    )


def _analyze_path(path: str) -> list[BlockReport]:
    """分析单个 Python 文件并返回全部函数、方法和类的评级。"""
    cc_visit = _load_radon()
    source_path = ROOT / path
    try:
        source = source_path.read_text(encoding="utf-8")
        blocks = cc_visit(source, no_assert=False)
    except SyntaxError:
        print(f"[跳过] 语法错误：{path}")
        return []
    except OSError:
        print(f"[跳过] 无法读取：{path}")
        return []
    return [_block_report(path, block) for block in blocks]


def _analyze_source(path: str, source: str) -> list[BlockReport]:
    """分析 Git 基线中的源码文本，返回与当前文件同构的评级记录。"""
    cc_visit = _load_radon()
    try:
        blocks = cc_visit(source, no_assert=False)
    except SyntaxError:
        return []
    return [_block_report(path, block) for block in blocks]


def _changed_python_files(base_ref: str) -> list[str]:
    """返回相对 Git 基线新增或修改的 Python 文件。"""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base_ref, "--"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    names = result.stdout.decode("utf-8").splitlines()
    return sorted(name.strip() for name in names if _is_python_source(name))


def _base_source(base_ref: str, path: str) -> str | None:
    """读取 Git 基线中指定文件的内容；新文件或路径不存在时返回 ``None``。"""
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{path}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8")


def _base_complexities(base_ref: str, paths: list[str]) -> dict[str, int]:
    """建立基线中“函数全名 -> 圈复杂度”映射，只统计函数与方法。"""
    complexities: dict[str, int] = {}
    for path in paths:
        source = _base_source(base_ref, path)
        if source is None:
            continue
        for report in _analyze_source(path, source):
            if report.is_function:
                complexities[report.fullname] = report.complexity
    return complexities


def _new_violations(
    reports: list[BlockReport],
    base_complexities: dict[str, int],
    threshold: int,
) -> list[tuple[BlockReport, int | None]]:
    """返回本次变更新增或变得更复杂的超标函数。

    基线中同函数已经超标且复杂度未上升的不算新问题，避免历史代码阻塞新提交。
    """
    violations: list[tuple[BlockReport, int | None]] = []
    for report in reports:
        if not report.is_function or report.complexity <= threshold:
            continue
        previous = base_complexities.get(report.fullname)
        if previous is None or report.complexity > previous:
            violations.append((report, previous))
    return violations


def _sort_reports(reports: list[BlockReport]) -> list[BlockReport]:
    """按复杂度、文件、行号稳定排序，便于快速看到最需要改进的函数。"""
    return sorted(reports, key=lambda item: (-item.complexity, item.path, item.lineno))


def _console_table(reports: list[BlockReport]) -> None:
    """在控制台输出 ASCII 评级表，兼容 Windows GBK 控制台。"""
    print("\n函数评级表（按复杂度降序）：")
    print("-" * 100)
    print(f"{'函数':<44} {'文件':<32} {'复杂度':>6} {'评级':>4} {'行数':>6}")
    print("-" * 100)
    for report in reports:
        name = report.name if len(report.name) <= 40 else report.name[:39] + "…"
        print(f"{name:<44} {report.path:<32} {report.complexity:>6} {report.rank:>4} {report.lines:>6}")
    print("-" * 100)


def _rank_counts(reports: list[BlockReport]) -> dict[str, int]:
    """按 A-F 统计评级分布。"""
    counts: dict[str, int] = {}
    for report in reports:
        counts[report.rank] = counts.get(report.rank, 0) + 1
    return dict(sorted(counts.items()))


def _github_summary(reports: list[BlockReport], counts: dict[str, int], title: str, github: bool = False) -> None:
    """把评级表写入 GitHub Actions 的步骤摘要。"""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not github or not summary_path:
        return
    lines = [
        f"## {title}",
        "",
        "| 函数 | 文件 | 复杂度 | 评级 | 行数 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for report in reports:
        lines.append(
            f"| {report.name} | {report.path} | {report.complexity} "
            f"| {report.rank} | {report.lines} |"
        )
    distribution = "，".join(f"{rank} 级 {count} 个" for rank, count in counts.items())
    lines.extend(["", f"评级分布：{distribution or '无'}", ""])
    with open(summary_path, "a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def _annotation(level: str, report: BlockReport, message: str, github: bool = False) -> None:
    """在 GitHub Actions 中为超标函数输出文件级注释。"""
    if github:
        print(f"::{level} file={report.path},line={report.lineno},title=圈复杂度检查::{message}")


def _collect_reports(args):
    """按基线或全仓模式收集评级记录与基线复杂度映射。"""
    if args.base:
        changed_paths = _changed_python_files(args.base)
        reports = []
        for path in changed_paths:
            reports.extend(_analyze_path(path))
        base_complexities = _base_complexities(args.base, changed_paths)
        title = f"圈复杂度评级（相对 {args.base} 变更 {len(changed_paths)} 个文件）"
    else:
        paths = args.paths or list(DEFAULT_PATHS)
        reports = []
        for path in _iter_python_files(paths):
            reports.extend(_analyze_path(path))
        base_complexities = {}
        title = "圈复杂度评级（全仓）"
    return _sort_reports(reports), base_complexities, title


def _emit_annotations(args, reports, violations, threshold):
    """在 GitHub Actions 中输出超标函数注释；历史问题只警告。"""
    for report, previous in violations:
        delta = f"，基线复杂度 {previous}" if previous is not None else "，新函数"
        _annotation(
            "error",
            report,
            f"函数“{report.name}”圈复杂度 {report.complexity}（{report.rank} 级）超过阈值 "
            f"{threshold}{delta}，请拆分。",
            github=args.github,
        )
    flagged = {violation[0].fullname for violation in violations}
    for report in reports:
        if not report.is_function or report.complexity <= threshold:
            continue
        if report.fullname in flagged:
            continue
        if not args.strict and not args.base:
            continue
        _annotation(
            "warning",
            report,
            f"函数“{report.name}”圈复杂度 {report.complexity}（{report.rank} 级）"
            f"超过阈值 {threshold}，历史遗留建议拆分。",
            github=args.github,
        )


def _run(args) -> int:
    """执行扫描、基线比较与结果输出，返回进程退出码。"""
    threshold = args.threshold
    reports, base_complexities, title = _collect_reports(args)
    counts = _rank_counts(reports)
    _console_table(reports)
    _github_summary(reports, counts, title, github=args.github)
    print(f"共分析 {len(reports)} 个代码块。")
    print(f"评级分布：{counts or '无'}")

    violations = _new_violations(reports, base_complexities, threshold) if args.base else []
    _emit_annotations(args, reports, violations, threshold)
    if violations:
        print(f"[失败] 本次变更新增或恶化 {len(violations)} 个超标函数。")
        return 1
    if args.strict:
        current_violations = [
            report for report in reports
            if report.is_function and report.complexity > threshold
        ]
        if current_violations:
            print(f"[失败] 全量扫描仍有 {len(current_violations)} 个超标函数。")
            return 1
    print("[通过] 本次变更没有新增或恶化的超标函数。" if args.base else "[提示] 全量评级完成。")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="检查圈复杂度并输出函数评级表")
    parser.add_argument("paths", nargs="*", help="要扫描的文件或目录；缺省使用项目默认源码目录")
    parser.add_argument(
        "--base",
        default=os.environ.get("COMPLEXITY_BASE", ""),
        help="Git 基线引用（如 HEAD、origin/main）；只检查相对该基线的变更",
    )
    parser.add_argument("--threshold", type=int, default=COMPLEXITY_THRESHOLD, help="圈复杂度阈值")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="任何超标函数都导致失败，而不仅限本次变更新增或恶化的函数",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="同时输出 GitHub Actions 注释与步骤摘要",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
