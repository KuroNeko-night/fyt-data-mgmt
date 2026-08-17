# AGENTS.md：峰运通数据管理系统

本文件是仓库维护约束，不是客户帮助文档。项目面向峰运通内部的 Tauri 桌面端、局域网 Web 端和 Linux/Windows 服务端。回复、代码注释、文档和界面文案一律使用中文；涉及协议、环境变量、稳定键名或外部工具名称时保留其原文。

## 项目边界

- 正式业务入口只有 Tauri 桌面端和 Web 端。
- `core/` 是考勤、到料、采购、对账、主数据、现场问题、日清和文件工具的业务算法唯一事实源；不得导入 UI、弹窗或依赖 Web/Tauri。
- `web_server.py` 只保留兼容启动、运行配置和依赖组合；HTTP、数据库、领域服务和任务执行位于 `web_backend/`。新功能不得把领域逻辑重新塞回这个文件。
- 不新增独立 Qt 业务入口，不在前端、Rust 或 Web 服务中复制 `core/` 的表格解析和业务算法。
- 除非现有协议确实需要，禁止新增旧入口或无期限兼容层。当前仍在使用的兼容门面（例如 `common_core.py`、`daily_report_core.py`、`library.py`）必须保持公开入口稳定，并把新实现放在对应拆分模块中。

## 技术基线

- Windows 桌面端：Windows 10/11、Python 3.13、Rust stable MSVC、Tauri 2.11。
- 双端前端：React 19.2、Vite 8.1、TypeScript 7；Web 端由 Python 服务托管 `web-app/dist`。
- Linux 服务端安装器支持 Python 3.10～3.13，不替换系统 Python；运行依赖由 `requirements.txt` 锁定。
- `web_control_gui.py` 只使用标准库 Tkinter/ttk，不引入第三方 GUI 框架。
- 中文 Windows 控制台可能使用 GBK；脚本不得依赖特殊符号能被控制台正确显示。测试前设置 `PYTHONIOENCODING=utf-8`。

## 当前目录与分层

下面的结构以当前仓库实际代码为准。树中列出的是有稳定职责的源码目录和关键入口；构建产物、运行数据、私密配置和本地工具目录不属于源码架构。

