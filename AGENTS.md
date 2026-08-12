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

```text
峰运通数据管理系统/
├─ core/               纯业务逻辑、主数据、路径、缓存、任务历史和桥接
├─ web_backend/        Web 配置、HTTP、数据库、领域服务和任务运行器
├─ web_server.py       Web 兼容启动入口和组合根
├─ web_control_gui.py  Web 服务与 Cloudflare Tunnel 控制台
├─ tauri-app/          React/Vite/Tauri 桌面端
├─ web-app/            React/Vite Web 前端
├─ design-system/      双端设计令牌
├─ assets/             品牌与已验收美术资源
├─ packaging/          Tauri sidecar、Windows/Linux 部署和升级脚本
├─ scripts/            构建、发布、同步、打包和质量检查
├─ tests/              unittest 合成数据回归
└─ docs/               当前实现与维护文档
```

Web 请求链路为：

```text
Web React -> 同源 /api -> web_backend/http -> services/tasks -> core.tauri_bridge -> core/*
```

Tauri 请求链路为：

```text
Tauri React -> Rust 白名单命令 -> core.tauri_bridge -> core/*
```

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
- Linux 增量补丁：`.\.venv\Scripts\python.exe scripts\build_linux_upgrade_patch.py`；补丁不得读取、覆盖或删除 `/var/lib/fyt-web`。
- Windows Web 包包含静态前端、主服务、任务桥接、Tkinter 控制台和 Cloudflare 客户端，不混入 Tauri 安装程序。
- Linux 服务安装到 `/opt/fyt/server`，配置位于 `/etc/fyt-web/fyt-web.env`，数据位于 `/var/lib/fyt-web`，备份位于 `/var/backups/fyt-web`。
- Windows 控制台与脚本必须使用 `pythonw.exe`、隐藏窗口和受控 PID；不得恢复会弹出命令窗口的启动方式。

## 文档与仓库安全

- 行为、接口、权限、模块、输出格式、打包或部署变化都同步 `峰运通数据管理系统/docs/项目全景-模块与实现.md`；本文和 `README.md` 只描述当前实现。
- 不提交 `.venv`、`node_modules`、`dist`、`target`、`web-data`、可执行 sidecar、生成 schema、日志、缓存、备份、证书、私钥、Token 和真实业务数据。
- 源码包由 `scripts/build_deploy.py` 的根文件与目录白名单生成；本文件位于仓库根，并随源码包一起交付。
- 不提交或推送 Git，不发布 Release，不删除文件，不修改生产环境，除非用户明确授权。
