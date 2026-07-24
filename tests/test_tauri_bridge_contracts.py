# -*- coding: utf-8 -*-
"""Tauri 桥接全动作契约测试，不重复验证各 core 的算法细节。"""
import os
import tempfile
import unittest
from unittest import mock

import openpyxl
from pypdf import PdfWriter

from core import mapping_store
from core import settings as settings_mod
from core import tauri_bridge
from core import template_store


class TestTauriBridgeContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fyt_tauri_contract_")
        self.old_env = {key: os.environ.get(key) for key in (
            "FYT_CONFIG_PATH", "FYT_TASK_HISTORY_PATH", "FYT_INCREMENTAL_CACHE_PATH",
            "FYT_MAPPING_STORE_PATH", "FYT_TEMPLATE_STORE_PATH")}
        os.environ["FYT_CONFIG_PATH"] = self.path("配置.json")
        os.environ["FYT_TASK_HISTORY_PATH"] = self.path("任务.db")
        os.environ["FYT_INCREMENTAL_CACHE_PATH"] = self.path("缓存.json")
        os.environ["FYT_MAPPING_STORE_PATH"] = self.path("映射.json")
        os.environ["FYT_TEMPLATE_STORE_PATH"] = self.path("模板.json")
        self.old_settings = settings_mod._instance
        settings_mod._instance = None
        settings = settings_mod.get_settings()
        settings.set("output_mode", "custom")
        settings.set("custom_output_root", self.path("输出"))
        settings.save()
        self.file_a = self.path("A.xlsx")
        self.file_b = self.path("B.xlsx")
        self._write_book(self.file_a, [["编号", "数量"], ["A", 1], ["B", 2]])
        self._write_book(self.file_b, [["编号", "数量"], ["A", 1], ["B", 3]])

    def tearDown(self):
        settings_mod._instance = self.old_settings
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    def path(self, name):
        return os.path.join(self.temp.name, name)

    @staticmethod
    def _write_book(path, rows):
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "数据"
        for row in rows:
            worksheet.append(row)
        workbook.save(path)
        workbook.close()

    @staticmethod
    def dispatch(action, payload=None):
        response = tauri_bridge.dispatch({"action": action, "payload": payload or {}})
        return response["data"]

    def test_system_preview_and_sheet_actions(self):
        sheets = self.dispatch("system.sheets", {"path": self.file_a})
        self.assertEqual(sheets["sheets"], ["数据"])
        preview = self.dispatch("system.preview", {
            "path": self.file_a, "sheet": "数据", "max_rows": 3, "max_cols": 2})
        self.assertIn("编号", str(preview))

    def test_six_business_action_payloads(self):
        with mock.patch("core.attendance_core.run", return_value={"out_dir": self.temp.name}) as run:
            self.dispatch("attendance.run", {
                "targets": [self.file_a], "sources": [self.file_b],
                "options": {"workday_hours": 8}})
            self.assertEqual(run.call_args.args[:2], ([self.file_a], [self.file_b]))
            self.assertEqual(run.call_args.kwargs["opts"].workday_hours, 8)
            self.assertTrue(callable(run.call_args.kwargs["progress"]))

        with mock.patch("core.reconcile_core.analyze", return_value={"target": {}}) as analyze:
            self.dispatch("reconcile.analyze", {
                "target": [self.file_a], "sources": [self.file_b], "labor": [self.file_b]})
            self.assertEqual(analyze.call_args.args[:3], (self.file_a, [self.file_b], [self.file_b]))
        with mock.patch("core.reconcile_core.run", return_value={"out_dir": self.temp.name}) as run:
            self.dispatch("reconcile.run", {
                "target": [self.file_a], "sources": [self.file_b], "labor": [self.file_b],
                "choices": {"aliases": {"甲": "乙"}}})
            self.assertEqual(run.call_args.kwargs["choices"]["aliases"], {"甲": "乙"})

        with mock.patch("core.arrival_core.detect_batch", return_value="46A"):
            prepared = self.dispatch("arrival.prepare", {"paths": [self.file_a]})
        self.assertEqual(prepared["rows"][0]["batch_no"], "46A")
        with mock.patch("core.arrival_core.run", return_value={"out_dir": self.temp.name}) as run:
            self.dispatch("arrival.run", {"rows": prepared["rows"], "top_label": "截止 16 点"})
            self.assertEqual(run.call_args.args[0][0]["path"], self.file_a)

        with mock.patch("core.pivot_core.analyze", return_value={"sources": []}) as analyze:
            self.dispatch("pivot.analyze", {"paths": [self.file_a]})
            self.assertEqual(analyze.call_args.args[0], [self.file_a])
        choices = {
            "sheets": {"A.xlsx": ["数据"]},
            "held": [{"sid": "A.xlsx", "ridx": 3, "keep": True}],
            "unit_overrides": [{"gk": ["A", "甲"], "value": "件"}],
            "spec_overrides": [{"gk": ["A", "甲"], "value": "10×20"}],
        }
        with mock.patch("core.pivot_core.run", return_value={"out_dir": self.temp.name}) as run:
            self.dispatch("pivot.run", {"paths": [self.file_a], "choices": choices})
            restored = run.call_args.kwargs["choices"]
            self.assertTrue(restored["held"][("A.xlsx", 3)])
            self.assertEqual(restored["unit_overrides"][("A", "甲")], "件")

        with mock.patch("core.purchase_core.run", return_value={"out_dir": self.temp.name}) as run:
            self.dispatch("purchase.run", {
                "file1": [self.file_a], "file2": [self.file_b],
                "sheet1": "数据", "sheet2": "数据", "name1": "我方", "name2": "供应商"})
            self.assertEqual(run.call_args.kwargs["name2"], "供应商")
            self.assertTrue(callable(run.call_args.kwargs["progress"]))

        with mock.patch("core.delivery_core.analyze", return_value={"sheets": ["数据"]}):
            self.assertEqual(self.dispatch("delivery.analyze", {
                "path": [self.file_a], "sheet": "数据"})["sheets"], ["数据"])
        with mock.patch("core.delivery_core.run", return_value={"out_dir": self.temp.name}) as run:
            self.dispatch("delivery.run", {
                "file1": [self.file_a], "file2": [self.file_b],
                "sheet1": "数据", "sheet2": "数据", "order_type": "KD"})
            self.assertEqual(run.call_args.kwargs["order_type"], "KD")

    def test_invoice_json_roundtrip(self):
        from core import invoice_core
        invoice = invoice_core.Invoice(
            path=self.file_a, num="12345678", date="2026-07-01", seller="测试公司",
            amount=100.0, tax=13.0, total=113.0, rate="13%",
            item_seed="材料费", note_seed="", special=True)
        scan_result = invoice_core.ScanResult([invoice], [(self.file_b, "字段存疑")])
        with mock.patch("core.invoice_core.scan", return_value=scan_result):
            scanned = self.dispatch("invoice.scan", {"root": self.temp.name})["result"]
        self.assertEqual(scanned["invoices"][0]["num"], "12345678")
        rows = [invoice.as_row()]
        with mock.patch("core.invoice_core.generate", return_value={
                "xlsx": self.path("发票.xlsx"), "out_dir": self.temp.name}) as generate:
            generated = self.dispatch("invoice.generate", {
                "scan": scanned, "rows": rows, "month": "2026-07"})["result"]
        self.assertEqual(generated["out_dir"], self.temp.name)
        self.assertIsInstance(generate.call_args.args[0], invoice_core.ScanResult)
        self.assertEqual(generate.call_args.args[0].invoices[0].num, "12345678")
        self.assertTrue(callable(generate.call_args.kwargs["progress"]))

    def test_file_tools_use_real_synthetic_files(self):
        text = self.dispatch("text.transform", {
            "text": "乙\n甲\n乙", "operation": "dedup"})
        self.assertEqual(text["text"].splitlines(), ["乙", "甲"])

        rename_path = self.path("原文件.TXT")
        with open(rename_path, "w", encoding="utf-8") as stream:
            stream.write("测试")
        rule = {"prefix": "新_", "ext_lower": True}
        preview = self.dispatch("rename.preview", {"paths": [rename_path], "rule": rule})
        self.assertEqual(preview["summary"]["ok"], 1)
        applied = self.dispatch("rename.apply", {"paths": [rename_path], "rule": rule})
        self.assertEqual(applied["result"]["count"], 1)
        undone = self.dispatch("rename.undo", {"undo_map": applied["result"]["undo_map"]})
        self.assertEqual(undone["count"], 1)
        self.assertTrue(os.path.isfile(rename_path))

        pdf_path = self.path("两页.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_blank_page(width=200, height=200)
        with open(pdf_path, "wb") as stream:
            writer.write(stream)
        self.assertEqual(self.dispatch("pdf.info", {"path": [pdf_path]})["pages"], 2)
        pdf_result = self.dispatch("pdf.run", {
            "paths": [pdf_path], "mode": "extract", "spec": "1"})["result"]
        self.assertTrue(pdf_result["out_files"])

        excel_result = self.dispatch("excel.run", {
            "paths": [self.file_a, self.file_b], "mode": "merge",
            "keep_formula": False})["result"]
        self.assertTrue(excel_result["out_files"])
        prepared = self.dispatch("compare.prepare", {
            "file1": [self.file_a], "file2": [self.file_b],
            "sheet1": "数据", "sheet2": "数据"})
        self.assertIn("编号", prepared["common"])
        compared = self.dispatch("compare.run", {
            "file1": [self.file_a], "file2": [self.file_b], "key": "编号",
            "sheet1": "数据", "sheet2": "数据"})["result"]
        self.assertEqual(compared["counts"]["diffs"], 1)
        self.assertTrue(os.path.isfile(compared["report_path"]))

    def test_library_mapping_template_and_update_actions(self):
        item = {"name": "A.xlsx", "category": "unknown", "path": self.file_a}
        with mock.patch.object(tauri_bridge.library, "import_many", return_value=[item]) as imported:
            result = self.dispatch("library.import", {"paths": [self.file_a]})["result"]
            self.assertEqual(result["items"][0]["name"], "A.xlsx")
            imported.assert_called_once()
        with mock.patch.object(tauri_bridge.library, "reclassify", return_value=True):
            self.assertEqual(self.dispatch("library.reclassify", {
                "items": [item], "category": "att_source"})["changed"], 1)
        with mock.patch.object(tauri_bridge.library, "remove_item", return_value=1):
            self.assertEqual(self.dispatch("library.remove", {"items": [item]})["removed"], 1)

        mapping = mapping_store.save_mapping(
            "采购模板", "purchase", "数据", 1, {"key": 0}, rows=[["编号", "数量"]])
        self.assertEqual(len(self.dispatch("mappings.list")["items"]), 1)
        self.assertTrue(self.dispatch("mappings.delete", {"id": mapping["id"]})["removed"])
        mapping_store.save_mapping(
            "采购模板", "purchase", "数据", 1, {"key": 0}, rows=[["编号", "数量"]])
        self.assertEqual(self.dispatch("mappings.clear")["removed"], 1)

        template = template_store.save_template(
            "采购模板", "purchase", "数据", ["编号", "数量"])
        rule = self.dispatch("templates.rule", {
            "id": template["id"], "from_version": 1, "to_version": 2,
            "rules": {"rename": {"数量": "采购数量"}}})
        self.assertEqual(rule["to"], 2)
        self.assertEqual(len(self.dispatch("templates.list")["items"]), 1)
        self.assertTrue(self.dispatch("templates.delete", {"id": template["id"]})["removed"])
        template_store.save_template("采购模板", "purchase", "数据", ["编号"])
        self.assertEqual(self.dispatch("templates.clear")["removed"], 1)

        with mock.patch("core.updater.is_configured", return_value=True), \
                mock.patch("core.updater.check_update", return_value={"status": "latest"}):
            checked = self.dispatch("updater.check")
        self.assertTrue(checked["configured"])
        self.assertEqual(checked["result"]["status"], "latest")
        installer = self.path("更新.exe")
        with open(installer, "wb") as stream:
            stream.write(b"test")
        with mock.patch("core.updater.run_installer") as run_installer:
            self.assertTrue(self.dispatch("updater.install", {"path": [installer]})["started"])
            run_installer.assert_called_once_with(installer)


if __name__ == "__main__":
    unittest.main()
