"""维护中的 Python 源码编码与中文注释回归测试。"""

from __future__ import annotations

import ast
import io
from pathlib import Path
import tokenize
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ROOT / "web_server.py",
    ROOT / "web_control_gui.py",
    ROOT / "web_backend",
    ROOT / "core",
    ROOT / "packaging",
    ROOT / "tests",
)


def iter_python_sources():
    """枚举当前维护的 Python 源码，不扫描依赖和运行数据目录。"""
    for source_root in SOURCE_ROOTS:
        if source_root.is_file():
            yield source_root
        elif source_root.is_dir():
            yield from sorted(source_root.rglob("*.py"))


def iter_docstrings(tree):
    """返回语法树中所有模块、类和函数的文档字符串节点。"""
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            yield first.value


class SourceEncodingTests(unittest.TestCase):
    """防止中文注释再次因错误代码页写入而变成问号或替代字符。"""

    def test_python_sources_are_utf8_and_comments_are_not_replaced(self):
        """逐文件解码、分词和解析，分别检查注释与文档字符串的完整性。"""

        failures = []
        for path in iter_python_sources():
            relative = path.relative_to(ROOT)
            try:
                text = path.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                failures.append(f"{relative}: 不是有效的 UTF-8 文件：{exc}")
                continue

            # tokenize 能识别真正的注释，避免把业务字符串中的问号误判为编码损坏。
            try:
                tokens = tokenize.generate_tokens(io.StringIO(text).readline)
                for token in tokens:
                    if token.type != tokenize.COMMENT:
                        continue
                    if "?" in token.string or "\ufffd" in token.string:
                        failures.append(
                            f"{relative}:{token.start[0]}: 注释含 ASCII 问号或 Unicode 替换字符"
                        )
            except (IndentationError, tokenize.TokenError) as exc:
                failures.append(f"{relative}: 无法解析注释：{exc}")
                continue

            # AST 单独定位文档字符串；普通客户文案可以合法包含疑问标点，不在本项拦截。
            try:
                tree = ast.parse(text, filename=str(relative))
            except SyntaxError as exc:
                failures.append(f"{relative}:{exc.lineno}: Python 语法解析失败：{exc.msg}")
                continue
            for docstring in iter_docstrings(tree):
                if "?" in docstring.value or "\ufffd" in docstring.value:
                    failures.append(
                        f"{relative}:{docstring.lineno}: 文档字符串含 ASCII 问号或 Unicode 替换字符"
                    )

        self.assertFalse(failures, "\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
