#!/usr/bin/env bash
# 峰运通数据管理系统 —— 从 Git 仓库直接部署 Linux 服务端
#
# 本脚本用于公开仓库部署：服务器无需先上传 ZIP 包。它在受控临时目录克隆指定分支或
# 标签，校验提交、构建 Web 前端并组装与 Linux ZIP 相同的运行载荷，最后复用 install.sh
# 完成 Python 环境、数据备份、systemd 切换、健康检查与失败回滚。
#
# 默认仓库：https://github.com/KuroNeko-night/fyt-data-mgmt.git
# 默认引用：main
#
# 可选环境变量：
#   FYT_GIT_REPO             Git 仓库地址
#   FYT_GIT_REF              分支或标签，默认 main
#   FYT_GIT_EXPECTED_COMMIT  期望提交哈希前缀，用于固定部署内容
#   FYT_NPM_REGISTRY         npm 镜像地址
#   FYT_NODE_DIST_BASE       Node.js 发行目录，默认 https://nodejs.org/dist
#   FYT_NODE_RELEASE         Node 22 版本目录，默认 latest-v22.x
#   FYT_GIT_TOOLS_DIR        Node 与 npm 缓存目录，默认 /opt/fyt/git-tools
#
# install.sh 支持的 FYT_INSTALL_ROOT、FYT_INSTALL_DIR、FYT_DATA_DIR、FYT_WEB_PORT、
# FYT_WEB_HOST、FYT_ADMIN_PASSWORD、FYT_PYTHON、PIP_INDEX_URL 和 FYT_CADDY_* 等变量会原样继承。
set -euo pipefail
umask 077

GIT_REPO="${FYT_GIT_REPO:-https://github.com/KuroNeko-night/fyt-data-mgmt.git}"
GIT_REF="${FYT_GIT_REF:-main}"
EXPECTED_COMMIT="${FYT_GIT_EXPECTED_COMMIT:-}"
INSTALL_ROOT="${FYT_INSTALL_ROOT:-/opt/fyt}"
APP_DIR="${FYT_INSTALL_DIR:-$INSTALL_ROOT/server}"
TOOLS_DIR="${FYT_GIT_TOOLS_DIR:-$INSTALL_ROOT/git-tools}"
NODE_LINK="$TOOLS_DIR/node-current"
NPM_CACHE="${FYT_NPM_CACHE:-$TOOLS_DIR/npm-cache}"
LOCK_FILE="${FYT_GIT_LOCK_FILE:-/run/lock/fyt-git-deploy.lock}"
WORK_DIR=""
CHECKOUT_DIR=""
BUNDLE_DIR=""
DEPLOY_COMMIT=""
DEPLOY_VERSION=""

say() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf '[错误] %s\n' "$*" >&2; exit 1; }

cleanup() {
    # 临时目录只能由本脚本在 INSTALL_ROOT 下通过 mktemp 创建；前缀检查阻止变量异常时
    # 删除宽泛目录。正式程序、配置和 /var/lib/fyt-web 从不进入清理范围。
    local status=$?
    if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
        case "$WORK_DIR" in
            "$INSTALL_ROOT"/.git-deploy.*) rm -rf -- "$WORK_DIR" ;;
            *) printf '[警告] 跳过异常临时目录清理：%s\n' "$WORK_DIR" >&2 ;;
        esac
    fi
    return "$status"
}
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || die "请使用 sudo bash deploy-from-git.sh 运行"
command -v systemctl >/dev/null 2>&1 || die "当前系统未提供 systemd，无法部署 fyt-web 服务"

# 固定工具和暂存路径只允许绝对 ASCII 路径，避免 shell、systemd 和旧版工具处理空格或
# 中文路径时产生歧义；仓库 URL 与引用始终作为独立参数传递，不参与命令拼接。
for path in "$INSTALL_ROOT" "$APP_DIR" "$TOOLS_DIR"; do
    [[ "$path" =~ ^/[A-Za-z0-9._/-]+$ ]] \
        || die "部署路径必须是无空格的绝对 ASCII 路径：$path"
done
case "$INSTALL_ROOT" in
    /|/opt|/var|/etc) die "拒绝使用过于宽泛的安装根目录：$INSTALL_ROOT" ;;