```text
峰运通数据管理系统/
├─ AGENTS.md                         仓库协作约束与架构事实
├─ README.md                         面向使用者的项目介绍
├─ LICENSE                           许可证
├─ pyproject.toml                    Python 工具与质量配置
├─ requirements*.txt                 运行依赖与完整开发依赖
├─ .env.example                      环境变量示例，不含真实凭据
├─ web_server.py                     Web 兼容启动入口、配置导出和组合根
├─ web_control_gui.py                Tkinter/ttk 服务与 Tunnel 控制台
├─ web_control_gui_process.py        GUI 使用的 PID、日志和进程生命周期工具
│
├─ core/                             跨桌面端、Web 端共享的纯 Python 业务核心
│  ├─ common_core.py                 公共兼容门面
│  ├─ common_parsing.py              值解析、数字/日期/文本规范化
│  ├─ common_workbook.py             Excel 读取、公式缓存和工作簿安全处理
│  ├─ header_detect.py               表头与列角色识别
│  ├─ shape_detect.py                表格形态识别
│  ├─ attendance_core.py             考勤填报
│  ├─ attendance_archive_core.py     考勤月度归档
│  ├─ attendance_source.py           考勤来源识别与多表合并
│  ├─ reconcile_core.py              工时对账主流程
│  ├─ reconcile_sources.py            对账来源读取与字段识别
│  ├─ reconcile_zong.py               对账总表布局识别与填写
│  ├─ reconcile_reporting.py          对账报告与可信度工作表
│  ├─ arrival_core.py                 每日到料识别与报告生成
│  ├─ delivery_core.py                送货计划
│  ├─ shipping_review_core.py         发运评审对比
│  ├─ supplier_batch_core.py          供应商批次表
│  ├─ purchase_core.py                采购对账
│  ├─ purchase_plan_core.py            采购计划导入与差异清单
│  ├─ purchase_reporting.py            采购类报告渲染
│  ├─ reconcile_statement_core.py     对账单制作
│  ├─ pivot_core.py                   销售透视主流程
│  ├─ pivot_analysis.py               透视结构识别与复核计划
│  ├─ pivot_clustering.py             规格、单位归并与静态聚合
│  ├─ pivot_ooxml.py                  原生透视缓存与 OOXML 写入
│  ├─ pivot_reporting.py              透视可信度和兼容报告
│  ├─ daily_report_core.py            日清兼容门面
│  ├─ daily_report_snapshot.py        日清快照总装
│  ├─ daily_report_arrival.py         日清到料投影
│  ├─ daily_report_attendance.py      日清考勤投影
│  ├─ daily_report_workshop.py        日清现场问题投影
│  ├─ daily_report_production.py      日清生产与订单投影
│  ├─ daily_report_values.py          日清共享值规范化
│  ├─ daily_report_excel.py            日清 Excel 输出
│  ├─ daily_production_plan_core.py   生产计划、订单和发运资料识别
│  ├─ daily_safety_check_core.py      安全检查日报
│  ├─ workshop_issue_core.py          现场问题模板、图片和导出
│  ├─ business_result_core.py         双端业务结果投影兼容入口
│  ├─ business_result_common.py       结果公共规范化
│  ├─ business_result_daily.py        到料、考勤和日清结果投影
│  ├─ business_result_operations.py   采购、运营和业务结果投影
│  ├─ business_result_finance.py      财务与通用比对结果投影
│  ├─ master_data_import_core.py      主数据学习、冲突治理和合并
│  ├─ material_catalog.py             正式主数据库
│  ├─ mapping_store.py                字段映射确认记录
│  ├─ template_store.py               模板族、版本和迁移规则
│  ├─ library.py                      文件库公开门面与分类事实源
│  ├─ library_classification.py       文件分类评分器注册表
│  ├─ library_scan.py                 Excel 文件有限扫描
│  ├─ library_storage.py              文件归档、删除和回滚事务
│  ├─ batch_track_core.py             批次关联追踪
│  ├─ report_center_core.py           报表中心汇总
│  ├─ invoice_core.py                 发票统计
│  ├─ invoice_match_core.py           票货匹配
│  ├─ compare_core.py                 表格比对
│  ├─ currency_core.py                金额大写
│  ├─ excel_tools_core.py             Excel/CSV 工具
│  ├─ pdf_core.py                     PDF 工具
│  ├─ rename_core.py                  批量重命名
│  ├─ text_core.py                    文本工具
│  ├─ preview_core.py                 轻量文件预览
│  ├─ paths.py                        配置、输出和运行目录
│  ├─ settings.py                     桌面端运行设置
│  ├─ storage_lock.py                 文件锁、临时文件和原子替换
│  ├─ incremental_cache.py            输入指纹与增量缓存
│  ├─ task_history.py                 桌面端任务历史
│  ├─ updater.py                      更新包校验与下载
│  ├─ tauri_bridge.py                 JSON stdin/stdout 桥接协议
│  ├─ tauri_bridge_actions.py         桥接载荷校验和动作处理器
│  ├─ version.py                      版本、应用信息和构建日期
│  └─ __init__.py                     Core 包入口
│
├─ web_backend/                      Web 服务端实现边界
│  ├─ config.py                       Web 能力目录、角色、限制和业务时区
│  ├─ server_runtime.py               ThreadingHTTPServer、清理和后台维护循环
│  ├─ errors.py                       领域异常到公开错误的映射
│  ├─ passwords.py                    密码哈希和验证
│  ├─ serializers.py                  JSON 兼容转换
│  ├─ presenters.py                   账号、日清、文件库和问题的公开结构
│  ├─ database/                       SQLite 数据层
│  │  ├─ connection.py                连接、事务和线程边界
│  │  ├─ schema.py                    完整表结构、索引和约束
│  │  ├─ migrations.py                幂等字段升级与历史迁移
│  │  └─ initializer.py               建库、默认数据和初始化事务编排
│  ├─ http/                           HTTP 协议层
│  │  ├─ routes.py                    方法、路径和领域端点分发
│  │  ├─ handler.py                   请求解析、鉴权上下文和响应调度
│  │  ├─ context.py                   会话、用户和权限上下文
│  │  ├─ path_params.py               路径参数与目录边界校验
│  │  ├─ responses.py                 JSON、文件、错误和缓存响应
│  │  └─ static_files.py              前端静态资源与入口页
│  ├─ services/                       领域服务层
│  │  ├─ auth.py                      登录、注册、会话和设备
│  │  ├─ admin_accounts.py            账号审核、角色和管理员操作
│  │  ├─ admin_data.py                管理数据、审计和系统设置
│  │  ├─ uploads.py                   上传句柄、文件流和配额
│  │  ├─ jobs.py                      任务创建、查询、取消和重试
│  │  ├─ library.py                   Web 团队数据库
│  │  ├─ master_data.py               主数据上传、冲突治理和合并
│  │  ├─ workshop.py                  现场问题草稿、发布、闭环和导出
│  │  ├─ daily_management.py          日清兼容门面
│  │  ├─ daily_management_types.py    日清共享类型与请求契约
│  │  ├─ daily_people.py              人员、班组、班次和考勤
│  │  ├─ daily_briefs.py              事项、通报和会议待办
│  │  ├─ daily_files.py               到料、安全、生产和订单资料
│  │  ├─ daily_report.py              日清总览和结构化投影
│  │  ├─ dashboard.py                 工作台聚合
│  │  ├─ reports.py                   报表中心与批次追踪查询
│  │  ├─ notifications.py             公告、定向消息和阅读状态
│  │  ├─ backups.py                   备份、校验和恢复
│  │  ├─ trash.py                     回收站与保留策略
│  │  ├─ maintenance.py               定期清理、周报和月报
│  │  └─ __init__.py                  服务包入口
│  ├─ tasks/                          长任务和 Core 桥接层
│  │  ├─ runner.py                    持久化任务状态机与子进程生命周期
│  │  ├─ bridge.py                    Core 子进程调用和事件转发
│  │  ├─ actions.py                   Web 特殊动作编排
│  │  ├─ results.py                   结果文件、预览和投影整理
│  │  └─ __init__.py                  任务包入口
│  └─ __init__.py                     Web Backend 包入口
│
├─ web-app/                          React/Vite Web 前端
│  ├─ package.json/vite.config.ts     Web 依赖、构建和开发服务器配置
│  ├─ src/App.tsx                     Web 应用根与会话状态
│  ├─ src/main.tsx                    前端挂载入口
│  ├─ src/api/                        同源 API 客户端与类型契约
│  │  ├─ client.ts                    会话请求和通用请求封装
│  │  └─ types.ts                     接口数据类型
│  ├─ src/app/                        外壳、认证、导航和响应式入口
│  │  ├─ WebShell.tsx                 页面外壳与路由舞台
│  │  ├─ AppSidebar.tsx               桌面侧栏
│  │  ├─ AppTopbar.tsx                顶栏
│  │  ├─ MobileNavigation.tsx         移动端底栏
│  │  ├─ MoreDrawer.tsx               移动端更多抽屉
│  │  ├─ AuthScreen.tsx               登录、注册和审核提示
│  │  ├─ navigation.ts                导航和角色入口矩阵
│  │  └─ *.css                        认证与外壳样式
│  ├─ src/pages/                      页面级业务组合
│  │  └─ FeaturesPage.tsx             业务模块目录
│  ├─ src/ui/                         共享交互组件
│  │  ├─ Button/IconButton             操作按钮
│  │  ├─ Dialog/Drawer                 弹窗和抽屉
│  │  ├─ DataTable/FileRow/TaskRow     数据、文件和任务展示
│  │  ├─ FormField/SegmentedControl    表单与分段控件
│  │  ├─ Surface/PageHeader            页面表面和标题
│  │  ├─ StatusBadge/Notice            状态和提示
│  │  ├─ EmptyState/Skeleton           空态和加载态
│  │  └─ ArtAsset/status               美术资源和状态映射
│  ├─ src/hooks/                       数据读取和交互 Hook
│  ├─ src/styles/                      令牌、布局、主题、组件和响应式样式
│  ├─ src/FeatureWorkspace.tsx         业务上传、参数、复核和任务结果
│  ├─ src/BusinessResultView.tsx       结构化结果与可信度展示
│  ├─ src/DailyReportPage.tsx           日清看板
│  ├─ src/DailyReportManagement.tsx     日清资料和人工维护
│  ├─ src/WorkshopIssuePage.tsx         现场问题移动端页面
│  ├─ src/FileLibraryPage.tsx           团队数据库
│  ├─ src/BatchTrackPage.tsx            批次跟踪
│  ├─ src/TaskCenterPage.tsx            任务中心
│  ├─ src/NotificationCenterPage.tsx   消息中心
│  ├─ src/AdminPage.tsx                 系统管理
│  ├─ src/AccountSecurityPage.tsx       账号安全
│  └─ src/*.css                         业务页面和结果样式
│
├─ tauri-app/                          React/Vite/Tauri 桌面端
│  ├─ src/App.tsx                       桌面应用根
│  ├─ src/app/                          桌面外壳、模式和工作台
│  │  ├─ AppSidebar.tsx/AppTopbar.tsx   桌面导航
│  │  ├─ LocalWorkbench.tsx             本地模式
│  │  ├─ RemoteWorkbench.tsx            Web 远程模式
│  │  ├─ ContextPanel.tsx/ModePicker.tsx 上下文与模式切换
│  │  └─ navigation.ts                  桌面导航兼容入口
│  ├─ src/components/                   页面组合与引导组件
│  ├─ src/data/navigation.ts            NAV_ITEMS 单一导航来源
│  ├─ src/hooks/useBridgeTask.ts        桥接任务、日志、进度和完成事件
│  ├─ src/lib/                          Rust 桥接和本地文件访问
│  ├─ src/pages/                        人事、业务、数据、财务和工具页面
│  ├─ src/ui/                           与 Web 对齐的共享语义组件
│  ├─ src/styles/                       桌面布局、主题、页面和结果样式
│  ├─ src/assets/illustrations/         桌面端内置 SVG 插图
│  ├─ package.json/vite.config.ts       桌面前端依赖和构建配置
│  └─ src-tauri/                        Rust/Tauri 宿主
│     ├─ tauri.conf.json                Tauri 窗口、资源和 sidecar 配置
│     ├─ Cargo.toml/Cargo.lock          Rust 依赖锁定
│     ├─ build.rs                       Tauri 构建脚本
│     └─ src/
│        ├─ lib.rs                      命令白名单、sidecar 和进程取消
│        └─ main.rs                     桌面进程入口
│
├─ design-system/                      双端共享设计系统
│  ├─ tokens.json                       颜色、排版、间距、动效和状态令牌
│  └─ README.md                         令牌使用说明
├─ assets/                             品牌和已验收美术资源
│  ├─ logo.png/logo_128.png/icon.ico    应用品牌资源
│  └─ generated/                        已投入运行的 Web/Tauri 生成资源
│     ├─ manifest.json                  资源清单与版本
│     ├─ web/                           Web 端资源
│     └─ tauri/                         Tauri 端资源
├─ packaging/                          交付包与 sidecar 配置
│  ├─ bridge_worker.spec                Core 桥接 worker 构建配置
│  ├─ tauri_bridge.spec                 Tauri sidecar 构建配置
│  ├─ tauri_bridge_entry.py             sidecar 无控制台入口
│  ├─ web_server.spec                   Web 服务构建配置
│  ├─ web_control_gui.spec              GUI 构建配置
│  └─ linux/                            Linux 安装、服务、备份和 Tunnel 脚本
│     ├─ install/deploy-from-git.sh              本地载荷安装与 Git 自动部署
│     ├─ update/apply-upgrade-patch.sh           整包升级说明和增量升级
│     ├─ start/stop/restart/status/logs.sh      服务控制与日志
│     ├─ backup.sh/common.sh                     备份和共享脚本函数
│     ├─ fyt-web.service                         systemd 单元
│     └─ cloudflared*.sh                         临时与固定 Tunnel
├─ scripts/                            构建、同步、部署和质量检查工具
│  ├─ setup-modern.ps1                  Windows 开发环境准备
│  ├─ run-web*.ps1/stop-web-tunnel.ps1 Web 服务和 Tunnel 启停
│  ├─ build_deploy.py                   Windows/Linux/源码交付包
│  ├─ build_linux_upgrade_patch.py      Linux 增量补丁
│  ├─ smoke_deploy_package.py           部署包冒烟测试
│  ├─ check_repository_hygiene.py       仓库敏感文件和生成物检查
│  ├─ release.mjs                       版本同步
│  ├─ sync-design-tokens.mjs            设计令牌同步
│  ├─ sync-art-assets.mjs               美术资源同步
│  ├─ optimize-art-assets.py            美术资源本地优化
│  ├─ reset-web-admin-password.ps1      管理员密码安全重置
│  ├─ install-cloudflared.ps1           Windows cloudflared 安装辅助
│  ├─ sync-github.ps1/sync-github.sh    Git 同步辅助，不属于运行服务
│  └─ art-prompts/                      美术资源生成提示词和清单
├─ docker/                             容器运行编排（可选交付方式）
│  ├─ Dockerfile                        Web 多阶段镜像
│  └─ docker-compose.yml                Web 服务与数据卷编排
├─ tests/                              unittest 合成数据回归
│  ├─ sample_data.py                    合成业务表格和临时目录工具
│  ├─ web_server_test_base.py           Web HTTP 测试底座
│  ├─ test_<feature>.py                 Core 业务回归
│  ├─ test_web_server_*.py              Web 认证、任务、文件、现场问题和运维回归
│  └─ test_deploy_scripts.py/test_linux_packaging.py 部署边界回归
├─ docs/                               当前实现与维护规范
│  ├─ 项目全景-模块与实现.md             业务、接口和模块事实
│  ├─ 源码注释与编码风格规范.md          代码注释和复杂度基线
│  └─ 仓库维护与目录规范.md              源码包与仓库边界
└─ .github/workflows/ci.yml             GitHub CI（仅执行自动检查）
```

