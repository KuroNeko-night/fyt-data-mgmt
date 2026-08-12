#!/usr/bin/env bash
# 峰运通数据管理系统 Linux 增量升级脚本。
#
# 脚本只替换 /opt/fyt/server 下的服务端源码、依赖清单和 Web 静态资源。运行数据默认位于
# /var/lib/fyt-web，不在备份列表、暂存目录或删除目标中。升级前先验证补丁树和哈希，再把
# 当前程序归档；应用后执行 Python 编译与 HTTP 健康检查，任一步失败都恢复旧程序。
#
# 环境变量可以覆盖安装目录、配置、备份和服务名，但路径与服务名仍需通过下方安全校验。
# 使用独立暂存目录可避免把半复制状态直接暴露给服务，最终切换只发生在停服窗口内。
set -Eeuo pipefail

# 解析脚本自身位置，使补丁从中文上传目录或任意当前工作目录执行时都能找到 payload。
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_DIR="$PATCH_DIR/payload"
APP_DIR="${FYT_INSTALL_DIR:-/opt/fyt/server}"
ENV_FILE="${FYT_ENV_FILE:-/etc/fyt-web/fyt-web.env}"
BACKUP_DIR="${FYT_BACKUP_DIR:-/var/backups/fyt-web}"
SERVICE_NAME="${FYT_SERVICE_NAME:-fyt-web}"
HEALTH_RETRIES="${FYT_HEALTH_RETRIES:-45}"
STAGE=""                 # 仅存放程序文件的同盘暂存目录，退出时无条件清理。
BACKUP_FILE=""           # 旧程序归档路径；不包含业务数据。
SERVICE_WAS_ACTIVE=0      # 记录升级前状态，验证完成后恢复用户原有启停选择。
ROLLBACK_READY=0          # 只有旧程序备份成功后才允许执行自动回滚。
UPGRADE_SUCCEEDED=0       # 防止正常退出时触发失败恢复。

