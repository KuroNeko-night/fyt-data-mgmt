#!/usr/bin/env bash
# Linux 部署管理脚本共用路径、安装检查、提权和端口读取逻辑。
#
# 所有管理脚本从这里取得同一组可覆盖路径，避免 status、backup、restart 等命令各自解释
# 环境变量。普通用户调用需要写系统状态的脚本时，会通过 sudo 重新执行并显式传递这些值，
# 不把调用者的完整环境泄露给 root 进程。

# 默认值必须与 install.sh 和 systemd 模板保持一致；部署到非标准目录时可在命令前覆盖。
FYT_SERVICE_NAME="${FYT_SERVICE_NAME:-fyt-web}"
FYT_INSTALL_DIR="${FYT_INSTALL_DIR:-/opt/fyt/server}"
FYT_CONFIG_DIR="${FYT_CONFIG_DIR:-/etc/fyt-web}"
FYT_DATA_DIR="${FYT_DATA_DIR:-${FYT_WEB_DATA:-/var/lib/fyt-web}}"
FYT_BACKUP_DIR="${FYT_BACKUP_DIR:-${BACKUP_DIR:-/var/backups/fyt-web}}"
FYT_ENV_FILE="${FYT_ENV_FILE:-$FYT_CONFIG_DIR/fyt-web.env}"

fyt_die() {
    # 错误统一写入 stderr，便于脚本调用方区分正常状态输出和失败诊断。
    printf '[错误] %s\n' "$*" >&2
    exit 1
}

fyt_require_install() {
    # 虚拟环境解释器与配置文件共同构成“已完成安装”的最低条件。
    [ -x "$FYT_INSTALL_DIR/.venv/bin/python" ] \
        || fyt_die "未找到已安装服务，请先执行：sudo bash install.sh"
    [ -f "$FYT_ENV_FILE" ] \
        || fyt_die "未找到运行配置：$FYT_ENV_FILE"
}

fyt_reexec_root() {
    # 用于脚本整体必须提权的场景；exec 保持最终退出码并避免额外父 shell 残留。
    local script="$1"
    shift
    if [ "$(id -u)" -eq 0 ]; then
        return 0
    fi
    command -v sudo >/dev/null 2>&1 || fyt_die "此操作需要 root 权限，且当前系统没有 sudo"
    # 仅转交已知部署变量，不继承可能影响 Python、pip 或动态库加载的任意用户环境。
    exec sudo env \
        FYT_SERVICE_NAME="$FYT_SERVICE_NAME" \
        FYT_INSTALL_DIR="$FYT_INSTALL_DIR" \
        FYT_CONFIG_DIR="$FYT_CONFIG_DIR" \
        FYT_DATA_DIR="$FYT_DATA_DIR" \
        FYT_BACKUP_DIR="$FYT_BACKUP_DIR" \
        FYT_ENV_FILE="$FYT_ENV_FILE" \
        bash "$script" "$@"
}

fyt_run_root() {
    # 用于只需对单条 systemctl/journalctl 命令提权的只读或短操作脚本。
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        fyt_die "此操作需要 root 权限，且当前系统没有 sudo"
    fi
}

fyt_read_port() {
    # systemd EnvironmentFile 允许双引号值；非法或缺失端口与服务端默认值 8787 对齐。
    local value
    value="$(sed -n 's/^FYT_WEB_PORT=//p' "$FYT_ENV_FILE" 2>/dev/null | tail -1)"
    value="${value#\"}"
    value="${value%\"}"
    case "$value" in
        ''|*[!0-9]*) printf '8787\n' ;;
        *) printf '%s\n' "$value" ;;
    esac
}
