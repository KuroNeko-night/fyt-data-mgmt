"""Web 数据备份的创建、校验、下载与恢复。

备份包含一致的 SQLite 快照、主数据档案和业务文件，并用清单记录每个文件的
大小与 SHA-256。恢复前会再次创建安全备份，替换失败时按逆序恢复原文件。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from web_backend.errors import ApiError
from web_backend.config import BUSINESS_TZ


@dataclass(frozen=True)
class BackupDependencies:
    """备份服务的运行时依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    data_root: Path
    db_path: Path
    job_lock: Any
    job_processes: dict[str, Any]
    auto_backup_keep: int
    version: str
    now_iso: Callable[[], str]
    master_data_import_root: Callable[[], Path]
    catalog_file_lock: Callable[[str], Any]
    init_db: Callable[[], None]
    write_audit: Callable[[int, str], None]


def _file_sha256(path: Path) -> str:
    """分块计算文件 SHA-256，避免将大文件一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_id(path: str, suffix: str = "") -> str:
    """从管理员备份路由提取只含安全字符的备份编号。"""
    prefix = "/api/admin/backups/"
    ending = f"/{suffix}" if suffix else ""
    if not path.startswith(prefix) or (ending and not path.endswith(ending)):
        raise ApiError(HTTPStatus.BAD_REQUEST, "备份编号无效")
    value = path[len(prefix):]
    if ending:
        value = value[:-len(ending)]
    value = value.strip("/")
    if not value or not all(char.isalnum() or char in "-_" for char in value):
        raise ApiError(HTTPStatus.BAD_REQUEST, "备份编号无效")
    return value


def create_web_backup(
    deps: BackupDependencies,
    created_by: int | None = None,
    auto: bool = False,
) -> dict[str, object]:
    """创建包含 SQLite 快照、主数据和用户业务文件的可校验 ZIP 备份。

    数据库使用 SQLite Backup API 获取一致快照，文件写入临时 ZIP 并生成逐文件大小与
    SHA-256 清单，最后通过同目录原子改名发布。只收集定义好的用户、回收站和主数据目录，
    拒绝符号链接；生成后立即完整回读校验，避免留下看似成功但实际不可恢复的备份。
    """
    backup_root = deps.data_root / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    created_at = deps.now_iso()
    prefix = "auto-" if auto else ""
    backup_id = f"{prefix}{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"  # 时间便于人工识别，随机后缀避免同秒冲突。
    final_path = backup_root / f"{backup_id}.zip"
    temp_db = backup_root / f".{backup_id}.sqlite3"  # SQLite 在线备份先写独立快照，不直接压缩正在变化的数据库文件。
    temp_zip = backup_root / f".{backup_id}.zip.tmp"  # ZIP 完整生成并校验前不使用正式文件名。
    entries: list[dict[str, object]] = []
    try:
        with deps.db_lock:  # 快照期间串行数据库写入，确保关联表和主表处于同一时刻。
            source = deps.db()
            target = sqlite3.connect(temp_db)
            try:
                source.backup(target)  # 使用 SQLite Backup API，可在连接开启时生成一致数据库副本。
            finally:
                target.close()
                source.close()
        with zipfile.ZipFile(
            temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
        ) as archive:
            archive.write(temp_db, "database/accounts.sqlite3")
            entries.append({
                "path": "database/accounts.sqlite3",
                "size": temp_db.stat().st_size,
                "sha256": _file_sha256(temp_db),
            })
            catalog_path = deps.data_root / "catalog.json"
            with deps.catalog_file_lock(str(catalog_path)):  # 主数据 JSON 采用独立文件锁，避免恰在原子替换过程中读取。
                if catalog_path.is_file():
                    archive.write(catalog_path, "database/catalog.json")
                    entries.append({
                        "path": "database/catalog.json",
                        "size": catalog_path.stat().st_size,
                        "sha256": _file_sha256(catalog_path),
                    })
            roots = (
                deps.data_root / "users",
                deps.data_root / "trash",
                deps.master_data_import_root(),
            )
            for source_root in roots:
                if not source_root.is_dir():
                    continue
                for item in sorted(source_root.rglob("*")):  # 排序让清单和压缩包内容稳定，便于比较和排障。
                    if not item.is_file() or item.is_symlink():  # 拒绝符号链接，防止备份读取数据根之外的文件。
                        continue
                    relative = item.relative_to(deps.data_root).as_posix()
                    archive.write(item, relative)
                    entries.append({
                        "path": relative,
                        "size": item.stat().st_size,
                        "sha256": _file_sha256(item),
                    })
            manifest = {
                "format": 1,
                "app": "峰运通数据管理系统",
                "version": deps.version,
                "backup_id": backup_id,
                "created_at": created_at,
                "created_by": created_by,
                "files": entries,
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        os.replace(temp_zip, final_path)  # 同目录原子改名，正式备份名只对应完整 ZIP。
        try:
            verify_web_backup(final_path)  # 创建后立即回读全部清单与哈希，磁盘异常不会留下“可用”假象。
        except ValueError:
            final_path.unlink(missing_ok=True)
            raise
    finally:
        temp_db.unlink(missing_ok=True)
        temp_zip.unlink(missing_ok=True)
    return {
        "id": backup_id,
        "created_at": created_at,
        "size": final_path.stat().st_size,
        "file_count": len(entries),
    }


_BACKUP_DATABASE_FILES = {"database/accounts.sqlite3", "database/catalog.json"}
_BACKUP_DATA_PREFIXES = ("users/", "trash/", "master-data-imports/")


def _backup_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    """读取并验证备份清单顶层结构和格式版本。"""
    if "manifest.json" not in archive.namelist():
        raise ValueError("备份缺少校验清单")
    manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("format") != 1:
        raise ValueError("备份格式不受支持")
    if not isinstance(manifest.get("files"), list):
        raise ValueError("备份文件清单无效")
    return manifest


def _safe_backup_entry_name(entry: object) -> str:
    """验证单条清单记录及其数据根白名单，返回可交给 ZIP 读取的相对路径。"""
    if not isinstance(entry, dict):
        raise ValueError("备份文件清单无效")
    name = str(entry.get("path") or "")
    parts = Path(name.replace("/", os.sep)).parts  # 统一为当前平台路径段后检查 ``..`` 穿越。
    allowed = name in _BACKUP_DATABASE_FILES or name.startswith(_BACKUP_DATA_PREFIXES)
    if not name or name.startswith(("/", "\\")) or ".." in parts or not allowed:
        raise ValueError("备份包含不安全或未知路径")
    return name


def _archive_entry_digest(archive: zipfile.ZipFile, name: str) -> tuple[str, int]:
    """流式计算 ZIP 条目的 SHA-256 和解压后大小。"""
    digest = hashlib.sha256()
    size = 0
    with archive.open(name) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _verify_backup_entry(archive: zipfile.ZipFile, entry: object) -> str:
    """校验一条清单路径、哈希和大小，并返回其安全相对路径。"""
    name = _safe_backup_entry_name(entry)
    digest, size = _archive_entry_digest(archive, name)
    if digest != entry.get("sha256"):
        raise ValueError(f"备份文件校验失败：{name}")
    try:
        expected_size = int(entry.get("size") or -1)
    except (TypeError, ValueError) as exc:
        raise ValueError("备份文件清单无效") from exc
    if size != expected_size:
        raise ValueError(f"备份文件大小不符：{name}")
    return name


def verify_web_backup(path: Path) -> dict[str, object]:
    """验证备份结构、允许路径、清单哈希和最低必要数据库内容。

    清单必须覆盖 ZIP 中除自身外的全部条目，路径只能落在系统定义的数据目录，逐项流式
    计算哈希和大小。该函数只负责包级校验；恢复前还会对数据库执行 SQLite 结构检查。
    """
    try:
        with zipfile.ZipFile(path, "r") as archive:
            listed_names = archive.namelist()
            names = set(listed_names)
            if len(names) != len(listed_names):
                raise ValueError("备份包含重复文件路径")  # 重复 ZIP 条目会让校验与恢复读取到不同内容。
            manifest = _backup_manifest(archive)
            expected_names = {"manifest.json"}
            for entry in manifest["files"]:
                name = _verify_backup_entry(archive, entry)
                if name in expected_names:
                    raise ValueError("备份文件清单包含重复路径")
                expected_names.add(name)
            # ZIP 实际条目必须与清单一一对应；账号数据库是可恢复备份的最低必要内容。
            if names != expected_names or "database/accounts.sqlite3" not in expected_names:
                raise ValueError("备份内容与清单不一致")
            return manifest
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
        raise ValueError("备份文件损坏或无法读取") from exc


def auto_backup_if_due(deps: BackupDependencies) -> str:
    """每天执行一次自动备份，并滚动保留最近若干份自动备份。

    日期状态文件只在备份成功后原子更新；损坏或缺失状态会按未执行处理。清理仅匹配
    ``auto-`` 前缀，不会触碰管理员手工备份，自动清理失败也不删除状态，以便下一周期
    继续重试。
    """
    state_path = deps.data_root / "auto_backup_state.json"
    today = datetime.now(BUSINESS_TZ).strftime("%Y%m%d")  # 按业务时区去重，避免服务器本地时区导致同一天重复备份或漏备份。
    last = ""
    try:
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            last = str(state.get("last_auto_backup") or "") if isinstance(state, dict) else ""
    except (OSError, ValueError, json.JSONDecodeError):
        last = ""
    if last == today:  # 状态文件保证一天最多生成一次自动备份。
        return ""
    info = create_web_backup(deps, None, auto=True)
    temp_state = state_path.with_suffix(".tmp")
    temp_state.write_text(
        json.dumps({"last_auto_backup": today}, ensure_ascii=False), encoding="utf-8",
    )
    os.replace(temp_state, state_path)  # 备份成功后才原子记录日期，失败时下一维护周期会重试。
    removed = 0
    try:
        files = sorted(
            (deps.data_root / "backups").glob("auto-*.zip"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in files[deps.auto_backup_keep:]:  # 只滚动删除 auto- 前缀，管理员手工备份永不自动清理。
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return f"已创建自动备份 {info['id']}，清理超龄自动备份 {removed} 份"


def create_backup(handler: Any, deps: BackupDependencies) -> None:
    """由管理员手工创建并校验备份，同时登记审计记录。

    只有 ``create_web_backup`` 完成 ZIP 原子落盘和哈希回读后才返回成功；审计记录使用
    已生成的备份编号，便于后续下载、删除或恢复操作形成完整链路。
    """
    actor = handler.require_user(admin=True)
    info = create_web_backup(deps, int(actor["id"]))
    deps.write_audit(int(actor["id"]), f"create_backup:{info['id']}")
    handler.send_json(
        {"message": "备份已创建并完成校验", "backup": info},
        HTTPStatus.CREATED,
    )


def list_backups(handler: Any, deps: BackupDependencies) -> None:
    """列出备份目录中的 ZIP，并把无法读取清单的文件标记为损坏。

    列表页只读取清单摘要，不对每个大文件重新计算哈希，以免打开管理页时阻塞服务。
    真正恢复前仍会调用完整校验；单个坏包不会阻止其余可用备份显示。
    """
    handler.require_user(admin=True)
    backups = []
    root = deps.data_root / "backups"
    if root.is_dir():
        try:
            paths = sorted(root.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            paths = []
        for path in paths:
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    manifest = json.loads(archive.read("manifest.json"))
                    if not isinstance(manifest, dict):
                        raise ValueError("备份清单格式无效")
                backups.append({
                    "id": path.stem,
                    "created_at": str(manifest.get("created_at") or ""),
                    "version": str(manifest.get("version") or ""),
                    "file_count": len(manifest.get("files") or []),
                    "size": path.stat().st_size,
                    "status": "ready",
                })
            except (OSError, ValueError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                backups.append({
                    "id": path.stem,
                    "created_at": "",
                    "version": "",
                    "file_count": 0,
                    "size": size,
                    "status": "damaged",
                })
    handler.send_json({"backups": backups})


def download_backup(handler: Any, path: str, deps: BackupDependencies) -> None:
    """下载一个管理员可见的备份 ZIP，并记录敏感数据导出审计。

    备份编号只允许字母、数字、短横线和下划线，再拼接到固定备份目录，因此不能借路径
    参数读取目录外文件。下载不在此处重复校验完整哈希，恢复流程会执行强校验。
    """
    actor = handler.require_user(admin=True)
    backup_id = _backup_id(path, "download")
    target = deps.data_root / "backups" / f"{backup_id}.zip"
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "备份不存在")
    deps.write_audit(int(actor["id"]), f"download_backup:{backup_id}")
    handler.send_file(target, content_type="application/zip")


def delete_backup(handler: Any, path: str, deps: BackupDependencies) -> None:
    """永久删除指定备份文件并记录管理员审计。

    备份不进入同一数据根下的业务回收站，否则下一份备份会递归包含旧备份并快速膨胀。
    因此该操作是物理删除，只允许管理员对经过格式校验的备份编号执行。
    """
    actor = handler.require_user(admin=True)
    backup_id = _backup_id(path)
    target = deps.data_root / "backups" / f"{backup_id}.zip"
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "备份不存在")
    target.unlink()
    deps.write_audit(int(actor["id"]), f"delete_backup:{backup_id}")
    handler.send_json({"message": "备份已删除"})


def _validate_restored_database(path: Path) -> None:
    """验证暂存 SQLite 的页结构和最低必要业务表。

    ZIP 哈希只能证明文件与创建清单一致，不能证明它真是可打开的本系统数据库；恢复前
    还需要 ``quick_check`` 和核心表集合校验，避免用无关 SQLite 文件替换正式账号库。
    """
    try:
        connection = sqlite3.connect(path)
        try:
            check = connection.execute("PRAGMA quick_check").fetchone()  # 恢复前先验证 SQLite 页结构和索引一致性。
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "备份中的数据库校验失败") from exc
    required = {"users", "sessions", "web_jobs", "uploads"}  # 缺少核心表说明不是本系统的有效数据库。
    if not check or check[0] != "ok" or not required.issubset(tables):
        raise ApiError(HTTPStatus.BAD_REQUEST, "备份中的数据库校验失败")


def _extract_backup(source: Path, stage: Path, manifest: dict[str, object]) -> None:
    """按已验证清单把备份内容流式解压到暂存目录。

    调用前必须先通过 ``verify_web_backup``，因此清单路径已经过白名单和目录穿越校验。
    仍然逐项按清单解压而不调用全量解压，确保未登记的 ZIP 条目不会落到磁盘。
    """
    with zipfile.ZipFile(source, "r") as archive:
        for entry in manifest["files"]:
            name = str(entry["path"])
            target = stage / Path(name.replace("/", os.sep))  # 路径安全已由 verify_web_backup 完整校验。
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as input_stream, target.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)


def _restore_staged_data(
    deps: BackupDependencies,
    stage: Path,
    rollback: Path,
    actor_id: int,
    backup_id: str,
) -> None:
    """用暂存数据替换正式数据，并在任一步失败时恢复原状态。

    ``moved`` 保存每个原数据项的回滚位置和正式位置。替换顺序从数据库、主数据到业务
    目录，失败时按逆序恢复，以处理父目录和子资源之间的依赖。恢复完成后运行当前版本
    的幂等迁移，并清除会话和登录失败计数，避免历史安全状态继续生效。
    """
    restored_db = stage / "database" / "accounts.sqlite3"
    restored_catalog = stage / "database" / "catalog.json"
    _validate_restored_database(restored_db)
    moved: list[tuple[Path, Path]] = []  # 记录“回滚位置、正式位置”，失败时按逆序恢复。
    with deps.db_lock:
        try:
            if deps.db_path.exists():
                old_db = rollback / "accounts.sqlite3"
                os.replace(deps.db_path, old_db)  # 旧数据库先移入回滚目录，新数据库才可占用正式路径。
                moved.append((old_db, deps.db_path))
            os.replace(restored_db, deps.db_path)
            if restored_catalog.is_file():
                current_catalog = deps.data_root / "catalog.json"
                if current_catalog.exists():
                    old_catalog = rollback / "catalog.json"
                    os.replace(current_catalog, old_catalog)
                    moved.append((old_catalog, current_catalog))
                os.replace(restored_catalog, current_catalog)
            for name in ("users", "trash", "master-data-imports"):
                current = deps.data_root / name
                old = rollback / name
                incoming = stage / name
                if current.exists():
                    shutil.move(str(current), str(old))
                    moved.append((old, current))
                if incoming.exists():
                    shutil.move(str(incoming), str(current))
            deps.init_db()  # 允许旧版本备份通过当前幂等迁移补齐新增表和字段。
            with deps.db() as connection:
                connection.execute("DELETE FROM sessions")  # 恢复后强制所有设备重新认证，旧 Cookie 不继续有效。
                connection.execute("DELETE FROM login_attempts")  # 登录失败计数属于瞬时安全状态，不从历史备份恢复。
                if connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (actor_id,),
                ).fetchone():
                    connection.execute(
                        "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                        (actor_id, f"restore_backup:{backup_id}", deps.now_iso()),
                    )
        except Exception:  # 删除未完成的新数据，再按移动记录逆序恢复原数据库和目录。
            deps.db_path.unlink(missing_ok=True)
            for old, current in reversed(moved):
                if current.exists():
                    if current.is_dir():
                        shutil.rmtree(current)
                    else:
                        current.unlink()
                shutil.move(str(old), str(current))
            raise


def restore_backup(
    handler: Any,
    path: str,
    body: dict[str, object],
    deps: BackupDependencies,
) -> None:
    """在精确人工确认和安全备份之后恢复数据库与用户数据目录。

    恢复前要求没有运行中的任务，先校验目标备份，再创建当前状态的撤销点；数据在同一
    文件系统暂存并由可补偿替换函数处理。恢复后清除旧会话和登录失败计数，要求所有账号
    重新登录，避免历史 Cookie 或瞬时限流状态跨数据库版本继续生效。
    """
    actor = handler.require_user(admin=True)
    if body.get("confirmation") != "恢复备份":  # 高风险操作要求精确人工确认文本，不能只依赖按钮点击。
        raise ApiError(HTTPStatus.BAD_REQUEST, "请输入“恢复备份”确认操作")
    with deps.job_lock:  # 运行中的任务可能继续写数据库或文件，恢复前必须确保进程表为空闲状态。
        if any(process.poll() is None for process in deps.job_processes.values()):
            raise ApiError(HTTPStatus.CONFLICT, "仍有任务正在运行，请等待任务结束后再恢复")
    backup_id = _backup_id(path, "restore")
    source = deps.data_root / "backups" / f"{backup_id}.zip"
    if not source.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "备份不存在")
    try:
        manifest = verify_web_backup(source)
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    safety = create_web_backup(deps, int(actor["id"]))  # 无论目标备份多旧，恢复前都保留当前状态的撤销点。
    deps.data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=deps.data_root) as temp_name:  # 同数据盘暂存，原子替换不会跨文件系统失败。
        stage = Path(temp_name) / "stage"
        rollback = Path(temp_name) / "rollback"
        stage.mkdir()
        rollback.mkdir()
        _extract_backup(source, stage, manifest)
        _restore_staged_data(
            deps, stage, rollback, int(actor["id"]), backup_id,
        )
    handler.send_json({
        "message": "备份恢复完成，所有账号需要重新登录",
        "safety_backup_id": safety["id"],
    })