esac
case "$GIT_REPO" in
    *$'\n'*|*$'\r'*) die "FYT_GIT_REPO 不能包含换行" ;;
esac
[[ "$GIT_REF" =~ ^[A-Za-z0-9._/-]+$ ]] \
    || die "FYT_GIT_REF 只能包含字母、数字、点、下划线、斜杠和连字符"
case "$GIT_REF" in
    -*|*..*|*/|*/.|*/.lock) die "FYT_GIT_REF 不是安全的分支或标签名称：$GIT_REF" ;;
esac
if [ -n "$EXPECTED_COMMIT" ]; then
    [[ "$EXPECTED_COMMIT" =~ ^[0-9a-fA-F]{7,40}$ ]] \
        || die "FYT_GIT_EXPECTED_COMMIT 必须是 7 至 40 位十六进制提交哈希"
    EXPECTED_COMMIT="${EXPECTED_COMMIT,,}"
fi

install_base_tools() {
    # 只有缺少必要命令时才调用系统包管理器；不升级整个系统，也不替换系统 Python。
    local missing=0 command_name
    for command_name in git curl tar xz sha256sum flock; do
        command -v "$command_name" >/dev/null 2>&1 || missing=1
    done
    [ "$missing" -eq 0 ] && return 0

    say "安装 Git 部署所需的基础工具..."
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y
        apt-get install -y git curl ca-certificates tar xz-utils coreutils util-linux
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y git curl ca-certificates tar xz coreutils util-linux
    elif command -v yum >/dev/null 2>&1; then
        yum install -y git curl ca-certificates tar xz coreutils util-linux
    else
        die "无法识别包管理器，请先安装 git、curl、tar、xz、coreutils 和 util-linux"
    fi

    for command_name in git curl tar xz sha256sum flock; do
        command -v "$command_name" >/dev/null 2>&1 \
            || die "安装后仍缺少命令：$command_name"
    done
}

download() {
    # curl 使用有限重试和明确超时，网络中断会让部署在停服前失败，不影响现有服务。
    local url="$1" target="$2"
    curl --fail --show-error --location \
        --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 600 \
        --output "$target" "$url"
}

node_is_compatible() {
    # Vite 8 至少需要 Node 20.19 或 Node 22；21.x 不在长期支持范围内。
    local node_bin="$1"
    [ -x "$node_bin" ] || return 1
    "$node_bin" -e '
const [major, minor] = process.versions.node.split(".").map(Number);
process.exit((major === 20 && minor >= 19) || major >= 22 ? 0 : 1);
' >/dev/null 2>&1
}

