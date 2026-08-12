#!/usr/bin/env bash
# 查看服务日志：logs.sh 为实时日志，logs.sh 100 为最近 100 行。
# 日志直接来自 systemd journal，不读取应用数据目录，也不创建额外日志副本。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
. "$DIR/common.sh"
fyt_reexec_root "$0" "$@"

if [ -n "${1:-}" ]; then
    # 数字参数选择有限历史行；无参数才进入持续跟随，适合交互式故障排查。
    [[ "$1" =~ ^[0-9]+$ ]] || fyt_die "日志行数必须是正整数"
    fyt_run_root journalctl -u "$FYT_SERVICE_NAME" -n "$1" --no-pager
else
    fyt_run_root journalctl -u "$FYT_SERVICE_NAME" -f
fi
