#!/usr/bin/env bash
# 峰运通数据管理系统 —— Linux 服务端安装/升级脚本
#
# 设计原则：解压位置可以包含中文或空格；正式运行位置始终使用 ASCII 路径，
# 程序、配置、业务数据和备份分开存放，避免 systemd 与权限问题。
#
# 安装过程先在 /opt/fyt 下的同盘暂存目录创建虚拟环境、安装依赖并编译检查源码，只有这些
# 步骤全部成功后才暂停旧服务和切换程序目录。已有数据会在停服后备份；新版本健康检查失败
# 时恢复旧程序与旧 systemd 单元。脚本不会替换系统 Python，只创建应用私有 .venv。
set -euo pipefail

# SOURCE_DIR 使用脚本自身绝对路径，因此部署包可以从中文目录、空格目录或 /root 直接执行。
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="${FYT_INSTALL_ROOT:-/opt/fyt}"
APP_DIR="${FYT_INSTALL_DIR:-$INSTALL_ROOT/server}"
CONFIG_DIR="${FYT_CONFIG_DIR:-/etc/fyt-web}"
DATA_DIR="${FYT_DATA_DIR:-/var/lib/fyt-web}"
BACKUP_DIR="${FYT_BACKUP_DIR:-/var/backups/fyt-web}"
ENV_FILE="$CONFIG_DIR/fyt-web.env"
SERVICE_NAME="${FYT_SERVICE_NAME:-fyt-web}"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
STAGE=""       # 新版本同盘暂存目录，尚未切换前不会影响现有服务。
PREVIOUS=""    # 被移走的旧程序目录，用于健康检查失败时回滚。
was_active=0   # 记录安装前服务是否运行，失败时只恢复原有状态。

# 简洁时间戳便于从串行安装日志中定位耗时和失败阶段。
say() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf '[错误] %s\n' "$*" >&2; exit 1; }

cleanup() {
    # 保存原始状态，避免清理命令覆盖真正的安装退出码。
    local status=$?
    if [ -n "$STAGE" ] && [ -d "$STAGE" ]; then
        rm -rf -- "$STAGE"
    fi
    if [ "$status" -ne 0 ] && [ "$was_active" -eq 1 ] \
        && ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        # 这里只做最后兜底；主健康检查分支会优先恢复旧程序和服务单元。
        systemctl start "$SERVICE_NAME" 2>/dev/null || true
    fi
    return "$status"
}
trap cleanup EXIT

