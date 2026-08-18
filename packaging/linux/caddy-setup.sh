#!/usr/bin/env bash
# 峰运通数据管理系统 —— Caddy 自动发现与反向代理配置
#
# 安装器在应用健康检查通过后调用本脚本。脚本只扫描 /root 顶层普通文件，不递归读取
# 其他目录；只有找到可解析、未过期且公钥相互匹配的证书与未加密私钥时才安装和配置
# Caddy。没有识别到完整配对时正常返回，不改变已有 Caddy 服务和配置。
set -euo pipefail
umask 077

SEARCH_DIR="${FYT_CADDY_CERT_SEARCH_DIR:-/root}"
CADDY_CONFIG_DIR="${FYT_CADDY_CONFIG_DIR:-/etc/caddy}"
CADDYFILE="${FYT_CADDYFILE:-$CADDY_CONFIG_DIR/Caddyfile}"
CADDY_SNIPPET="${FYT_CADDY_SNIPPET:-$CADDY_CONFIG_DIR/fyt-web.caddy}"
CADDY_CERT_DIR="${FYT_CADDY_CERT_DIR:-$CADDY_CONFIG_DIR/certs}"
CADDY_CERT_FILE="$CADDY_CERT_DIR/fyt-origin.pem"
CADDY_KEY_FILE="$CADDY_CERT_DIR/fyt-origin.key"
CADDY_SERVICE="${FYT_CADDY_SERVICE_NAME:-caddy}"
BACKUP_DIR="${FYT_BACKUP_DIR:-/var/backups/fyt-web}"
UPSTREAM_PORT="${1:-${FYT_WEB_PORT:-8787}}"
UPSTREAM_HOST="${FYT_CADDY_UPSTREAM_HOST:-127.0.0.1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CADDYFILE_EXISTED_BEFORE_INSTALL=0
[ -f "$CADDYFILE" ] && CADDYFILE_EXISTED_BEFORE_INSTALL=1

SELECTED_CERT=""
SELECTED_KEY=""
SITE_LABEL=""
HEALTH_HOST=""
BACKUP_STATE_DIR=""
CADDY_WAS_ACTIVE=0
CONFIG_TOUCHED=0
CONFIGURED=0
VALIDATE_ONLY="${FYT_CADDY_VALIDATE_ONLY:-0}"

