# CLAUDE.md：峰运通数据管理系统

本仓库当前版本为 v1.3.0。正式入口只有 Tauri 桌面端和局域网 Web 端；旧 `main.py + ui/` 业务入口已经删除。`web_control_gui.py` 使用 Python 标准库 Tkinter 管理服务启停。

## 工作约束

- 回复、注释和界面文案使用中文。
- 基准环境为 Windows 10/11、Python 3.13、React 19、Vite 8、Tauri 2、Rust stable MSVC。
- Python 依赖只在 `requirements.txt` 维护；Node 依赖分别锁在两个 `package-lock.json`，Rust 依赖锁在 `Cargo.lock`。
- `core/` 是唯一业务事实源，不得导入桌面 UI 库、不得弹窗、不得复制业务算法到 Rust 或 React。
- Windows 控制台可能是 GBK，脚本输出使用 `[完成]` 等 GBK 安全文字；测试设置 `PYTHONIOENCODING=utf-8`。

## 当前结构

```text
core/              纯 Python 业务与共享基建
tauri-app/         Tauri 桌面端及 Rust 命令层
web-app/           局域网 React 前端
web_server.py      Web 登录、审核、任务和下载 API
web_control_gui.py Web 服务启停控制台
packaging/         Tauri Python sidecar 打包规格
tests/             core、桥接、Web 和控制台测试
assets/            共用图标与 Logo
```

## Core 约定

每个业务模块对外提供 `run(..., out_dir=None, log=None) -> dict`；未传输出目录时调用：

```python
st = settings.get_settings()
out_dir = paths.resolve_output_dir("feature", **st.output_kwargs())
```

- `log(str)` 和可选 `progress(int)` 只报告状态。
- 读取公式结果前使用 `warn_if_uncached`，避免 openpyxl `data_only=True` 得到空值。
- 大表顺序扫描优先使用 `load_data_only_stream()`，需要样式或随机写入时不能使用。
- 持久化 JSON 的读改写使用 `storage_lock.file_lock` 和临时文件原子替换。
- Web 输出、缓存和上传必须按用户隔离。

## 前端与桥接

- Tauri：React 调用 Rust `bridge_request`，Rust 通过 stdin/stdout 调用 `core.tauri_bridge`。
- Web：React 调用同源 `/api`，`web_server.py` 在独立 Python 子进程中调用同一 bridge。
- 新动作必须加入 bridge 白名单，路径参数先校验，返回值保证 JSON 安全。
- 长任务必须带 `request_id`，支持进度、日志和取消；人工复核先准备 plan，再提交 choices。
- 默认管理员凭据不得显示在登录页，生产首次启动必须通过 `FYT_ADMIN_PASSWORD` 覆盖。

## 版本与打包

- 单一运行时版本源：`core/version.py`。
- 发布时同步 Tauri/Web 的 `package.json` 和锁文件，以及 `Cargo.toml`、`Cargo.lock`、`tauri.conf.json`。
- Tauri 安装包：`npm --prefix tauri-app run tauri:build`。
- Web 静态包：`npm --prefix web-app run build`。
- sidecar：`packaging/tauri_bridge_entry.py` + `packaging/tauri_bridge.spec`，只收集业务核心和必要表格依赖。

## 验证

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm --prefix web-app run build
npm --prefix tauri-app run build
cd tauri-app\src-tauri
cargo test
```

## 文档与安全

- 每次代码改动同步 `docs/项目全景-模块与实现.md`。
- 不提交 `.venv`、`node_modules`、`dist`、`target`、`web-data`、生成 sidecar、schema、日志或真实业务文件。
- 删除文件、发布 Release、改生产或上传外部系统前必须获得用户明确授权。
