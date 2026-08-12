#!/usr/bin/env bash
# 备份运行数据与服务配置。
#
# 为取得 SQLite、上传目录和索引文件的一致快照，服务运行时会短暂停止；EXIT 陷阱保证
# 归档或校验失败后仍尝试恢复服务。归档从文件系统根目录记录数据和配置的相对绝对路径，
# 便于灾难恢复时还原到标准位置。轮换只删除本脚本命名的旧备份及其校验文件。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"  # 从安装目录加载 common.sh，不依赖调用者当前目录。
# shellcheck source=common.sh
. "$DIR/common.sh"

if [ "$(id -u)" -ne 0 ]; then
    # 备份目录和配置仅 root 可读，整体重新执行比对多条归档命令分别 sudo 更可靠。
    command -v sudo >/dev/null 2>&1 || fyt_die "备份需要 root 权限，且当前系统没有 sudo"
    exec sudo env \
        FYT_SERVICE_NAME="$FYT_SERVICE_NAME" \
        FYT_INSTALL_DIR="$FYT_INSTALL_DIR" \
        FYT_CONFIG_DIR="$FYT_CONFIG_DIR" \
        FYT_DATA_DIR="$FYT_DATA_DIR" \
        FYT_BACKUP_DIR="$FYT_BACKUP_DIR" \
        FYT_ENV_FILE="$FYT_ENV_FILE" \
        BACKUP_KEEP="${BACKUP_KEEP:-}" \
        bash "$0" "$@"
fi

fyt_require_install
KEEP="${BACKUP_KEEP:-14}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || fyt_die "BACKUP_KEEP 必须是正整数"
mkdir -p "$FYT_BACKUP_DIR"
chmod 700 "$FYT_BACKUP_DIR"

RESTART=0  # 只在脚本主动停止了服务时才负责重新启动。
if systemctl is-active --quiet "$FYT_SERVICE_NAME"; then
    printf '[提示] 为保障数据一致性，备份期间将短暂停止服务...\n'
    systemctl stop "$FYT_SERVICE_NAME"
    RESTART=1
fi

restore_service() {
    # 既由 EXIT 陷阱调用，也在成功末尾显式调用；RESTART 清零可防止启动两次。
    if [ "$RESTART" -eq 1 ]; then
        systemctl start "$FYT_SERVICE_NAME" || true
        printf '[提示] 服务已恢复启动\n'
    fi
}
trap restore_service EXIT

TS="$(date +%Y%m%d-%H%M%S)"
TARGET="$FYT_BACKUP_DIR/fyt-data-$TS.tar.gz"
# 去掉前导斜杠并以 / 为归档根，避免 tar 写入绝对路径警告，同时保留恢复目录层级。
tar_paths=("${FYT_DATA_DIR#/}")
[ -f "$FYT_ENV_FILE" ] && tar_paths+=("${FYT_ENV_FILE#/}")
tar -czf "$TARGET" -C / "${tar_paths[@]}"
sha256sum "$TARGET" > "$TARGET.sha256"  # 校验文件与归档同名，便于异机恢复前验证传输完整性。

# 先按修改时间倒序，只选择超出保留数量的 fyt-data 归档；其他安装备份不受影响。
mapfile -t OLD_BACKUPS < <(find "$FYT_BACKUP_DIR" -maxdepth 1 -type f -name 'fyt-data-*.tar.gz' -printf '%T@ %p\n' | sort -nr | tail -n +$((KEEP + 1)) | cut -d' ' -f2-)
for old in "${OLD_BACKUPS[@]}"; do
    [ -n "$old" ] || continue
    rm -f -- "$old" "$old.sha256"
done
restore_service
RESTART=0
trap - EXIT  # 成功路径已恢复服务，撤销陷阱避免 shell 退出时重复执行。
printf '[完成] 备份完成：%s（保留最近 %s 份）\n' "$TARGET" "$KEEP"
printf '       校验文件：%s.sha256\n' "$TARGET"
printf '       恢复时请停止服务后，在服务器根目录解压该 tar.gz。\n'
