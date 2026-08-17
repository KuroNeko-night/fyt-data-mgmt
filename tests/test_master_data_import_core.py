# -*- coding: utf-8 -*-
"""主数据库表格学习、冲突治理与合并。"""
from __future__ import annotations

import os
import tempfile
import unittest

from openpyxl import Workbook

from core import master_data_import_core, material_catalog


class MasterDataImportCoreTests(unittest.TestCase):
    """保护管理员表格学习的分析、冲突复核、确认和定期合并状态机。"""

    def setUp(self):
        """把主数据库和导入批次索引隔离到当前用例临时目录。"""

        self.temp = tempfile.TemporaryDirectory(prefix="fyt_master_import_")
        self.catalog_path = os.path.join(self.temp.name, "catalog.json")
        self.import_root = os.path.join(self.temp.name, "imports")
        os.environ["FYT_CATALOG_PATH"] = self.catalog_path  # 主数据库与批次索引隔离

    def tearDown(self):
        """移除主数据路径覆盖并删除上传批次副本。"""

        os.environ.pop("FYT_CATALOG_PATH", None)
        self.temp.cleanup()

    def make_book(self, name: str, rows: list[list[object]], headers=None) -> str:
        """生成可控制字段和冲突行的主数据学习工作簿。"""

        path = os.path.join(self.temp.name, name)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "材料清单"
        sheet.append(headers or ["物料编码", "物料名称", "规格型号", "单位", "供应商名称", "供应商编码"])
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        workbook.close()
        return path

    def analyze(self, path: str):
        """以固定管理员身份分析文件，简化各状态迁移用例。"""

        return master_data_import_core.analyze(
            path,
            original_name=os.path.basename(path),
            uploader_id=1,
            uploader_name="系统管理员",
            root=self.import_root,
        )

    def test_clean_batch_requires_confirmation_before_merge(self):
        """无冲突批次也必须人工确认后才能写主数据库，并在合并前保持零副作用。"""

        path = self.make_book("clean.xlsx", [["M001", "铁箱", "100x50", "个", "众瀚", "GYS01"]])
        batch = self.analyze(path)
        self.assertEqual(batch["status"], "ready_to_confirm")  # 无冲突待确认
        self.assertEqual(batch["candidate_count"], 5)  # 五个字段候选
        self.assertEqual(material_catalog.load()["materials"], {})  # 合并前零副作用

        with self.assertRaises(ValueError):
            master_data_import_core.merge_batch(batch["id"], root=self.import_root)  # 未确认不可合并
        confirmed = master_data_import_core.confirm_batch(
            batch["id"], actor_id=1, actor_name="系统管理员", root=self.import_root)
        self.assertEqual(confirmed["status"], "ready")  # 确认后进入就绪
        merged = master_data_import_core.merge_batch(
            batch["id"], actor_id=1, actor_name="系统管理员", root=self.import_root)
        self.assertEqual(merged["status"], "merged")  # 合并完成
        catalog = material_catalog.load()
        self.assertEqual(catalog["suppliers"]["众瀚"], "GYS01")  # 供应商入库
        self.assertEqual(catalog["materials"]["M001"]["spec"], "100x50")  # 规格入库
        self.assertTrue(merged["merge_summary"]["backup_path"])  # 合并前备份

    def test_in_file_conflict_keeps_sources_and_can_use_candidate(self):
        """同一文件冲突应保留行级来源，并允许管理员选择候选值。"""

        path = self.make_book("conflict.xlsx", [
            ["M001", "铁箱", "100x50", "个", "众瀚", "GYS01"],
            ["M001", "铁箱新版", "100x50", "个", "众瀚", "GYS01"],
        ])
        batch = self.analyze(path)
        self.assertEqual(batch["status"], "needs_review")  # 文件内冲突需复核
        conflict = next(item for item in batch["candidates"] if item["relation_type"] == "material_name")
        self.assertEqual({item["value"] for item in conflict["values"]}, {"铁箱", "铁箱新版"})  # 冲突值集合
        self.assertEqual({source["row"] for item in conflict["values"] for source in item["sources"]}, {2, 3})  # 行级来源

        reviewed = master_data_import_core.resolve_conflict(
            batch["id"], conflict["id"], "use_candidate", value="铁箱新版",
            actor_id=1, actor_name="系统管理员", root=self.import_root)
        self.assertEqual(reviewed["status"], "ready_to_confirm")  # 解决后待确认
        master_data_import_core.confirm_batch(
            batch["id"], actor_id=1, actor_name="系统管理员", root=self.import_root)
        master_data_import_core.merge_batch(batch["id"], root=self.import_root)
        self.assertEqual(material_catalog.load()["materials"]["M001"]["name"], "铁箱新版")  # 候选值生效

    def test_catalog_conflict_can_keep_current(self):
        """上传值与正式主库冲突时可保留管理员已确认的当前值。"""

        material_catalog.upsert_material("M001", "正式名称")
        path = self.make_book("catalog-conflict.xlsx", [["M001", "上传名称", "", "", "", ""]])
        batch = self.analyze(path)
        conflict = next(item for item in batch["candidates"] if item["relation_type"] == "material_name")
        self.assertEqual(conflict["current_value"], "正式名称")  # 冲突展示正式值
        master_data_import_core.resolve_conflict(
            batch["id"], conflict["id"], "keep_current",
            actor_id=1, actor_name="系统管理员", root=self.import_root)
        master_data_import_core.confirm_batch(
            batch["id"], actor_id=1, actor_name="系统管理员", root=self.import_root)
        master_data_import_core.merge_batch(batch["id"], root=self.import_root)
        self.assertEqual(material_catalog.load()["materials"]["M001"]["name"], "正式名称")  # 保留当前值

    def test_new_conflict_after_confirmation_returns_to_review(self):
        """确认后到合并前若主库被并发修改，批次必须重新进入复核而非覆盖。"""

        path = self.make_book("late-conflict.xlsx", [["M001", "上传名称", "", "", "", ""]])
        batch = self.analyze(path)
        master_data_import_core.confirm_batch(
            batch["id"], actor_id=1, actor_name="系统管理员", root=self.import_root)
        material_catalog.upsert_material("M001", "其他任务写入")  # 模拟另一管理员在确认窗口内更新正式值。
        result = master_data_import_core.merge_batch(batch["id"], root=self.import_root)
        self.assertEqual(result["status"], "needs_review")  # 合并前发现并发冲突
        conflict = next(item for item in result["candidates"] if item["relation_type"] == "material_name")
        self.assertEqual(conflict["current_value"], "其他任务写入")  # 新值成为当前值
        self.assertIsNone(conflict["decision"])  # 决策清空待重新复核

    def test_duplicate_file_is_rejected(self):
        """同内容文件重复上传应返回原批次标识，避免形成重复候选和重复学习。"""

        path = self.make_book("duplicate.xlsx", [["M001", "铁箱", "", "", "", ""]])
        first = self.analyze(path)
        with self.assertRaises(master_data_import_core.DuplicateImportError) as caught:
            self.analyze(path)  # 重复上传同内容文件
        self.assertEqual(caught.exception.batch_id, first["id"])  # 返回原批次 ID

    def test_unrecognized_workbook_is_not_persisted(self):
        """没有可学习关系的表应直接拒绝，不能在导入列表留下空批次。"""

        path = self.make_book("unknown.xlsx", [["A", "B"]], headers=["日期", "数量"])
        with self.assertRaisesRegex(ValueError, "没有识别到"):
            self.analyze(path)  # 无可学习关系拒绝
        self.assertEqual(master_data_import_core.list_batches(self.import_root)["items"], [])  # 不留空批次

    def test_periodic_merge_is_limited_and_idempotent(self):
        """定期合并遵守批次数量上限，已经合并的批次再次执行不会重复写入。"""

        batches = []
        for index in range(2):
            path = self.make_book(f"batch-{index}.xlsx", [[f"M{index}", f"材料{index}", "", "", "", ""]])
            batch = self.analyze(path)
            master_data_import_core.confirm_batch(
                batch["id"], actor_id=1, actor_name="系统管理员", root=self.import_root)
            batches.append(batch)
        first = master_data_import_core.merge_ready_batches(root=self.import_root, limit=1)
        self.assertEqual(len(first["merged"]), 1)  # 限额合并一个
        second = master_data_import_core.merge_ready_batches(root=self.import_root, limit=5)
        self.assertEqual(len(second["merged"]), 1)  # 剩余一个继续合并
        third = master_data_import_core.merge_ready_batches(root=self.import_root, limit=5)
        self.assertEqual(third["merged"], [])  # 幂等不再重复合并


if __name__ == "__main__":
    unittest.main()