install_node() {
    # 目标机没有合格 Node 时，从 Node.js 官方发行目录下载 Node 22 二进制并校验 SHA-256。
    # Node 只用于前端构建，正式 fyt-web 服务仍只运行 Python。
    local dist_base release arch node_arch checksums_url checksums_file
    local archive_name expected_hash archive_path extract_dir extracted_dir target_dir
    dist_base="${FYT_NODE_DIST_BASE:-https://nodejs.org/dist}"
    dist_base="${dist_base%/}"
    release="${FYT_NODE_RELEASE:-latest-v22.x}"
    if [ "$release" != "latest-v22.x" ] \
        && [[ ! "$release" =~ ^v22\.[0-9]+\.[0-9]+$ ]]; then
        die "FYT_NODE_RELEASE 只允许 latest-v22.x 或明确的 v22.x.x 版本"
    fi

    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64) node_arch="x64" ;;
        aarch64|arm64) node_arch="arm64" ;;
        *) die "当前 CPU 架构暂不支持自动安装 Node.js：$arch" ;;
    esac

    checksums_url="$dist_base/$release/SHASUMS256.txt"
    checksums_file="$WORK_DIR/node-SHASUMS256.txt"
    say "下载 Node.js 校验清单：$release"
    download "$checksums_url" "$checksums_file"

    if [ "$release" = "latest-v22.x" ]; then
        archive_name="$(awk -v suffix="linux-$node_arch.tar.xz" '
            {
                file = $2;
                sub(/^\*/, "", file);
                if (file ~ "^node-v22\\.[0-9]+\\.[0-9]+-" suffix "$") {
                    print file;
                    exit;
                }
            }
        ' "$checksums_file")"
    else
        archive_name="node-$release-linux-$node_arch.tar.xz"
    fi
    [[ "$archive_name" =~ ^node-v22\.[0-9]+\.[0-9]+-linux-(x64|arm64)\.tar\.xz$ ]] \
        || die "无法从校验清单识别 Node.js 归档文件"

    expected_hash="$(awk -v wanted="$archive_name" '
        {
            file = $2;
            sub(/^\*/, "", file);
            if (file == wanted) {
                print $1;
                exit;
            }
        }
    ' "$checksums_file")"
    [[ "$expected_hash" =~ ^[0-9a-fA-F]{64}$ ]] \
        || die "Node.js 校验清单中没有找到：$archive_name"

    archive_path="$WORK_DIR/$archive_name"
    say "下载并校验 Node.js：$archive_name"
    download "$dist_base/$release/$archive_name" "$archive_path"
    printf '%s  %s\n' "$expected_hash" "$archive_path" | sha256sum -c - >/dev/null \
        || die "Node.js SHA-256 校验失败"

    extract_dir="$WORK_DIR/node-extract"
    mkdir -p "$extract_dir" "$TOOLS_DIR"
    tar -xJf "$archive_path" -C "$extract_dir"
    extracted_dir="$extract_dir/${archive_name%.tar.xz}"
    [ -x "$extracted_dir/bin/node" ] || die "Node.js 归档内容不完整"

    target_dir="$TOOLS_DIR/${archive_name%.tar.xz}"
    if [ ! -d "$target_dir" ]; then
        mv "$extracted_dir" "$target_dir"
    fi
    chown -R root:root "$target_dir"
    if [ -e "$NODE_LINK" ] && [ ! -L "$NODE_LINK" ]; then
        die "Node.js 当前路径不是符号链接，请人工检查：$NODE_LINK"
    fi
    ln -sfn "$target_dir" "$NODE_LINK"
}

choose_node() {
    local candidate npm_candidate
    if [ -n "${FYT_NODE_BIN:-}" ]; then
        candidate="$FYT_NODE_BIN"
        [ -x "$candidate" ] || candidate="$(command -v "$FYT_NODE_BIN" 2>/dev/null || true)"
        node_is_compatible "$candidate" \
            || die "FYT_NODE_BIN 不是兼容的 Node 20.19+ 或 Node 22+"
        npm_candidate="$(dirname "$candidate")/npm"
        [ -x "$npm_candidate" ] || die "FYT_NODE_BIN 同目录缺少 npm"
        NODE_BIN="$candidate"
        NPM_BIN="$npm_candidate"
        return 0
    fi

    candidate="$(command -v node 2>/dev/null || true)"
    npm_candidate="$(command -v npm 2>/dev/null || true)"
    if node_is_compatible "$candidate" && [ -n "$npm_candidate" ]; then
        NODE_BIN="$candidate"
        NPM_BIN="$npm_candidate"
        return 0
    fi

    if node_is_compatible "$NODE_LINK/bin/node" && [ -x "$NODE_LINK/bin/npm" ]; then
        NODE_BIN="$NODE_LINK/bin/node"
        NPM_BIN="$NODE_LINK/bin/npm"
        return 0
    fi

    install_node
    NODE_BIN="$NODE_LINK/bin/node"
    NPM_BIN="$NODE_LINK/bin/npm"
    node_is_compatible "$NODE_BIN" || die "自动安装的 Node.js 版本不可用"
}

install_base_tools
mkdir -p "$INSTALL_ROOT" "$TOOLS_DIR" "$NPM_CACHE" "$(dirname "$LOCK_FILE")"
chown root:root "$INSTALL_ROOT" "$TOOLS_DIR" "$NPM_CACHE"
chmod 755 "$INSTALL_ROOT" "$TOOLS_DIR"
chmod 700 "$NPM_CACHE"

# 同一台服务器只允许一个 Git 部署过程；锁在脚本退出时由内核自动释放。
exec 9>"$LOCK_FILE"
flock -n 9 || die "已有 Git 部署进程正在运行，请等待其完成"

WORK_DIR="$(mktemp -d "$INSTALL_ROOT/.git-deploy.XXXXXX")"
CHECKOUT_DIR="$WORK_DIR/source"
BUNDLE_DIR="$WORK_DIR/bundle"

