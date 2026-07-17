# -*- coding: utf-8 -*-
"""text_core 文本工具箱单元测试。"""
import unittest

from core import text_core as tc


class TestDedup(unittest.TestCase):
    def test_keep_order(self):
        self.assertEqual(tc.dedup_lines("a\nb\na\nc"), "a\nb\nc")

    def test_ignore_case(self):
        self.assertEqual(tc.dedup_lines("A\na", ignore_case=True), "A")
        self.assertEqual(tc.dedup_lines("A\na", ignore_case=False), "A\na")


class TestSort(unittest.TestCase):
    def test_lexical(self):
        self.assertEqual(tc.sort_lines("c\na\nb"), "a\nb\nc")
        self.assertEqual(tc.sort_lines("c\na\nb", reverse=True), "c\nb\na")

    def test_numeric(self):
        self.assertEqual(tc.sort_lines("item 10\nitem 2\nitem 1", numeric=True),
                         "item 1\nitem 2\nitem 10")

    def test_numeric_nonnumbers_last(self):
        out = tc.sort_lines("x\n2\n1", numeric=True).split("\n")
        self.assertEqual(out, ["1", "2", "x"])


class TestLineOps(unittest.TestCase):
    def test_remove_empty(self):
        self.assertEqual(tc.remove_empty_lines("a\n\n  \nb"), "a\nb")

    def test_trim(self):
        self.assertEqual(tc.trim_lines("  a \n\tb\t"), "a\nb")

    def test_collapse_spaces(self):
        self.assertEqual(tc.collapse_spaces("a   b\t\tc"), "a b c")

    def test_case(self):
        self.assertEqual(tc.to_upper("aBc"), "ABC")
        self.assertEqual(tc.to_lower("aBc"), "abc")

    def test_reverse(self):
        self.assertEqual(tc.reverse_lines("a\nb\nc"), "c\nb\na")


class TestLineNumbers(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(tc.add_line_numbers("a\nb"), "1. a\n2. b")

    def test_start_and_sep(self):
        self.assertEqual(tc.add_line_numbers("a\nb", start=5, sep=") "), "5) a\n6) b")

    def test_pad(self):
        text = "\n".join(str(i) for i in range(10))   # 10 行 -> 宽度 2
        out = tc.add_line_numbers(text, pad=True).split("\n")
        self.assertTrue(out[0].startswith("01. "))
        self.assertTrue(out[9].startswith("10. "))


class TestExtract(unittest.TestCase):
    def test_email(self):
        out = tc.extract("foo@a.com bar baz@b.cn foo@a.com", "email")
        self.assertEqual(out.split("\n"), ["foo@a.com", "baz@b.cn"])

    def test_phone(self):
        out = tc.extract("call 13800138000 or 15912345678", "phone")
        self.assertEqual(out.split("\n"), ["13800138000", "15912345678"])

    def test_phone_boundary(self):
        # 前后粘连数字不应误匹配
        self.assertEqual(tc.extract("x1380013800012345", "phone"), "")

    def test_url(self):
        out = tc.extract("see https://a.com/x and http://b.cn", "url")
        self.assertEqual(out.split("\n"), ["https://a.com/x", "http://b.cn"])

    def test_unknown_kind(self):
        self.assertEqual(tc.extract("whatever", "bogus"), "")


class TestStats(unittest.TestCase):
    def test_counts(self):
        s = tc.stats("ab cd\n\nef")
        self.assertEqual(s["lines"], 3)
        self.assertEqual(s["nonempty_lines"], 2)
        self.assertEqual(s["words"], 3)
        self.assertEqual(s["chars"], len("ab cd\n\nef"))
        self.assertEqual(s["chars_no_ws"], 6)


if __name__ == "__main__":
    unittest.main()
