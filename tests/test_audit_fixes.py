# -*- coding: utf-8 -*-
"""审计修复回归：并发隔离、最优配对、结构校验与安全边界。"""
import io
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

import openpyxl

from core import common_core, compare_core, currency_core, excel_tools_core
from core import incremental_cache, pivot_core, purchase_core, settings, task_history
from core import tauri_bridge, text_core, updater


class TestAuditFixes(unittest.TestCase):
    """集中保护代码审计中已经修复的并发、匹配和安全退化问题。"""

    def test_pivot_cache_materializes_current_web_job(self):
        """命中缓存时仍应把产物复制到当前 Web 任务目录，不能返回上一任务路径。"""

        with tempfile.TemporaryDirectory(prefix="fyt_audit_cache_") as root:
            source = os.path.join(root, "输入.xlsx")
            with open(source, "wb") as file_obj:
                file_obj.write(b"same-input")
            cache_path = os.path.join(root, "cache.json")
            # 保存并恢复进程级环境和单例设置，避免本用例改变后续缓存测试的运行根。
            old_env = {key: os.environ.get(key) for key in (
                "FYT_INCREMENTAL_CACHE_PATH", "FYT_WEB_OUTPUT_ROOT")}
            state = settings.get_settings()
            old_enabled = state.get("enable_incremental_cache", True)
            state._data["enable_incremental_cache"] = True  # 开启增量缓存
            plan = {"in_paths": [source], "files": 1, "sheets": [],
                    "held_index": [], "unit_conflicts": [], "spec_merges": []}

            def apply_plan(_plan, _choices, out_path, log=None):
                """模拟销售表生成器，在指定当前任务目录创建可缓存产物。"""

                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as file_obj:
                    file_obj.write(b"result")
                return {"out": out_path, "groups": 0, "total": 0,
                        "level": "可信", "score": 100, "review": {}}

            try:
                os.environ["FYT_INCREMENTAL_CACHE_PATH"] = cache_path  # 缓存索引隔离
                with mock.patch.object(pivot_core, "warn_if_uncached"), \
                        mock.patch.object(pivot_core, "analyze_workbooks", return_value=plan), \
                        mock.patch.object(pivot_core, "_default_choices", return_value={}), \
                        mock.patch.object(pivot_core, "apply_plan", side_effect=apply_plan):
                    os.environ["FYT_WEB_OUTPUT_ROOT"] = os.path.join(root, "job-a")  # 首个任务目录
                    first = pivot_core.run(source)
                    os.environ["FYT_WEB_OUTPUT_ROOT"] = os.path.join(root, "job-b")  # 当前任务目录
                    second = pivot_core.run(source)
                self.assertTrue(second["cache_hit"])  # 第二次命中缓存
                self.assertNotEqual(first["out"], second["out"])  # 产物复制到当前任务
                self.assertIn("job-b", second["out"])  # 路径指向当前任务
                self.assertTrue(os.path.isfile(second["out"]))  # 文件确实存在
            finally:
                state._data["enable_incremental_cache"] = old_enabled
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_pivot_cache_serializes_concurrent_writes(self):
        """多个线程同时写缓存索引时不得丢条目或产生损坏 JSON。"""

        with tempfile.TemporaryDirectory(prefix="fyt_audit_lock_") as root:
            cache_path = os.path.join(root, "cache.json")
            artifact = os.path.join(root, "out.xlsx")
            with open(artifact, "wb") as file_obj:
                file_obj.write(b"ok")

            def write(index):
                """由单个线程写入唯一缓存键。"""

                incremental_cache.put("key-%d" % index, "pivot", {"index": index},
                                      [artifact], path=cache_path)

            workers = [threading.Thread(target=write, args=(index,)) for index in range(12)]  # 数量足以放大无锁读改写竞争。
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            self.assertEqual(incremental_cache.stats(cache_path)["entries"], 12)  # 并发写入无丢失

    def test_pivot_parser_patch_is_serialized(self):
        """openpyxl 透视缓存猴子补丁必须串行进入并在退出后恢复原属性。"""

        from openpyxl.reader.workbook import WorkbookParser
        original = WorkbookParser.pivot_caches
        entered = threading.Event()
        release = threading.Event()
        second_entered = threading.Event()

        def first():
            """持有全局解析补丁锁，直到测试主线程允许释放。"""

            with common_core._skip_pivot_cache_parse():
                entered.set()
                release.wait(2)

        def second():
            """等待第一线程进入后尝试获取同一补丁锁。"""

            entered.wait(2)
            with common_core._skip_pivot_cache_parse():
                second_entered.set()

        a = threading.Thread(target=first)
        b = threading.Thread(target=second)
        a.start(); b.start()
        entered.wait(2)
        self.assertFalse(second_entered.wait(0.1))  # 第一线程未释放前，第二线程不得进入全局补丁区。
        release.set()
        a.join(2); b.join(2)
        self.assertTrue(second_entered.is_set())  # 释放后第二线程进入
        self.assertIs(WorkbookParser.pivot_caches, original)  # 退出后恢复原属性

    def test_purchase_uses_maximum_cardinality_matching(self):
        """采购匹配应选择最大配对数，避免贪心先选后导致本可匹配的行落单。"""

        def row(batch):
            """构造除批次外完全相同的采购匹配行。"""

            return {"name": "材料A", "spec": "S", "qty": 1, "no": None, "batch": batch}

        matched_a, matched_b, pairs = purchase_core.match_rows(
            [row("123"), row("123-01")], [row("123"), row("123-02")])
        self.assertEqual(sum(matched_a), 2)  # 两侧全部匹配
        self.assertEqual(sum(matched_b), 2)
        self.assertEqual(len(pairs), 2)  # 最大配对数

    def test_stack_tables_aligns_reordered_headers_and_reads_csv(self):
        """纵向合并按列名对齐乱序表头，并接受 CSV 与 Excel 混合输入。"""

        with tempfile.TemporaryDirectory(prefix="fyt_audit_excel_") as root:
            def make_book(name, rows):
                """生成指定表头顺序的合成工作簿。"""

                path = os.path.join(root, name)
                book = openpyxl.Workbook()
                for row in rows:
                    book.active.append(row)
                book.save(path)
                book.close()
                return path

            first = make_book("a.xlsx", [["编码", "数量"], ["M1", 10]])
            second = make_book("b.xlsx", [["数量", "编码"], [20, "M2"]])
            result = excel_tools_core.stack_tables([first, second], out_dir=root)
            book = openpyxl.load_workbook(result["out_file"], data_only=True)
            self.assertEqual(list(book.active.values)[2][:2], ("M2", 20))  # 乱序表头按列名对齐
            book.close()
            csv_path = os.path.join(root, "c.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as file_obj:
                file_obj.write("编码,数量\nM3,30\n")
            merged = excel_tools_core.merge_books([first, csv_path], out_dir=root)
            self.assertTrue(os.path.isfile(merged["out_file"]))  # CSV 与 Excel 混合合并

    def test_compare_preserves_leading_zero_and_compares_duplicates(self):
        """文本编码前导零不可数值化，重复键也需逐条比较而非字典覆盖。"""

        headers = ["主键", "编码", "数量"]
        result = compare_core.compare(
            headers, [{"主键": "A", "编码": "001", "数量": 1}],
            headers, [{"主键": "A", "编码": "1", "数量": 1}], "主键")
        self.assertEqual(result["counts"]["diffs"], 1)  # 前导零差异保留
        duplicated = compare_core.compare(
            headers, [{"主键": "A", "编码": "X", "数量": 1},
                      {"主键": "A", "编码": "X", "数量": 9}],
            headers, [{"主键": "A", "编码": "X", "数量": 1},
                      {"主键": "A", "编码": "X", "数量": 10}], "主键")
        self.assertEqual(duplicated["counts"]["diffs"], 1)  # 重复键逐条比较

    def test_invalid_date_and_configuration_fall_back_safely(self):
        """非法日期返回空值，损坏配置字段回退为默认结构而不导致启动失败。"""

        self.assertIsNone(common_core.norm_date("2026-02-31"))  # 非法日历日
        self.assertIsNone(common_core.norm_date("20261340"))  # 非法月份
        with tempfile.TemporaryDirectory(prefix="fyt_audit_settings_") as root:
            config_path = os.path.join(root, "配置.json")
            with open(config_path, "w", encoding="utf-8") as file_obj:
                json.dump({"arrival": []}, file_obj)
            with mock.patch.dict(os.environ, {"FYT_CONFIG_PATH": config_path}):
                loaded = settings.Settings()
            self.assertIsInstance(loaded.arrival, dict)  # 损坏数组回退字典
            self.assertEqual(loaded.arrival["last_total"], 566)  # 默认值

    def test_bridge_rejects_empty_directory_and_nonfinite_currency(self):
        """桥接拒绝空目录，金额拒绝非有限数，数值排序仍保持非数字项稳定。"""

        with self.assertRaisesRegex(ValueError, "不能为空"):
            tauri_bridge._payload_dir({}, "root")  # 空目录拒绝
        self.assertFalse(currency_core.to_capital("NaN")[0])  # 非有限数拒绝
        self.assertFalse(currency_core.to_capital("Infinity")[0])
        self.assertEqual(text_core.sort_lines("x\n2\n1", numeric=True, reverse=True), "2\n1\nx")  # 非数字项稳定

    def test_cancelled_task_cannot_be_overwritten_by_completion(self):
        """取消状态是终态，迟到的后台完成回调不得把任务重新标记为成功。"""

        with tempfile.TemporaryDirectory(prefix="fyt_audit_tasks_") as root:
            db_path = os.path.join(root, "tasks.db")
            task_id = task_history.start_task("pivot", "透视", {"request_id": "req"}, db_path)
            self.assertEqual(task_history.cancel_request("req", db_path), 1)  # 取消生效
            self.assertFalse(task_history.finish_task(task_id, "ok", db_path=db_path))  # 取消后不可完成
            self.assertEqual(task_history.list_recent(db_path=db_path)[0]["status"], "cancelled")  # 终态保留

    def test_update_manifest_requires_hash_and_bypasses_proxy(self):
        """更新清单缺少 SHA-256 时必须拒绝，并使用清单声明的完整下载地址。"""

        body = json.dumps({"version": "9.9.9", "url": "https://example.com/app.exe"}).encode()

        class Response:
            """模拟 urllib 上下文响应，仅返回缺少哈希的更新清单。"""

            def read(self):
                """返回预设 JSON 字节。"""

                return body

            def __enter__(self):
                """支持 urlopen 响应的上下文管理协议。"""

                return self

            def __exit__(self, *_args):
                """不吞掉上下文内部异常。"""

                return False

        with mock.patch.object(updater.version, "UPDATE_MANIFEST_URL", "https://example.com/latest.json"), \
                mock.patch.object(updater.urllib.request, "urlopen", return_value=Response()) as request:
            result = updater.check_update()
        self.assertEqual(result["status"], "error")  # 缺少哈希拒绝更新
        self.assertIn("SHA-256", result["msg"])  # 错误信息指出哈希
        self.assertIn("example.com/latest.json", request.call_args.args[0].full_url)  # 使用清单声明地址

    def test_failed_installer_download_removes_partial_file(self):
        """安装包下载失败后必须删除旧 .part，防止下次误用不完整文件。"""

        with tempfile.TemporaryDirectory(prefix="fyt_audit_update_") as root:
            part = os.path.join(root, "app.exe.part")
            with open(part, "wb") as file_obj:
                file_obj.write(b"old-partial")
            with mock.patch.object(updater.urllib.request, "urlopen",
                                   side_effect=OSError("network down")):
                with self.assertRaises(OSError):
                    updater.download_installer(
                        "https://example.com/app.exe", dest_dir=root,
                        sha256="0" * 64)
            self.assertFalse(os.path.exists(part))  # 下载失败清理残留


if __name__ == "__main__":
    unittest.main()
