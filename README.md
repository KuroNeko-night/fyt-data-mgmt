# 峰运通数据管理系统

峰运通数据管理系统是一套面向企业内部业务的桌面端与 Web 数据工作台。它把考勤、到料、采购、对账、主数据、现场问题、日清看板和文件工具放在统一的工作流中，并让 Windows 桌面端与浏览器端复用同一套 Python 业务核心。

当前版本：`v1.3.0`（版本唯一来源：`core/version.py`）

## 适用场景

- **桌面端**：适合个人或办公室电脑离线处理业务表格，使用 Tauri 安装包运行。
- **Web 端**：适合局域网协作；账号注册由管理员审核，任务、资料和输出按账号隔离。
- **服务端**：Windows 服务端包适合快速部署，Linux 服务端包适合 systemd 长期运行，也可以在 Caddy/Nginx 后面提供 HTTPS。

## 功能概览

### 业务模块

| 分组 | 功能 |
| --- | --- |
| 人事 | 考勤填报、考勤月度归档、工时对账 |
| 业务 | 每日到料明细、销售透视、采购对账、送货计划、供应商批次表、采购计划导入、采购差异清单、对账单制作 |
| 财务 | 发票统计、票货匹配、金额大写 |
| 工具 | 批量重命名、文本工具、PDF 工具、Excel 工具、表格比对 |

### 协作与管理

- **工作台**：查看任务状态、待处理事项、最近任务和处理趋势。
- **现场问题**：移动端优先提交图片和问题信息；按五类标准模板校验、编辑、闭环和导出。
- **日清看板**：管理员按业务日期查看到料、考勤、生产计划、安全检查、现场问题、事项与待办。
- **数据库**：班组长和管理员上传、下载、分类和维护团队资料，列表记录上传者和修改时间。
- **主数据治理**：管理员上传表格学习供应商与材料对应关系，冲突先进入待治理区，确认后再合并正式主数据库。
- **任务中心**：查看进度、日志、结果版本，支持取消、重试、在线预览和下载。
- **消息中心**：接收全局公告与定向消息，支持未读筛选和阅读状态。
- **系统管理**：管理员审核账号、调整角色、维护资料、发布消息、管理回收站和备份。

## 角色权限

系统角色只有业务成员、班组长和管理员。前端隐藏入口不能替代服务端鉴权，所有接口都会再次检查角色与资源所属关系。

| 功能 | 业务成员 | 班组长 | 管理员 |
| --- | --- | --- | --- |
| 工作台、业务模块、任务中心、消息中心、账号安全 | 可用 | 可用 | 可用 |
| 现场问题查看与提交 | 可用 | 可用 | 可用 |
| 已发布现场问题维护 | 仅自己的草稿 | 可编辑、闭环、删除自己发布的内容 | 可维护全部内容 |
| 数据库、批次跟踪 | 不可用 | 可用 | 可用 |
| 日清看板、报表中心、系统管理 | 不可用 | 不可用 | 可用 |

新账号注册后必须等待管理员审核。管理员可以把已审核账号调整为业务成员、班组长或管理员；内置管理员、当前账号和最后一名管理员受到保护。

## 系统架构

```text
Tauri React ──> Rust 白名单命令 ──> core.tauri_bridge ──> core/*

Web React ────> 同源 /api ────────> web_server.py + web_backend
                                      └─> 任务桥接 ──> core.tauri_bridge ──> core/*
```

- `core/` 是业务算法、主数据、路径、缓存、任务历史和桥接协议的唯一事实源，不导入桌面 UI。
- `web_server.py` 是兼容启动入口和依赖组合根；实际 HTTP 协议、路由、数据库、领域服务和任务执行位于 `web_backend/`。
- `business_result_core.py` 统一把业务结果投影成标题、指标、明细、可信度和核对提示，桌面端与 Web 端都使用同一投影。
- Web 长任务以持久化任务 ID 运行在独立 Python 子进程中；上传句柄、任务、缓存、输出和运行目录都按用户隔离。
- SQLite 保存账号、会话、审核、任务、资料、日清、消息、现场问题和管理记录；运行数据不属于源码。

## 目录结构

```text
峰运通数据管理系统/
├─ core/               纯业务逻辑、主数据、缓存、任务历史和桥接
├─ web_backend/        Web 配置、HTTP、数据库、领域服务和任务运行器
├─ web_server.py       Web 兼容启动入口
├─ web_control_gui.py  Web 服务与 Cloudflare Tunnel 控制台
├─ web-app/            React/Vite Web 前端
├─ tauri-app/          React/Vite/Tauri 桌面端
├─ design-system/      双端设计令牌
├─ assets/             品牌和已验收美术资源
├─ packaging/          Tauri sidecar、Windows/Linux 部署脚本
├─ scripts/            构建、打包、升级补丁和质量检查
├─ tests/              unittest 合成数据回归
└─ docs/               当前实现与维护文档
```

