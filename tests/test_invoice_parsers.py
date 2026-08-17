# -*- coding: utf-8 -*-
"""invoice_core 纯解析函数单元测试（税率/金额/销售方/号码，无需 PDF）。"""
import unittest

from core import invoice_core as ic


class TestRate(unittest.TestCase):
    """验证发票税率文本解析和粘连字符恢复。"""

    def test_single_rate_to_decimal(self):
        self.assertEqual(ic._rate("税率13%"), 0.13)  # 百分数转小数
        self.assertEqual(ic._rate("6%"), 0.06)

    def test_multi_rate(self):
        # 多税率去重后按大到小拼接
        self.assertEqual(ic._rate("9%和6%"), "9%+6%")  # 多税率拼接

    def test_none(self):
        self.assertEqual(ic._rate("无税率信息"), "")  # 无税率返回空串

    def test_one_rate_recovers_glued(self):
        # 粘连型号数字的百分数还原成合法税率
        self.assertEqual(ic._one_rate("019713"), "13")  # 粘连数字还原
        self.assertEqual(ic._one_rate("6"), "6")


class TestMoney(unittest.TestCase):
    """验证金额候选提取和价税三元组识别。"""

    def test_last_three_amounts(self):
        raw = "小计 ¥100.00 ... 金额 ¥1000.00 税额 ¥130.00 价税合计 ¥1130.00"
        a, t, tot = ic._money3(raw)
        self.assertEqual((a, t, tot), (1000.00, 130.00, 1130.00))  # 取最后三项金额

    def test_spaces_in_number(self):
        raw = "¥1 000.0 0 ¥1 3 0.0 0 ¥1 130.0 0"
        a, t, tot = ic._money3(raw)
        self.assertEqual((a, t, tot), (1000.00, 130.00, 1130.00))  # 数字内空格被还原

    def test_too_few(self):
        self.assertEqual(ic._money3("¥5.00"), (None, None, None))  # 金额不足返回空


class TestSeller(unittest.TestCase):
    """验证销售方名称从文本区块中提取。"""

    def test_picks_non_buyer_company(self):
        raw = ("购买方\n%s\n销售方\n某某科技有限公司\n开户行: 工商银行\n" % ic.BUYER)
        self.assertEqual(ic._seller(raw), "某某科技有限公司")  # 销售方名称正确提取

    def test_skips_bank_lines(self):
        raw = "开户账号: 中国建设银行 6222\n某某贸易有限公司\n"
        self.assertEqual(ic._seller(raw), "某某贸易有限公司")  # 银行行被跳过


class TestFindNum(unittest.TestCase):
    """验证发票号码定位和数字边界。"""

    def test_anchored_20(self):
        n = "发票号码:" + "1" * 20
        self.assertEqual(ic._find_num(n), "1" * 20)  # 20 位号码完整提取

    def test_anchored_8(self):
        self.assertEqual(ic._find_num("发票号码:12345678"), "12345678")  # 锚定短号提取

    def test_loose_prefers_20(self):
        n = "xx" + "9" * 20 + "yy"
        self.assertEqual(ic._find_num(n), "9" * 20)  # 无锚定时优先 20 位

    def test_none(self):
        self.assertEqual(ic._find_num("no number here"), "")  # 无号码返回空串


class TestDeriveRate(unittest.TestCase):
    """验证缺失税率时由金额与税额反推税率。"""

    def test_from_tax_over_amount(self):
        # 130/1000 = 0.13 -> 吸附到标准税率
        self.assertEqual(ic._derive_rate(1000.0, 130.0, 1130.0, None), 0.13)  # 税额反推税率

    def test_no_tax(self):
        self.assertIsNone(ic._derive_rate(1000.0, 0, 1000.0, None))  # 无税额无法反推


class TestDetectMonth(unittest.TestCase):
    """验证发票集合月份识别与多月份冲突。"""

    def test_most_common(self):
        items = [ic.Invoice(date="2026-06-01"), ic.Invoice(date="2026-06-15"),
                 ic.Invoice(date="2026-05-30")]
        self.assertEqual(ic.detect_month(items), "2026-06")  # 多数月份胜出

    def test_empty(self):
        self.assertEqual(ic.detect_month([]), "")  # 空集合返回空串


class TestFilterMonth(unittest.TestCase):
    """验证按月份筛选发票且保留问题文件。"""

    def test_filter(self):
        items = [ic.Invoice(date="2026-06-01"), ic.Invoice(date="2026-05-30")]
        got = ic.filter_month(items, "2026-06")
        self.assertEqual(len(got), 1)  # 只保留指定月份
        self.assertEqual(got[0].date, "2026-06-01")

    def test_no_filter_when_empty(self):
        items = [ic.Invoice(date="2026-06-01"), ic.Invoice(date="2026-05-30")]
        self.assertEqual(len(ic.filter_month(items, "")), 2)  # 空月份不过滤


if __name__ == "__main__":
    unittest.main()