say() { printf '[%s] [Caddy] %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '[警告] [Caddy] %s\n' "$*" >&2; }
die() { printf '[错误] [Caddy] %s\n' "$*" >&2; exit 1; }

# 失败恢复只覆盖本脚本管理的文件；已安装的 Caddy 软件包或二进制保留，避免回滚过程
# 卸载系统软件。原服务之前处于运行状态时恢复后重新启动，否则停止本轮新启动的服务。
restore_file() {
    local target="$1" backup_name="$2" existed="$3"
    if [ "$existed" -eq 1 ]; then
        cp -a "$BACKUP_STATE_DIR/$backup_name" "$target"
    else
        rm -f -- "$target"
    fi
}

cleanup() {
    local status=$?
    if [ "$status" -ne 0 ] && [ "$CONFIG_TOUCHED" -eq 1 ] && [ "$CONFIGURED" -eq 0 ]; then
        set +e
        warn "配置失败，正在恢复修改前的 Caddy 配置"
        restore_file "$CADDYFILE" Caddyfile "$CADDYFILE_EXISTED"
        restore_file "$CADDY_SNIPPET" fyt-web.caddy "$SNIPPET_EXISTED"
        restore_file "$CADDY_CERT_FILE" fyt-origin.pem "$CERT_FILE_EXISTED"
        restore_file "$CADDY_KEY_FILE" fyt-origin.key "$KEY_FILE_EXISTED"
        if [ "$SERVICE_FILE_TOUCHED" -eq 1 ]; then
            restore_file /etc/systemd/system/"$CADDY_SERVICE".service caddy.service "$SERVICE_FILE_EXISTED"
        fi
        systemctl daemon-reload >/dev/null 2>&1
        if [ "$CADDY_WAS_ACTIVE" -eq 1 ]; then
            systemctl restart "$CADDY_SERVICE" >/dev/null 2>&1
        else
            systemctl stop "$CADDY_SERVICE" >/dev/null 2>&1
        fi
        set -e
    fi
    return "$status"
}
trap cleanup EXIT

[[ "$UPSTREAM_PORT" =~ ^[0-9]+$ ]] && [ "$UPSTREAM_PORT" -ge 1 ] && [ "$UPSTREAM_PORT" -le 65535 ] \
    || die "反向代理端口必须是 1 至 65535 的整数"
[[ "$UPSTREAM_HOST" =~ ^[A-Za-z0-9:.-]+$ ]] || die "反向代理主机格式不正确"

if [ "${FYT_CADDY_SKIP:-0}" = "1" ]; then
    say "已按 FYT_CADDY_SKIP=1 跳过自动配置"
    exit 0
fi
EXPLICIT_PAIR=0
if [ -n "${FYT_CADDY_CERT_FILE:-}" ] || [ -n "${FYT_CADDY_KEY_FILE:-}" ]; then
    [ -n "${FYT_CADDY_CERT_FILE:-}" ] && [ -n "${FYT_CADDY_KEY_FILE:-}" ] \
        || die "FYT_CADDY_CERT_FILE 与 FYT_CADDY_KEY_FILE 必须同时指定"
    [ -f "$FYT_CADDY_CERT_FILE" ] && [ -f "$FYT_CADDY_KEY_FILE" ] \
        || die "显式指定的证书或私钥文件不存在"
    EXPLICIT_PAIR=1
elif [ ! -d "$SEARCH_DIR" ]; then
    say "证书搜索目录不存在，跳过自动配置：$SEARCH_DIR"
    exit 0
fi

# 先用 PEM 边界标记进行轻量预检；没有同时出现证书和私钥时不安装 openssl、Caddy
# 或其他系统软件。限制单文件大小可以避免误扫上传到 /root 的大型业务文件。
has_certificate_marker=0
has_private_key_marker=0
if [ "$EXPLICIT_PAIR" -eq 1 ]; then
    grep -q -- '-----BEGIN CERTIFICATE-----' "$FYT_CADDY_CERT_FILE" 2>/dev/null \
        && has_certificate_marker=1
    grep -Eq -- '-----BEGIN (RSA |EC )?PRIVATE KEY-----' "$FYT_CADDY_KEY_FILE" 2>/dev/null \
        && has_private_key_marker=1
else
    while IFS= read -r -d '' candidate; do
        if grep -q -- '-----BEGIN CERTIFICATE-----' "$candidate" 2>/dev/null; then
            has_certificate_marker=1
        fi
        if grep -Eq -- '-----BEGIN (RSA |EC )?PRIVATE KEY-----' "$candidate" 2>/dev/null; then
            has_private_key_marker=1
        fi
    done < <(find "$SEARCH_DIR" -maxdepth 1 -type f -size -2M -print0 2>/dev/null)
fi

if [ "$has_certificate_marker" -ne 1 ] || [ "$has_private_key_marker" -ne 1 ]; then
    say "未在 $SEARCH_DIR 识别到完整的证书和私钥，跳过 Caddy 配置"
    exit 0
fi

install_support_tools() {
    command -v openssl >/dev/null 2>&1 && command -v curl >/dev/null 2>&1 && return 0
    say "安装证书校验和下载工具..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y openssl curl ca-certificates
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y openssl curl ca-certificates
    elif command -v yum >/dev/null 2>&1; then
        yum install -y openssl curl ca-certificates
    else
        return 1
    fi
}
if [ "$VALIDATE_ONLY" = "1" ]; then
    command -v openssl >/dev/null 2>&1 || die "识别测试需要 openssl"
else
    [ "$(id -u)" -eq 0 ] || die "请由 Linux 安装器以 root 权限调用"
    command -v systemctl >/dev/null 2>&1 || die "当前系统未提供 systemd"
    install_support_tools || die "无法安装 openssl/curl，不能安全校验证书与下载 Caddy"
fi

certificate_fingerprint() {
    local digest
    digest="$(openssl x509 -in "$1" -pubkey -noout 2>/dev/null \
        | openssl pkey -pubin -outform DER 2>/dev/null \
        | sha256sum | awk '{print $1}')" || return 1
    [ -n "$digest" ] || return 1
    printf '%s\n' "$digest"
}

private_key_fingerprint() {
    # pass: 明确使用空密码，防止遇到加密私钥时在无人值守部署中等待交互输入。
    local digest
    digest="$(openssl pkey -in "$1" -passin pass: -pubout -outform DER 2>/dev/null \
        | sha256sum | awk '{print $1}')" || return 1
    [ -n "$digest" ] || return 1
    printf '%s\n' "$digest"
}

declare -a certificate_candidates=()
declare -a private_key_candidates=()
if [ "$EXPLICIT_PAIR" -eq 1 ]; then
    certificate_candidates=("$FYT_CADDY_CERT_FILE")
    private_key_candidates=("$FYT_CADDY_KEY_FILE")
else
    while IFS= read -r -d '' candidate; do
        grep -q -- '-----BEGIN CERTIFICATE-----' "$candidate" 2>/dev/null \
            && certificate_candidates+=("$candidate")
        grep -Eq -- '-----BEGIN (RSA |EC )?PRIVATE KEY-----' "$candidate" 2>/dev/null \
            && private_key_candidates+=("$candidate")
    done < <(find "$SEARCH_DIR" -maxdepth 1 -type f -size -2M -print0 2>/dev/null)
fi

best_expiry=0
for certificate in "${certificate_candidates[@]}"; do
    [ -f "$certificate" ] || continue
    openssl x509 -in "$certificate" -noout >/dev/null 2>&1 || continue
    openssl x509 -in "$certificate" -checkend 0 -noout >/dev/null 2>&1 || continue
    cert_fingerprint="$(certificate_fingerprint "$certificate" 2>/dev/null || true)"
    [ -n "$cert_fingerprint" ] || continue
    expiry_text="$(openssl x509 -in "$certificate" -enddate -noout 2>/dev/null | sed 's/^notAfter=//')"
    expiry_epoch="$(date -d "$expiry_text" +%s 2>/dev/null || printf '0')"
    for private_key in "${private_key_candidates[@]}"; do
        [ -f "$private_key" ] || continue
        key_fingerprint="$(private_key_fingerprint "$private_key" 2>/dev/null || true)"
        [ -n "$key_fingerprint" ] || continue
        if [ "$cert_fingerprint" = "$key_fingerprint" ] && [ "$expiry_epoch" -ge "$best_expiry" ]; then
            SELECTED_CERT="$certificate"
            SELECTED_KEY="$private_key"
            best_expiry="$expiry_epoch"
        fi
    done
done

if [ -z "$SELECTED_CERT" ] || [ -z "$SELECTED_KEY" ]; then
    warn "发现了 PEM 文件，但没有识别到有效且相互匹配的证书/私钥；已跳过 Caddy 配置"
    exit 0
fi

valid_domain() {
    local domain="$1"
    [[ "$domain" =~ ^(\*\.)?([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]]
}

declare -a domains=()
add_domain() {
    local domain="$1" existing
    domain="${domain%.}"
    valid_domain "$domain" || return 0
    for existing in "${domains[@]:-}"; do
        [ "$existing" = "$domain" ] && return 0
    done
    domains+=("$domain")
}

if [ -n "${FYT_CADDY_DOMAINS:-}" ]; then
    while IFS= read -r domain; do
        [ -n "$domain" ] && add_domain "$domain"
    done < <(printf '%s' "$FYT_CADDY_DOMAINS" | tr ', ' '\n\n')
else
    while IFS= read -r domain; do
        [ -n "$domain" ] && [[ "$domain" != \*.* ]] && add_domain "$domain"
    done < <(openssl x509 -in "$SELECTED_CERT" -noout -ext subjectAltName 2>/dev/null \
        | grep -oE 'DNS:[^,[:space:]]+' | sed 's/^DNS://' || true)
    while IFS= read -r domain; do
        [ -n "$domain" ] && [[ "$domain" == \*.* ]] && add_domain "$domain"
    done < <(openssl x509 -in "$SELECTED_CERT" -noout -ext subjectAltName 2>/dev/null \
        | grep -oE 'DNS:[^,[:space:]]+' | sed 's/^DNS://' || true)
fi

if [ "${#domains[@]}" -eq 0 ]; then
    common_name="$(openssl x509 -in "$SELECTED_CERT" -noout -subject -nameopt RFC2253 2>/dev/null \
        | sed -n 's/^subject=.*CN=\([^,]*\).*$/\1/p' | head -n 1)"
    [ -n "$common_name" ] && add_domain "$common_name"
fi
if [ "${#domains[@]}" -eq 0 ]; then
    warn "证书与私钥有效，但证书中没有可用于网站的 DNS 域名；已跳过 Caddy 配置"
    exit 0
fi

SITE_LABEL="${domains[0]}"
HEALTH_HOST="${domains[0]}"
for domain in "${domains[@]:1}"; do
    SITE_LABEL+=", $domain"
done
if [[ "$HEALTH_HOST" == \*.* ]]; then
    HEALTH_HOST="fyt.${HEALTH_HOST#*.}"
fi

# 测试模式只证明证书、私钥和域名能够被真实解析，不安装软件、不复制私钥、不写系统目录。
if [ "$VALIDATE_ONLY" = "1" ]; then
    say "识别测试通过：$SITE_LABEL"
    exit 0
fi

install_caddy_package() {
    if command -v apt-get >/dev/null 2>&1; then
        say "通过 Caddy 官方 Debian/Ubuntu 软件源安装..."
        apt-get update -y || return 1
        apt-get install -y debian-keyring debian-archive-keyring apt-transport-https \
            ca-certificates curl gnupg || return 1
        curl --proto '=https' --tlsv1.2 -1fsSL \
            https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
            | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
            || return 1
        curl --proto '=https' --tlsv1.2 -1fsSL \
            https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
            -o /etc/apt/sources.list.d/caddy-stable.list || return 1
        chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
            /etc/apt/sources.list.d/caddy-stable.list
        apt-get update -y || return 1
        apt-get install -y caddy || return 1
        return 0
    fi
    if command -v dnf >/dev/null 2>&1; then
        say "通过 Caddy 官方 COPR 软件源安装..."
        dnf install -y dnf-plugins-core || return 1
        dnf copr enable -y @caddy/caddy || return 1
        dnf install -y caddy || return 1
        return 0
    fi
    return 1
}

install_caddy_static() {
    local machine architecture download_url temporary
    machine="$(uname -m)"
    case "$machine" in
        x86_64|amd64) architecture=amd64 ;;
        aarch64|arm64) architecture=arm64 ;;
        *) return 1 ;;
    esac
    download_url="${FYT_CADDY_DOWNLOAD_URL:-https://caddyserver.com/api/download?os=linux&arch=$architecture}"
    temporary="$(mktemp -d)"
    say "软件源不可用，改从 Caddy 官方下载接口获取静态二进制..."
    if ! curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
        --output "$temporary/caddy" "$download_url"; then
        rm -rf -- "$temporary"
        return 1
    fi
    chmod 755 "$temporary/caddy"
    if ! "$temporary/caddy" version >/dev/null 2>&1; then
        rm -rf -- "$temporary"
        return 1
    fi
    install -o root -g root -m 755 "$temporary/caddy" /usr/bin/caddy
    command -v restorecon >/dev/null 2>&1 && restorecon /usr/bin/caddy >/dev/null 2>&1 || true
    rm -rf -- "$temporary"
}

