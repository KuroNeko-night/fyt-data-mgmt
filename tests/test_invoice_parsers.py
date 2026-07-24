# -*- coding: utf-8 -*-
"""invoice_core 纯解析函数单元测试（税率/金额/销售方/号码，无需 PDF）。"""
import unittest

from core import invoice_core as ic


class TestRate(unittest.TestCase):
    def test_single_rate_to_decimal(self):
        self.assertEqual(ic._rate("税率13%"), 0.13)
        self.assertEqual(ic._rate("6%"), 0.06)

    def test_multi_rate(self):
        # 多税率去重后按大到小拼接
        self.assertEqual(ic._rate("9%和6%"), "9%+6%")

    def test_none(self):
        self.assertEqual(ic._rate("无税率信息"), "")

    def test_one_rate_recovers_glued(self):
        # 粘连型号数字的百分数还原成合法税率
        self.assertEqual(ic._one_rate("019713"), "13")
        self.assertEqual(ic._one_rate("6"), "6")


class TestMoney(unittest.TestCase):
    def test_last_three_amounts(self):
        raw = "小计 ¥100.00 ... 金额 ¥1000.00 税额 ¥130.00 价税合计 ¥1130.00"
        a, t, tot = ic._money3(raw)
        self.assertEqual((a, t, tot), (1000.00, 130.00, 1130.00))

    def test_spaces_in_number(self):
        raw = "¥1 000.0 0 ¥1 3 0.0 0 ¥1 130.0 0"
        a, t, tot = ic._money3(raw)
        self.assertEqual((a, t, tot), (1000.00, 130.00, 1130.00))

    def test_too_few(self):
        self.assertEqual(ic._money3("¥5.00"), (None, None, None))


class TestSeller(unittest.TestCase):
    def test_picks_non_buyer_company(self):
        raw = ("购买方\n%s\n销售方\n某某科技有限公司\n开户行: 工商银行\n" % ic.BUYER)
        self.assertEqual(ic._seller(raw), "某某科技有限公司")

    def test_skips_bank_lines(self):
        raw = "开户账号: 中国建设银行 6222\n某某贸易有限公司\n"
        self.assertEqual(ic._seller(raw), "某某贸易有限公司")


class TestFindNum(unittest.TestCase):
    def test_anchored_20(self):
        n = "发票号码:" + "1" * 20
        self.assertEqual(ic._find_num(n), "1" * 20)

    def test_anchored_8(self):
        self.assertEqual(ic._find_num("发票号码:12345678"), "12345678")

    def test_loose_prefers_20(self):
        n = "xx" + "9" * 20 + "yy"
        self.assertEqual(ic._find_num(n), "9" * 20)

    def test_none(self):
        self.assertEqual(ic._find_num("no number here"), "")


class TestDeriveRate(unittest.TestCase):
    def test_from_tax_over_amount(self):
        # 130/1000 = 0.13 -> 吸附到标准税率
        self.assertEqual(ic._derive_rate(1000.0, 130.0, 1130.0, None), 0.13)

    def test_no_tax(self):
        self.assertIsNone(ic._derive_rate(1000.0, 0, 1000.0, None))


class TestDetectMonth(unittest.TestCase):
    def test_most_common(self):
        items = [ic.Invoice(date="2026-06-01"), ic.Invoice(date="2026-06-15"),
                 ic.Invoice(date="2026-05-30")]
        self.assertEqual(ic.detect_month(items), "2026-06")

    def test_empty(self):
        self.assertEqual(ic.detect_month([]), "")


class TestFilterMonth(unittest.TestCase):
    def test_filter(self):
        items = [ic.Invoice(date="2026-06-01"), ic.Invoice(date="2026-05-30")]
        got = ic.filter_month(items, "2026-06")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].date, "2026-06-01")

    def test_no_filter_when_empty(self):
        items = [ic.Invoice(date="2026-06-01"), ic.Invoice(date="2026-05-30")]
        self.assertEqual(len(ic.filter_month(items, "")), 2)


if __name__ == "__main__":
    unittest.main()