# 安装需要创建系统账号、写入系统目录并管理 systemd，必须从一开始就拥有完整权限。
[ "$(id -u)" -eq 0 ] || die "请使用 sudo bash install.sh 运行"
command -v systemctl >/dev/null 2>&1 || die "当前系统未提供 systemd，无法注册 fyt-web 服务"
[[ "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "FYT_SERVICE_NAME 格式不正确"

# 固定运行路径必须是 ASCII，用户仍可从任意中文目录解压并执行本脚本。
# 限制字符集还能避免路径被插入 sed、systemd 单元和归档命令时产生二次解释。
for path in "$INSTALL_ROOT" "$APP_DIR" "$CONFIG_DIR" "$DATA_DIR" "$BACKUP_DIR"; do
    [[ "$path" =~ ^/[A-Za-z0-9._/-]+$ ]] \
        || die "正式运行路径必须是无空格的绝对 ASCII 路径：$path"
done

# 防止环境变量误设为宽泛目录后，程序切换阶段移动或覆盖系统级路径。
case "$APP_DIR" in
    /|/opt|/var|/etc) die "拒绝使用过于宽泛的安装目录：$APP_DIR" ;;
esac

find_python() {
    # 优先尊重管理员指定的解释器，再按新到旧版本查找；每个候选都实际验证版本下限。
    local candidate resolved
    if [ -n "${FYT_PYTHON:-}" ]; then
        resolved="$FYT_PYTHON"
        [ -x "$resolved" ] || resolved="$(command -v "$FYT_PYTHON" 2>/dev/null || true)"
        if [ -n "$resolved" ] && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            printf '%s\n' "$resolved"
            return 0
        fi
    fi
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        resolved="$(command -v "$candidate" 2>/dev/null || true)"
        if [ -n "$resolved" ] && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done
    return 1
}

install_python() {
    # 只安装额外的 Python 包，不修改 alternatives、不覆盖 /usr/bin/python，也不卸载系统版本。
    say "未找到 Python 3.10+，开始并行安装，不修改系统 Python..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf >/dev/null 2>&1; then
        # Alibaba Cloud Linux 3 可能将 python3 指向系统 Python 3.6，按版本号探测可用包。
        local package
        for package in python3.13 python3.12 python3.11 python3.10; do
            if dnf install -y "$package"; then
                find_python >/dev/null 2>&1 && return 0
            fi
        done
    elif command -v yum >/dev/null 2>&1; then
        local package
        for package in python3.11 python3.10; do
            if yum install -y "$package"; then
                find_python >/dev/null 2>&1 && return 0
            fi
        done
    else
        die "无法识别包管理器，请先安装 Python 3.10+"
    fi
}

# ``|| true`` 让未找到解释器进入自动安装分支，而不是被 set -e 提前终止。
PYTHON_BIN="$(find_python || true)"
if [ -z "$PYTHON_BIN" ]; then
    install_python
    PYTHON_BIN="$(find_python || true)"
fi
[ -n "$PYTHON_BIN" ] || die "安装后仍未找到 Python 3.10+；可用 FYT_PYTHON=/绝对路径/python3.11 指定"
say "使用 Python：$PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

# 在创建暂存目录前验证包结构，避免半安装后才发现交付物缺失。
for required in web_server.py web_backend core web-app/dist requirements.txt fyt-web.service; do
    [ -e "$SOURCE_DIR/$required" ] || die "部署包缺少必要文件：$required"
done

mkdir -p "$INSTALL_ROOT"
chown root:root "$INSTALL_ROOT"
chmod 755 "$INSTALL_ROOT"
# 暂存目录位于安装根内，最终 mv 与正式目录处于同一文件系统，切换快速且可预测。
STAGE="$(mktemp -d "$INSTALL_ROOT/.server-stage.XXXXXX")"
say "准备 ASCII 运行目录：$APP_DIR"
cp -a "$SOURCE_DIR/web_server.py" "$STAGE/"
cp -a "$SOURCE_DIR/web_backend" "$STAGE/"
cp -a "$SOURCE_DIR/core" "$STAGE/"
cp -a "$SOURCE_DIR/web-app" "$STAGE/"
cp -a "$SOURCE_DIR/requirements.txt" "$STAGE/"
cp -a "$SOURCE_DIR/fyt-web.service" "$STAGE/"
[ -f "$SOURCE_DIR/VERSION" ] && cp -a "$SOURCE_DIR/VERSION" "$STAGE/"
for script in "$SOURCE_DIR"/*.sh; do
    [ -f "$script" ] || continue
    cp -a "$script" "$STAGE/"
done

say "创建独立虚拟环境..."
# 虚拟环境随程序版本切换，既不污染系统 Python，也避免旧依赖残留影响新版本。
"$PYTHON_BIN" -m venv "$STAGE/.venv" \
    || die "创建虚拟环境失败；Debian/Ubuntu 请安装对应版本的 venv 组件"
say "安装运行依赖..."
"$STAGE/.venv/bin/python" -m pip install --upgrade pip -q
"$STAGE/.venv/bin/python" -m pip install -r "$STAGE/requirements.txt"

say "检查 Python 源码..."
# 只执行 compile，不导入 web_server；检查阶段不会建库、读取业务数据或监听端口。
PYTHONPATH="$STAGE" "$STAGE/.venv/bin/python" - "$STAGE" <<'PY'
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

# 服务账号禁止交互登录，home 指向数据目录以确保 expanduser("~") 落在可写且受控的位置。
NOLOGIN="$(command -v nologin || printf '/usr/sbin/nologin')"
if ! id -u fyt-web >/dev/null 2>&1; then
    say "创建低权限服务账号 fyt-web..."
    useradd --system --home-dir "$DATA_DIR" --shell "$NOLOGIN" --no-create-home fyt-web
else
    # 旧版本可能把中文部署目录写入服务账号的 home。只更新 passwd 中的 home，
    # 不移动或删除原目录内容，避免 expanduser("~") 再次落到不可写的旧路径。
    say "更新 fyt-web 服务账号的数据主目录：$DATA_DIR"
    usermod --home "$DATA_DIR" --shell "$NOLOGIN" fyt-web
fi

# 配置只允许 root 写、服务组读；数据只允许服务账号访问；备份只允许 root 访问。
mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$BACKUP_DIR"
chown root:fyt-web "$CONFIG_DIR"
chmod 750 "$CONFIG_DIR"
chown fyt-web:fyt-web "$DATA_DIR"
chmod 700 "$DATA_DIR"
chown root:root "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# 从旧版本部署目录迁移数据，但只在新数据目录为空时执行，拒绝隐式合并。
# 复制而不删除旧目录，为人工核对和失败回退保留原始数据副本。
legacy_data="${FYT_LEGACY_DATA_DIR:-}"
if [ -z "$legacy_data" ] && [ -d "$APP_DIR/web-data" ]; then
    legacy_data="$APP_DIR/web-data"
fi
if [ -n "$legacy_data" ] && [ -d "$legacy_data" ] && [ -z "$(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    say "迁移旧版运行数据：$legacy_data -> $DATA_DIR"
    cp -a "$legacy_data/." "$DATA_DIR/"
fi

if [ ! -f "$ENV_FILE" ]; then
    # 升级旧包时允许迁移程序目录内的历史配置；已有正式配置绝不被新版覆盖。
    if [ -f "$APP_DIR/fyt-web.env" ]; then
        cp -a "$APP_DIR/fyt-web.env" "$ENV_FILE"
    else
        : > "$ENV_FILE"
    fi
fi
sed -i 's/\r$//' "$ENV_FILE"  # 清除 Windows CRLF 尾部，防止环境变量值混入不可见回车。

set_env() {
    # 每个键保持单行单值；存在则原位更新，不存在才追加，避免 systemd 读取到重复旧值。
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}
# 数据根始终写入独立配置，应用不得回退到程序目录下的 web-data。
set_env FYT_WEB_DATA "$DATA_DIR"
if [ -n "${FYT_WEB_PORT:-}" ]; then
    [[ "$FYT_WEB_PORT" =~ ^[0-9]+$ ]] && [ "$FYT_WEB_PORT" -ge 1 ] && [ "$FYT_WEB_PORT" -le 65535 ] \
        || die "FYT_WEB_PORT 必须是 1 至 65535 的整数"
    set_env FYT_WEB_PORT "$FYT_WEB_PORT"
elif ! grep -q '^FYT_WEB_PORT=' "$ENV_FILE"; then
    set_env FYT_WEB_PORT 8787
fi
if [ -n "${FYT_WEB_HOST:-}" ]; then
    [[ "$FYT_WEB_HOST" =~ ^[A-Za-z0-9:.-]+$ ]] || die "FYT_WEB_HOST 格式不正确"
    set_env FYT_WEB_HOST "$FYT_WEB_HOST"
elif ! grep -q '^FYT_WEB_HOST=' "$ENV_FILE"; then
    set_env FYT_WEB_HOST 0.0.0.0
fi

# 只有首次建库才准备管理员密码；已有账号库升级时绝不重置管理员凭据。
if [ ! -f "$DATA_DIR/accounts.sqlite3" ] && ! grep -q '^FYT_ADMIN_PASSWORD=' "$ENV_FILE"; then
    if [ -n "${FYT_ADMIN_PASSWORD:-}" ]; then
        case "$FYT_ADMIN_PASSWORD" in
            *$'\n'*|*$'\r'*) die "FYT_ADMIN_PASSWORD 不能包含换行" ;;
        esac
        if ! FYT_PASSWORD_CHECK="$FYT_ADMIN_PASSWORD" "$PYTHON_BIN" -c \
            'import os,sys; p=os.environ["FYT_PASSWORD_CHECK"]; sys.exit(0 if 10 <= len(p) <= 128 and any(c.isalpha() for c in p) and any(c.isdigit() for c in p) else 1)'; then
            die "管理员密码必须为 10 至 128 位，并同时包含字母和数字"
        fi
        # 配置采用双引号值，只转义反斜杠和双引号；换行已在上方明确拒绝。
        ESCAPED_PASSWORD="${FYT_ADMIN_PASSWORD//\\/\\\\}"
        ESCAPED_PASSWORD="${ESCAPED_PASSWORD//\"/\\\"}"
        printf 'FYT_ADMIN_PASSWORD="%s"\n' "$ESCAPED_PASSWORD" >> "$ENV_FILE"
        say "使用 FYT_ADMIN_PASSWORD 指定的初始管理员密码"
    else
        # secrets 生成一次性随机密码，并强制前缀满足字母与数字复杂度要求。
        RANDOM_PW="$("$PYTHON_BIN" -c 'import secrets,string; print("Aa1" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(13)))')"
        printf 'FYT_ADMIN_PASSWORD="%s"\n' "$RANDOM_PW" >> "$ENV_FILE"
        say "已生成随机管理员密码：$RANDOM_PW"
        say "请立即保存，首次建库成功后会从配置文件删除"
    fi
fi

chown root:fyt-web "$ENV_FILE"
chmod 640 "$ENV_FILE"

if systemctl is-active --quiet "$SERVICE_NAME"; then
    was_active=1
    say "暂停现有服务以切换程序文件..."
    systemctl stop "$SERVICE_NAME"
fi

# 停服后为已有数据留一份一致、可恢复的备份；SQLite 与上传目录不会在写入中途被归档。
if [ -f "$DATA_DIR/accounts.sqlite3" ] || [ -n "$(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    backup_file="$BACKUP_DIR/pre-install-$(date +%Y%m%d-%H%M%S).tar.gz"
    say "备份现有运行数据：$backup_file"
    # 去掉前导斜杠后从 / 打包，恢复时仍能还原原始绝对目录层级。
    tar_paths=("${DATA_DIR#/}")
    [ -f "$ENV_FILE" ] && tar_paths+=("${ENV_FILE#/}")
    tar -czf "$backup_file" -C / "${tar_paths[@]}"
fi

if [ -e "$APP_DIR" ]; then
    # 旧程序先整体改名保留，健康检查成功前不删除；这比逐文件覆盖更容易完整回滚。
    PREVIOUS="$APP_DIR.previous-$(date +%Y%m%d-%H%M%S)"
    mv "$APP_DIR" "$PREVIOUS"
fi
mv "$STAGE" "$APP_DIR"
STAGE=""

# 运行代码可由服务组读取但不可写，业务数据与配置继续使用各自更严格的权限边界。
chown -R root:fyt-web "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 750 {} +
find "$APP_DIR" -type f -exec chmod 640 {} +
find "$APP_DIR/.venv/bin" -type f -exec chmod 750 {} +
find "$APP_DIR" -maxdepth 1 -type f -name '*.sh' -exec chmod 750 {} +
chown -R fyt-web:fyt-web "$DATA_DIR"
chmod 700 "$DATA_DIR"

say "注册 systemd 服务..."
SERVICE_BACKUP=""
if [ -f "$SERVICE_FILE" ]; then
    # 单元文件单独备份，保证新版模板错误时能与旧程序一起恢复。
    SERVICE_BACKUP="$BACKUP_DIR/$SERVICE_NAME.service.pre-install-$(date +%Y%m%d-%H%M%S)"
    cp -a "$SERVICE_FILE" "$SERVICE_BACKUP"
fi
# 路径已经限制为安全 ASCII 字符，可直接替换模板占位符而不会破坏 sed 表达式。
sed -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__ENV_FILE__|$ENV_FILE|g" \
    -e "s|__DATA_DIR__|$DATA_DIR|g" \
    "$APP_DIR/fyt-web.service" > "$SERVICE_FILE"
chmod 644 "$SERVICE_FILE"
systemctl daemon-reload
service_prepared=1
# enable 或 start 任一步失败都进入统一健康失败与回滚分支。
systemctl enable "$SERVICE_NAME" >/dev/null || service_prepared=0
if [ "$service_prepared" -eq 1 ]; then
    systemctl start "$SERVICE_NAME" || service_prepared=0
fi

# 配置读取与服务端约定一致，兼容带双引号的环境文件值。
PORT="$(sed -n 's/^FYT_WEB_PORT=//p' "$ENV_FILE" | tail -1)"
PORT="${PORT#\"}"
PORT="${PORT%\"}"
PORT="${PORT:-8787}"
healthy=0
# 最多等待约三十秒，要求 systemd 活跃且应用健康接口返回明确的 ok 标记。
for _ in $(seq 1 30); do
    [ "$service_prepared" -eq 1 ] || break
    if systemctl is-active --quiet "$SERVICE_NAME" \
        && "$APP_DIR/.venv/bin/python" - "$PORT" <<'PY'
import sys
import urllib.request

port = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
        body = response.read().decode("utf-8")
        raise SystemExit(0 if response.status == 200 and '"status": "ok"' in body else 1)
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
    say "服务启动失败，最近日志如下："
    journalctl -u "$SERVICE_NAME" -n 80 --no-pager || true
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
        # 失败的新程序也保留带时间戳副本，便于离线诊断，不与已恢复目录混合。
        failed_dir="$APP_DIR.failed-$(date +%Y%m%d-%H%M%S)"
        mv "$APP_DIR" "$failed_dir"
        mv "$PREVIOUS" "$APP_DIR"
        say "已回退到旧程序，失败版本保留在：$failed_dir"
    fi
    if [ -n "$SERVICE_BACKUP" ] && [ -f "$SERVICE_BACKUP" ]; then
        cp -a "$SERVICE_BACKUP" "$SERVICE_FILE"
        systemctl daemon-reload
    fi
    if [ "$was_active" -eq 1 ]; then
        systemctl start "$SERVICE_NAME" || true
    fi
    exit 1
fi

# 初始密码只用于首次建库，健康检查成功意味着账号库已初始化，此时立即从长期配置移除。
# 密码仍应由管理员在首次输出时保存，后续只能通过受控的重置流程处理。
if grep -q '^FYT_ADMIN_PASSWORD=' "$ENV_FILE"; then
    sed -i '/^FYT_ADMIN_PASSWORD=/d' "$ENV_FILE"
    chown root:fyt-web "$ENV_FILE"
    chmod 640 "$ENV_FILE"
fi

say "安装完成"
say "程序目录：$APP_DIR"
say "配置文件：$ENV_FILE"
say "数据目录：$DATA_DIR"
say "备份目录：$BACKUP_DIR"
say "服务地址：http://<服务器IP>:$PORT"
say "管理命令：sudo bash $APP_DIR/status.sh / restart.sh / stop.sh / logs.sh"
