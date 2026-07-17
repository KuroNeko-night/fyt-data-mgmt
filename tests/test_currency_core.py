# -*- coding: utf-8 -*-
"""currency_core.to_capital 金额转中文大写单元测试。"""
import unittest

from core.currency_core import to_capital


class TestToCapital(unittest.TestCase):
    def _cap(self, amount):
        ok, s = to_capital(amount)
        self.assertTrue(ok, "expected success for %r, got %r" % (amount, s))
        return s

    def test_docstring_examples(self):
        self.assertEqual(self._cap(1000000), "壹佰万元整")
        self.assertEqual(self._cap(12345.6), "壹万贰仟叁佰肆拾伍元陆角")
        self.assertEqual(self._cap(0.05), "伍分")
        self.assertEqual(self._cap(10800.09), "壹万零捌佰元零玖分")
        self.assertEqual(self._cap(-320), "负叁佰贰拾元整")

    def test_zero(self):
        self.assertEqual(self._cap(0), "零元整")

    def test_integer_adds_zheng(self):
        self.assertEqual(self._cap(100), "壹佰元整")
        self.assertEqual(self._cap(1), "壹元整")

    def test_internal_zeros(self):
        self.assertEqual(self._cap(10005), "壹万零伍元整")
        self.assertEqual(self._cap(100000005), "壹亿零伍元整")

    def test_jiao_only_no_zheng(self):
        # 只有角、无分：不加"整"
        self.assertEqual(self._cap(5.5), "伍元伍角")

    def test_comma_stripping(self):
        self.assertEqual(self._cap("1,000,000"), "壹佰万元整")

    def test_rounding_to_cents(self):
        # 四舍五入到分
        ok, s = to_capital("12.345")
        self.assertTrue(ok)
        self.assertEqual(s, self._cap(12.35))

    def test_invalid_inputs(self):
        ok, msg = to_capital("")
        self.assertFalse(ok)
        ok, msg = to_capital(None)
        self.assertFalse(ok)
        ok, msg = to_capital("abc")
        self.assertFalse(ok)

    def test_too_large(self):
        # 超出兆级应失败并给提示，而不是返回错误结果
        ok, msg = to_capital(10 ** 20)
        self.assertFalse(ok)
        self.assertIn("范围", msg)


if __name__ == "__main__":
    unittest.main()