say "从远程仓库克隆：$GIT_REPO"
say "部署分支或标签：$GIT_REF"
# 禁止交互式凭据提示，公开仓库可直接克隆；若未来改回私有仓库，应由管理员显式配置
# SSH 凭据或 Git credential helper，不能把 Token 写入仓库地址或部署文档。
GIT_TERMINAL_PROMPT=0 git clone \
    --depth 1 --single-branch --branch "$GIT_REF" \
    "$GIT_REPO" "$CHECKOUT_DIR"

DEPLOY_COMMIT="$(git -C "$CHECKOUT_DIR" rev-parse HEAD)"
DEPLOY_COMMIT="${DEPLOY_COMMIT,,}"
[[ "$DEPLOY_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "无法取得克隆提交哈希"
if [ -n "$EXPECTED_COMMIT" ] && [[ "$DEPLOY_COMMIT" != "$EXPECTED_COMMIT"* ]]; then
    die "远程提交与期望值不一致：期望 $EXPECTED_COMMIT，实际 $DEPLOY_COMMIT"
fi
say "已取得提交：${DEPLOY_COMMIT:0:12}"

for required in \
    web_server.py web_backend core requirements-runtime.txt \
    web-app/package.json web-app/package-lock.json \
    packaging/linux/install.sh packaging/linux/fyt-web.service; do
    [ -e "$CHECKOUT_DIR/$required" ] || die "仓库缺少部署所需内容：$required"
done

choose_node
say "使用 Node.js：$($NODE_BIN --version)"
say "安装 Web 前端依赖..."
NPM_CONFIG_CACHE="$NPM_CACHE" \
NPM_CONFIG_REGISTRY="${FYT_NPM_REGISTRY:-https://registry.npmjs.org/}" \
PATH="$(dirname "$NODE_BIN"):$PATH" \
    "$NPM_BIN" --prefix "$CHECKOUT_DIR/web-app" ci --no-audit --no-fund

say "构建 Web 前端..."
NPM_CONFIG_CACHE="$NPM_CACHE" \
NPM_CONFIG_REGISTRY="${FYT_NPM_REGISTRY:-https://registry.npmjs.org/}" \
PATH="$(dirname "$NODE_BIN"):$PATH" \
    "$NPM_BIN" --prefix "$CHECKOUT_DIR/web-app" run build
[ -f "$CHECKOUT_DIR/web-app/dist/index.html" ] \
    || die "Web 前端构建完成后未找到 dist/index.html"

say "组装 Linux 运行载荷..."
mkdir -p "$BUNDLE_DIR/web-app"
cp -a "$CHECKOUT_DIR/web_server.py" "$BUNDLE_DIR/"
cp -a "$CHECKOUT_DIR/web_backend" "$BUNDLE_DIR/"
cp -a "$CHECKOUT_DIR/core" "$BUNDLE_DIR/"
cp -a "$CHECKOUT_DIR/web-app/dist" "$BUNDLE_DIR/web-app/"
cp -a "$CHECKOUT_DIR/requirements-runtime.txt" "$BUNDLE_DIR/requirements.txt"
for source in "$CHECKOUT_DIR/packaging/linux/"*.sh "$CHECKOUT_DIR/packaging/linux/"*.service; do
    [ -f "$source" ] || continue
    cp -a "$source" "$BUNDLE_DIR/"
done

DEPLOY_VERSION="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$CHECKOUT_DIR/core/version.py" | head -n 1)"
[ -n "$DEPLOY_VERSION" ] || die "无法从 core/version.py 读取版本号"
printf '%s\n' "$DEPLOY_VERSION" > "$BUNDLE_DIR/VERSION"
printf '%s\n' "$DEPLOY_COMMIT" > "$BUNDLE_DIR/SOURCE_COMMIT"
printf '%s\n' "$GIT_REF" > "$BUNDLE_DIR/SOURCE_REF"

say "开始安装版本 $DEPLOY_VERSION..."
# install.sh 在停服前完成 Python 环境和源码编译检查，并负责数据备份、原子切换、健康检查
# 与回滚。这里不复制、更改或删除 /var/lib/fyt-web。
bash "$BUNDLE_DIR/install.sh"

say "Git 部署完成：v$DEPLOY_VERSION (${DEPLOY_COMMIT:0:12})"
say "以后升级可执行：sudo bash $APP_DIR/deploy-from-git.sh"