以下目录可能在本地出现，但不属于源码架构，禁止复制进源码包或提交到 Git：

```text
.venv/、node_modules/、target/、__pycache__/  本地依赖与编译缓存
dist/、outputs/                              构建产物与业务输出
web-data/、secrets/                          账号数据库、上传资料和私密配置（仅保留已审阅示例文件）
三份本地部署与排错指南                    维护电脑资料，由 .gitignore 和源码包白名单排除
.git/、.superpowers/、.vibeskills/           Git 元数据和本地工具状态
```

关键依赖方向必须保持单向：

```text
共享设计令牌 ──> Web/Tauri 样式与资源
core/*       ──> Tauri Rust 白名单 ──> Tauri React
core/*       ──> web_backend/tasks ──> web_backend/http ──> Web React
web_backend/database ──> services ──> http/presenters
```

Web 请求链路为：

```text
Web React -> 同源 /api -> web_backend/http -> services/tasks -> core.tauri_bridge -> core/*
```

Tauri 请求链路为：

```text
Tauri React -> Rust 白名单命令 -> core.tauri_bridge -> core/*
```

长任务和结果链路为：

```text
上传/参数 -> services.jobs -> tasks.runner
          -> tasks.bridge -> core.tauri_bridge -> <feature>_core.run()
          -> business_result_core -> tasks.results/presenters
          -> 任务历史、结构化预览和正式下载文件
```