## 环境要求

### Windows 开发环境

- Windows 10/11 64 位。
- Python 3.13，建议通过 `py -3.13` 创建虚拟环境。
- Node.js 与 npm，使用与 Vite 8 兼容的 LTS 版本。
- Rust stable MSVC、Visual Studio C++ 构建工具和 WebView2；只有构建 Tauri 安装包时需要。
- PowerShell 5.1 或更高版本。

### Linux 服务端

- x86_64 Linux；部署脚本已覆盖 Alibaba Cloud Linux 3、Ubuntu、Debian 和 CentOS Stream 等 systemd 系统。
- Python 3.10～3.13。安装器会创建项目私有虚拟环境，不替换系统 Python。
- `systemd`、`sudo`、`unzip`、`tar`、`curl`。

## Windows 源码运行

以下命令在 `峰运通数据管理系统` 目录执行。

### 安装依赖

```powershell
.\setup-modern.ps1
npm --prefix web-app ci
npm --prefix tauri-app ci
```

`setup-modern.ps1` 只安装 `requirements.txt` 中锁定的 Python 依赖，不修改系统 Python。中文控制台建议先设置：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

### 启动 Web 服务

先构建静态前端，再启动 Web 服务：

```powershell
npm --prefix web-app run build
.\run-web-gui.ps1
```

图形控制台可以设置端口、启动或关闭 Web 服务、启动或关闭 Cloudflare Tunnel，并显示局域网地址和公网地址。首次创建数据库时，密码通过控制台安全输入；管理员凭据不会写入登录页、帮助文案或普通运行日志。

需要前台查看服务日志时使用：

```powershell
.\run-web.ps1 -Foreground
```

默认监听 `0.0.0.0:8787`，本机地址为 `http://127.0.0.1:8787/`，局域网用户访问 `http://本机IPv4地址:8787/`。首次访问前请在 Windows 防火墙放行对应 TCP 端口。常规启停优先使用图形控制台；由隧道脚本启动的 Web 服务和隧道可用以下入口一起关闭：

```powershell
.\stop-web-tunnel.ps1
```

### 管理员密码

系统初始化会创建受保护的管理员账号；账号信息不在登录页面、帮助文案或普通日志中展示。管理员密码必须是至少 10 位且同时包含字母和数字的强密码。

忘记密码时先停止服务，再运行：

```powershell
.\reset-web-admin-password.ps1
```

脚本会以安全输入读取新密码，复用服务端的哈希实现，不把密码写入脚本或配置文件。

### 启动 Tauri 桌面端

```powershell
cd tauri-app
npm run tauri -- dev --no-watch
```

桌面端开发模式通过 Rust 白名单调用 `core.tauri_bridge`。正式桌面安装包使用无控制台的 sidecar，不需要单独启动 Python 服务。

## Windows 服务端交付包

使用 `scripts/build_deploy.py` 生成的 Windows 包是免安装 Python 的服务端整合包，包含静态前端、任务桥接、Tkinter 服务控制台和 Cloudflare 客户端。

1. 解压包到不含重要业务数据的目录。
2. 双击服务控制台或启动脚本。
3. 首次初始化时在控制台安全设置管理员密码。
4. 浏览器访问 `http://127.0.0.1:8787/` 或局域网地址。

升级时先停止服务并备份包内 `web-data/`，再替换程序文件；不要覆盖 `web-data/`。Windows 包不包含 Tauri 安装程序。

## Linux 一键部署

Linux 包目录名和正式安装路径使用 ASCII，包本身可以从中文目录或 `/root` 解压。以下示例适用于新包目录：

```bash
sudo mkdir -p /opt/fyt
sudo unzip fyt-server-linux-v1.3.0.zip -d /opt/fyt
cd /opt/fyt/fyt-server-linux-v1.3.0
sudo bash install.sh
```

安装器会创建低权限 `fyt-web` 服务账号、项目私有虚拟环境、SQLite 数据目录和 systemd 服务，并执行本机健康检查。首次建库时可通过环境变量显式提供密码：

```bash
sudo env FYT_ADMIN_PASSWORD='请替换为强密码' bash install.sh
```

