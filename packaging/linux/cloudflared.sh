#!/usr/bin/env bash
# ============================================================
# Cloudflare 公网隧道脚本（快速隧道，免账号免域名）
#
# 用法：
#   bash cloudflared.sh              前台启动（Ctrl+C 退出）
#   bash cloudflared.sh --daemon     后台启动，打印公网地址
#   bash cloudflared.sh stop         停止后台隧道
#   bash cloudflared.sh status       查看状态与当前公网地址
#
# 可选环境变量：
#   CLOUDFLARED_MIRROR  下载镜像前缀（默认 https://gh-proxy.com/，留空=直连 GitHub）
#   FYT_WEB_PORT        本机服务端口（默认从 fyt-web.env 读取，再默认 8787）
#
# 快速隧道地址由 Cloudflare 临时分配，进程停止或重新创建后可能变化。本脚本仅管理隧道
# 客户端进程，不修改 DNS、服务端配置和运行数据。后台模式把 PID、日志和最新地址写入
# 数据目录下的 logs，便于重启后判断旧 PID 是否仍有效；日志并不作为进程身份的唯一依据。
# ============================================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"  # 从安装目录加载通用路径与端口读取逻辑。
# shellcheck source=common.sh
. "$DIR/common.sh"
LOG_DIR="$FYT_DATA_DIR/logs"  # 运行日志不写入只读程序目录，随数据目录权限统一管理。
PID_FILE="$LOG_DIR/cloudflare-tunnel.pid"
LOG_FILE="$LOG_DIR/cloudflare-tunnel.log"
URL_FILE="$LOG_DIR/cloudflare-tunnel.url"
URL_PATTERN='https://[a-z0-9-]+\.trycloudflare\.com'  # 只接受官方快速隧道域名格式。
MIRROR="${CLOUDFLARED_MIRROR:-https://gh-proxy.com/}"

PORT="$(fyt_read_port)"

find_cloudflared() {
    # 优先使用 PATH 中的管理员安装版本，否则返回本脚本约定的系统级下载位置。
    command -v cloudflared 2>/dev/null || echo "/usr/local/bin/cloudflared"
}

ensure_cloudflared() {
    # 下载只在可执行文件缺失时发生；已有程序不会被“latest”静默覆盖。
    local bin
    bin="$(find_cloudflared)"
    [ -x "$bin" ] && return 0
    echo "[开始] 未找到 cloudflared，正在下载..."
    mkdir -p "$(dirname "$bin")"
    if [ -n "$MIRROR" ] && [ "$MIRROR" != "-" ]; then
        # 镜像值为“-”或空字符串时直连 GitHub，便于在不同网络环境中明确切换来源。
        curl -fL --max-time 300 "$MIRROR""https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$bin"
    else
        curl -fL --max-time 300 "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$bin"
    fi
    chmod +x "$bin"
    echo "[完成] cloudflared 已安装：$bin"
}

print_url() {
    # 取日志中最后一次地址，连接重试产生多个 URL 时展示最新分配结果。
    local url
    url="$(grep -oE "$URL_PATTERN" "$LOG_FILE" 2>/dev/null | tail -1 || true)"
    if [ -n "${url:-}" ]; then
        echo "公网地址：$url"
    else
        echo "[提示] 尚未获得公网地址，稍等片刻再执行：bash cloudflared.sh status"
    fi
}

start_daemon() {
    # 每次启动清空旧日志，避免 status 把上一进程的临时地址误认为当前地址。
    mkdir -p "$LOG_DIR"
    : > "$LOG_FILE"
    # cloudflared 只连接本机回环地址；公网入口不能借此代理到任意内网服务。
    nohup "$(find_cloudflared)" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"  # $! 是刚刚后台启动的 cloudflared PID，而不是 nohup/shell PID。
    echo "[启动] 隧道正在连接，等待分配公网地址..."
    # 只等待地址出现，不把二十秒内未分配视为进程失败；慢网络仍可稍后用 status 查看。
    for _ in $(seq 1 20); do
        if grep -qE "$URL_PATTERN" "$LOG_FILE" 2>/dev/null; then
            print_url
            return 0
        fi
        sleep 1
    done
    echo "[提示] 20 秒内未获得地址，请执行：bash cloudflared.sh status"
}

# 未提供子命令时以前台模式运行，exec 让 Ctrl+C 和退出码直接作用于 cloudflared。
case "${1:-}" in
    --daemon)
        ensure_cloudflared
        start_daemon
        ;;
    stop)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            # kill -0 只探测 PID 是否存在；真正停止时发送默认 TERM，允许客户端正常断开。
            kill "$(cat "$PID_FILE")"
            rm -f "$PID_FILE"
            echo "[完成] 隧道已停止"
        else
            echo "[提示] 隧道未在运行"
        fi
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "[运行中] PID：$(cat "$PID_FILE")"
            print_url
        else
            echo "[未运行] 隧道未在运行"
            [ -f "$LOG_FILE" ] && { echo "---- 最近日志 ----"; tail -5 "$LOG_FILE"; }
        fi
        ;;
    *)
        ensure_cloudflared
        echo "[启动] 公网隧道（本机 http://127.0.0.1:$PORT），等待地址..."
        exec "$(find_cloudflared)" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT"
        ;;
esac