服务启动链路为：

```text
Windows GUI/脚本或 Linux systemd
    -> web_server.py
    -> web_backend.server_runtime
    -> database.initializer + ThreadingHTTPServer
    -> http.handler/routes
```

桌面端启动时由 Tauri 宿主管理 sidecar 和请求取消；Web 长任务由服务端为当前账号创建隔离运行目录和持久化任务 ID。两条链路最终都只能通过 `core/` 的公开入口执行业务算法，前端不得自行解析或重算业务表格。

## 单一事实来源

- 版本：`core/version.py` 的 `VERSION`、`VERSION_TUPLE`、`BUILD_DATE`。运行 `node scripts/release.mjs` 同步两个 `package.json`、`tauri.conf.json` 和 Cargo 顶层版本。
- Web 配置和能力目录：`web_backend/config.py` 的 `FEATURES`、`WEB_ACTIONS`、`REVIEW_ACTIONS`、角色、限制和业务时区；`web_server.py` 只兼容导出这些值。
- Web 路由和协议：`web_backend/http/routes.py`、`web_backend/http/handler.py`、`web_backend/http/responses.py`、`web_backend/http/context.py`。
- Web 数据库：`web_backend/database/schema.py` 声明完整表结构和索引，`migrations.py` 执行幂等迁移，`initializer.py` 编排初始化事务。
- Web 领域服务：`web_backend/services/`；长任务和桥接：`web_backend/tasks/`。
- Web 表单与动作展示：`web-app/src/FeatureWorkspace.tsx` 的 `SPECS`；Web 导航：`web-app/src/app/navigation.ts`。
- Tauri 导航：`tauri-app/src/data/navigation.ts` 的 `NAV_ITEMS`；Rust 命令白名单：`tauri-app/src-tauri/src/lib.rs`。
- Python 桥接白名单：`core/tauri_bridge.py` 的 `_ACTIONS`。所有新增动作必须同时评估 Web 白名单、人工复核协议和路径校验。
- 配置路径：统一调用 `core.paths.config_path()`；Web 任务通过 `FYT_CONFIG_PATH` 指向账号隔离运行目录。
- 输出目录：`core.paths.resolve_output_dir()` 和 `core.paths.FEATURE_DIRS`；新输出类型必须注册中文目录名。
- Web 数据根：`FYT_WEB_DATA`；未设置时为项目下的 `web-data`，部署环境应与程序目录分离。
- 主数据：`core/material_catalog.py`；字段映射：`core/mapping_store.py`；模板规则：`core/template_store.py`。
- 数据库文件分类：`core/library.py` 的 `CATEGORIES`、`CATEGORY_TITLES` 与分类评分规则；实现拆分在 `library_classification.py`、`library_scan.py`、`library_storage.py`。
- 双端设计令牌：`design-system/tokens.json`；生成样式由同步脚本维护，不手工改生成文件。
- 已投入运行的美术资源：`assets/generated/manifest.json`；通过 `scripts/sync-art-assets.mjs` 同步到双端。

