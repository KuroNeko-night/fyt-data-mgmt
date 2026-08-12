#!/usr/bin/env bash
# 重启峰运通 Web 服务。
# 只重启已注册的 systemd 单元，不重建虚拟环境、不修改配置和运行数据。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
. "$DIR/common.sh"
fyt_reexec_root "$0" "$@"
fyt_require_install  # 在 systemctl 操作前给出比“ExecStart 不存在”更直观的安装错误。
fyt_run_root systemctl restart "$FYT_SERVICE_NAME"
printf '[完成] 服务已重启（%s）\n' "$FYT_SERVICE_NAME"
