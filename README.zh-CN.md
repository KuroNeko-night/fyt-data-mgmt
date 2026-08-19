<div align="center">
  <img src="assets/logo.png" alt="峰运通数据管理系统 Logo" width="128" height="128" />
  <h1>峰运通数据管理系统</h1>
  <p>面向生产、采购、财务与现场管理的桌面端 + Web 数据工作台</p>
  <p>
    <a href="README.md">English</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10--3.13-3776AB?logo=python&logoColor=white" alt="Python 3.10-3.13" />
    <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=20232A" alt="React 19.2" />
    <img src="https://img.shields.io/badge/Vite-8.1-646CFF?logo=vite&logoColor=white" alt="Vite 8.1" />
    <img src="https://img.shields.io/badge/Tauri-2.11-FFC131?logo=tauri&logoColor=black" alt="Tauri 2.11" />
  </p>
  <p>
    <img src="https://img.shields.io/badge/Rust-stable-000000?logo=rust&logoColor=white" alt="Rust stable" />
    <img src="https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white" alt="SQLite" />
    <img src="https://img.shields.io/badge/Docker-optional-2496ED?logo=docker&logoColor=white" alt="Docker optional" />
    <img src="https://img.shields.io/badge/License-MIT-2EA44F" alt="MIT License" />
  </p>
</div>

> 把分散在 Excel、PDF、文件夹和人工步骤中的业务处理，整理成可复核、可追踪、可协作的统一工作流。

当前版本：`v1.3.0`

## 项目简介

峰运通数据管理系统是一套面向企业日常业务的数据工作台，覆盖考勤、到料、采购、对账、发票、生产资料、现场问题和日清管理等场景。

系统的核心流程是：上传资料 → 识别与分析 → 人工复核 → 在线查看结果 → 下载正式报告。业务处理使用上传文件的副本，默认不会直接修改原始文件。

系统支持三种使用方式：

- **Windows 桌面端**：适合个人或办公室电脑处理业务文件。
- **Web 端**：通过浏览器访问，适合局域网或企业内部多人协作。
- **移动端浏览器**：重点支持现场问题拍照、填写、查看和闭环。

## 功能地图

| 领域 | 主要功能 |
| --- | --- |
| 人事 | 考勤填报、考勤月度归档、工时对账 |
| 到料与生产 | 每日到料明细、送货计划、发运评审对比、生产资料管理 |
| 采购与供应商 | 采购对账、供应商批次表、采购计划导入、采购差异清单、对账单制作 |
| 采购与财务 | 采购汇总、采购对账、发票统计、票货匹配、金额大写 |
| 文件工具 | 批量重命名、文本处理、PDF 工具、Excel 工具、表格比对 |
| 日清与协作 | 日清看板、现场问题、事项与待办、任务中心、消息中心 |
| 数据治理 | 团队数据库、主数据学习、冲突确认、资料分类和回收站 |

适用的业务会在处理完成后直接展示关键指标、明细、差异、可信度和核对提示，同时保留正式 Excel 或 PDF 报告下载。

## 主要特点

### 统一的业务工作流

上传文件后，可以调整日期、容差、统计方式等人工参数；对于需要确认的业务，系统会先返回识别计划，再由人工选择和确认，最后生成正式结果。

### 在线结果与正式报告并存

业务结果优先在 Web 或桌面端直接展示，方便快速检查；需要归档、流转或继续处理时，仍可下载 Excel、PDF 等正式报告。

### 主数据持续治理

管理员可以上传新的业务表格，让系统学习材料、供应商和字段之间的对应关系。发现冲突时，系统先提示人工确认，不会直接覆盖已经确认的正式数据。

### 移动端现场闭环

现场问题支持图片、文本、负责人、备注和问题状态，用户可以编辑已发布问题、补充解决信息，并按日期导出后续处理表格。

## 使用流程