## Core 开发规范

每个业务功能使用一个 `<feature>_core.py`，公开入口保持以下形状：

```python
def run(inputs, out_dir=None, log=None) -> dict:
    if out_dir is None:
        st = settings.get_settings()
        out_dir = paths.resolve_output_dir("<feature>", **st.output_kwargs())
    return {"out_dir": out_dir}
```

- `log` 和可选 `progress` 只报告状态；异常必须向上抛出，不静默吞掉。
- 读取公式结果前调用 `common_core.warn_if_uncached()`；需要样式、图片或随机写入时不得使用只读流式模式。
- 大表顺序读取可使用 `load_data_only_stream()`；Excel 读取、表头识别和工作簿写入分别复用 `common_workbook.py`、`header_detect.py` 和现有公共工具。
- JSON 索引读改写必须使用 `storage_lock.file_lock()`、临时文件和原子替换。
- 正式主数据只补空值，不覆盖源文件已有值；管理员确认值不得被被动学习覆盖。
- 结构化预览必须在 `core/business_result_core.py` 及其拆分投影中注册，前端不得重新分析输出文件。投影失败只能增加提示，不能把成功业务任务改为失败。
- 新业务同时评估主数据补全、可信度、人工可调参数、结果预览、人工确认和合成数据测试。
- 注释重点说明业务不变量、事务顺序、并发边界、路径安全、失败回滚和兼容原因；不要给显而易见的语法逐行复述注释。

