#!/usr/bin/env bash
# 停止峰运通 Web 服务。
# 停止动作不要求程序目录完整，便于安装损坏时仍能关闭现有 systemd 服务。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
. "$DIR/common.sh"
fyt_reexec_root "$0" "$@"  # 使用 systemctl 正常停止，遵守单元文件中的 TimeoutStopSec。
fyt_run_root systemctl stop "$FYT_SERVICE_NAME"
printf '[完成] 服务已停止（%s）\n' "$FYT_SERVICE_NAME"
