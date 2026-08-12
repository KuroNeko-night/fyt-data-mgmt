#!/usr/bin/env bash
set -euo pipefail

# Linux/macOS 源码同步入口；默认只提交，追加 --push 才推送到远程仓库。
MESSAGE="同步源码"; PUSH=0; BRANCH="main"; REMOTE_URL=""; DEFAULT_REMOTE_URL="https://github.com/KuroNeko-night/fyt-data-mgmt.git"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --push) PUSH=1 ;;
        --message) shift; MESSAGE="${1:-同步源码}" ;;
        --branch) shift; BRANCH="${1:-main}" ;;
        --remote) shift; REMOTE_URL="${1:-$REMOTE_URL}" ;;
        *) printf '[错误] 未知参数：%s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
command -v git >/dev/null 2>&1 || { printf '[错误] 未找到 Git。\n' >&2; exit 1; }
[ -d .git ] || git init
git branch -M "$BRANCH"
if ! current_remote="$(git remote get-url origin 2>/dev/null)"; then
    current_remote="${REMOTE_URL:-$DEFAULT_REMOTE_URL}"
    git remote add origin "$current_remote"
elif [ -n "$REMOTE_URL" ] && [ "$current_remote" != "$REMOTE_URL" ]; then
    git remote set-url origin "$REMOTE_URL"
    current_remote="$REMOTE_URL"
fi
git add --all
staged="$(git diff --cached --name-only)"
forbidden="$({
    printf '%s\n' "$staged" | grep -E '(^|/)(web-data|docker-data|dist|build|target|node_modules|\.venv|tmp|\.playwright-mcp|\.codex-audit|\.reasonix)(/|$)|\.(sqlite|sqlite3|db|log|pem|key|cer|crt|pfx|p12|zip|bak|secret|token)$' || true
    printf '%s\n' "$staged" | grep -E '(^|/)secrets/' | grep -Ev '^secrets/admin-password\.example\.txt$' || true
    printf '%s\n' "$staged" | grep -E '(^|/)\.env($|\.)' | grep -Ev '(^|/)\.env\.example$' || true
} | sed '/^$/d' | sort -u)"
if [ -n "$forbidden" ]; then git reset; printf '[错误] 检测到不允许同步的运行数据或敏感文件：\n%s\n' "$forbidden" >&2; exit 1; fi
if git diff --cached --quiet; then
    if [ "$PUSH" -eq 1 ] && git rev-parse --verify HEAD >/dev/null 2>&1; then
        git push -u origin "$BRANCH"
        printf '已有本地提交已推送到 %s 的 %s 分支。\n' "$current_remote" "$BRANCH"
    else
        printf '没有需要提交的源码变更。\n'
    fi
    exit 0
fi
git commit -m "$MESSAGE"
if [ "$PUSH" -eq 1 ]; then git push -u origin "$BRANCH"; printf '源码已推送到 %s 的 %s 分支。\n' "$current_remote" "$BRANCH"; else printf '本地提交已完成；追加 --push 才会推送。\n'; fi