1. 打开桌面端，或使用浏览器进入 Web 端。
2. 登录账号并选择业务功能。
3. 上传表格、PDF 或图片资料。
4. 根据页面提示调整人工参数。
5. 检查识别结果、差异、可信度和复核内容。
6. 确认后在线查看结果或下载正式报告。

部分业务采用“先分析、后确认”的两阶段流程，避免自动识别结果未经检查就进入正式文件。

## 账号与权限

Web 端账号注册后需要管理员审核，系统提供三种角色：

| 角色 | 主要权限 |
| --- | --- |
| 业务成员 | 使用工作台、业务模块、任务与消息功能；查看和提交现场问题 |
| 班组长 | 包含业务成员能力，并可使用团队数据库，维护自己发布的现场问题 |
| 管理员 | 查看日清看板和报表中心，审核账号、调整角色、维护主数据及管理全部现场问题 |

权限不仅控制页面入口，服务端也会再次校验账号角色、任务归属和资料所属关系。

## 技术栈与运行基线

| 层级 | 技术 |
| --- | --- |
| 共享业务核心 | Python 3.10–3.13、Excel/PDF 文件处理、SQLite |
| Web 前端 | React 19.2、TypeScript 7、Vite 8.1 |
| 桌面端 | Tauri 2.11、Rust stable、React |
| Web 服务 | Python 标准库 HTTP 服务、SQLite、systemd |
| 可选部署 | Docker Compose、Caddy 反向代理、Cloudflare Origin CA |

## 数据与安全

- 账号、上传文件、任务结果和个人配置按用户隔离。
- 注册账号必须经过管理员审核，密码需满足系统安全要求。
- 修改密码、撤销设备或重置账号后，相关登录会话会自动失效。
- 管理员可以管理回收站、备份和恢复，业务结果不会无限增长。
- 公网部署应使用 HTTPS，并由管理员配置域名、反向代理和访问控制。
- 管理员密码、证书私钥、Token、账号数据库和真实业务资料不应出现在截图或公开问题中。

## 支持的文件

- Excel：`.xlsx`、`.xlsm`、`.xls`、`.csv`
- PDF：发票识别、合并、拆分、提取页面等
- 图片：现场问题上传，支持一条问题附带多张图片

不同业务模块支持的文件类型可能不同，实际选择文件时以页面提示为准。

## 部署指令

### Linux：从公开 Git 仓库部署

```bash
sudo dnf install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/KuroNeko-night/fyt-data-mgmt/main/packaging/linux/deploy-from-git.sh | sudo bash
```

### Linux：从部署包安装

```bash
sudo unzip fyt-server-linux-v1.3.0.zip -d /opt/fyt
cd /opt/fyt/fyt-server-linux-v1.3.0
sudo bash install.sh
```

### Docker

```bash
umask 077
mkdir -p secrets
{ printf 'Aa1'; openssl rand -hex 16; } > secrets/admin-password.local.txt
FYT_ADMIN_PASSWORD_FILE=../secrets/admin-password.local.txt docker compose -f docker/docker-compose.yml up -d --build
```

### Windows：构建服务端交付包

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe scripts\build_deploy.py
```

### Tauri：构建桌面安装包

```powershell
npm --prefix tauri-app ci
npm --prefix tauri-app run tauri:build
```

## 常见问题

### 上传文件后会修改原文件吗？

不会。系统处理上传文件的副本，生成的结果会保存为新文件。

### 为什么有些功能需要人工复核？

业务表格可能存在合并单元格、非固定表头、人工备注和历史模板差异。人工复核用于确认系统识别出的批次、供应商、日期和匹配关系，避免错误结果被直接采用。

### Web 端可以在手机上使用吗？

可以。大部分页面支持移动端浏览，其中现场问题功能针对手机拍照和竖屏填写进行了重点适配。

### 忘记密码怎么办？

普通用户联系管理员重置密码。管理员账号使用部署环境提供的受控密码重置入口，不要在公开页面发送旧密码、数据库或私钥。

## 许可证

本项目采用 [MIT License](LICENSE)。

Copyright © 2026 KuroNeko-night