如果没有提供，安装器会生成一次性随机管理员密码并在安装过程显示；请立即记录并登录后修改。密码不会写入发布包。生产环境建议使用密钥管理或受保护的部署终端，不要把密码写进历史脚本。

固定目录如下：

| 内容 | 路径 |
| --- | --- |
| 程序与虚拟环境 | `/opt/fyt/server` |
| 服务配置 | `/etc/fyt-web/fyt-web.env` |
| 账号、上传、任务和输出 | `/var/lib/fyt-web` |
| 安装备份 | `/var/backups/fyt-web` |
| systemd 服务 | `fyt-web.service` |

常用运维命令：

```bash
sudo bash /opt/fyt/server/status.sh
sudo bash /opt/fyt/server/restart.sh
sudo bash /opt/fyt/server/stop.sh
sudo bash /opt/fyt/server/logs.sh 100
sudo bash /opt/fyt/server/backup.sh
```

升级新版时重新解压并执行 `sudo bash install.sh`。安装器会先备份程序和配置，再切换版本；不会覆盖 `/var/lib/fyt-web`。升级失败或健康检查失败时会回滚程序和服务状态。

## HTTPS 与公网访问

正式公网访问建议采用以下任一方式：

1. Caddy/Nginx 监听 80/443，反向代理到 `127.0.0.1:8787`，由代理负责证书和 HTTPS。
2. Cloudflare Named Tunnel 连接到本机 Web 服务，域名路由和 Tunnel 服务由 Cloudflare 管理。

临时 Quick Tunnel 适合测试，不适合作为固定入口；每次重启或重新建立连接都可能更换 `trycloudflare.com` 地址。无论使用代理还是 Tunnel，都应让 Web 服务只监听回环地址，并在 Cloudflare、反向代理和应用层分别配置访问控制。

Linux 包随附：

- `cloudflared.sh`：临时 Tunnel 的前台/后台启动、停止和状态查看。
- `cloudflared-named.sh`：授权、创建固定 Tunnel、绑定域名并可注册 systemd 服务。

不要把 Tunnel token、证书私钥、管理员密码或真实 `web-data` 放进源码包、Git 仓库或截图。

## Docker 运行与 GitHub 同步

项目提供多阶段 `Dockerfile` 和 `docker-compose.yml`。容器只运行 Web 服务，业务数据通过 `FYT_DATA_DIR` 挂载到 `/data`，不会写入镜像层。

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory secrets -Force
[System.IO.File]::WriteAllText(
  (Join-Path (Resolve-Path secrets) "admin-password.txt"),
  "请替换为至少10位且包含字母和数字的强密码",
  [System.Text.UTF8Encoding]::new($false)
)
docker compose up -d --build
docker compose ps
```

默认端口只绑定本机 `127.0.0.1:8787`，适合放在 Caddy/Nginx 或 Cloudflare Tunnel 后面。局域网直连时把 `.env` 中的 `FYT_WEB_BIND` 改为 `0.0.0.0`。详细说明见 `docs/docker与github同步.md`。

源码同步入口：

```powershell
.\scripts\sync-github.ps1 -Message "说明本次修改" -Push
```

脚本默认关联 `https://github.com/KuroNeko-night/fyt-data-mgmt.git`，会拒绝提交 `web-data`、`docker-data`、数据库、日志、证书、压缩包、构建产物和本地依赖。Linux/macOS 使用 `bash scripts/sync-github.sh --message "说明本次修改" --push`。提交前请先配置 GitHub SSH 或 Personal Access Token；不要把凭据写入项目。

## 配置项

配置统一通过环境变量或 Linux 的 `/etc/fyt-web/fyt-web.env` 提供。常用项如下：

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `FYT_WEB_HOST` | `0.0.0.0` | Web 监听地址；反向代理或 Tunnel 建议设为 `127.0.0.1` |
| `FYT_WEB_PORT` | `8787` | Web 服务端口 |
| `FYT_WEB_DATA` | 项目下 `web-data` | Web 数据根目录；Linux 安装器会改为 `/var/lib/fyt-web` |
| `FYT_ADMIN_PASSWORD` | 首次安装时生成或显式提供 | 仅用于首次初始化管理员密码，不用于覆盖既有密码 |
| `FYT_BUSINESS_TZ_OFFSET` | `8` | 日清业务时区偏移，默认 UTC+8 |
| `FYT_OUTPUT_RETENTION_COUNT` | `20` | 每个账号保留的最近结果版本数量 |
| `FYT_TRASH_RETENTION_DAYS` | `30` | 回收站自动清理天数 |
| `FYT_AUTO_BACKUP_KEEP` | `7` | 自动备份保留份数 |
| `FYT_LIBRARY_USER_QUOTA_BYTES` | `2 GiB` | 单账号数据库文件配额 |
| `FYT_NOTIFY_WEBHOOK_URL` | 空 | 可选的企业微信/钉钉兼容文本通知地址 |

