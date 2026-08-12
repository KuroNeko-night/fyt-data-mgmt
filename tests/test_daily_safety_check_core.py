"""安全检查日报日期、分类继承和不合格项统计回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from core import daily_safety_check_core


class DailySafetyCheckCoreTests(unittest.TestCase):
    """验证上传的规范安全检查表能够直接进入日清总览。"""

    def test_analyze_groups_categories_and_unqualified_items(self):
        """空白分类续行应继承上一类别，并正确统计合格与不合格记录。"""

        with tempfile.TemporaryDirectory() as temp_name:
            target = Path(temp_name) / "安全检查记录.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet["A1"] = "安全检查日报"
            sheet["H1"] = date(2026, 8, 4)
            sheet.append(["检查类别", "序号", "检查项目", "安全标准要求", "检查结果", "问题描述", "整改措施", "责任人"])
            sheet.append(["人员安全", 1, "劳保用品", "按规定佩戴", "合格", "佩戴规范", "持续检查", "张工"])
            # 第二条分类为空，模拟模板中的纵向合并单元格，解析后仍应归入“人员安全”。
            sheet.append([None, 2, "作业规范", "无违章作业", "不合格", "隔离带缺失", "当天补齐", "李工"])
            workbook.save(target)
            workbook.close()

            result = daily_safety_check_core.analyze(target, image_dir=Path(temp_name) / "images")

        self.assertEqual(result["report_date"], "2026-08-04")
        self.assertEqual(result["total_checks"], 2)
        self.assertEqual(result["qualified_count"], 1)
        self.assertEqual(result["unqualified_count"], 1)
        self.assertEqual(result["records"][1]["category"], "人员安全")


if __name__ == "__main__":
    unittest.main()