当前已完成的拆分包括：

- `common_core.py` 兼容入口，解析和工作簿能力分别在 `common_parsing.py`、`common_workbook.py`。
- 日清总装入口 `daily_report_snapshot.py`，到料、考勤、现场问题、生产、值规范化和 Excel 输出分别在 `daily_report_arrival.py`、`daily_report_attendance.py`、`daily_report_workshop.py`、`daily_report_production.py`、`daily_report_values.py`、`daily_report_excel.py`。
- `attendance_source.py` 独立维护考勤来源识别与合并。
- `library.py` 保持文件库事实源和稳定公开操作，分类、扫描、存储事务分别在三个拆分模块。
- `business_result_core.py` 为双端业务结果投影兼容入口，公共规范化与财务、运营、日清投影已拆分到相邻模块。
- `reconcile_core.py` 的主流程按来源读取、总表填写、劳务合并、比较、评估和汇总分阶段组织；复杂识别和报表样式应继续保持独立可测。

## Tauri 与 Web 协议

- Tauri Rust 通过白名单命令调用 `core.tauri_bridge`。桥接请求带 `request_id`；stderr 传递日志和进度，Rust 按请求精确取消子进程。
- Web React 只调用同源 `/api`。服务端把长任务保存为持久化任务 ID，在独立 Python 子进程中调用同一桥接层。
- Web 上传句柄、缓存、输出、运行目录、任务历史和配置必须按用户 ID 隔离；绝对路径、下载路径、预览和分享链接都要经过所属关系与目录穿越校验。
- 人工复核功能采用“只读分析 -> 返回计划 -> 用户选择 -> 最终执行”的两阶段协议，不得提供绕过确认的隐藏入口。
- Web JSON 请求体上限为 4 MB，普通文件上限 200 MB，主数据导入上限 50 MB；现场图片每张上限 15 MB、每条最多 8 张。
- 服务端统一使用流式文件响应、UTF-8 下载名和禁止缓存策略；结果版本、限时分享和回收站都由后端控制。

