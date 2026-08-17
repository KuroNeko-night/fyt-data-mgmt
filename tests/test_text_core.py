# -*- coding: utf-8 -*-
"""text_core 文本工具箱单元测试。"""
import unittest

from core import text_core as tc


class TestDedup(unittest.TestCase):
    """验证文本去重顺序和大小写策略。"""

    def test_keep_order(self):
        self.assertEqual(tc.dedup_lines("a\nb\na\nc"), "a\nb\nc")  # 去重保持首见顺序

    def test_ignore_case(self):
        self.assertEqual(tc.dedup_lines("A\na", ignore_case=True), "A")  # 忽略大小写去重
        self.assertEqual(tc.dedup_lines("A\na", ignore_case=False), "A\na")  # 区分大小写保留


class TestSort(unittest.TestCase):
    """验证字典序、数值排序和非数字位置。"""

    def test_lexical(self):
        self.assertEqual(tc.sort_lines("c\na\nb"), "a\nb\nc")  # 字典序
        self.assertEqual(tc.sort_lines("c\na\nb", reverse=True), "c\nb\na")  # 逆序

    def test_numeric(self):
        self.assertEqual(tc.sort_lines("item 10\nitem 2\nitem 1", numeric=True),
                         "item 1\nitem 2\nitem 10")  # 按数字大小排序

    def test_numeric_nonnumbers_last(self):
        out = tc.sort_lines("x\n2\n1", numeric=True).split("\n")
        self.assertEqual(out, ["1", "2", "x"])  # 非数字行排最后


class TestLineOps(unittest.TestCase):
    """验证空行、首尾空白、连续空格、大小写和反转操作。"""

    def test_remove_empty(self):
        self.assertEqual(tc.remove_empty_lines("a\n\n  \nb"), "a\nb")  # 空白行删除

    def test_trim(self):
        self.assertEqual(tc.trim_lines("  a \n\tb\t"), "a\nb")  # 首尾空白去除

    def test_collapse_spaces(self):
        self.assertEqual(tc.collapse_spaces("a   b\t\tc"), "a b c")  # 连续空白折叠

    def test_case(self):
        self.assertEqual(tc.to_upper("aBc"), "ABC")  # 转大写
        self.assertEqual(tc.to_lower("aBc"), "abc")  # 转小写

    def test_reverse(self):
        self.assertEqual(tc.reverse_lines("a\nb\nc"), "c\nb\na")  # 行序反转


class TestLineNumbers(unittest.TestCase):
    """验证行号起点、分隔符和补零格式。"""

    def test_basic(self):
        self.assertEqual(tc.add_line_numbers("a\nb"), "1. a\n2. b")  # 默认从 1 开始

    def test_start_and_sep(self):
        self.assertEqual(tc.add_line_numbers("a\nb", start=5, sep=") "), "5) a\n6) b")  # 自定义起点与分隔

    def test_pad(self):
        text = "\n".join(str(i) for i in range(10))   # 10 行 -> 宽度 2
        out = tc.add_line_numbers(text, pad=True).split("\n")
        self.assertTrue(out[0].startswith("01. "))  # 位数补零
        self.assertTrue(out[9].startswith("10. "))


class TestExtract(unittest.TestCase):
    """验证邮箱、电话、网址提取和未知类型拒绝。"""

    def test_email(self):
        out = tc.extract("foo@a.com bar baz@b.cn foo@a.com", "email")
        self.assertEqual(out.split("\n"), ["foo@a.com", "baz@b.cn"])  # 邮箱去重提取

    def test_phone(self):
        out = tc.extract("call 13800138000 or 15912345678", "phone")
        self.assertEqual(out.split("\n"), ["13800138000", "15912345678"])  # 手机号提取

    def test_phone_boundary(self):
        # 前后粘连数字不应误匹配
        self.assertEqual(tc.extract("x1380013800012345", "phone"), "")  # 粘连号码不误报

    def test_url(self):
        out = tc.extract("see https://a.com/x and http://b.cn", "url")
        self.assertEqual(out.split("\n"), ["https://a.com/x", "http://b.cn"])  # URL 提取

    def test_unknown_kind(self):
        self.assertEqual(tc.extract("whatever", "bogus"), "")  # 未知类型返回空


class TestStats(unittest.TestCase):
    """验证文本行数、字符数和非空统计。"""

    def test_counts(self):
        s = tc.stats("ab cd\n\nef")
        self.assertEqual(s["lines"], 3)  # 总行数
        self.assertEqual(s["nonempty_lines"], 2)  # 非空行数
        self.assertEqual(s["words"], 3)  # 单词数
        self.assertEqual(s["chars"], len("ab cd\n\nef"))  # 总字符数
        self.assertEqual(s["chars_no_ws"], 6)  # 去空白字符数


if __name__ == "__main__":
    unittest.main()
