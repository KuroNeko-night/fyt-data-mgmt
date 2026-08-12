#!/usr/bin/env bash
# ============================================================
# Cloudflare 命名隧道交互式配置脚本（正式公网，固定域名）
#
# 前置条件：Cloudflare 账号 + 域名（DNS 已托管到 Cloudflare）
# 用法：bash cloudflared-named.sh
# 流程：授权登录 → 创建隧道 → 绑定域名 → 生成配置 → 试运行 → 安装系统服务
#
# 可选环境变量：
#   CLOUDFLARED_MIRROR  下载镜像前缀（默认 https://gh-proxy.com/，"-" 直连 GitHub）
#
# 本脚本是一次性交互式配置工具，不参与峰运通服务自身的启动。Cloudflare 授权证书、隧道
# 凭据和 config.yml 保存在当前用户的 .cloudflared 目录；选择安装 systemd 服务时才复制
# 配置到 /etc/cloudflared。域名、隧道名称和服务端口均先校验后写入 YAML，避免生成歧义配置。
# ============================================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"  # 无论从哪个工作目录调用，都读取同包 common.sh。
# shellcheck source=common.sh
. "$DIR/common.sh"
CF_DIR="${CLOUDFLARED_CONFIG_DIR:-$HOME/.cloudflared}"  # 授权应在实际运维用户上下文完成。
MIRROR="${CLOUDFLARED_MIRROR:-https://gh-proxy.com/}"
SERVICE_PORT="$(fyt_read_port 2>/dev/null || printf '8787')"  # 配置缺失时与 Web 默认端口一致。

say() { printf "[%s] %s\n" "$(date +%H:%M:%S)" "$*"; }
die() { printf "[错误] %s\n" "$*" >&2; exit 1; }

ensure_cloudflared() {
    # 只在本机缺少可执行程序时下载；不自动升级已经验证可用的固定版本。
    local bin
    bin="$(command -v cloudflared 2>/dev/null || echo /usr/local/bin/cloudflared)"
    [ -x "$bin" ] && return 0
    say "未找到 cloudflared，正在下载..."
    sudo mkdir -p "$(dirname "$bin")"  # /usr/local/bin 通常需要 root 写权限。
    if [ -n "$MIRROR" ] && [ "$MIRROR" != "-" ]; then
        sudo curl -fL --max-time 300 "$MIRROR""https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$bin"
    else
        sudo curl -fL --max-time 300 "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$bin"
    fi
    sudo chmod +x "$bin"
    say "cloudflared 已安装：$bin"
}

ensure_cloudflared

# ---------- 1. 账号授权 ----------
if [ ! -f "$CF_DIR/cert.pem" ]; then
    say "第 1 步：授权 Cloudflare 账号"
    say "浏览器将打开（或显示链接），登录后选择你的域名并点击授权即可。"
    cloudflared tunnel login  # 浏览器授权结果由 cloudflared 写入当前用户配置目录。
    [ -f "$CF_DIR/cert.pem" ] || die "未检测到授权文件 $CF_DIR/cert.pem，请重新运行"
    say "授权完成"
else
    say "已检测到授权文件，跳过登录"
fi

# ---------- 2. 输入隧道名称与域名 ----------
read -r -p "隧道名称 [fyt-web]: " TUNNEL_NAME
TUNNEL_NAME="${TUNNEL_NAME:-fyt-web}"
[[ "$TUNNEL_NAME" =~ ^[A-Za-z0-9_-]+$ ]] || die "隧道名称只能包含字母、数字、下划线、短横线"
read -r -p "公网域名（如 fyt.example.com）: " DOMAIN
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "域名格式不正确"  # 同时阻止 YAML 控制字符进入配置。

# ---------- 3. 创建（或复用）隧道 ----------
mkdir -p "$CF_DIR"
CRED_FILE="$CF_DIR/$TUNNEL_NAME.json"  # cloudflared create 默认以隧道名写入凭据文件。
if [ ! -f "$CRED_FILE" ]; then
    say "第 2 步：创建隧道 $TUNNEL_NAME ..."
    cloudflared tunnel create "$TUNNEL_NAME"
else
    say "隧道 $TUNNEL_NAME 已存在，复用现有配置"
fi
# 只提取凭据 JSON 中第一个 id 字符串，不把完整凭据内容打印到终端或日志。
TUNNEL_ID="$(grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' "$CRED_FILE" | head -1 | sed -E 's/.*"id"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/')"
[ -n "$TUNNEL_ID" ] || die "无法从 $CRED_FILE 读取隧道 ID"

# ---------- 4. 绑定域名（重复绑定会提示已存在，忽略即可） ----------
say "第 3 步：绑定域名 $DOMAIN ..."
cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN" 2>/dev/null \
    || say "（域名可能已绑定，继续）"

# ---------- 5. 生成配置文件 ----------
say "第 4 步：生成配置 $CF_DIR/config.yml ..."
# ingress 只把指定域名转到本机峰运通端口，最后的 404 规则拒绝所有未匹配主机名。
cat > "$CF_DIR/config.yml" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CF_DIR/$TUNNEL_NAME.json
ingress:
  - hostname: $DOMAIN
    service: http://127.0.0.1:$SERVICE_PORT
  - service: http_status:404
EOF
say "配置内容："
cat "$CF_DIR/config.yml"

# ---------- 6. 试运行验证 ----------
say "第 5 步：试运行 8 秒验证连接 ..."
# timeout 的预期退出码不应触发 set -e；只根据日志中是否注册连接给出结果。
set +e
TEST_LOG="$(timeout 8 cloudflared tunnel run "$TUNNEL_NAME" 2>&1 || true)"
set -e
if echo "$TEST_LOG" | grep -qE "Registered tunnel connection"; then
    say "连接正常，隧道已就绪"
else
    say "[警告] 8 秒内未见成功连接，可能仍在建立或配置有误："
    echo "$TEST_LOG" | tail -5
fi

# ---------- 7. 安装为开机自启服务 ----------
read -r -p "是否安装为系统服务（开机自启，需要 sudo）？[Y/n]: " INSTALL
case "${INSTALL:-y}" in
    n|N|no)
        say "跳过服务安装；手动启动：cloudflared tunnel run $TUNNEL_NAME"
        ;;
    *)
        say "安装 systemd 服务 ..."
        sudo mkdir -p /etc/cloudflared
        # systemd 的 cloudflared 服务从固定系统目录读取配置，不依赖配置用户的 HOME。
        sudo cp "$CF_DIR/config.yml" /etc/cloudflared/config.yml
        sudo cloudflared service install
        sudo systemctl enable --now cloudflared
        sleep 2
        if sudo systemctl is-active --quiet cloudflared; then
            say "服务已启动"
        else
            say "[警告] 服务状态异常，查看日志：journalctl -u cloudflared -f"
        fi
        ;;
esac

say "================================================"
say "完成！公网访问：https://$DOMAIN"
say "常用命令："
say "  状态：sudo systemctl status cloudflared"
say "  重启：sudo systemctl restart cloudflared"
say "  日志：journalctl -u cloudflared -f"
say "================================================"
