"""业务结果前端投影回归测试。"""

from __future__ import annotations

import unittest

from core import business_result_core


class BusinessResultCoreTests(unittest.TestCase):
    """保护双端统一结果投影的指标口径、隐私裁剪和复核信息结构。"""

    def test_arrival_projection_has_direct_batch_values(self):
        """到料投影应直接给出批次数、总体到料率和每批完成率。"""

        result = {
            "result": {
                "results": [
                    ["26035-01", 3, 7, 10],
                    ["26035-02", 0, 8, 8],
                ],
            },
            "logs": [],
            "task_id": "task-1",
            "out_dir": "输出",
        }
        presentation = business_result_core.present("web.arrival", result)
        self.assertEqual(presentation["kind"], "arrival")
        self.assertEqual(presentation["metrics"][0]["value"], "2")
        self.assertEqual(presentation["metrics"][1]["value"], "83.3%")
        self.assertEqual(presentation["sections"][0]["rows"][0]["batch_no"], "26035-01")
        self.assertEqual(presentation["sections"][0]["rows"][0]["completion_label"], "70.0%")

    def test_arrival_projection_lists_missing_materials_and_quantity_gap(self):
        """批次详情必须保留具体未到物料、需求、实收和缺口数量。"""

        presentation = business_result_core.present("arrival.run", {
            "results": [["26035-01", 1, 9, 10]],
            "batches": [{
                "batch_no": "26035-01",
                "missing_count": 1,
                "arrived_count": 9,
                "total_count": 10,
                "missing_materials": [{
                    "material_code": "A-01",
                    "material_name": "固定螺栓",
                    "supplier": "供应商甲",
                    "demand_quantity": 12,
                    "received_quantity": 9,
                    "shortage_quantity": 3,
                }],
            }],
        })
        self.assertEqual(len(presentation["sections"]), 2)
        detail = presentation["sections"][1]
        self.assertEqual(detail["title"], "未到物料明细")
        self.assertFalse(detail["truncated"])
        self.assertEqual(detail["rows"][0]["material_code"], "A-01")
        self.assertEqual(detail["rows"][0]["shortage_quantity"], "3")

    def test_reconcile_projection_limits_rows_and_keeps_real_total(self):
        """异常预览可截断展示行，但总数与可信度检查必须保持真实值。"""

        # 三十五行超过前端预览上限三十行，用于同时验证截断标记和真实 total。
        anomalies = [{
            "姓名": f"员工{index}",
            "所属劳务公司": "测试劳务",
            "异常类型": "总工时不一致",
            "我司出勤工时": 8,
            "劳务公司工时": 7,
            "差异": 1,
            "差异明细": "1日:我司8/劳务7",
        } for index in range(35)]
        result = {
            "credibility": {
                "level": "需复核",
                "score": 72,
                "checks": [{"级别": "警告", "项目": "名单范围", "说明": "单方名单较多"}],
            },
            "metrics": {
                "matched_pairs": 20,
                "only_us": 2,
                "only_labor": 1,
                "diff_people": 10,
                "anomaly_count": 35,
            },
            "anomalies": anomalies,
        }
        presentation = business_result_core.present("reconcile.run", result)
        section = presentation["sections"][0]
        self.assertEqual(section["total"], 35)
        self.assertEqual(len(section["rows"]), 30)
        self.assertTrue(section["truncated"])
        self.assertEqual(presentation["notices"][0]["title"], "可信度检查提示")
        self.assertEqual(presentation["quality"]["checks"][0]["title"], "名单范围")

    def test_attendance_projection_aggregates_stats_and_parameters(self):
        """考勤投影应聚合匹配率，并把可调参数转换为客户可读标签。"""

        presentation = business_result_core.present("attendance.run", {
            "out_files": [r"C:\output\考勤表_已填写.xlsx"],
            "source_stat": {"records": 12, "conflicts": 1},
            "results": [[
                r"C:\input\考勤表.xlsx",
                r"C:\output\考勤表_已填写.xlsx",
                {"matched": 9, "computed_work": 8, "unmatched": 1, "anomalies": 2},
            ]],
            "parameters": {
                "workday_hours": 8.5,
                "conflict": "first",
                "auto_actual": True,
                "day_max_hours": 15,
                "night_shift": False,
            },
        })
        self.assertEqual(presentation["kind"], "attendance")
        self.assertEqual(presentation["metrics"][2]["value"], "90.0%")
        self.assertEqual(presentation["sections"][0]["rows"][0]["file"], "考勤表.xlsx")
        parameters = {item["key"]: item["value"] for item in presentation["parameters"]}
        self.assertEqual(parameters["conflict"], "先者优先")
        self.assertEqual(parameters["day_max_hours"], "15 小时")
        self.assertTrue(presentation["quality"]["checks"])

    def test_pivot_projection_embeds_quality_and_sheet_audit(self):
        """销售表结果应内嵌可信度和工作表识别审计，不再依赖独立分析文件。"""

        presentation = business_result_core.present("pivot.run", {
            "files": 1,
            "groups": 3,
            "total": 18,
            "score": 82,
            "level": "需复核",
            "issues": [["警告", "采购数量存在一处勾稽提示"]],
            "audit": [{
                "file": r"C:\input\销售数据.xlsx",
                "sheet": "明细",
                "use": True,
                "kind": "采购量核算表",
                "confidence": 88,
                "reason": "识别到材料编码和最终采购数量",
            }],
            "review": {"held_kept_n": 1},
        })
        self.assertEqual(presentation["quality"]["score"], 82)
        self.assertEqual(presentation["quality"]["checks"][0]["title"], "警告")
        self.assertEqual(presentation["sections"][0]["title"], "工作表识别明细")
        self.assertEqual(presentation["sections"][0]["rows"][0]["file"], "销售数据.xlsx")

    def test_delivery_projection_lists_missing_supplier_materials(self):
        """送货计划投影必须列出未匹配供应商物料并呈现关键业务参数。"""

        presentation = business_result_core.present("delivery.run", {
            "plan_path": r"C:\output\送货计划.xlsx",
            "rows": 4,
            "matched": 3,
            "missing": ["M-004"],
            "order_type": "正式订单",
            "supplier_used": True,
            "case_used": True,
            "case_hit": 4,
        })
        self.assertEqual(presentation["sections"][0]["rows"][0]["material_code"], "M-004")
        self.assertEqual(presentation["quality"]["checks"][0]["title"], "供应商匹配")
        self.assertEqual(presentation["parameters"][0]["value"], "正式订单")

    def test_invoice_match_projection_lists_suppliers_for_review(self):
        """发票匹配需按无票采购和有票无采购列出待人工核对供应商。"""

        presentation = business_result_core.present("invoice_match.run", {
            "matched": 2,
            "no_invoice": 1,
            "no_purchase": 1,
            "no_invoice_suppliers": ["供应商甲"],
            "no_purchase_suppliers": ["供应商乙"],
        })
        section = presentation["sections"][0]
        self.assertEqual(section["title"], "待核对供应商")
        self.assertEqual(section["rows"][0], {"supplier": "供应商甲", "status": "无票采购"})
        self.assertEqual(section["rows"][1], {"supplier": "供应商乙", "status": "有发票无采购"})

    def test_compare_quality_does_not_penalize_real_business_differences(self):
        """真实表间差异属于业务结果，不能被误算成解析可信度下降。"""

        presentation = business_result_core.present("compare.run", {
            "key": "编号",
            "columns": ["数量", "单价"],
            "counts": {
                "matched": 1, "diffs": 2, "only_a": 0, "only_b": 0,
                "dup_a": 0, "dup_b": 0, "blank_a": 0, "blank_b": 0,
            },
            "diffs": [
                {"key": "A-1", "column": "数量", "a": 10, "b": 8},
                {"key": "A-1", "column": "单价", "a": 3, "b": 4},
            ],
            "only_a": [],
            "only_b": [],
        })
        self.assertEqual(presentation["quality"]["score"], 100)
        self.assertEqual(presentation["metrics"][1]["value"], "2")
        parameters = {item["key"]: item["value"] for item in presentation["parameters"]}
        self.assertEqual(parameters["columns"], "数量、单价")

    def test_purchase_diff_action_uses_purchase_diff_projection(self):
        """采购计划差异动作必须路由到专用投影，而不是普通采购对账结构。"""

        presentation = business_result_core.present("purchase_plan.diff", {
            "path": r"C:\output\实收差异清单.xlsx",
            "rows": 6,
            "excluded_original_count": 2,
        })
        self.assertEqual(presentation["kind"], "purchase_diff")
        self.assertEqual(presentation["metrics"][0]["value"], "6")

    def test_purchase_projection_uses_side_names_and_conflicts(self):
        """采购对账应使用双方实际名称标注未配对和数量冲突列。"""

        left = {"no": "A-1", "name": "螺栓", "spec": "M8", "qty": 10, "batch": "B01"}
        right = {"no": "A-1", "name": "螺栓", "spec": "M8", "qty": 8, "batch": "B01"}
        result = {
            "name1": "峰运通",
            "name2": "供应商甲",
            "rows1": [left, {"no": "B-1", "name": "垫片", "spec": "M8", "qty": 4, "batch": "B02"}],
            "rows2": [right],
            "matched1": [False, False],
            "matched2": [False],
            "pairs": [],
            "qty_conflicts": [[left, right]],
        }
        presentation = business_result_core.present("purchase.run", result)
        labels = {item["label"] for item in presentation["metrics"]}
        self.assertIn("峰运通未配对", labels)
        self.assertIn("供应商甲未配对", labels)
        conflict = presentation["sections"][0]["rows"][0]
        self.assertEqual(conflict["difference"], "2")
        self.assertEqual(presentation["sections"][0]["columns"][3]["label"], "峰运通数量")

    def test_reconcile_statement_projection_hides_path(self):
        """对账单结果只展示文件名，不能把服务器绝对路径暴露给前端。"""

        presentation = business_result_core.present("reconcile_statement.build", {
            "files": [{
                "path": r"C:\\private\\供应商甲-202607.xlsx",
                "supplier": "供应商甲",
                "month": "202607",
                "rows": 12,
            }],
            "total_rows": 12,
        })
        row = presentation["sections"][0]["rows"][0]
        self.assertEqual(row["name"], "供应商甲-202607.xlsx")
        self.assertNotIn("private", row["name"])

    def test_unknown_feature_has_no_projection(self):
        """未登记业务返回空投影，让调用端保留原始结果而不是猜测结构。"""

        self.assertIsNone(business_result_core.present("text.transform", {"text": "完成"}))


if __name__ == "__main__":
    unittest.main()
