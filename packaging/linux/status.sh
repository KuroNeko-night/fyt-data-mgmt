#!/usr/bin/env bash
# 查看服务状态并执行本机应用级健康检查。
# systemd 活跃只代表进程存在，后续 HTTP 检查还会确认 Web 服务能返回业务健康标记。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
. "$DIR/common.sh"
fyt_reexec_root "$0" "$@"
fyt_require_install
PORT="$(fyt_read_port)"  # 与 EnvironmentFile 使用同一端口，避免只检查默认 8787。

printf '==== 服务状态 ====\n'
# 状态输出截取前二十行，避免历史日志淹没启停原因；失败仍继续执行更明确的健康检查。
fyt_run_root systemctl status "$FYT_SERVICE_NAME" --no-pager -l | head -20 || true
printf '\n==== 开机启动 ====\n'
fyt_run_root systemctl is-enabled "$FYT_SERVICE_NAME" || true
printf '\n==== 健康检查 http://127.0.0.1:%s/api/health ====\n' "$PORT"
if "$FYT_INSTALL_DIR/.venv/bin/python" - "$PORT" <<'PY'
import sys
import urllib.request

port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
    body = response.read().decode("utf-8")
    # 同时验证状态码和应用标记，端口被其他进程占用时不会误报为峰运通正常。
    if response.status != 200 or '"status": "ok"' not in body:
        raise SystemExit(1)
    print(body)
PY
then
    printf '[正常] 服务可以访问\n'
else
    printf '[异常] 服务无响应，请查看：sudo bash %s/logs.sh 100\n' "$FYT_INSTALL_DIR"
    exit 1
fi