if systemctl is-active --quiet "$CADDY_SERVICE" 2>/dev/null; then
    CADDY_WAS_ACTIVE=1
fi
if ! command -v caddy >/dev/null 2>&1; then
    install_caddy_package || install_caddy_static \
        || die "无法从官方软件源或官方下载接口安装 Caddy"
fi
CADDY_BIN="$(command -v caddy)"
"$CADDY_BIN" version >/dev/null 2>&1 || die "Caddy 二进制无法运行"

# 软件包通常会创建 caddy 账号和服务；静态下载回退则按官方 systemd 运行方式补齐。
if ! getent group caddy >/dev/null 2>&1; then
    groupadd --system caddy
fi
if ! id -u caddy >/dev/null 2>&1; then
    NOLOGIN="$(command -v nologin || printf '/usr/sbin/nologin')"
    useradd --system --gid caddy --create-home --home-dir /var/lib/caddy \
        --shell "$NOLOGIN" --comment "Caddy web server" caddy
fi
install -d -m 750 -o root -g caddy "$CADDY_CONFIG_DIR" "$CADDY_CERT_DIR"
install -d -m 750 -o caddy -g caddy /var/lib/caddy
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

BACKUP_STATE_DIR="$BACKUP_DIR/caddy-auto-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_STATE_DIR"
chmod 700 "$BACKUP_STATE_DIR"
CADDYFILE_EXISTED="$CADDYFILE_EXISTED_BEFORE_INSTALL"
SNIPPET_EXISTED=0
CERT_FILE_EXISTED=0
KEY_FILE_EXISTED=0
SERVICE_FILE_EXISTED=0
SERVICE_FILE_TOUCHED=0
if [ "$CADDYFILE_EXISTED" -eq 1 ] && [ -f "$CADDYFILE" ]; then cp -a "$CADDYFILE" "$BACKUP_STATE_DIR/Caddyfile"; fi
if [ -f "$CADDY_SNIPPET" ]; then SNIPPET_EXISTED=1; cp -a "$CADDY_SNIPPET" "$BACKUP_STATE_DIR/fyt-web.caddy"; fi
if [ -f "$CADDY_CERT_FILE" ]; then CERT_FILE_EXISTED=1; cp -a "$CADDY_CERT_FILE" "$BACKUP_STATE_DIR/fyt-origin.pem"; fi
if [ -f "$CADDY_KEY_FILE" ]; then KEY_FILE_EXISTED=1; cp -a "$CADDY_KEY_FILE" "$BACKUP_STATE_DIR/fyt-origin.key"; fi
if [ -f /etc/systemd/system/"$CADDY_SERVICE".service ]; then
    SERVICE_FILE_EXISTED=1
    cp -a /etc/systemd/system/"$CADDY_SERVICE".service "$BACKUP_STATE_DIR/caddy.service"