## Web 角色与安全

- 角色只有业务成员、班组长、管理员；角色键使用稳定英文值，客户文案使用 `web_backend/config.py` 的中文映射。
- 所有角色可使用工作台、业务模块、任务中心、消息中心、账号安全，并可查看和提交现场问题。
- 班组长和管理员可使用数据库、批次跟踪；只有管理员可使用日清看板、报表中心和系统管理。
- 普通成员只能维护自己的现场问题草稿；班组长可编辑、闭环和删除自己发布的问题；管理员可维护全部问题。
- 注册账号必须经管理员审核。默认管理员凭据不得出现在登录页、README、帮助文案、截图或日志中。
- 首次建库必须通过 `FYT_ADMIN_PASSWORD` 或控制台安全输入提供管理员密码；若使用安装器生成一次性随机密码，安装器仍须通过受保护环境变量传递，并在初始化后清理。
- 密码至少 10 位且同时包含字母和数字。登录失败、会话撤销、设备管理、备份恢复和管理操作遵循服务端现行规则。
- 使用 `HttpOnly`、`SameSite=Strict` 会话 Cookie；修改、重置密码或管理员撤销设备时必须使相关会话失效。

## 日清与资料规则

- 日清业务日期统一使用 `web_backend/config.py` 的 `BUSINESS_TZ`、`web_server.py` 兼容导出的 `business_today()` 和 `business_date()`；数据库时间戳存 UTC，按业务时区统计。
- 成品每日到料、安全检查和生产/订单/发运资料可由管理员直接上传；服务端必须从表格内容解析日期、批次、数量和月份，不要求人工重复填写表内已有数据。
- 到料自动识别主料总类数，并把剩余未收数为非零的物料列为未到料；人工填写的主料总类数仍可在复核阶段覆盖自动值。
- 生产人员考勤按班组、班次、编制、当日出勤和备注维护，不维护个人姓名；参会人员按名册逐人设置出勤状态和原因。
- 日清事项按类别显示各自字段；重大/升级事项和通报不得要求不属于模板的字段；安全检查使用独立资料入口，不属于事项类别。
- 现场问题严格使用 `workshop_issue_core.py` 的五类模板及字段白名单：主料、辅料、包装、海外问题需要图片，防错异常不要求图片。

## 前端规范

