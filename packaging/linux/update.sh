#!/usr/bin/env bash
# 新版升级入口：数据与程序分离后，可直接从新版解压目录重新安装。
# 本文件只打印安全操作顺序，不自动下载或替换任何文件，避免“update”命令误触生产环境。
set -euo pipefail

printf '%s\n' '[升级说明]'
printf '%s\n' '1. 上传并解压新的 Linux ZIP 包。'
printf '%s\n' '2. 进入新包的 ASCII 目录 fyt-server-linux-v<版本>。'
printf '%s\n' '3. 执行 sudo bash install.sh。'
printf '%s\n' '4. 安装器会先构建新环境，再停服备份、切换程序并启动。'
printf '%s\n' '5. 运行数据位于 /var/lib/fyt-web，不再跟随解压目录覆盖。'