JSON 请求体、普通上传、主数据导入和现场图片还有独立大小限制，具体以 `web_backend/config.py` 当前值为准。

## 数据、备份与恢复

- 桌面端默认把配置和业务输出放在当前用户文档目录的“峰运通数据管理系统”目录。
- Web 源码运行默认使用项目下的 `web-data`；部署时建议通过 `FYT_WEB_DATA` 与程序目录分离。
- Web 结果默认只保留最近 20 次；超出部分进入回收站，回收站默认保留 30 天。
- Linux `backup.sh` 会一致性备份账号数据库、上传资料、任务结果、回收站和服务配置，并生成 SHA-256 校验文件。
- 恢复前必须停止服务并验证备份校验值；恢复完成后应重新检查 `/api/health`，服务端会撤销已有会话。
- 任何升级、迁移或恢复前都应先保留一份可离线读取的备份。

## 测试与质量检查

以下命令在项目根目录执行：

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe scripts\check_repository_hygiene.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm --prefix web-app run build
npm --prefix tauri-app run build
cd tauri-app\src-tauri
cargo test
```

按改动范围还可以运行：

```powershell
npm --prefix tauri-app run qa:visual
npm --prefix tauri-app run qa:functional
npm --prefix tauri-app run qa:web-smoke
```

部署包冒烟检查：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_deploy_package.py
```

测试使用合成 Excel 和临时目录。不要把真实业务资料、账号数据库、日志、缓存或备份复制进仓库。

## 打包与发布

### 构建三类服务端交付物

先构建 Web 静态文件，再执行：

```powershell
npm --prefix web-app run build
.\.venv\Scripts\python.exe scripts\build_deploy.py
```

产物位于 `dist/`：

- `峰运通数据管理系统_源码_v<版本>.zip`：纯净源码包，不含运行数据和可执行文件。
- `峰运通服务端_windows_v<版本>.zip`：Windows Web 服务包，含 Cloudflare 客户端。
- `fyt-server-linux-v<版本>.zip`：Linux 一键部署包。

只构建 Linux 包可使用：

```powershell
.\.venv\Scripts\python.exe scripts\build_deploy.py --linux-only
```

### 构建 Linux 增量补丁

```powershell
.\.venv\Scripts\python.exe scripts\build_linux_upgrade_patch.py
```

补丁只包含 `web_server.py`、`web_backend/`、`core/*.py`、`web-app/dist`、依赖清单和升级脚本，不读取、不复制、不删除或覆盖 `/var/lib/fyt-web`。

### 版本发布

1. 只修改 `core/version.py` 的 `VERSION`、`VERSION_TUPLE` 和 `BUILD_DATE`。
2. 运行 `node scripts/release.mjs` 同步 Web、Tauri 和 Cargo 版本。
3. 运行双端构建、Python 回归和对应部署检查。
4. 运行 `npm --prefix tauri-app run tauri:build` 生成 MSI/NSIS。
5. 发布包、更新清单和校验值经人工核对后再交付。

## 安全与维护约束

- 不在登录页、README、日志、截图或提交记录中写入管理员密码、Token、证书私钥或内部公网地址。
- 不把 `web-data`、`.venv`、`node_modules`、`dist`、`target`、sidecar、数据库、日志、缓存、备份和真实业务数据提交到 Git。
- 业务算法只维护在 `core/`；Web 和 Tauri 通过白名单、桥接协议和结构化结果调用，不在前端复制 Excel 解析逻辑。
- 修改权限、接口、数据目录、输出格式、部署脚本或模块边界时，同步更新 `docs/项目全景-模块与实现.md` 和本 README。
- 代码注释优先说明业务不变量、事务顺序、路径边界、兼容原因和失败回滚；不要在客户界面暴露动作 key、任务 ID、绝对路径、Python 或调试过程。

## 相关文档

- [项目全景：模块与实现](docs/项目全景-模块与实现.md)
- [仓库维护与目录规范](docs/仓库维护与目录规范.md)
- [Web 前端说明](web-app/README.md)
- [设计令牌说明](design-system/README.md)
- [MIT License](LICENSE)

## 许可证

本项目采用 [MIT License](LICENSE)。Copyright © 2026 KuroNeko-night。
