# 峰运通数据管理系统

面向峰运通内部使用的 Windows 桌面数据管理工具，将考勤填报、工时对账、到料明细、透视表制作四项日常工作集成到一个程序中，开箱即用，支持一键在线更新。

> Windows 桌面应用 · 兼容 Windows 7 SP1 及以上（64 位）· 无需预装 Python 或其他运行环境。

## 功能

- **考勤填报**：批量处理考勤数据并生成考勤填报表。
- **工时对账**：核对工时记录，快速定位差异。
- **到料明细**：整理、汇总到料明细数据。
- **透视表制作**：按所选维度一键生成 Excel 透视表。

## 下载与安装

1. 打开[最新发布页](https://github.com/ayahahruana67-ai/fyt-data-mgmt/releases/latest)
2. 在 **Assets** 中下载 `FYTDataMgmt_Setup_x.x.x.exe`
3. 双击运行，按向导完成安装；安装后会在桌面和开始菜单生成快捷方式
4. 若过程中弹出系统权限（UAC）提示，选择「是」

## 在线更新

程序内置在线更新。进入「关于 / 更新」页，点击 **检查更新**：

- 已是最新版本时会直接提示。
- 发现新版本时，按钮变为「下载并安装」，点击后自动下载安装包并显示进度，下载完成后启动安装向导，旧程序会自动关闭。按向导装完重新打开即可。

## 数据存放位置

程序的配置、导出结果、数据库与运行日志均保存在当前用户的文档目录下：

```
文档\峰运通数据管理系统\
```

该目录独立于程序安装目录，**卸载或更新程序都不会删除你的数据**。

## 系统要求

- 操作系统：Windows 7 SP1 / 8 / 10 / 11（64 位）
- 磁盘空间：约 250 MB 可用空间
- 无需联网即可使用；检查更新时才需要网络

## 版权

Copyright © 2026 重庆峰运通供应链管理公司. 保留所有权利（All Rights Reserved）。

本软件为重庆峰运通供应链管理公司内部专有软件，仅供授权范围内使用。未经许可，不得复制、分发、修改或用于其他用途。

---

## 开发与发布（维护者）

技术栈：Python 3.8 · PySide2(Qt 5.15) · openpyxl。打包用 PyInstaller，安装包用 Inno Setup。

**准备环境**

```bash
pip install -r requirements.txt
```

**本地运行**

```bash
python main.py
```

**打包**（产物在 `dist/`：绿色版目录 + `dist/installer/` 安装包）

```bash
python build.py               # 完整流程：绿色版 + 安装包
python build.py --no-installer  # 只出免安装的绿色版
```

**发布新版本**

1. 改 [`core/version.py`](core/version.py) 的 `VERSION`、`VERSION_TUPLE`（两者保持一致）、`BUILD_DATE`
2. `python build.py` 生成安装包
3. 编辑 `dist/installer/latest.json`：`version` 填新版本号，`url` 指向对应 tag 的安装包直链
4. 在 GitHub 新建 Release，tag 用 `vX.Y.Z`，把安装包 `.exe` 和 `latest.json` **一并上传**为 Assets
5. 客户端「检查更新」即会读取 `latest.json` 发现新版本

> 更多打包与更新机制细节见项目内文档与脚本注释。国内下载慢时可在 `core/version.py` 的 `DOWNLOAD_ACCEL_PREFIX` 填镜像前缀。