# 输出带时间的运维进度，不使用特殊图标，兼容精简服务器终端。
say() {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

die() {
    printf '[错误] %s\n' "$*" >&2
    exit 1
}

restore_program() {
    # 本函数由 EXIT 陷阱调用，必须关闭“遇错退出”，让回滚中的单项失败不阻断后续恢复步骤。
    set +e
    [ "$ROLLBACK_READY" -eq 1 ] || return 0
    [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ] || return 0

    say "升级未完成，正在恢复升级前的程序文件"
    systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
    # 删除目标严格限定为本次补丁可替换的三个目录；数据目录、虚拟环境和运维脚本均保留。
    rm -rf -- "$APP_DIR/web_backend" "$APP_DIR/core" "$APP_DIR/web-app/dist"
    tar -xzf "$BACKUP_FILE" -C "$APP_DIR"

    if getent group fyt-web >/dev/null 2>&1; then
        # 兼容早期没有 web_backend 目录的备份，只有实际恢复出的路径才参与 chown。
        restored_paths=(
            "$APP_DIR/web_server.py" \
            "$APP_DIR/requirements.txt" \
            "$APP_DIR/core" \
            "$APP_DIR/web-app/dist"
        )
        [ -d "$APP_DIR/web_backend" ] && restored_paths+=("$APP_DIR/web_backend")
        chown -R root:fyt-web "${restored_paths[@]}"
    fi
    restored_dirs=("$APP_DIR/core" "$APP_DIR/web-app/dist")
    [ -d "$APP_DIR/web_backend" ] && restored_dirs+=("$APP_DIR/web_backend")
    find "${restored_dirs[@]}" -type d -exec chmod 750 {} +
    find "${restored_dirs[@]}" -type f -exec chmod 640 {} +
    chmod 640 "$APP_DIR/web_server.py" "$APP_DIR/requirements.txt"

    if [ "$SERVICE_WAS_ACTIVE" -eq 1 ]; then
        systemctl start "$SERVICE_NAME" >/dev/null 2>&1 || true
    fi
    say "程序文件已恢复，业务数据未做任何改动"
}

finish() {
    # 先保存触发陷阱的原始退出码；清理命令的结果不能覆盖真正的升级失败状态。
    local status=$?
    trap - EXIT INT TERM
    if [ "$status" -ne 0 ] && [ "$UPGRADE_SUCCEEDED" -ne 1 ]; then
        restore_program
    fi
    if [ -n "$STAGE" ] && [ -d "$STAGE" ]; then
        rm -rf -- "$STAGE"
    fi
    exit "$status"
}

# EXIT 统一负责失败回滚与暂存清理；信号转换为常见退出码后仍会进入同一收尾路径。
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 升级涉及 systemd、/opt 和备份目录，拒绝以普通用户进行部分成功的写入。
[ "$(id -u)" -eq 0 ] || die "请使用 root 身份运行本脚本"
command -v systemctl >/dev/null 2>&1 || die "当前系统未提供 systemd"
command -v tar >/dev/null 2>&1 || die "当前系统未提供 tar"
command -v sha256sum >/dev/null 2>&1 || die "当前系统未提供 sha256sum"
[[ "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "服务名称格式不正确"
[[ "$HEALTH_RETRIES" =~ ^[0-9]+$ ]] && [ "$HEALTH_RETRIES" -ge 1 ] \
    || die "FYT_HEALTH_RETRIES 必须是大于 0 的整数"

# 先拒绝可造成大范围删除的目录，再限制为无空格 ASCII 绝对路径，降低变量展开风险。
case "$APP_DIR" in
    /|/opt|/opt/fyt|/var|/etc|/usr) die "拒绝使用过于宽泛的程序目录：$APP_DIR" ;;
esac
[[ "$APP_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || die "程序目录必须是无空格的绝对 ASCII 路径：$APP_DIR"

# 补丁必须具备完整运行骨架，避免删除旧目录后才发现新负载缺文件。
for required in \
    "$PAYLOAD_DIR/web_server.py" \
    "$PAYLOAD_DIR/requirements.txt" \
    "$PAYLOAD_DIR/web_backend/__init__.py" \
    "$PAYLOAD_DIR/core/__init__.py" \
    "$PAYLOAD_DIR/web-app/dist/index.html"; do
    [ -e "$required" ] || die "补丁负载缺少必要文件：$required"
done

# 同样验证既有安装，尤其是虚拟环境和配置；增量补丁不承担首次安装职责。
for required in \
    "$APP_DIR/web_server.py" \
    "$APP_DIR/requirements.txt" \
    "$APP_DIR/core/__init__.py" \
    "$APP_DIR/web-app/dist/index.html" \
    "$APP_DIR/.venv/bin/python" \
    "$ENV_FILE"; do
    [ -e "$required" ] || die "服务器安装不完整，缺少：$required"
done

# 内容检查与构建端规则重复是刻意的：服务器不能假设上传的压缩包未经篡改。
if find "$PAYLOAD_DIR" \
    \( -iname 'web-data' -o -iname '.venv' -o -iname 'node_modules' \
       -o -iname '__pycache__' -o -iname '*.sqlite3' -o -iname '*.db' \
       -o -iname '*.log' \) -print -quit | grep -q .; then
    die "补丁负载包含数据、依赖或缓存目录，已拒绝升级"
fi
if find "$PAYLOAD_DIR" -type l -print -quit | grep -q .; then
    # 符号链接可能在目标机解析到 payload 或安装目录之外，不能按普通文件复制。
    die "补丁负载包含符号链接，已拒绝升级"
fi

if [ -f "$PATCH_DIR/SHA256SUMS" ]; then
    # 在补丁根目录校验相对路径，既核对内容，也能发现遗漏或损坏的上传文件。
    say "校验补丁文件"
    (cd "$PATCH_DIR" && sha256sum -c SHA256SUMS)
fi

if systemctl is-active --quiet "$SERVICE_NAME"; then
    SERVICE_WAS_ACTIVE=1
fi

APP_PARENT="$(dirname "$APP_DIR")"
mkdir -p "$APP_PARENT" "$BACKUP_DIR"
# 暂存目录创建在程序父目录中，保证后续 mv 不跨文件系统并缩短停服切换时间。
STAGE="$(mktemp -d "$APP_PARENT/.fyt-upgrade-stage.XXXXXX")"
mkdir -p "$STAGE/web-app"
cp -a "$PAYLOAD_DIR/web_server.py" "$STAGE/"
cp -a "$PAYLOAD_DIR/requirements.txt" "$STAGE/"
cp -a "$PAYLOAD_DIR/web_backend" "$STAGE/"
cp -a "$PAYLOAD_DIR/core" "$STAGE/"
cp -a "$PAYLOAD_DIR/web-app/dist" "$STAGE/web-app/"

if getent group fyt-web >/dev/null 2>&1; then
    chown -R root:fyt-web "$STAGE"
fi
# 程序目录对服务组只读；不赋予服务账号修改代码和前端文件的权限。
find "$STAGE" -type d -exec chmod 750 {} +
find "$STAGE" -type f -exec chmod 640 {} +

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/code-before-patch-$STAMP.tar.gz"
say "备份当前程序文件：$BACKUP_FILE"
# 备份列表与替换白名单保持一致，回滚不会覆盖 .venv、配置或业务数据。
program_paths=(web_server.py requirements.txt core web-app/dist)
[ -d "$APP_DIR/web_backend" ] && program_paths+=(web_backend)
tar -czf "$BACKUP_FILE" -C "$APP_DIR" \
    "${program_paths[@]}"
sha256sum "$BACKUP_FILE" > "$BACKUP_FILE.sha256"
ROLLBACK_READY=1  # 只有 tar 与校验文件都成功后，EXIT 陷阱才可依赖此备份。

say "停止服务并应用升级"
systemctl stop "$SERVICE_NAME"

if ! cmp -s "$APP_DIR/requirements.txt" "$STAGE/requirements.txt"; then
    # 复用现有虚拟环境能保留目标机 Python 解释器选择；依赖失败将触发旧程序回滚。
    say "Python 依赖清单有变化，正在更新现有虚拟环境"
    "$APP_DIR/.venv/bin/python" -m pip install -r "$STAGE/requirements.txt"
else
    say "Python 依赖没有变化，跳过依赖安装"
fi

# 停服后删除并移动完整目录，避免新旧模块混合；单文件使用 mv -f 覆盖。
rm -rf -- "$APP_DIR/web_backend" "$APP_DIR/core" "$APP_DIR/web-app/dist"
mv "$STAGE/web_backend" "$APP_DIR/web_backend"
mv "$STAGE/core" "$APP_DIR/core"
mkdir -p "$APP_DIR/web-app"
mv "$STAGE/web-app/dist" "$APP_DIR/web-app/dist"
mv -f "$STAGE/web_server.py" "$APP_DIR/web_server.py"
mv -f "$STAGE/requirements.txt" "$APP_DIR/requirements.txt"

if getent group fyt-web >/dev/null 2>&1; then
    chown -R root:fyt-web \
        "$APP_DIR/web_server.py" \
        "$APP_DIR/requirements.txt" \
        "$APP_DIR/web_backend" \
        "$APP_DIR/core" \
        "$APP_DIR/web-app/dist"
fi
find "$APP_DIR/web_backend" "$APP_DIR/core" "$APP_DIR/web-app/dist" -type d -exec chmod 750 {} +
find "$APP_DIR/web_backend" "$APP_DIR/core" "$APP_DIR/web-app/dist" -type f -exec chmod 640 {} +
chmod 640 "$APP_DIR/web_server.py" "$APP_DIR/requirements.txt"

say "检查 Python 源码"
# 仅编译字节码语法而不导入模块，避免检查阶段连接数据库或启动后台任务。
PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" - "$APP_DIR" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
paths = [
    root / "web_server.py",
    *sorted((root / "core").rglob("*.py")),
    *sorted((root / "web_backend").rglob("*.py")),
]
for path in paths:
    compile(path.read_bytes(), str(path), "exec")
print(f"已检查 {len(paths)} 个 Python 文件")
PY

# 配置可能用双引号包裹值；无效端口回退到服务端默认值，保持健康检查与实际启动一致。
PORT="$(sed -n 's/^FYT_WEB_PORT=//p' "$ENV_FILE" | tail -1)"
PORT="${PORT#\"}"
PORT="${PORT%\"}"
case "$PORT" in
    ''|*[!0-9]*) PORT=8787 ;;
esac

say "启动服务并进行健康检查"
systemctl start "$SERVICE_NAME"
healthy=0
# 每秒同时检查 systemd 活跃状态和应用级 JSON，端口监听但应用未就绪不会被误判为成功。
for _ in $(seq 1 "$HEALTH_RETRIES"); do
    if systemctl is-active --quiet "$SERVICE_NAME" \
        && "$APP_DIR/.venv/bin/python" - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
try:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/health", timeout=2
    ) as response:
        body = json.loads(response.read().decode("utf-8"))
        # 必须同时满足 HTTP 200 与业务健康标记，反向代理错误页不能通过检查。
        raise SystemExit(0 if response.status == 200 and body.get("status") == "ok" else 1)
except Exception:
    raise SystemExit(1)
PY
    then
        healthy=1
        break
    fi
    sleep 1
done

if [ "$healthy" -ne 1 ]; then
    say "健康检查失败，最近服务日志如下"
    journalctl -u "$SERVICE_NAME" -n 80 --no-pager || true
    die "新程序未能通过健康检查"
fi

if [ "$SERVICE_WAS_ACTIVE" -ne 1 ]; then
    # 健康检查需要临时启动服务，但升级不能擅自改变原本由管理员保持的停止状态。
    say "升级前服务处于停止状态，验证完成后恢复停止状态"
    systemctl stop "$SERVICE_NAME"
fi

UPGRADE_SUCCEEDED=1
ROLLBACK_READY=0  # 从此以后正常 EXIT 只清理暂存目录，不再恢复已经验收的新程序。
say "升级完成，业务数据目录未读取、未复制、未删除、未覆盖"
say "程序备份保留在：$BACKUP_FILE"
if [ "$SERVICE_WAS_ACTIVE" -eq 1 ]; then
    say "健康检查地址：http://127.0.0.1:$PORT/api/health"
fi
