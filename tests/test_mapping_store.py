# -*- coding: utf-8 -*-
"""字段映射中心核心存储与自动复用测试。"""
import os
import tempfile
import unittest

import openpyxl

from core import common_core, mapping_store


class TestMappingStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fyt_mapping_")
        self.path = os.path.join(self.tmp.name, "mapping.json")
        self.old = os.environ.get("FYT_MAPPING_STORE_PATH")
        os.environ["FYT_MAPPING_STORE_PATH"] = self.path

    def tearDown(self):
        if self.old is None:
            os.environ.pop("FYT_MAPPING_STORE_PATH", None)
        else:
            os.environ["FYT_MAPPING_STORE_PATH"] = self.old
        self.tmp.cleanup()

    def test_save_find_replace_and_delete(self):
        rows = [["姓名", "日期", "实际工时"], ["张三", "2026-07-01", 8]]
        saved = mapping_store.save_mapping(
            "考勤模板", "rec_source", "Sheet1", 1,
            {"name": 0, "date": 1, "work": 2}, rows=rows, path=self.path)
        found = mapping_store.find_for_rows("Sheet1", rows, "rec_source", self.path)
        self.assertEqual(found["id"], saved["id"])
        mapping_store.save_mapping(
            "考勤模板（更新）", "rec_source", "Sheet1", 1,
            {"name": 0, "date": 1}, rows=rows, path=self.path)
        self.assertEqual(len(mapping_store.list_mappings(path=self.path)), 1)
        self.assertTrue(mapping_store.delete_mapping(saved["id"], path=self.path))
        self.assertEqual(mapping_store.list_mappings(path=self.path), [])

    def test_apply_saved_mapping_to_options(self):
        opts = common_core.Options()
        mapping = {"sheet": "总表", "header": 3,
                   "roles": {"name": 1, "work": 4}}
        self.assertTrue(common_core.apply_saved_mapping(opts, r"C:\data\a.xlsx", mapping))
        self.assertEqual(opts.resolve_sheet(r"C:\other\a.xlsx"), "总表")
        self.assertEqual(opts.resolve_header(r"C:\other\a.xlsx"), 3)
        self.assertEqual(opts.resolve_roles(r"C:\other\a.xlsx"), {"name": 1, "work": 4})

    def test_auto_apply_by_template_fingerprint(self):
        book = os.path.join(self.tmp.name, "本月总表.xlsx")
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "总表"
        ws.append(["姓名", "所属公司", "出勤工时"])
        ws.append(["张三", "甲公司", 8])
        wb.save(book)
        _, rows = common_core.preview_rows(book, sheet="总表", limit=5)
        mapping_store.save_mapping("月度总表", "rec_zong", "总表", 1,
                                   {"name": 0, "comp": 1, "work": 2}, rows=rows)
        opts = common_core.Options()
        found = common_core.auto_apply_mapping(opts, book, "rec_zong")
        self.assertEqual(found["name"], "月度总表")
        self.assertEqual(opts.resolve_roles(book)["work"], 2)


if __name__ == "__main__":
    unittest.main()
