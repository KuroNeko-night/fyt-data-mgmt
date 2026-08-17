# -*- coding: utf-8 -*-
"""currency_core.to_capital 金额转中文大写单元测试。"""
import unittest

from core.currency_core import to_capital


class TestToCapital(unittest.TestCase):
    """验证人民币大写转换、分角舍入和非法金额边界。"""

    def _cap(self, amount):
        """断言转换成功并返回大写文本。"""

        ok, s = to_capital(amount)
        self.assertTrue(ok, "expected success for %r, got %r" % (amount, s))  # 转换必须成功
        return s

    def test_docstring_examples(self):
        self.assertEqual(self._cap(1000000), "壹佰万元整")  # 整百万加整
        self.assertEqual(self._cap(12345.6), "壹万贰仟叁佰肆拾伍元陆角")  # 角位正确
        self.assertEqual(self._cap(0.05), "伍分")  # 纯分位
        self.assertEqual(self._cap(10800.09), "壹万零捌佰元零玖分")  # 内部零补位
        self.assertEqual(self._cap(-320), "负叁佰贰拾元整")  # 负数前缀

    def test_zero(self):
        self.assertEqual(self._cap(0), "零元整")  # 零值大写

    def test_integer_adds_zheng(self):
        self.assertEqual(self._cap(100), "壹佰元整")
        self.assertEqual(self._cap(1), "壹元整")

    def test_internal_zeros(self):
        self.assertEqual(self._cap(10005), "壹万零伍元整")  # 万位内部零
        self.assertEqual(self._cap(100000005), "壹亿零伍元整")  # 亿位内部零

    def test_jiao_only_no_zheng(self):
        # 只有角、无分：不加"整"
        self.assertEqual(self._cap(5.5), "伍元伍角")

    def test_comma_stripping(self):
        self.assertEqual(self._cap("1,000,000"), "壹佰万元整")  # 千分位逗号忽略

    def test_rounding_to_cents(self):
        # 四舍五入到分
        ok, s = to_capital("12.345")
        self.assertTrue(ok)  # 合法金额可转换
        self.assertEqual(s, self._cap(12.35))  # 第三位小数四舍五入

    def test_invalid_inputs(self):
        ok, msg = to_capital("")
        self.assertFalse(ok)  # 空串非法
        ok, msg = to_capital(None)
        self.assertFalse(ok)  # 空值非法
        ok, msg = to_capital("abc")
        self.assertFalse(ok)  # 非数字非法

    def test_too_large(self):
        # 超出兆级应失败并给提示，而不是返回错误结果
        ok, msg = to_capital(10 ** 20)
        self.assertFalse(ok)  # 超范围不转换
        self.assertIn("范围", msg)


if __name__ == "__main__":
    unittest.main()
