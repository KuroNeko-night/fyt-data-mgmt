# -*- coding: utf-8 -*-
"""考勤来源读取模块的人工映射和跨文件冲突回归测试。"""

from __future__ import annotations

import os
import tempfile
import unittest

import openpyxl

from core import attendance_core
from core.common_core import Options


def _write_source(path, headers, rows):
    """生成一份最小系统打卡来源表。"""

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "每日统计"  # 表名固定为来源模块可识别值
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()  # 关闭工作簿释放文件


class AttendanceSourceTests(unittest.TestCase):
    """保护来源模块拆分后的列映射优先级与字段级覆盖规则。"""

    def setUp(self):
        """创建隔离目录，所有工作簿只包含合成数据。"""

        self.temp = tempfile.TemporaryDirectory(prefix="fyt_att_source_")

    def tearDown(self):
        """删除合成输入文件。"""

        self.temp.cleanup()

    def path(self, name):
        """返回临时目录中的文件路径。"""

        return os.path.join(self.temp.name, name)

    def test_manual_mapping_precedes_header_guess(self):
        """人工确认的角色列应允许读取完全没有标准关键词的表头。"""

        source = self.path("人工映射.xlsx")
        _write_source(source, ["人员", "业务日", "首次", "末次"], [["张三", "2026-08-11", "08:01", "17:02"]])  # 表头无标准关键词
        options = Options(columns={
            os.path.basename(source): {
                "sheet": "每日统计",
                "header": 1,
                "roles": {"name": 0, "date": 1, "on": 2, "off": 3},  # 人工指定角色列
            },
        })
        records = attendance_core.load_source(source, options)
        self.assertEqual(records[("张三", (2026, 8, 11))], ("08:01", "17:02"))  # 人工映射优先生效

    def test_last_conflict_only_overwrites_nonempty_punch(self):
        """补发文件只更新有效下班时间，横线不能擦除旧上班打卡。"""

        first = self.path("第一次.xlsx")
        second = self.path("补发.xlsx")
        headers = ["姓名", "日期", "上班1打卡时间", "下班1打卡时间"]
        _write_source(first, headers, [["张三", "2026-08-11", "08:00", "17:00"]])
        _write_source(second, headers, [["张三", "2026-08-11", "-", "18:00"]])  # 补发仅下班有效
        records, stats = attendance_core.load_source_multi(
            [first, second], Options(conflict="last"), log=lambda _message: None,
        )
        self.assertEqual(records[("张三", (2026, 8, 11))], ("08:00", "18:00"))  # 旧上班不擦除
        self.assertEqual(stats["conflicts"], 1)  # 统计一次冲突


if __name__ == "__main__":
    unittest.main()