- 客户界面只使用业务语言，不展示动作 key、任务 ID、绝对路径、桥接、Python、调试口径或实现过程。
- 双端共享设计令牌、状态色、亮暗主题、键盘焦点、移动触控目标和 `prefers-reduced-motion` 规则。
- 页面滚动容器可以隐藏滚动条外观，但必须保留滚轮、触控板、触摸和键盘滚动能力；侧栏、顶栏和移动端底栏不随内容区滚动。
- 美术资源只承担背景、主视觉和空态；交互控件与业务文字使用 HTML/React，图片加载失败必须有 CSS fallback。
- 结构化业务结果优先在线展示，正式 Excel/PDF 报告仍可下载；可信度分析与核对提示属于结果投影的一部分。
- Web 权限入口和服务端接口使用同一角色矩阵；隐藏导航不能替代后端鉴权。

## 测试

以下命令在 `峰运通数据管理系统` 目录执行：

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe scripts\check_repository_hygiene.py
.\.venv\Scripts\python.exe scripts\check_complexity.py --base HEAD
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm --prefix web-app run build
npm --prefix tauri-app run build
cd tauri-app\src-tauri
cargo test
```

- 修改 `core/` 后运行相关合成数据测试和全量 Python 回归。
- 修改 Web 页面或 API 后运行 Web 构建，并按影响范围运行 `npm --prefix tauri-app run qa:web-smoke`。
- 修改 Tauri 页面、桥接或 sidecar 后运行 Tauri 构建、相关视觉/功能检查和 Rust 测试。
- 测试只使用合成 Excel 与临时目录；真实业务文件缺失时友好跳过，不把真实业务资料复制进仓库。
- 中文源码、注释和文档使用 UTF-8；提交前检查 Unicode 替换字符（`U+FFFD`）、异常 ASCII 问号和编码转换残留。

## 打包与部署

- Web 静态文件：`npm --prefix web-app run build`。
- Tauri 安装包：`npm --prefix tauri-app run tauri:build`；构建脚本先生成无控制台的 `FYTCoreBridge.exe`，再生成 MSI/NSIS。
- 三类交付包：`.\.venv\Scripts\python.exe scripts\build_deploy.py`；只构建 Linux 包时追加 `--linux-only`。
- Git 直接部署：公开仓库使用 `packaging/linux/deploy-from-git.sh`；脚本必须先克隆和构建候选版本，再复用 `install.sh` 的备份、切换、健康检查与回滚，不得在构建阶段停服或写入 `/var/lib/fyt-web`。
- Linux 增量补丁：`.\.venv\Scripts\python.exe scripts\build_linux_upgrade_patch.py`；补丁不得读取、覆盖或删除 `/var/lib/fyt-web`。
- Windows Web 包包含静态前端、主服务、任务桥接、Tkinter 控制台和 Cloudflare 客户端，不混入 Tauri 安装程序。
- Linux 服务安装到 `/opt/fyt/server`，配置位于 `/etc/fyt-web/fyt-web.env`，数据位于 `/var/lib/fyt-web`，备份位于 `/var/backups/fyt-web`。
- Windows 控制台与脚本必须使用 `pythonw.exe`、隐藏窗口和受控 PID；不得恢复会弹出命令窗口的启动方式。

## 文档与仓库安全

- 行为、接口、权限、模块、输出格式、打包或部署变化都同步 `峰运通数据管理系统/docs/项目全景-模块与实现.md`；本文和 `README.md` 只描述当前实现。
- 注释质量、文件规模、函数复杂度和嵌套深度等编码约束以 `docs/源码注释与编码风格规范.md` 为长期基线；阶段性计划文档只在仍有维护价值时保留，不得把历史实施状态当作当前约束。
- 不提交 `.venv`、`node_modules`、`dist`、`target`、`web-data`、可执行 sidecar、生成 schema、日志、缓存、备份、证书、私钥、Token 和真实业务数据。
- 源码包由 `scripts/build_deploy.py` 的根文件与目录白名单生成；本文件位于仓库根，并随源码包一起交付。
- 不提交或推送 Git，不发布 Release，不删除文件，不修改生产环境，除非用户明确授权。
