# 🌸 屎山代码分析报告 🌸

## 📑 目录

- [糟糕指数](#overall-score)
- [评分指标详情](#metrics-details)
- [最屎代码排行榜](#problem-files)
- [诊断结论](#conclusion)

![Score](https://img.shields.io/badge/Score-83%25-brightgreen)

## 糟糕指数 {#overall-score}

| 指标摘要 | 评分 |
|------|-------|
| **糟糕指数** | **83.02/100** |
| 屎山等级 | 😐 微臭青年 |

> 清新宜人，初闻像早晨的露珠

### 📊 统计信息

| 指标 | 数值 |
|--------|-------|
| 总文件数 | 284 |
| 已跳过 | 13583 |
| 耗时 | 2696ms |

### 📋 项目概览

| 指标 | 数值 |
|--------|-------|
| 总代码行数 | 51275 |
| 总注释行数 | 3685 |
| 整体注释比例 | 7.2% |
| 平均文件大小 | 222 行 |
| 最大文件 | `tests\test_web_server.py` (2396) |

#### 语言分布

| 语言 | 文件数 |
|:-----|------:|
| Python | 170 |
| TypeScript | 92 |
| Shell | 13 |
| JavaScript | 6 |
| Rust | 3 |

## 评分指标详情 {#metrics-details}

| 指标摘要 | 评分 | Min | Max | Median | 状态 |
|:-----|------:|------:|------:|------:|:------:|
| 循环复杂度 | 7.42% | 0.0% | 60.0% | 0.0% | ✓✓ |
| 认知复杂度 | 9.13% | 0.0% | 61.0% | 0.0% | ✓✓ |
| 嵌套深度 | 2.37% | 0.0% | 96.0% | 0.0% | ✓✓ |
| 函数长度 | 3.53% | 0.0% | 71.0% | 0.0% | ✓✓ |
| 文件长度 | 3.87% | 0.0% | 96.1% | 0.0% | ✓✓ |
| 参数数量 | 9.16% | 0.0% | 98.0% | 0.0% | ✓✓ |
| 代码重复 | 5.10% | 0.0% | 81.7% | 0.0% | ✓✓ |
| 结构分析 | 3.89% | 0.0% | 60.5% | 0.0% | ✓✓ |
| 错误处理 | 36.01% | 0.0% | 98.8% | 0.0% | ○ |
| 注释比例 | 36.22% | 0.0% | 100.0% | 21.4% | ○ |
| 命名规范 | 21.43% | 0.0% | 100.0% | 0.0% | ✓ |

## 最屎代码排行榜 {#problem-files}

### 1. tests\test_web_server.py

**糟糕指数: 37.63**

> 行数: 2396 总计, 2172 代码, 21 注释 | 函数: 50 | 类: 1

**问题**: 🔄 复杂度问题: 3, ⚠️ 其他问题: 15, 📋 重复问题: 7, 🏗️ 结构问题: 3, ❌ 错误处理问题: 41, 📝 注释问题: 1

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `call` | L61-79 | 19 | 13 | 2 | 7 | ✓ |
| `test_storage_maintenance_limits_outputs_and_purges_expired_trash` | L1859-1948 | 90 | 8 | 3 | 1 | ✓ |
| `test_http_context_json_and_static_cache_policy` | L104-164 | 61 | 7 | 1 | 1 | ✓ |
| `test_workshop_daily_issue_publish_permissions_export_and_restore` | L1368-1547 | 180 | 5 | 2 | 1 | ✓ |
| `test_daily_report_admin_scope_result_projection_and_export` | L266-368 | 103 | 4 | 2 | 1 | ✓ |
| `test_login_lock_password_change_and_device_sessions` | L966-1005 | 40 | 4 | 1 | 1 | ✓ |
| `test_report_center_and_batch_track_include_result_files` | L1029-1099 | 71 | 4 | 1 | 1 | ✓ |
| `test_job_trash_restores_record_and_result_file` | L1822-1857 | 36 | 4 | 1 | 1 | ✓ |
| `wait_job` | L81-92 | 12 | 3 | 2 | 2 | ✓ |
| `test_text_task_and_upload_download` | L166-213 | 48 | 3 | 1 | 1 | ✓ |
| `test_daily_source_uploads_feed_arrival_and_safety_dashboard` | L527-608 | 82 | 3 | 1 | 1 | ✓ |
| `test_role_matrix_and_workshop_edit_scope` | L1101-1174 | 74 | 3 | 2 | 1 | ✓ |
| `test_library_category_migration_keeps_secondary_labels` | L1343-1366 | 24 | 3 | 1 | 1 | ✓ |
| `test_slow_workshop_upload_does_not_block_other_uploads` | L1709-1755 | 47 | 3 | 2 | 1 | ✓ |
| `test_workshop_stale_draft_cleanup_removes_isolated_images` | L1757-1787 | 31 | 3 | 1 | 1 | ✓ |
| `test_backup_verification_rejects_duplicate_manifest_paths` | L1980-1998 | 19 | 3 | 1 | 1 | ✓ |
| `test_webhook_notify_on_job_completion` | L2275-2318 | 32 | 3 | 2 | 1 | ✓ |
| `test_share_link_anonymous_download_and_revoke` | L2321-2357 | 37 | 3 | 1 | 1 | ✓ |
| `test_daily_report_manual_attendance_briefs_and_production_plan` | L370-525 | 156 | 2 | 1 | 1 | ✓ |
| `test_legacy_production_group_attendance_migrates_to_default_shift` | L610-643 | 34 | 2 | 1 | 1 | ✓ |
| `test_production_staffing_update_refreshes_today_but_keeps_history` | L645-684 | 40 | 2 | 1 | 1 | ✓ |
| `test_templates_search_preflight_and_retry` | L686-718 | 33 | 2 | 1 | 1 | ✓ |
| `test_compare_review_continues_same_job` | L720-777 | 48 | 2 | 1 | 1 | ✓ |
| `book_bytes` | L723-732 | 10 | 2 | 1 | 1 | ✓ |
| `test_shared_library_permissions_pagination_and_restore` | L1176-1284 | 97 | 2 | 1 | 1 | ✓ |
| `test_workshop_issue_export_supports_date_range_and_rejects_reverse_range` | L1592-1635 | 44 | 2 | 1 | 1 | ✓ |
| `test_admin_master_data_upload_review_merge_and_permissions` | L2000-2111 | 112 | 2 | 1 | 1 | ✓ |
| `test_upload_handle_rejects_cross_user_and_outside_paths` | L2114-2163 | 50 | 2 | 1 | 1 | ✓ |
| `test_job_file_download_rejects_path_outside_owned_roots` | L2165-2200 | 36 | 2 | 2 | 1 | ✓ |
| `test_daily_auto_backup_and_rollover` | L2202-2225 | 24 | 2 | 1 | 1 | ✓ |
| `test_download_action_written_to_audit` | L2227-2253 | 27 | 2 | 1 | 1 | ✓ |
| `test_login_failure_lock_configurable` | L2255-2272 | 18 | 2 | 2 | 1 | ✓ |
| `do_POST` | L2282-2289 | 8 | 2 | 0 | 1 | ✓ |
| `setUp` | L33-49 | 17 | 1 | 0 | 1 | ✓ |
| `tearDown` | L51-59 | 9 | 1 | 0 | 1 | ✓ |
| `test_requires_login` | L94-102 | 9 | 1 | 0 | 1 | ✓ |
| `test_arrival_scan_and_manual_total_override` | L215-264 | 50 | 1 | 0 | 1 | ✓ |
| `test_supplier_batch_review_selects_suppliers_and_excludes_original` | L779-837 | 59 | 1 | 0 | 1 | ✓ |
| `test_admin_data_account_and_notifications` | L839-887 | 49 | 1 | 0 | 1 | ✓ |
| `test_admin_role_access_sessions_and_audit` | L889-964 | 76 | 1 | 0 | 1 | ✓ |
| `test_admin_password_reset_revokes_target_sessions` | L1007-1027 | 21 | 1 | 0 | 1 | ✓ |
| `upload` | L1203-1214 | 12 | 1 | 0 | 3 | ✓ |
| `test_library_classification_filter_override_and_replacement` | L1286-1341 | 45 | 1 | 0 | 1 | ✓ |
| `workbook_bytes` | L1289-1299 | 11 | 1 | 0 | 2 | ✓ |
| `test_workshop_error_proofing_publishes_without_images` | L1549-1590 | 42 | 1 | 0 | 1 | ✓ |
| `test_workshop_published_issue_edit_resolve_and_reopen` | L1637-1707 | 71 | 1 | 0 | 1 | ✓ |
| `test_upload_trash_restore_and_permanent_delete` | L1789-1820 | 32 | 1 | 0 | 1 | ✓ |
| `test_backup_verification_and_restore` | L1950-1978 | 29 | 1 | 0 | 1 | ✓ |
| `log_message` | L2290-2293 | 4 | 1 | 0 | 1 | ✓ |
| `test_assign_job_to_user_and_notify` | L2360-2392 | 33 | 1 | 0 | 1 | ✓ |

**全部问题 (68)**

- 🔄 `call()` L61: 复杂度: 13
- 🔄 `call()` L61: 认知复杂度: 17
- 🔄 `test_storage_maintenance_limits_outputs_and_purges_expired_trash()` L1859: 认知复杂度: 14
- 📏 `test_http_context_json_and_static_cache_policy()` L104: 61 代码量
- 📏 `test_daily_report_admin_scope_result_projection_and_export()` L266: 103 代码量
- 📏 `test_daily_report_manual_attendance_briefs_and_production_plan()` L370: 156 代码量
- 📏 `test_daily_source_uploads_feed_arrival_and_safety_dashboard()` L527: 82 代码量
- 📏 `test_supplier_batch_review_selects_suppliers_and_excludes_original()` L779: 59 代码量
- 📏 `test_admin_role_access_sessions_and_audit()` L889: 76 代码量
- 📏 `test_report_center_and_batch_track_include_result_files()` L1029: 71 代码量
- 📏 `test_role_matrix_and_workshop_edit_scope()` L1101: 74 代码量
- 📏 `test_shared_library_permissions_pagination_and_restore()` L1176: 97 代码量
- 📏 `test_workshop_daily_issue_publish_permissions_export_and_restore()` L1368: 180 代码量
- 📏 `test_workshop_published_issue_edit_resolve_and_reopen()` L1637: 71 代码量
- 📏 `test_storage_maintenance_limits_outputs_and_purges_expired_trash()` L1859: 90 代码量
- 📏 `test_admin_master_data_upload_review_merge_and_permissions()` L2000: 112 代码量
- 📏 `call()` L61: 7 参数数量
- 📋 `test_text_task_and_upload_download()` L166: 重复模式: test_text_task_and_upload_download, test_workshop_published_issue_edit_resolve_and_reopen, test_workshop_stale_draft_cleanup_removes_isolated_images, test_upload_trash_restore_and_permanent_delete
- 📋 `test_arrival_scan_and_manual_total_override()` L215: 重复模式: test_arrival_scan_and_manual_total_override, test_admin_data_account_and_notifications
- 📋 `test_templates_search_preflight_and_retry()` L686: 重复模式: test_templates_search_preflight_and_retry, test_job_file_download_rejects_path_outside_owned_roots, test_share_link_anonymous_download_and_revoke
- 📋 `test_supplier_batch_review_selects_suppliers_and_excludes_original()` L779: 重复模式: test_supplier_batch_review_selects_suppliers_and_excludes_original, test_upload_handle_rejects_cross_user_and_outside_paths
- 📋 `test_workshop_error_proofing_publishes_without_images()` L1549: 重复模式: test_workshop_error_proofing_publishes_without_images, test_download_action_written_to_audit, test_assign_job_to_user_and_notify
- 📋 `test_job_trash_restores_record_and_result_file()` L1822: 重复模式: test_job_trash_restores_record_and_result_file, test_backup_verification_and_restore
- 📋 `test_daily_auto_backup_and_rollover()` L2202: 重复模式: test_daily_auto_backup_and_rollover, test_login_failure_lock_configurable
- 🏗️ `test_storage_maintenance_limits_outputs_and_purges_expired_trash()` L1859: 中等嵌套: 3
- 🏗️ L1: 文件过大: 2396 行
- 🏗️ L1: 导入过多: 22
- ❌ L119: 未处理的易出错调用
- ❌ L132: 未处理的易出错调用
- ❌ L151: 未处理的易出错调用
- ❌ L164: 未处理的易出错调用
- ❌ L196: 未处理的易出错调用
- ❌ L203: 未处理的易出错调用
- ❌ L228: 未处理的易出错调用
- ❌ L260: 未处理的易出错调用
- ❌ L311: 未处理的易出错调用
- ❌ L317: 未处理的易出错调用
- ❌ L368: 未处理的易出错调用
- ❌ L453: 未处理的易出错调用
- ❌ L500: 未处理的易出错调用
- ❌ L551: 未处理的易出错调用
- ❌ L573: 未处理的易出错调用
- ❌ L624: 未处理的易出错调用
- ❌ L981: 未处理的易出错调用
- ❌ L1044: 未处理的易出错调用
- ❌ L1349: 未处理的易出错调用
- ❌ L1361: 未处理的易出错调用
- ❌ L1504: 未处理的易出错调用
- ❌ L1731: 未处理的易出错调用
- ❌ L1751: 未处理的易出错调用
- ❌ L1779: 未处理的易出错调用
- ❌ L1785: 未处理的易出错调用
- ❌ L1831: 未处理的易出错调用
- ❌ L1857: 未处理的易出错调用
- ❌ L1870: 未处理的易出错调用
- ❌ L1874: 未处理的易出错调用
- ❌ L1880: 未处理的易出错调用
- ❌ L1895: 未处理的易出错调用
- ❌ L1900: 未处理的易出错调用
- ❌ L1905: 未处理的易出错调用
- ❌ L1926: 未处理的易出错调用
- ❌ L2034: 未处理的易出错调用
- ❌ L2079: 未处理的易出错调用
- ❌ L2189: 未处理的易出错调用
- ❌ L2191: 未处理的易出错调用
- ❌ L2286: 未处理的易出错调用
- ❌ L2289: 未处理的易出错调用
- ❌ L2348: 未处理的易出错调用

**详情**:
- 循环复杂度: 平均: 2.5, 最大: 13
- 认知复杂度: 平均: 4.2, 最大: 17
- 嵌套深度: 平均: 0.9, 最大: 3
- 函数长度: 平均: 46.2 行, 最大: 180 行
- 文件长度: 2172 代码量 (2396 总计)
- 参数数量: 平均: 1.2, 最大: 7
- 代码重复: 22.0% 重复 (11/50)
- 结构分析: 3 个结构问题
- 错误处理: 41/66 个错误被忽略 (62.1%)
- 注释比例: 1.0% (21/2172)
- 命名规范: 发现 3 个违规

### 2. core\shipping_review_core.py

**糟糕指数: 33.74**

> 行数: 700 总计, 588 代码, 5 注释 | 函数: 30 | 类: 0

**问题**: 🔄 复杂度问题: 5, ⚠️ 其他问题: 6, 🏗️ 结构问题: 2, ❌ 错误处理问题: 6, 📝 注释问题: 1, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `_read_package` | L234-313 | 80 | 18 | 5 | 6 | ✓ |
| `_compare` | L389-418 | 30 | 9 | 1 | 3 | ✓ |
| `_write_compare_sheet` | L472-509 | 38 | 9 | 2 | 4 | ✓ |
| `_select_review_sheet` | L179-204 | 26 | 8 | 2 | 2 | ✓ |
| `_write_audit_sheet` | L535-567 | 33 | 8 | 2 | 2 | ✓ |
| `_material_code` | L68-83 | 16 | 7 | 1 | 1 | ✓ |
| `_read_review` | L316-354 | 39 | 7 | 3 | 6 | ✓ |
| `_row_status` | L371-386 | 16 | 7 | 1 | 4 | ✓ |
| `_decimal` | L92-110 | 19 | 6 | 1 | 5 | ✓ |
| `_select_package_sheet` | L160-176 | 17 | 6 | 2 | 2 | ✓ |
| `_name_state` | L357-368 | 12 | 6 | 1 | 2 | ✓ |
| `_write_pivot_sheet` | L512-532 | 21 | 6 | 2 | 2 | ✓ |
| `run` | L601-696 | 93 | 6 | 2 | 7 | ✓ |
| `_fill_empty_names` | L221-231 | 11 | 4 | 2 | 3 | ✓ |
| `_status_fill` | L460-469 | 10 | 4 | 1 | 1 | ✓ |
| `_match_headers` | L121-131 | 11 | 3 | 2 | 2 | ✓ |
| `_optional_headers` | L134-143 | 10 | 3 | 2 | 2 | ✓ |
| `_sheet_layout` | L146-157 | 12 | 3 | 2 | 3 | ✓ |
| `_json_number` | L113-118 | 6 | 2 | 1 | 1 | ✓ |
| `_add_name` | L213-218 | 6 | 2 | 1 | 2 | ✓ |
| `_counts` | L421-435 | 15 | 2 | 0 | 1 | ✓ |
| `_style_header` | L450-457 | 8 | 2 | 1 | 1 | ✓ |
| `_write_report` | L570-588 | 19 | 2 | 2 | 4 | ✓ |
| `_resolve_output_dir` | L591-598 | 8 | 2 | 1 | 1 | ✓ |
| `_log` | L624-626 | 3 | 2 | 1 | 1 | ✗ |
| `_text` | L56-59 | 4 | 1 | 0 | 1 | ✓ |
| `_header_key` | L62-65 | 4 | 1 | 0 | 1 | ✓ |
| `_code_key` | L86-89 | 4 | 1 | 0 | 1 | ✓ |
| `_new_item` | L207-210 | 4 | 1 | 0 | 1 | ✓ |
| `_style_title` | L438-447 | 10 | 1 | 0 | 3 | ✓ |

**全部问题 (28)**

- 🔄 `_read_package()` L234: 复杂度: 18
- 🔄 `_read_package()` L234: 认知复杂度: 28
- 🔄 `_read_review()` L316: 认知复杂度: 13
- 🔄 `_write_compare_sheet()` L472: 认知复杂度: 13
- 🔄 `_read_package()` L234: 嵌套深度: 5
- 📏 `_read_package()` L234: 80 代码量
- 📏 `run()` L601: 93 代码量
- 📏 `_read_package()` L234: 6 参数数量
- 📏 `_read_review()` L316: 6 参数数量
- 📏 `run()` L601: 7 参数数量
- 🏗️ `_read_package()` L234: 嵌套过深: 5
- 🏗️ `_read_review()` L316: 中等嵌套: 3
- ❌ L230: 未处理的易出错调用
- ❌ L313: 未处理的易出错调用
- ❌ L354: 未处理的易出错调用
- ❌ L585: 未处理的易出错调用
- ❌ L587: 未处理的易出错调用
- ❌ L688: 未处理的易出错调用
- 🏷️ `_text()` L56: "_text" - snake_case
- 🏷️ `_header_key()` L62: "_header_key" - snake_case
- 🏷️ `_material_code()` L68: "_material_code" - snake_case
- 🏷️ `_code_key()` L86: "_code_key" - snake_case
- 🏷️ `_decimal()` L92: "_decimal" - snake_case
- 🏷️ `_json_number()` L113: "_json_number" - snake_case
- 🏷️ `_match_headers()` L121: "_match_headers" - snake_case
- 🏷️ `_optional_headers()` L134: "_optional_headers" - snake_case
- 🏷️ `_sheet_layout()` L146: "_sheet_layout" - snake_case
- 🏷️ `_select_package_sheet()` L160: "_select_package_sheet" - snake_case

**详情**:
- 循环复杂度: 平均: 4.6, 最大: 18
- 认知复杂度: 平均: 7.4, 最大: 28
- 嵌套深度: 平均: 1.4, 最大: 5
- 函数长度: 平均: 19.5 行, 最大: 93 行
- 文件长度: 588 代码量 (700 总计)
- 参数数量: 平均: 2.5, 最大: 7
- 代码重复: 3.3% 重复 (1/30)
- 结构分析: 2 个结构问题
- 错误处理: 6/10 个错误被忽略 (60.0%)
- 注释比例: 0.9% (5/588)
- 命名规范: 发现 29 个违规

### 3. core\reconcile_core.py

**糟糕指数: 32.88**

> 行数: 1413 总计, 1140 代码, 46 注释 | 函数: 69 | 类: 5

**问题**: 🔄 复杂度问题: 14, ⚠️ 其他问题: 10, 📋 重复问题: 5, 🏗️ 结构问题: 10, ❌ 错误处理问题: 7, 📝 注释问题: 1, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `_parse_labor_rows` | L342-372 | 31 | 15 | 2 | 3 | ✓ |
| `_apply_review_choices` | L1012-1043 | 32 | 15 | 4 | 4 | ✓ |
| `_scan_zong_role_columns` | L444-464 | 21 | 14 | 3 | 2 | ✓ |
| `_detect_source_header` | L64-85 | 22 | 11 | 2 | 3 | ✓ |
| `_find_labor_name_position` | L212-236 | 25 | 11 | 3 | 3 | ✓ |
| `analyze` | L837-909 | 73 | 9 | 2 | 4 | ✓ |
| `_source_header_columns` | L46-61 | 16 | 8 | 3 | 1 | ✓ |
| `_source_row_record` | L88-106 | 19 | 8 | 1 | 5 | ✓ |
| `_load_source_one` | L126-168 | 39 | 8 | 2 | 5 | ✓ |
| `fill_zong` | L604-649 | 42 | 8 | 2 | 5 | ✓ |
| `_apply_name_aliases` | L1213-1227 | 15 | 8 | 2 | 3 | ✓ |
| `_unmapped_person_days` | L568-580 | 13 | 7 | 2 | 3 | ✓ |
| `_project_zong_rows` | L685-711 | 27 | 7 | 3 | 5 | ✓ |
| `_extract_company_map` | L1114-1129 | 16 | 7 | 2 | 2 | ✓ |
| `_find_labor_total_column` | L276-289 | 14 | 6 | 3 | 4 | ✓ |
| `_find_labor_layout` | L292-321 | 30 | 6 | 1 | 4 | ✓ |
| `_resolve_company_name` | L674-682 | 9 | 6 | 1 | 5 | ✓ |
| `_find_labor_day_layout` | L252-263 | 12 | 5 | 2 | 3 | ✓ |
| `_collect_labor_candidates` | L324-339 | 16 | 5 | 2 | 6 | ✓ |
| `load_labor` | L393-432 | 36 | 5 | 1 | 4 | ✓ |
| `_zong_day_columns` | L477-485 | 9 | 5 | 2 | 3 | ✓ |
| `_find_zong_day_layout` | L488-499 | 12 | 5 | 2 | 3 | ✓ |
| `_locate_zong` | L502-538 | 37 | 5 | 1 | 3 | ✓ |
| `_fill_zong_person` | L583-601 | 19 | 5 | 2 | 6 | ✓ |
| `_matched_person_anomalies` | L762-789 | 28 | 5 | 1 | 4 | ✓ |
| `_merge_labor_file` | L1194-1210 | 17 | 5 | 3 | 5 | ✓ |
| `load_source` | L171-191 | 17 | 4 | 1 | 3 | ✓ |
| `_find_header_cell` | L203-209 | 7 | 4 | 2 | 2 | ✓ |
| `_day_columns` | L239-249 | 11 | 4 | 2 | 2 | ✓ |
| `_combined_header_text` | L266-273 | 8 | 4 | 2 | 3 | ✓ |
| `_append_labor_meta` | L375-390 | 16 | 4 | 1 | 8 | ✓ |
| `_source_month_days` | L541-549 | 9 | 4 | 3 | 1 | ✓ |
| `_cached_cell_value` | L665-671 | 7 | 4 | 1 | 4 | ✓ |
| `_daily_difference_details` | L746-759 | 14 | 4 | 2 | 3 | ✓ |
| `reconcile` | L792-818 | 23 | 4 | 1 | 8 | ✓ |
| `_select_target_sheet` | L1093-1100 | 8 | 4 | 2 | 2 | ✓ |
| `_unified_out_dir` | L1393-1412 | 20 | 4 | 2 | 2 | ✓ |
| `_accumulate_source_sheet` | L109-123 | 15 | 3 | 2 | 6 | ✓ |
| `_apply_zong_role_overrides` | L467-474 | 8 | 3 | 2 | 2 | ✓ |
| `_source_day_value` | L558-565 | 8 | 3 | 2 | 3 | ✓ |
| `_zong_names` | L652-659 | 8 | 3 | 2 | 2 | ✓ |
| `_roster_anomalies` | L714-743 | 30 | 3 | 1 | 2 | ✓ |
| `_fmt` | L821-827 | 7 | 3 | 1 | 1 | ✓ |
| `_resolve_run_output_dir` | L1046-1052 | 7 | 3 | 1 | 2 | ✓ |
| `_safe_close_workbook` | L1103-1111 | 9 | 3 | 1 | 1 | ✓ |
| `_assess_run` | L1304-1317 | 14 | 3 | 2 | 2 | ✓ |
| `_lg` | L133-136 | 4 | 2 | 1 | 1 | ✓ |
| `_lg` | L178-181 | 4 | 2 | 1 | 1 | ✓ |
| `_lg` | L402-405 | 4 | 2 | 1 | 1 | ✓ |
| `_zong_header_rows` | L438-441 | 4 | 2 | 0 | 1 | ✓ |
| `_target_source_month` | L552-555 | 4 | 2 | 0 | 1 | ✓ |
| `_lg` | L612-615 | 4 | 2 | 1 | 1 | ✓ |
| `_lg` | L805-808 | 4 | 2 | 1 | 1 | ✓ |
| `log` | L933-938 | 6 | 2 | 1 | 2 | ✓ |
| `_path_list` | L1006-1009 | 4 | 2 | 0 | 1 | ✓ |
| `_build_run_context` | L1055-1074 | 20 | 2 | 0 | 7 | ✓ |
| `_read_source_stage` | L1077-1090 | 14 | 2 | 1 | 1 | ✓ |
| `_load_target_value_projection` | L1132-1146 | 15 | 2 | 1 | 3 | ✓ |
| `_prepare_target_stage` | L1149-1191 | 43 | 2 | 1 | 2 | ✓ |
| `_read_labor_stage` | L1230-1255 | 26 | 2 | 1 | 1 | ✓ |
| `__init__` | L928-931 | 4 | 1 | 0 | 3 | ✗ |
| `stage` | L940-943 | 4 | 1 | 0 | 2 | ✓ |
| `done` | L945-948 | 4 | 1 | 0 | 1 | ✓ |
| `text` | L950-953 | 4 | 1 | 0 | 1 | ✓ |
| `close` | L990-994 | 5 | 1 | 0 | 1 | ✓ |
| `_compare_target_stage` | L1258-1274 | 17 | 1 | 0 | 3 | ✓ |
| `_build_run_metrics` | L1277-1301 | 25 | 1 | 0 | 5 | ✓ |
| `_write_summary_stage` | L1320-1337 | 18 | 1 | 0 | 3 | ✓ |
| `run` | L1340-1390 | 51 | 1 | 1 | 8 | ✓ |

**全部问题 (55)**

- 🔄 `_detect_source_header()` L64: 复杂度: 11
- 🔄 `_find_labor_name_position()` L212: 复杂度: 11
- 🔄 `_parse_labor_rows()` L342: 复杂度: 15
- 🔄 `_scan_zong_role_columns()` L444: 复杂度: 14
- 🔄 `_apply_review_choices()` L1012: 复杂度: 15
- 🔄 `_source_header_columns()` L46: 认知复杂度: 14
- 🔄 `_detect_source_header()` L64: 认知复杂度: 15
- 🔄 `_find_labor_name_position()` L212: 认知复杂度: 17
- 🔄 `_parse_labor_rows()` L342: 认知复杂度: 19
- 🔄 `_scan_zong_role_columns()` L444: 认知复杂度: 20
- 🔄 `_project_zong_rows()` L685: 认知复杂度: 13
- 🔄 `analyze()` L837: 认知复杂度: 13
- 🔄 `_apply_review_choices()` L1012: 认知复杂度: 23
- 🔄 `_apply_review_choices()` L1012: 嵌套深度: 4
- 📏 `analyze()` L837: 73 代码量
- 📏 `run()` L1340: 51 代码量
- 📏 `_accumulate_source_sheet()` L109: 6 参数数量
- 📏 `_collect_labor_candidates()` L324: 6 参数数量
- 📏 `_append_labor_meta()` L375: 8 参数数量
- 📏 `_fill_zong_person()` L583: 6 参数数量
- 📏 `reconcile()` L792: 8 参数数量
- 📏 `_build_run_context()` L1055: 7 参数数量
- 📏 `run()` L1340: 8 参数数量
- 📋 `_day_columns()` L239: 重复模式: _day_columns, _zong_day_columns, _daily_difference_details
- 📋 `_apply_zong_role_overrides()` L467: 重复模式: _apply_zong_role_overrides, _zong_names
- 📋 `_unmapped_person_days()` L568: 重复模式: _unmapped_person_days, _merge_labor_file
- 📋 `_fill_zong_person()` L583: 重复模式: _fill_zong_person, _read_labor_stage
- 📋 `_load_target_value_projection()` L1132: 重复模式: _load_target_value_projection, _unified_out_dir
- 🏗️ `_source_header_columns()` L46: 中等嵌套: 3
- 🏗️ `_find_labor_name_position()` L212: 中等嵌套: 3
- 🏗️ `_find_labor_total_column()` L276: 中等嵌套: 3
- 🏗️ `_scan_zong_role_columns()` L444: 中等嵌套: 3
- 🏗️ `_source_month_days()` L541: 中等嵌套: 3
- 🏗️ `_project_zong_rows()` L685: 中等嵌套: 3
- 🏗️ `_apply_review_choices()` L1012: 中等嵌套: 4
- 🏗️ `_merge_labor_file()` L1194: 中等嵌套: 3
- 🏗️ L1: 文件过大: 1413 行
- 🏗️ L1: 函数过多: 69
- ❌ L873: 未处理的易出错调用
- ❌ L898: 未处理的易出错调用
- ❌ L990: 未处理的易出错调用
- ❌ L1109: 未处理的易出错调用
- ❌ L1292: 未处理的易出错调用
- ❌ L1374: 未处理的易出错调用
- ❌ L1406: 未处理的易出错调用
- 🏷️ `_source_header_columns()` L46: "_source_header_columns" - snake_case
- 🏷️ `_detect_source_header()` L64: "_detect_source_header" - snake_case
- 🏷️ `_source_row_record()` L88: "_source_row_record" - snake_case
- 🏷️ `_accumulate_source_sheet()` L109: "_accumulate_source_sheet" - snake_case
- 🏷️ `_load_source_one()` L126: "_load_source_one" - snake_case
- 🏷️ `_lg()` L133: "_lg" - snake_case
- 🏷️ `_lg()` L178: "_lg" - snake_case
- 🏷️ `_find_header_cell()` L203: "_find_header_cell" - snake_case
- 🏷️ `_find_labor_name_position()` L212: "_find_labor_name_position" - snake_case
- 🏷️ `_day_columns()` L239: "_day_columns" - snake_case

**详情**:
- 循环复杂度: 平均: 4.4, 最大: 15
- 认知复杂度: 平均: 7.3, 最大: 23
- 嵌套深度: 平均: 1.4, 最大: 4
- 函数长度: 平均: 16.9 行, 最大: 73 行
- 文件长度: 1140 代码量 (1413 总计)
- 参数数量: 平均: 3.0, 最大: 8
- 代码重复: 8.7% 重复 (6/69)
- 结构分析: 10 个结构问题
- 错误处理: 7/21 个错误被忽略 (33.3%)
- 注释比例: 4.0% (46/1140)
- 命名规范: 发现 63 个违规

### 4. core\pivot_core.py

**糟糕指数: 32.75**

> 行数: 1492 总计, 1216 代码, 92 注释 | 函数: 73 | 类: 2

**问题**: 🔄 复杂度问题: 18, ⚠️ 其他问题: 6, 📋 重复问题: 3, 🏗️ 结构问题: 14, ❌ 错误处理问题: 12, 📝 注释问题: 1, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `clean_rows_ex` | L504-553 | 50 | 15 | 4 | 1 | ✓ |
| `_assign_block_column` | L188-206 | 19 | 13 | 1 | 3 | ✓ |
| `analyze_workbooks` | L1011-1086 | 71 | 12 | 3 | 4 | ✓ |
| `clean_rows` | L457-483 | 27 | 11 | 3 | 1 | ✓ |
| `_compute_unit_best` | L710-752 | 43 | 10 | 3 | 2 | ✓ |
| `aggregate` | L787-816 | 30 | 10 | 2 | 1 | ✓ |
| `_classify_by_name_and_cols` | L377-407 | 31 | 9 | 2 | 5 | ✓ |
| `_spec_base` | L589-607 | 19 | 9 | 3 | 1 | ✓ |
| `normalize_rows` | L409-431 | 23 | 8 | 3 | 1 | ✓ |
| `_looks_like_pivot_output` | L259-274 | 16 | 7 | 3 | 1 | ✓ |
| `normalize_stream_rows` | L434-455 | 22 | 7 | 4 | 2 | ✓ |
| `_name_unit_prior` | L671-688 | 18 | 7 | 2 | 1 | ✓ |
| `process_workbook` | L906-957 | 52 | 7 | 3 | 3 | ✓ |
| `_analyze_stream_sheet` | L978-1008 | 31 | 7 | 2 | 5 | ✓ |
| `find_all_blocks` | L239-257 | 19 | 6 | 3 | 1 | ✓ |
| `unify_specs` | L646-659 | 14 | 6 | 2 | 2 | ✓ |
| `write_clean_sheet` | L835-853 | 19 | 6 | 2 | 2 | ✓ |
| `write_pivot_sheet` | L855-902 | 48 | 6 | 2 | 3 | ✓ |
| `run` | L1438-1464 | 27 | 6 | 3 | 5 | ✓ |
| `_match_anchor` | L71-80 | 10 | 5 | 2 | 2 | ✓ |
| `cell` | L151-157 | 7 | 5 | 1 | 3 | ✓ |
| `_block_from_anchor` | L209-236 | 28 | 5 | 2 | 4 | ✓ |
| `_complete_rows_from_catalog` | L321-340 | 20 | 5 | 2 | 3 | ✓ |
| `compute_spec_canon` | L622-643 | 22 | 5 | 2 | 1 | ✓ |
| `unify_units` | L763-776 | 14 | 5 | 2 | 2 | ✓ |
| `_build_selected_pivot_workbook` | L1193-1228 | 36 | 5 | 1 | 2 | ✓ |
| `_try_cached_pivot` | L1382-1397 | 16 | 5 | 2 | 6 | ✓ |
| `_header_anchor_columns` | L178-185 | 8 | 4 | 2 | 3 | ✓ |
| `classify_sheet` | L343-374 | 32 | 4 | 1 | 1 | ✓ |
| `_final_has_qty` | L493-501 | 9 | 4 | 1 | 1 | ✓ |
| `_norm_key` | L569-580 | 12 | 4 | 1 | 1 | ✓ |
| `_spec_keyof` | L610-615 | 6 | 4 | 0 | 1 | ✓ |
| `_unit_gkey` | L691-696 | 6 | 4 | 1 | 1 | ✓ |
| `_safe_sheet_name` | L960-974 | 15 | 4 | 1 | 2 | ✓ |
| `_selected_sheet_rows` | L1121-1141 | 21 | 4 | 2 | 2 | ✓ |
| `_collect_selected_plan_rows` | L1144-1190 | 47 | 4 | 2 | 2 | ✓ |
| `_inject_pivot_jobs` | L1231-1242 | 12 | 4 | 2 | 3 | ✓ |
| `_fmt_num` | L1316-1322 | 7 | 4 | 1 | 1 | ✓ |
| `_materialize_web_cache` | L1346-1364 | 19 | 4 | 2 | 2 | ✓ |
| `_prepare_run` | L1367-1379 | 13 | 4 | 1 | 2 | ✓ |
| `_has_chinese` | L97-102 | 6 | 3 | 2 | 1 | ✓ |
| `_is_zero` | L104-111 | 8 | 3 | 1 | 1 | ✓ |
| `_norm` | L113-123 | 11 | 3 | 1 | 1 | ✓ |
| `_preview_sheet` | L160-167 | 8 | 3 | 2 | 2 | ✓ |
| `_last_col` | L169-175 | 7 | 3 | 2 | 2 | ✓ |
| `is_data_sheet` | L284-290 | 7 | 3 | 1 | 1 | ✓ |
| `_unit_simplicity` | L662-668 | 7 | 3 | 1 | 1 | ✓ |
| `_unit_key_sample` | L699-707 | 9 | 3 | 1 | 2 | ✓ |
| `_st` | L827-833 | 7 | 3 | 1 | 3 | ✓ |
| `default_rows` | L1061-1065 | 5 | 3 | 2 | 0 | ✓ |
| `_build_pivot_result` | L1400-1423 | 24 | 3 | 1 | 6 | ✓ |
| `_save_pivot_cache` | L1426-1434 | 9 | 3 | 1 | 3 | ✓ |
| `analyze` | L1467-1485 | 16 | 3 | 1 | 3 | ✓ |
| `_is_excluded_sheet` | L279-282 | 4 | 2 | 0 | 1 | ✓ |
| `_sheet_name` | L308-310 | 3 | 2 | 0 | 1 | ✓ |
| `_is_valid_code` | L486-490 | 5 | 2 | 1 | 1 | ✓ |
| `process_workbooks` | L1305-1314 | 10 | 2 | 1 | 3 | ✓ |
| `_cacheable_result` | L1325-1343 | 19 | 2 | 1 | 1 | ✓ |
| `on_file` | L1477-1479 | 3 | 2 | 0 | 2 | ✓ |
| `_contains_any` | L82-84 | 3 | 1 | 0 | 2 | ✓ |
| `_cell` | L126-128 | 3 | 1 | 0 | 3 | ✓ |
| `__init__` | L135-137 | 3 | 1 | 0 | 2 | ✓ |
| `__init__` | L144-149 | 6 | 1 | 0 | 3 | ✓ |
| `_has_token` | L312-314 | 3 | 1 | 0 | 2 | ✓ |
| `_is_compound_unit` | L584-586 | 3 | 1 | 0 | 1 | ✓ |
| `_spec_gkey` | L617-620 | 4 | 1 | 0 | 3 | ✓ |
| `compute_unit_best` | L755-760 | 6 | 1 | 0 | 1 | ✓ |
| `drop_blank_code_rows` | L779-784 | 6 | 1 | 0 | 1 | ✓ |
| `_default_choices` | L1089-1100 | 12 | 1 | 0 | 1 | ✓ |
| `_sheet_audit_record` | L1103-1118 | 16 | 1 | 0 | 2 | ✓ |
| `_build_apply_result` | L1245-1275 | 31 | 1 | 0 | 8 | ✓ |
| `apply_plan` | L1278-1302 | 25 | 1 | 0 | 4 | ✓ |
| `_beijing_date` | L1488-1491 | 4 | 1 | 0 | 0 | ✓ |

**全部问题 (62)**

- 🔄 `_assign_block_column()` L188: 复杂度: 13
- 🔄 `clean_rows()` L457: 复杂度: 11
- 🔄 `clean_rows_ex()` L504: 复杂度: 15
- 🔄 `analyze_workbooks()` L1011: 复杂度: 12
- 🔄 `_assign_block_column()` L188: 认知复杂度: 15
- 🔄 `_looks_like_pivot_output()` L259: 认知复杂度: 13
- 🔄 `_classify_by_name_and_cols()` L377: 认知复杂度: 13
- 🔄 `normalize_rows()` L409: 认知复杂度: 14
- 🔄 `normalize_stream_rows()` L434: 认知复杂度: 15
- 🔄 `clean_rows()` L457: 认知复杂度: 17
- 🔄 `clean_rows_ex()` L504: 认知复杂度: 23
- 🔄 `_spec_base()` L589: 认知复杂度: 15
- 🔄 `_compute_unit_best()` L710: 认知复杂度: 16
- 🔄 `aggregate()` L787: 认知复杂度: 14
- 🔄 `process_workbook()` L906: 认知复杂度: 13
- 🔄 `analyze_workbooks()` L1011: 认知复杂度: 18
- 🔄 `normalize_stream_rows()` L434: 嵌套深度: 4
- 🔄 `clean_rows_ex()` L504: 嵌套深度: 4
- 📏 `process_workbook()` L906: 52 代码量
- 📏 `analyze_workbooks()` L1011: 71 代码量
- 📏 `_build_apply_result()` L1245: 8 参数数量
- 📏 `_try_cached_pivot()` L1382: 6 参数数量
- 📏 `_build_pivot_result()` L1400: 6 参数数量
- 📋 `_last_col()` L169: 重复模式: _last_col, _header_anchor_columns
- 📋 `_spec_keyof()` L610: 重复模式: _spec_keyof, compute_unit_best, process_workbooks, _cacheable_result
- 📋 `unify_specs()` L646: 重复模式: unify_specs, _selected_sheet_rows
- 🏗️ `find_all_blocks()` L239: 中等嵌套: 3
- 🏗️ `_looks_like_pivot_output()` L259: 中等嵌套: 3
- 🏗️ `normalize_rows()` L409: 中等嵌套: 3
- 🏗️ `normalize_stream_rows()` L434: 中等嵌套: 4
- 🏗️ `clean_rows()` L457: 中等嵌套: 3
- 🏗️ `clean_rows_ex()` L504: 中等嵌套: 4
- 🏗️ `_spec_base()` L589: 中等嵌套: 3
- 🏗️ `_compute_unit_best()` L710: 中等嵌套: 3
- 🏗️ `process_workbook()` L906: 中等嵌套: 3
- 🏗️ `analyze_workbooks()` L1011: 中等嵌套: 3
- 🏗️ `run()` L1438: 中等嵌套: 3
- 🏗️ L1: 文件过大: 1492 行
- 🏗️ L1: 函数过多: 73
- 🏗️ L1: 导入过多: 29
- ❌ L1048: 未处理的易出错调用
- ❌ L1131: 未处理的易出错调用
- ❌ L1227: 未处理的易出错调用
- ❌ L1337: 未处理的易出错调用
- ❌ L1338: 未处理的易出错调用
- ❌ L1339: 未处理的易出错调用
- ❌ L1340: 未处理的易出错调用
- ❌ L1341: 未处理的易出错调用
- ❌ L1420: 未处理的易出错调用
- ❌ L1421: 未处理的易出错调用
- ❌ L1432: 未处理的易出错调用
- ❌ L1448: 未处理的易出错调用
- 🏷️ `_match_anchor()` L71: "_match_anchor" - snake_case
- 🏷️ `_contains_any()` L82: "_contains_any" - snake_case
- 🏷️ `_has_chinese()` L97: "_has_chinese" - snake_case
- 🏷️ `_is_zero()` L104: "_is_zero" - snake_case
- 🏷️ `_norm()` L113: "_norm" - snake_case
- 🏷️ `_cell()` L126: "_cell" - snake_case
- 🏷️ `__init__()` L135: "__init__" - snake_case
- 🏷️ `__init__()` L144: "__init__" - snake_case
- 🏷️ `_preview_sheet()` L160: "_preview_sheet" - snake_case
- 🏷️ `_last_col()` L169: "_last_col" - snake_case

**详情**:
- 循环复杂度: 平均: 4.4, 最大: 15
- 认知复杂度: 平均: 7.1, 最大: 23
- 嵌套深度: 平均: 1.4, 最大: 4
- 函数长度: 平均: 16.9 行, 最大: 71 行
- 文件长度: 1216 代码量 (1492 总计)
- 参数数量: 平均: 2.2, 最大: 8
- 代码重复: 6.8% 重复 (5/73)
- 结构分析: 14 个结构问题
- 错误处理: 12/30 个错误被忽略 (40.0%)
- 注释比例: 7.6% (92/1216)
- 命名规范: 发现 51 个违规

### 5. web_backend\services\workshop.py

**糟糕指数: 32.53**

> 行数: 812 总计, 711 代码, 42 注释 | 函数: 22 | 类: 1

**问题**: 🔄 复杂度问题: 20, ⚠️ 其他问题: 6, 📋 重复问题: 2, 🏗️ 结构问题: 7, ❌ 错误处理问题: 19, 📝 注释问题: 1, 🏷️ 命名问题: 9

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `upload_workshop_issue_image` | L293-386 | 94 | 17 | 5 | 3 | ✓ |
| `delete_workshop_issue_image` | L632-695 | 64 | 14 | 4 | 3 | ✓ |
| `resolve_workshop_issue` | L473-513 | 41 | 12 | 3 | 4 | ✓ |
| `export_workshop_issues` | L697-757 | 61 | 12 | 2 | 2 | ✓ |
| `delete_workshop_issue` | L759-811 | 53 | 12 | 4 | 3 | ✓ |
| `_workshop_template_values` | L137-161 | 25 | 11 | 1 | 6 | ✓ |
| `update_workshop_issue` | L388-434 | 47 | 11 | 3 | 4 | ✓ |
| `reopen_workshop_issue` | L515-556 | 42 | 10 | 3 | 4 | ✓ |
| `_workshop_issue_id` | L58-70 | 13 | 9 | 1 | 2 | ✓ |
| `_normalize_workshop_issue_payload` | L188-236 | 46 | 8 | 1 | 4 | ✓ |
| `publish_workshop_issue` | L436-471 | 36 | 8 | 4 | 3 | ✓ |
| `download_workshop_issue_image` | L599-630 | 32 | 8 | 1 | 3 | ✓ |
| `_workshop_issue_row` | L88-110 | 23 | 6 | 1 | 4 | ✓ |
| `_workshop_image_ids` | L239-251 | 13 | 6 | 1 | 1 | ✓ |
| `_validate_workshop_lengths` | L172-185 | 14 | 5 | 2 | 5 | ✓ |
| `_validate_workshop_required` | L164-169 | 6 | 4 | 2 | 2 | ✓ |
| `_payload_text` | L128-134 | 7 | 3 | 0 | 4 | ✓ |
| `create_workshop_issue` | L254-291 | 38 | 3 | 1 | 3 | ✓ |
| `list_workshop_issues` | L558-597 | 40 | 3 | 1 | 2 | ✓ |
| `_workshop_issue_images` | L113-125 | 13 | 2 | 1 | 2 | ✓ |
| `workshop_issue_select` | L73-85 | 13 | 1 | 0 | 0 | ✓ |
| `value` | L202-204 | 3 | 1 | 0 | 2 | ✓ |

**全部问题 (62)**

- 🔄 `_workshop_template_values()` L137: 复杂度: 11
- 🔄 `upload_workshop_issue_image()` L293: 复杂度: 17
- 🔄 `update_workshop_issue()` L388: 复杂度: 11
- 🔄 `resolve_workshop_issue()` L473: 复杂度: 12
- 🔄 `delete_workshop_issue_image()` L632: 复杂度: 14
- 🔄 `export_workshop_issues()` L697: 复杂度: 12
- 🔄 `delete_workshop_issue()` L759: 复杂度: 12
- 🔄 `_workshop_template_values()` L137: 认知复杂度: 13
- 🔄 `upload_workshop_issue_image()` L293: 认知复杂度: 27
- 🔄 `update_workshop_issue()` L388: 认知复杂度: 17
- 🔄 `publish_workshop_issue()` L436: 认知复杂度: 16
- 🔄 `resolve_workshop_issue()` L473: 认知复杂度: 18
- 🔄 `reopen_workshop_issue()` L515: 认知复杂度: 16
- 🔄 `delete_workshop_issue_image()` L632: 认知复杂度: 22
- 🔄 `export_workshop_issues()` L697: 认知复杂度: 16
- 🔄 `delete_workshop_issue()` L759: 认知复杂度: 20
- 🔄 `upload_workshop_issue_image()` L293: 嵌套深度: 5
- 🔄 `publish_workshop_issue()` L436: 嵌套深度: 4
- 🔄 `delete_workshop_issue_image()` L632: 嵌套深度: 4
- 🔄 `delete_workshop_issue()` L759: 嵌套深度: 4
- 📏 `upload_workshop_issue_image()` L293: 94 代码量
- 📏 `delete_workshop_issue_image()` L632: 64 代码量
- 📏 `export_workshop_issues()` L697: 61 代码量
- 📏 `delete_workshop_issue()` L759: 53 代码量
- 📏 `_workshop_template_values()` L137: 6 参数数量
- 📋 `create_workshop_issue()` L254: 重复模式: create_workshop_issue, resolve_workshop_issue
- 📋 `publish_workshop_issue()` L436: 重复模式: publish_workshop_issue, download_workshop_issue_image
- 🏗️ `upload_workshop_issue_image()` L293: 嵌套过深: 5
- 🏗️ `update_workshop_issue()` L388: 中等嵌套: 3
- 🏗️ `publish_workshop_issue()` L436: 中等嵌套: 4
- 🏗️ `resolve_workshop_issue()` L473: 中等嵌套: 3
- 🏗️ `reopen_workshop_issue()` L515: 中等嵌套: 3
- 🏗️ `delete_workshop_issue_image()` L632: 中等嵌套: 4
- 🏗️ `delete_workshop_issue()` L759: 中等嵌套: 4
- ❌ L168: 未处理的易出错调用
- ❌ L169: 未处理的易出错调用
- ❌ L280: 未处理的易出错调用
- ❌ L324: 未处理的易出错调用
- ❌ L329: 未处理的易出错调用
- ❌ L359: 未处理的易出错调用
- ❌ L366: 未处理的易出错调用
- ❌ L371: 未处理的易出错调用
- ❌ L425: 未处理的易出错调用
- ❌ L458: 未处理的易出错调用
- ❌ L462: 未处理的易出错调用
- ❌ L504: 未处理的易出错调用
- ❌ L547: 未处理的易出错调用
- ❌ L584: 未处理的易出错调用
- ❌ L677: 未处理的易出错调用
- ❌ L681: 未处理的易出错调用
- ❌ L743: 未处理的易出错调用
- ❌ L795: 未处理的易出错调用
- ❌ L802: 未处理的易出错调用
- 🏷️ `_workshop_issue_id()` L58: "_workshop_issue_id" - snake_case
- 🏷️ `_workshop_issue_row()` L88: "_workshop_issue_row" - snake_case
- 🏷️ `_workshop_issue_images()` L113: "_workshop_issue_images" - snake_case
- 🏷️ `_payload_text()` L128: "_payload_text" - snake_case
- 🏷️ `_workshop_template_values()` L137: "_workshop_template_values" - snake_case
- 🏷️ `_validate_workshop_required()` L164: "_validate_workshop_required" - snake_case
- 🏷️ `_validate_workshop_lengths()` L172: "_validate_workshop_lengths" - snake_case
- 🏷️ `_normalize_workshop_issue_payload()` L188: "_normalize_workshop_issue_payload" - snake_case
- 🏷️ `_workshop_image_ids()` L239: "_workshop_image_ids" - snake_case

**详情**:
- 循环复杂度: 平均: 7.5, 最大: 17
- 认知复杂度: 平均: 11.3, 最大: 27
- 嵌套深度: 平均: 1.9, 最大: 5
- 函数长度: 平均: 32.9 行, 最大: 94 行
- 文件长度: 711 代码量 (812 总计)
- 参数数量: 平均: 3.0, 最大: 6
- 代码重复: 9.1% 重复 (2/22)
- 结构分析: 7 个结构问题
- 错误处理: 19/53 个错误被忽略 (35.8%)
- 注释比例: 5.9% (42/711)
- 命名规范: 发现 9 个违规

### 6. core\supplier_batch_core.py

**糟糕指数: 31.07**

> 行数: 828 总计, 670 代码, 52 注释 | 函数: 38 | 类: 0

**问题**: 🔄 复杂度问题: 9, ⚠️ 其他问题: 6, 🏗️ 结构问题: 7, ❌ 错误处理问题: 5, 📝 注释问题: 1, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `_detect_layout` | L98-137 | 40 | 13 | 6 | 1 | ✓ |
| `_history_mapping` | L200-236 | 37 | 12 | 5 | 2 | ✓ |
| `_read_batch` | L239-293 | 55 | 9 | 3 | 4 | ✓ |
| `_write_supplier_workbook` | L606-654 | 49 | 8 | 3 | 4 | ✓ |
| `_assign_suppliers` | L321-357 | 37 | 7 | 3 | 5 | ✓ |
| `_write_block` | L549-603 | 55 | 7 | 2 | 5 | ✓ |
| `_validate_files` | L80-95 | 16 | 6 | 2 | 2 | ✓ |
| `_current_supplier_mapping` | L296-318 | 23 | 6 | 3 | 1 | ✓ |
| `_normalized_batch_dates` | L680-711 | 32 | 6 | 1 | 2 | ✓ |
| `_quantity` | L62-72 | 11 | 5 | 1 | 1 | ✓ |
| `_iter_data_rows` | L154-176 | 23 | 5 | 3 | 2 | ✓ |
| `_best_sheet` | L140-151 | 12 | 4 | 2 | 1 | ✓ |
| `_collect` | L443-477 | 35 | 4 | 1 | 4 | ✓ |
| `_combined_sheet_name` | L522-535 | 14 | 4 | 1 | 1 | ✓ |
| `_selected_supplier_names` | L657-677 | 21 | 4 | 1 | 2 | ✓ |
| `_generate_supplier_files` | L734-761 | 28 | 4 | 2 | 5 | ✓ |
| `_log_generation_summary` | L774-782 | 9 | 4 | 1 | 4 | ✓ |
| `_cell` | L179-182 | 4 | 3 | 0 | 3 | ✓ |
| `_read_current_batches` | L388-401 | 14 | 3 | 2 | 5 | ✓ |
| `_batch_group` | L513-519 | 7 | 3 | 1 | 1 | ✓ |
| `_text` | L43-47 | 5 | 2 | 1 | 1 | ✓ |
| `_supplier` | L55-59 | 5 | 2 | 0 | 1 | ✓ |
| `_batch_name` | L185-189 | 5 | 2 | 0 | 1 | ✓ |
| `_infer_file_supplier` | L192-197 | 6 | 2 | 0 | 1 | ✓ |
| `_collection_inputs` | L381-385 | 5 | 2 | 0 | 2 | ✓ |
| `_ensure_batch_items` | L404-407 | 4 | 2 | 1 | 1 | ✓ |
| `_resolve_batch_suppliers` | L410-424 | 15 | 2 | 1 | 4 | ✓ |
| `analyze` | L480-503 | 24 | 2 | 1 | 4 | ✓ |
| `_safe_name` | L506-510 | 5 | 2 | 0 | 2 | ✓ |
| `_style_sheet` | L538-546 | 9 | 2 | 1 | 1 | ✓ |
| `_supplier_output_dir` | L714-731 | 18 | 2 | 1 | 2 | ✓ |
| `_header` | L50-52 | 3 | 1 | 0 | 1 | ✓ |
| `_is_original` | L75-77 | 3 | 1 | 0 | 1 | ✓ |
| `_supplier_summaries` | L360-378 | 19 | 1 | 0 | 1 | ✓ |
| `_build_collection_result` | L427-440 | 14 | 1 | 0 | 6 | ✓ |
| `_prepare_run_review` | L764-771 | 8 | 1 | 0 | 3 | ✓ |
| `_build_run_result` | L785-796 | 12 | 1 | 0 | 6 | ✓ |
| `run` | L799-827 | 29 | 1 | 0 | 7 | ✓ |

**全部问题 (36)**

- 🔄 `_detect_layout()` L98: 复杂度: 13
- 🔄 `_history_mapping()` L200: 复杂度: 12
- 🔄 `_detect_layout()` L98: 认知复杂度: 25
- 🔄 `_history_mapping()` L200: 认知复杂度: 22
- 🔄 `_read_batch()` L239: 认知复杂度: 15
- 🔄 `_assign_suppliers()` L321: 认知复杂度: 13
- 🔄 `_write_supplier_workbook()` L606: 认知复杂度: 14
- 🔄 `_detect_layout()` L98: 嵌套深度: 6
- 🔄 `_history_mapping()` L200: 嵌套深度: 5
- 📏 `_read_batch()` L239: 55 代码量
- 📏 `_write_block()` L549: 55 代码量
- 📏 `_build_collection_result()` L427: 6 参数数量
- 📏 `_build_run_result()` L785: 6 参数数量
- 📏 `run()` L799: 7 参数数量
- 🏗️ `_detect_layout()` L98: 嵌套过深: 6
- 🏗️ `_iter_data_rows()` L154: 中等嵌套: 3
- 🏗️ `_history_mapping()` L200: 嵌套过深: 5
- 🏗️ `_read_batch()` L239: 中等嵌套: 3
- 🏗️ `_current_supplier_mapping()` L296: 中等嵌套: 3
- 🏗️ `_assign_suppliers()` L321: 中等嵌套: 3
- 🏗️ `_write_supplier_workbook()` L606: 中等嵌套: 3
- ❌ L123: 未处理的易出错调用
- ❌ L233: 未处理的易出错调用
- ❌ L293: 未处理的易出错调用
- ❌ L634: 未处理的易出错调用
- ❌ L653: 未处理的易出错调用
- 🏷️ `_text()` L43: "_text" - snake_case
- 🏷️ `_header()` L50: "_header" - snake_case
- 🏷️ `_supplier()` L55: "_supplier" - snake_case
- 🏷️ `_quantity()` L62: "_quantity" - snake_case
- 🏷️ `_is_original()` L75: "_is_original" - snake_case
- 🏷️ `_validate_files()` L80: "_validate_files" - snake_case
- 🏷️ `_detect_layout()` L98: "_detect_layout" - snake_case
- 🏷️ `_best_sheet()` L140: "_best_sheet" - snake_case
- 🏷️ `_iter_data_rows()` L154: "_iter_data_rows" - snake_case
- 🏷️ `_cell()` L179: "_cell" - snake_case

**详情**:
- 循环复杂度: 平均: 3.8, 最大: 13
- 认知复杂度: 平均: 6.4, 最大: 25
- 嵌套深度: 平均: 1.3, 最大: 6
- 函数长度: 平均: 18.7 行, 最大: 55 行
- 文件长度: 670 代码量 (828 总计)
- 参数数量: 平均: 2.6, 最大: 7
- 代码重复: 0.0% 重复 (0/38)
- 结构分析: 7 个结构问题
- 错误处理: 5/10 个错误被忽略 (50.0%)
- 注释比例: 7.8% (52/670)
- 命名规范: 发现 36 个违规

### 7. tauri-app\scripts\web-smoke-qa.mjs

**糟糕指数: 30.59**

> 行数: 489 总计, 416 代码, 42 注释 | 函数: 11 | 类: 0

**问题**: 🔄 复杂度问题: 3, ⚠️ 其他问题: 1, 🏗️ 结构问题: 1, ❌ 错误处理问题: 6

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `mockApi` | L237-260 | 24 | 16 | 11 | 1 | ✓ |
| `waitForServer` | L31-43 | 12 | 4 | 2 | 1 | ✓ |
| `currentUser` | L48-58 | 11 | 4 | 0 | 0 | ✓ |
| `main` | L450-482 | 31 | 4 | 1 | 0 | ✓ |
| `recordCheck` | L263-270 | 8 | 3 | 1 | 3 | ✓ |
| `run` | L25-28 | 4 | 2 | 1 | 3 | ✓ |
| `runChecks` | L273-277 | 5 | 2 | 1 | 2 | ✓ |
| `adminPayload` | L214-228 | 15 | 1 | 0 | 1 | ✓ |
| `verifyLoginAndWorkbench` | L280-307 | 15 | 1 | 0 | 2 | ✓ |
| `verifyResponsiveRoutes` | L310-361 | 39 | 1 | 0 | 2 | ✓ |
| `verifyAdminPages` | L364-447 | 54 | 1 | 0 | 2 | ✓ |

**全部问题 (10)**

- 🔄 `mockApi()` L237: 复杂度: 16
- 🔄 `mockApi()` L237: 认知复杂度: 38
- 🔄 `mockApi()` L237: 嵌套深度: 11
- 🏗️ `mockApi()` L237: 嵌套过深: 11
- ❌ L242: 未处理的易出错调用
- ❌ L259: 未处理的易出错调用
- ❌ L381: 未处理的易出错调用
- ❌ L394: 未处理的易出错调用
- ❌ L413: 未处理的易出错调用
- ❌ L438: 未处理的易出错调用

**详情**:
- 循环复杂度: 平均: 3.5, 最大: 16
- 认知复杂度: 平均: 6.6, 最大: 38
- 嵌套深度: 平均: 1.5, 最大: 11
- 函数长度: 平均: 19.8 行, 最大: 54 行
- 文件长度: 416 代码量 (489 总计)
- 参数数量: 平均: 1.5, 最大: 3
- 代码重复: 0.0% 重复 (0/11)
- 结构分析: 1 个结构问题
- 错误处理: 6/10 个错误被忽略 (60.0%)
- 注释比例: 10.1% (42/416)
- 命名规范: 无命名违规

### 8. core\business_result_operations.py

**糟糕指数: 30.35**

> 行数: 712 总计, 665 代码, 5 注释 | 函数: 15 | 类: 0

**问题**: 🔄 复杂度问题: 10, ⚠️ 其他问题: 7, 🏗️ 结构问题: 1, ❌ 错误处理问题: 29, 📝 注释问题: 1, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `_present_reconcile` | L26-102 | 77 | 19 | 2 | 2 | ✓ |
| `_present_shipping_review` | L422-498 | 77 | 16 | 1 | 2 | ✓ |
| `_present_pivot` | L105-168 | 64 | 14 | 2 | 2 | ✓ |
| `_present_purchase` | L315-419 | 105 | 12 | 1 | 2 | ✓ |
| `_present_delivery` | L558-599 | 42 | 12 | 1 | 2 | ✓ |
| `_delivery_quality` | L501-542 | 42 | 10 | 1 | 6 | ✓ |
| `_purchase_conflict_rows` | L182-205 | 24 | 8 | 2 | 1 | ✓ |
| `_present_supplier_batch` | L602-648 | 47 | 7 | 1 | 2 | ✓ |
| `_purchase_unmatched_rows` | L208-240 | 33 | 6 | 3 | 6 | ✓ |
| `_present_purchase_plan` | L651-690 | 40 | 6 | 1 | 2 | ✓ |
| `_purchase_quality_checks` | L243-268 | 26 | 5 | 1 | 4 | ✓ |
| `_present_purchase_diff` | L693-711 | 19 | 4 | 1 | 2 | ✓ |
| `_purchase_sections` | L271-312 | 42 | 3 | 1 | 5 | ✓ |
| `_delivery_missing_sections` | L545-555 | 11 | 2 | 1 | 2 | ✓ |
| `_row_summary` | L171-179 | 9 | 1 | 0 | 1 | ✓ |

**全部问题 (56)**

- 🔄 `_present_reconcile()` L26: 复杂度: 19
- 🔄 `_present_pivot()` L105: 复杂度: 14
- 🔄 `_present_purchase()` L315: 复杂度: 12
- 🔄 `_present_shipping_review()` L422: 复杂度: 16
- 🔄 `_present_delivery()` L558: 复杂度: 12
- 🔄 `_present_reconcile()` L26: 认知复杂度: 23
- 🔄 `_present_pivot()` L105: 认知复杂度: 18
- 🔄 `_present_purchase()` L315: 认知复杂度: 14
- 🔄 `_present_shipping_review()` L422: 认知复杂度: 18
- 🔄 `_present_delivery()` L558: 认知复杂度: 14
- 📏 `_present_reconcile()` L26: 77 代码量
- 📏 `_present_pivot()` L105: 64 代码量
- 📏 `_present_purchase()` L315: 105 代码量
- 📏 `_present_shipping_review()` L422: 77 代码量
- 📏 `_purchase_unmatched_rows()` L208: 6 参数数量
- 📏 `_delivery_quality()` L501: 6 参数数量
- 🏗️ `_purchase_unmatched_rows()` L208: 中等嵌套: 3
- ❌ L43: 未处理的易出错调用
- ❌ L44: 未处理的易出错调用
- ❌ L45: 未处理的易出错调用
- ❌ L46: 未处理的易出错调用
- ❌ L47: 未处理的易出错调用
- ❌ L48: 未处理的易出错调用
- ❌ L49: 未处理的易出错调用
- ❌ L53: 未处理的易出错调用
- ❌ L77: 未处理的易出错调用
- ❌ L78: 未处理的易出错调用
- ❌ L131: 未处理的易出错调用
- ❌ L132: 未处理的易出错调用
- ❌ L133: 未处理的易出错调用
- ❌ L134: 未处理的易出错调用
- ❌ L135: 未处理的易出错调用
- ❌ L136: 未处理的易出错调用
- ❌ L140: 未处理的易出错调用
- ❌ L174: 未处理的易出错调用
- ❌ L175: 未处理的易出错调用
- ❌ L176: 未处理的易出错调用
- ❌ L177: 未处理的易出错调用
- ❌ L178: 未处理的易出错调用
- ❌ L323: 未处理的易出错调用
- ❌ L327: 未处理的易出错调用
- ❌ L478: 未处理的易出错调用
- ❌ L479: 未处理的易出错调用
- ❌ L593: 未处理的易出错调用
- ❌ L609: 未处理的易出错调用
- ❌ L654: 未处理的易出错调用
- 🏷️ `_present_reconcile()` L26: "_present_reconcile" - snake_case
- 🏷️ `_present_pivot()` L105: "_present_pivot" - snake_case
- 🏷️ `_row_summary()` L171: "_row_summary" - snake_case
- 🏷️ `_purchase_conflict_rows()` L182: "_purchase_conflict_rows" - snake_case
- 🏷️ `_purchase_unmatched_rows()` L208: "_purchase_unmatched_rows" - snake_case
- 🏷️ `_purchase_quality_checks()` L243: "_purchase_quality_checks" - snake_case
- 🏷️ `_purchase_sections()` L271: "_purchase_sections" - snake_case
- 🏷️ `_present_purchase()` L315: "_present_purchase" - snake_case
- 🏷️ `_present_shipping_review()` L422: "_present_shipping_review" - snake_case
- 🏷️ `_delivery_quality()` L501: "_delivery_quality" - snake_case

**详情**:
- 循环复杂度: 平均: 8.3, 最大: 19
- 认知复杂度: 平均: 10.9, 最大: 23
- 嵌套深度: 平均: 1.3, 最大: 3
- 函数长度: 平均: 43.9 行, 最大: 105 行
- 文件长度: 665 代码量 (712 总计)
- 参数数量: 平均: 2.7, 最大: 6
- 代码重复: 0.0% 重复 (0/15)
- 结构分析: 1 个结构问题
- 错误处理: 29/90 个错误被忽略 (32.2%)
- 注释比例: 0.8% (5/665)
- 命名规范: 发现 15 个违规

### 9. core\master_data_import_core.py

**糟糕指数: 30.18**

> 行数: 850 总计, 710 代码, 25 注释 | 函数: 40 | 类: 1

**问题**: 🔄 复杂度问题: 10, ⚠️ 其他问题: 7, 🏗️ 结构问题: 7, ❌ 错误处理问题: 30, 📝 注释问题: 1, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `mutate` | L617-657 | 41 | 18 | 2 | 1 | ✓ |
| `_analyze_workbook` | L350-447 | 94 | 15 | 3 | 2 | ✓ |
| `analyze` | L519-577 | 59 | 15 | 3 | 7 | ✓ |
| `_sheet_layout` | L227-253 | 27 | 10 | 3 | 1 | ✓ |
| `merge_batch` | L731-786 | 56 | 10 | 4 | 4 | ✓ |
| `_read_json` | L159-176 | 18 | 6 | 2 | 2 | ✓ |
| `_summary` | L450-473 | 24 | 6 | 0 | 1 | ✓ |
| `_merge_relations` | L706-728 | 23 | 6 | 2 | 1 | ✓ |
| `export_catalog` | L814-849 | 36 | 6 | 2 | 1 | ✓ |
| `_public` | L476-485 | 10 | 5 | 2 | 2 | ✓ |
| `merge_ready_batches` | L789-811 | 23 | 5 | 3 | 2 | ✓ |
| `_atomic_write_json` | L136-156 | 21 | 4 | 3 | 2 | ✓ |
| `_text` | L189-200 | 12 | 4 | 1 | 1 | ✓ |
| `_field_for_header` | L216-224 | 9 | 4 | 2 | 1 | ✓ |
| `_iter_openpyxl` | L256-285 | 21 | 4 | 4 | 1 | ✓ |
| `_all_batches` | L488-496 | 9 | 4 | 2 | 1 | ✓ |
| `import_root` | L92-103 | 12 | 3 | 1 | 1 | ✓ |
| `_file_sha256` | L179-186 | 8 | 3 | 2 | 1 | ✓ |
| `remaining` | L273-281 | 9 | 3 | 1 | 2 | ✓ |
| `_append_relation` | L328-347 | 20 | 3 | 1 | 6 | ✓ |
| `cell` | L381-384 | 4 | 3 | 0 | 1 | ✓ |
| `mutate` | L671-679 | 9 | 3 | 1 | 1 | ✓ |
| `mutate` | L693-700 | 8 | 3 | 1 | 1 | ✓ |
| `_batch_path` | L113-122 | 10 | 2 | 1 | 2 | ✓ |
| `_iter_xls` | L288-305 | 14 | 2 | 2 | 1 | ✓ |
| `rows` | L298-301 | 4 | 2 | 1 | 1 | ✓ |
| `_iter_sheets` | L308-310 | 3 | 2 | 0 | 1 | ✓ |
| `_mutate_batch` | L580-595 | 16 | 2 | 1 | 3 | ✓ |
| `resolve_conflict` | L598-660 | 22 | 2 | 1 | 7 | ✓ |
| `__init__` | L81-84 | 4 | 1 | 0 | 2 | ✓ |
| `_now_iso` | L87-89 | 3 | 1 | 0 | 0 | ✓ |
| `_batches_dir` | L106-110 | 5 | 1 | 0 | 1 | ✓ |
| `_root_guard` | L125-133 | 9 | 1 | 0 | 1 | ✓ |
| `_header` | L203-207 | 5 | 1 | 0 | 1 | ✓ |
| `_candidate_id` | L313-320 | 8 | 1 | 0 | 2 | ✓ |
| `_source` | L323-325 | 3 | 1 | 0 | 3 | ✓ |
| `list_batches` | L499-511 | 13 | 1 | 0 | 1 | ✓ |
| `get_batch` | L514-516 | 3 | 1 | 0 | 2 | ✓ |
| `confirm_batch` | L663-682 | 11 | 1 | 0 | 4 | ✓ |
| `reject_batch` | L685-703 | 11 | 1 | 0 | 4 | ✓ |

**全部问题 (63)**

- 🔄 `_analyze_workbook()` L350: 复杂度: 15
- 🔄 `analyze()` L519: 复杂度: 15
- 🔄 `mutate()` L617: 复杂度: 18
- 🔄 `_sheet_layout()` L227: 认知复杂度: 16
- 🔄 `_analyze_workbook()` L350: 认知复杂度: 21
- 🔄 `analyze()` L519: 认知复杂度: 21
- 🔄 `mutate()` L617: 认知复杂度: 22
- 🔄 `merge_batch()` L731: 认知复杂度: 18
- 🔄 `_iter_openpyxl()` L256: 嵌套深度: 4
- 🔄 `merge_batch()` L731: 嵌套深度: 4
- 📏 `_analyze_workbook()` L350: 94 代码量
- 📏 `analyze()` L519: 59 代码量
- 📏 `merge_batch()` L731: 56 代码量
- 📏 `_append_relation()` L328: 6 参数数量
- 📏 `analyze()` L519: 7 参数数量
- 📏 `resolve_conflict()` L598: 7 参数数量
- 🏗️ `_atomic_write_json()` L136: 中等嵌套: 3
- 🏗️ `_sheet_layout()` L227: 中等嵌套: 3
- 🏗️ `_iter_openpyxl()` L256: 中等嵌套: 4
- 🏗️ `_analyze_workbook()` L350: 中等嵌套: 3
- 🏗️ `analyze()` L519: 中等嵌套: 3
- 🏗️ `merge_batch()` L731: 中等嵌套: 4
- 🏗️ `merge_ready_batches()` L789: 中等嵌套: 3
- ❌ L153: 未处理的易出错调用
- ❌ L182: 未处理的易出错调用
- ❌ L184: 未处理的易出错调用
- ❌ L285: 未处理的易出错调用
- ❌ L456: 未处理的易出错调用
- ❌ L457: 未处理的易出错调用
- ❌ L458: 未处理的易出错调用
- ❌ L459: 未处理的易出错调用
- ❌ L460: 未处理的易出错调用
- ❌ L461: 未处理的易出错调用
- ❌ L462: 未处理的易出错调用
- ❌ L463: 未处理的易出错调用
- ❌ L467: 未处理的易出错调用
- ❌ L468: 未处理的易出错调用
- ❌ L469: 未处理的易出错调用
- ❌ L470: 未处理的易出错调用
- ❌ L471: 未处理的易出错调用
- ❌ L472: 未处理的易出错调用
- ❌ L575: 未处理的易出错调用
- ❌ L619: 未处理的易出错调用
- ❌ L625: 未处理的易出错调用
- ❌ L653: 未处理的易出错调用
- ❌ L713: 未处理的易出错调用
- ❌ L723: 未处理的易出错调用
- ❌ L724: 未处理的易出错调用
- ❌ L726: 未处理的易出错调用
- ❌ L763: 未处理的易出错调用
- ❌ L837: 未处理的易出错调用
- ❌ L838: 未处理的易出错调用
- ❌ L848: 未处理的易出错调用
- 🏷️ `__init__()` L81: "__init__" - snake_case
- 🏷️ `_now_iso()` L87: "_now_iso" - snake_case
- 🏷️ `_batches_dir()` L106: "_batches_dir" - snake_case
- 🏷️ `_batch_path()` L113: "_batch_path" - snake_case
- 🏷️ `_root_guard()` L125: "_root_guard" - snake_case
- 🏷️ `_atomic_write_json()` L136: "_atomic_write_json" - snake_case
- 🏷️ `_read_json()` L159: "_read_json" - snake_case
- 🏷️ `_file_sha256()` L179: "_file_sha256" - snake_case
- 🏷️ `_text()` L189: "_text" - snake_case
- 🏷️ `_header()` L203: "_header" - snake_case

**详情**:
- 循环复杂度: 平均: 4.2, 最大: 18
- 认知复杂度: 平均: 6.7, 最大: 22
- 嵌套深度: 平均: 1.3, 最大: 4
- 函数长度: 平均: 17.4 行, 最大: 94 行
- 文件长度: 710 代码量 (850 总计)
- 参数数量: 平均: 2.0, 最大: 7
- 代码重复: 5.0% 重复 (2/40)
- 结构分析: 7 个结构问题
- 错误处理: 30/57 个错误被忽略 (52.6%)
- 注释比例: 3.5% (25/710)
- 命名规范: 发现 24 个违规

### 10. core\delivery_core.py

**糟糕指数: 29.03**

> 行数: 678 总计, 517 代码, 68 注释 | 函数: 26 | 类: 0

**问题**: 🔄 复杂度问题: 10, ⚠️ 其他问题: 5, 🏗️ 结构问题: 3, ❌ 错误处理问题: 8, 🏷️ 命名问题: 10

#### 函数详情

| 函数 | 行范围 | 行数 | 复杂度 | 嵌套 | 参数 | 注释 |
|:-----|------:|------:|------:|------:|------:|:------:|
| `build_plan_sheet` | L344-415 | 72 | 16 | 2 | 7 | ✓ |
| `_match_ref_header` | L481-508 | 28 | 14 | 5 | 2 | ✓ |
| `classify` | L284-315 | 32 | 13 | 1 | 5 | ✓ |
| `run` | L583-677 | 91 | 12 | 2 | 8 | ✓ |
| `build_supplier_map` | L418-441 | 24 | 9 | 3 | 2 | ✓ |
| `_complete_from_catalog` | L444-470 | 27 | 8 | 2 | 4 | ✓ |
| `_select_delivery_sheet` | L133-160 | 28 | 7 | 2 | 3 | ✓ |
| `_reference_case_record` | L521-532 | 12 | 7 | 1 | 3 | ✓ |
| `analyze` | L230-271 | 42 | 6 | 3 | 3 | ✓ |
| `_read_reference_case_map` | L535-547 | 13 | 5 | 2 | 3 | ✓ |
| `norm_code` | L50-61 | 12 | 4 | 1 | 1 | ✓ |
| `cell_text` | L64-70 | 7 | 4 | 1 | 1 | ✓ |
| `_delivery_row` | L176-195 | 20 | 4 | 1 | 3 | ✓ |
| `_read_delivery_rows` | L198-206 | 9 | 4 | 2 | 3 | ✓ |
| `build_case_map` | L550-580 | 27 | 4 | 2 | 2 | ✓ |
| `detect_layout_or_shape` | L101-114 | 14 | 3 | 1 | 3 | ✓ |
| `list_sheets` | L117-130 | 14 | 3 | 2 | 1 | ✓ |
| `_find_reference_detail_sheet` | L511-518 | 8 | 3 | 2 | 1 | ✓ |
| `_delivery_optional_value` | L163-166 | 4 | 2 | 0 | 4 | ✓ |
| `_is_delivery_summary_row` | L169-173 | 5 | 2 | 0 | 1 | ✓ |
| `load_sheet` | L209-227 | 19 | 2 | 2 | 3 | ✓ |
| `_has_supplier` | L274-276 | 3 | 2 | 0 | 1 | ✓ |
| `_lg` | L556-559 | 4 | 2 | 1 | 1 | ✓ |
| `_lg` | L597-600 | 4 | 2 | 1 | 1 | ✓ |
| `detect_layout` | L80-88 | 9 | 1 | 0 | 3 | ✓ |
| `_has_qty` | L279-281 | 3 | 1 | 0 | 1 | ✓ |

**全部问题 (35)**

- 🔄 `classify()` L284: 复杂度: 13
- 🔄 `build_plan_sheet()` L344: 复杂度: 16
- 🔄 `_match_ref_header()` L481: 复杂度: 14
- 🔄 `run()` L583: 复杂度: 12
- 🔄 `classify()` L284: 认知复杂度: 15
- 🔄 `build_plan_sheet()` L344: 认知复杂度: 20
- 🔄 `build_supplier_map()` L418: 认知复杂度: 15
- 🔄 `_match_ref_header()` L481: 认知复杂度: 24
- 🔄 `run()` L583: 认知复杂度: 16
- 🔄 `_match_ref_header()` L481: 嵌套深度: 5
- 📏 `build_plan_sheet()` L344: 72 代码量
- 📏 `run()` L583: 91 代码量
- 📏 `build_plan_sheet()` L344: 7 参数数量
- 📏 `run()` L583: 8 参数数量
- 🏗️ `analyze()` L230: 中等嵌套: 3
- 🏗️ `build_supplier_map()` L418: 中等嵌套: 3
- 🏗️ `_match_ref_header()` L481: 嵌套过深: 5
- ❌ L127: 未处理的易出错调用
- ❌ L227: 未处理的易出错调用
- ❌ L267: 未处理的易出错调用
- ❌ L384: 未处理的易出错调用
- ❌ L396: 未处理的易出错调用
- ❌ L432: 未处理的易出错调用
- ❌ L457: 未处理的易出错调用
- ❌ L580: 未处理的易出错调用
- 🏷️ `_select_delivery_sheet()` L133: "_select_delivery_sheet" - snake_case
- 🏷️ `_delivery_optional_value()` L163: "_delivery_optional_value" - snake_case
- 🏷️ `_is_delivery_summary_row()` L169: "_is_delivery_summary_row" - snake_case
- 🏷️ `_delivery_row()` L176: "_delivery_row" - snake_case
- 🏷️ `_read_delivery_rows()` L198: "_read_delivery_rows" - snake_case
- 🏷️ `_has_supplier()` L274: "_has_supplier" - snake_case
- 🏷️ `_has_qty()` L279: "_has_qty" - snake_case
- 🏷️ `_complete_from_catalog()` L444: "_complete_from_catalog" - snake_case
- 🏷️ `_match_ref_header()` L481: "_match_ref_header" - snake_case
- 🏷️ `_find_reference_detail_sheet()` L511: "_find_reference_detail_sheet" - snake_case

**详情**:
- 循环复杂度: 平均: 5.4, 最大: 16
- 认知复杂度: 平均: 8.4, 最大: 24
- 嵌套深度: 平均: 1.5, 最大: 5
- 函数长度: 平均: 20.4 行, 最大: 91 行
- 文件长度: 517 代码量 (678 总计)
- 参数数量: 平均: 2.7, 最大: 8
- 代码重复: 3.8% 重复 (1/26)
- 结构分析: 3 个结构问题
- 错误处理: 8/14 个错误被忽略 (57.1%)
- 注释比例: 13.2% (68/517)
- 命名规范: 发现 14 个违规

## 最差函数 Top 10

| 函数 | 文件 | 复杂度 | 嵌套 | 行数 |
|:-----|:-----|------:|------:|------:|
| `_present_reconcile` | core\business_result_operations.py | 19 | 2 | 77 |
| `_read_attendance` | core\attendance_archive_core.py | 19 | 4 | 45 |
| `bridge_request_sync_with_events` | tauri-app\src-tauri\src\lib.rs | 19 | 5 | 74 |
| `save_template` | core\template_store.py | 18 | 2 | 45 |
| `_report_build` | core\tauri_bridge.py | 18 | 3 | 42 |
| `_read_package` | core\shipping_review_core.py | 18 | 5 | 80 |
| `build_report` | core\report_center_core.py | 18 | 2 | 102 |
| `parse_pages` | core\pdf_core.py | 18 | 4 | 37 |
| `mutate` | core\master_data_import_core.py | 18 | 2 | 41 |
| `_present_attendance` | core\business_result_daily.py | 18 | 2 | 77 |

## 诊断结论 {#conclusion}

🌸 **微臭青年** - 略有异味，建议适量通风

👍 继续保持，你是编码界的一股清流，代码洁癖者的骄傲

---

*由 [fuck-u-code](https://github.com/Done-0/fuck-u-code) 生成*