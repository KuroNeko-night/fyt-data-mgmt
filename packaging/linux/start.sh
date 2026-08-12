#!/usr/bin/env bash
# 启动峰运通 Web 服务。
# 整体提权后先验证安装完整性，再交由 systemd 管理；不直接运行 Python 后台进程。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
. "$DIR/common.sh"
fyt_reexec_root "$0" "$@"  # 普通用户通过 sudo 重新执行，后续命令处于同一权限上下文。
fyt_require_install
fyt_run_root systemctl start "$FYT_SERVICE_NAME"
printf '[完成] 服务已启动（%s）\n' "$FYT_SERVICE_NAME"