fi
CONFIG_TOUCHED=1

install -o root -g caddy -m 640 "$SELECTED_CERT" "$CADDY_CERT_FILE"
install -o root -g caddy -m 640 "$SELECTED_KEY" "$CADDY_KEY_FILE"

cat > "$CADDY_SNIPPET" <<EOF
# 本文件由峰运通 Linux 安装器维护；修改前请先备份。
$SITE_LABEL {
    tls $CADDY_CERT_FILE $CADDY_KEY_FILE
    reverse_proxy $UPSTREAM_HOST:$UPSTREAM_PORT
}
EOF
chown root:caddy "$CADDY_SNIPPET"
chmod 640 "$CADDY_SNIPPET"

IMPORT_LINE="import $CADDY_SNIPPET"
if [ "$CADDYFILE_EXISTED" -eq 0 ]; then
    printf '%s\n' "$IMPORT_LINE" > "$CADDYFILE"
elif ! grep -Fqx "$IMPORT_LINE" "$CADDYFILE"; then
    printf '\n# 峰运通反向代理（由安装器维护）\n%s\n' "$IMPORT_LINE" >> "$CADDYFILE"
fi
chown root:caddy "$CADDYFILE"
chmod 640 "$CADDYFILE"

if ! systemctl cat "$CADDY_SERVICE".service >/dev/null 2>&1; then
    SERVICE_TEMPLATE="$SCRIPT_DIR/fyt-caddy.service"
    [ -f "$SERVICE_TEMPLATE" ] || die "缺少静态 Caddy 服务模板：fyt-caddy.service"
    sed -e "s|__CADDY_BIN__|$CADDY_BIN|g" -e "s|__CADDYFILE__|$CADDYFILE|g" "$SERVICE_TEMPLATE" \
        > /etc/systemd/system/"$CADDY_SERVICE".service
    chmod 644 /etc/systemd/system/"$CADDY_SERVICE".service
    SERVICE_FILE_TOUCHED=1
