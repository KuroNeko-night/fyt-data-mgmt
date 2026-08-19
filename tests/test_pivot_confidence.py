# -*- coding: utf-8 -*-
"""采购汇总可信度评分规则回归测试。"""
import unittest

from core import pivot_core


def _audit(file_name, sheet, kind, *, use=True, missing=None, confidence=90):
    """构造仅包含可信度规则所需字段的页签审计记录。"""
    return {
        "file": file_name,
        "sheet": sheet,
        "kind": kind,
        "use": use,
        "missing": list(missing or []),
        "confidence": confidence,
    }


class PivotConfidenceTests(unittest.TestCase):
    """钉死来源、字段、文件和结果勾稽的现行扣分口径。"""

    def test_complete_sources_keep_full_score(self):
        """核心来源齐全且结果可勾稽时应保持一百分。"""
        result = pivot_core.assess_confidence({
            "processed": 2,
            "clean_rows": 8,
            "groups": 4,
            "total": 25,
            "audit": [
                _audit("采购.xlsx", "包装", "包装方案汇总"),
                _audit("采购.xlsx", "组托", "组托辅材(PFEP)"),
            ],
        })
        self.assertEqual(result, {"level": "可信", "score": 100, "issues": []})  # 满分可信无问题

    def test_all_penalties_preserve_order_and_threshold(self):
        """缺来源、整文件未采用、字段缺失和异常结果应按既定顺序累计扣分。"""
        result = pivot_core.assess_confidence({
            "processed": 1,
            "clean_rows": 2,
            "groups": 3,
            "total": 0,
            "audit": [
                _audit(
                    "已识别.xlsx", "数据", "通用采购表",
                    missing=["规格"], confidence=70,
                ),
                _audit("未识别.xlsx", "说明", "排除:无数据区", use=False),
            ],
        })
        self.assertEqual(result["score"], 0)  # 扣分到底
        self.assertEqual(result["level"], "存疑")
        messages = [message for _severity, message in result["issues"]]
        self.assertIn("包装方案汇总", messages[0])  # 核心来源缺失
        self.assertIn("组托辅材", messages[1])
        self.assertIn("未识别.xlsx", messages[2])  # 未采用文件
        self.assertIn("缺失字段", messages[3])  # 字段缺失
        self.assertIn("低置信识别", messages[4])  # 低置信来源
        self.assertIn("采购数量总计为 0", messages[5])  # 异常总计
        self.assertIn("分组数(3)大于清洗行数(2)", messages[6])  # 分组数异常

    def test_no_rows_is_zero_but_keeps_explanatory_issues(self):
        """完全无数据时分数归零，同时仍返回两个核心来源缺失说明。"""
        result = pivot_core.assess_confidence({
            "processed": 0,
            "clean_rows": 0,
            "groups": 0,
            "total": 0,
            "audit": [],
        })
        self.assertEqual(result["score"], 0)  # 无数据归零
        self.assertEqual(result["level"], "存疑")
        self.assertEqual(len(result["issues"]), 3)  # 仍给出可解释问题


if __name__ == "__main__":
    unittest.main()
