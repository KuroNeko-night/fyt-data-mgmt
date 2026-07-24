# 峰运通 Web 入口

这是面向局域网的浏览器入口，前端由 Vite 构建，服务端使用 Python 标准库托管静态文件并提供 SQLite 账号服务。

## 启动

在 `峰运通数据管理系统` 目录执行：

```powershell
npm --prefix web-app install
npm --prefix web-app run build
.\run-web.ps1
```

也可以直接启动图形控制台，快速设置端口并启动/关闭服务：

```powershell
.\run-web-gui.ps1
```

控制台关闭窗口时会询问是否同时停止由它启动的服务；选择“否”可让 Web 服务继续在后台运行。

局域网其他电脑访问本机 IPv4 地址，例如 `http://192.168.1.25:8787/`。Windows 防火墙需要允许 TCP `8787` 入站。

## 账号规则

- 首次启动自动创建管理员：`admin` / `admin123456`。
- 可通过 `$env:FYT_ADMIN_PASSWORD` 或 `-AdminPassword` 在首次初始化前设置管理员密码。
- 新用户注册后状态为“待审核”，管理员在“账号审核”页面通过或拒绝。
- 密码使用 PBKDF2-HMAC-SHA256 加盐保存，会话令牌保存于 SQLite，默认有效期 7 天。
- 数据库默认位于 `web-data/accounts.sqlite3`，可用 `FYT_WEB_DATA` 指定其他目录。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FYT_WEB_HOST` | `0.0.0.0` | 监听地址，局域网服务保持默认值 |
| `FYT_WEB_PORT` | `8787` | HTTP 端口 |
| `FYT_ADMIN_PASSWORD` | `admin123456` | 仅首次创建管理员时读取 |
| `FYT_WEB_DATA` | `web-data` | SQLite 数据目录 |

## 业务处理

业务模块已经通过同一套 `core.tauri_bridge` 接入 Web：浏览器先把文件上传到当前账号的隔离工作区，服务端以独立 Python 进程执行桥接动作，再通过任务接口返回状态、进度、日志和结果下载链接。支持考勤、工时对账、到料、销售透视、采购对账、送货计划、数据库导入、发票统计、批量重命名、文本、PDF、Excel、表格比对和金额大写。

- `POST /api/files/upload`：上传文件并返回账号隔离句柄。
- `POST /api/jobs`：提交白名单业务任务。
- `GET /api/jobs/<id>`：读取任务状态、日志、结果和下载列表。
- `POST /api/jobs/<id>/cancel`：终止正在运行的 Python 核心进程。
- `GET /api/jobs/<id>/files/<index>`：带会话鉴权下载结果文件。

上传文件限制为单个 200 MB；服务重启时运行中的任务标记为“已中断”，不向其他账号暴露文件或任务。