fi

"$CADDY_BIN" fmt --overwrite "$CADDYFILE" >/dev/null
"$CADDY_BIN" fmt --overwrite "$CADDY_SNIPPET" >/dev/null
"$CADDY_BIN" validate --config "$CADDYFILE" --adapter caddyfile
systemctl daemon-reload
systemctl enable "$CADDY_SERVICE" >/dev/null
if systemctl is-active --quiet "$CADDY_SERVICE"; then
    systemctl reload "$CADDY_SERVICE" || systemctl restart "$CADDY_SERVICE"
else
    systemctl start "$CADDY_SERVICE"
fi
systemctl is-active --quiet "$CADDY_SERVICE" || die "Caddy systemd 服务未能进入运行状态"

# 使用 --resolve 直接连接本机 443，不依赖 DNS 是否已经生效。Cloudflare Origin CA 不在
# 普通系统信任库中，因此这里只用 -k 验证本机转发链路，正式访问仍由 Cloudflare 校验证书。
if command -v curl >/dev/null 2>&1; then
    health_body="$(curl -kfsS --connect-timeout 5 --max-time 10 \
        --resolve "$HEALTH_HOST:443:127.0.0.1" \
        "https://$HEALTH_HOST/api/health" 2>/dev/null || true)"
    printf '%s' "$health_body" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' \
        || die "Caddy 已启动，但 HTTPS 反向代理健康检查未通过"
fi

CONFIGURED=1
say "已自动配置域名：$SITE_LABEL"
say "反向代理目标：http://$UPSTREAM_HOST:$UPSTREAM_PORT"
say "Caddy 已注册为开机启动服务：$CADDY_SERVICE"
say "原配置备份：$BACKUP_STATE_DIR"
