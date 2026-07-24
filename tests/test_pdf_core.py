# -*- coding: utf-8 -*-
"""pdf_core.parse_pages 页码解析单元测试（纯函数，不需真实 PDF）。"""
import unittest

from core import pdf_core as pc


class TestParsePages(unittest.TestCase):
    def test_single_and_list(self):
        self.assertEqual(pc.parse_pages("1", 10), [0])
        self.assertEqual(pc.parse_pages("1,3,5", 10), [0, 2, 4])

    def test_range(self):
        self.assertEqual(pc.parse_pages("2-4", 10), [1, 2, 3])

    def test_open_ended(self):
        self.assertEqual(pc.parse_pages("8-", 10), [7, 8, 9])

    def test_dedup_and_order(self):
        # 去重且保持首见顺序
        self.assertEqual(pc.parse_pages("3,1,3,2", 10), [2, 0, 1])

    def test_clamps_out_of_range(self):
        self.assertEqual(pc.parse_pages("5-100", 6), [4, 5])

    def test_reversed_range(self):
        self.assertEqual(pc.parse_pages("4-2", 10), [1, 2, 3])

    def test_fullwidth_separators(self):
        self.assertEqual(pc.parse_pages("1，3－4", 10), [0, 2, 3])

    def test_empty_raises(self):
        with self.assertRaises(pc.PdfError):
            pc.parse_pages("", 10)
        with self.assertRaises(pc.PdfError):
            pc.parse_pages("   ", 10)

    def test_all_out_of_range_raises(self):
        with self.assertRaises(pc.PdfError):
            pc.parse_pages("50,60", 10)

    def test_junk_segment_ignored(self):
        # "a-b" 非法段被跳过，"3" 仍生效
        self.assertEqual(pc.parse_pages("a-b,3", 10), [2])


if __name__ == "__main__":
    unittest.main()
