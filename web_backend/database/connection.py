"""SQLite 连接、外键和服务端数据库锁。

本模块是数据库访问的唯一入口：``DB_LOCK`` 用可重入锁串行化读改写复合操作，``db``
返回启用外键与行对象的短连接，``ManagedConnection`` 保证 ``with`` 块结束后立即释放
SQLite 文件句柄，供 Windows 备份与恢复安全执行。
"""

from __future__ import annotations

import sqlite3
import threading

from pathlib import Path

from ..config import DATA_ROOT, DB_PATH


DB_LOCK = threading.RLock()  # 同一请求的辅助函数可能再次进入数据库区段，必须使用可重入锁避免自锁。


class ManagedConnection(sqlite3.Connection):
    """让 ``with db()`` 在提交后同时释放 Windows 文件句柄。"""

    def __exit__(self, *args):
        """结束事务后立即关闭连接，并保留标准 SQLite 上下文管理语义。

        ``sqlite3.Connection.__exit__`` 会根据代码块是否抛出异常决定提交还是回滚，
        因此必须先调用父类实现，再在 ``finally`` 中关闭句柄。若顺序相反，提交会在已
        关闭连接上执行；若只依赖垃圾回收，Windows 下备份、恢复和临时目录清理可能因
        数据库仍被占用而失败。
        """
        try:
            return super().__exit__(*args)  # 先让 sqlite3 根据异常状态提交或回滚事务。
        finally:
            self.close()  # Windows 对打开的 SQLite 文件保持独占语义，测试和备份前必须及时释放句柄。


def db(data_root: Path | None = None, db_path: Path | None = None) -> sqlite3.Connection:
    """打开启用外键和行对象的短生命周期 SQLite 连接。

    生产调用通常不传参数，测试和恢复校验则可注入临时数据根与数据库路径。连接允许
    跨线程使用，是因为标准库 HTTP 服务会为请求创建线程；上层仍约定每个连接只在创建
    它的请求或事务块内使用，并由 ``DB_LOCK`` 保护需要读改写一致性的复合操作。
    """
    active_root = data_root or DATA_ROOT  # 测试传入临时目录，生产环境使用配置模块的持久数据根。
    active_path = db_path or DB_PATH
    active_root.mkdir(parents=True, exist_ok=True)  # 首次启动允许在空数据目录直接建库。
    connection = sqlite3.connect(
        active_path,
        check_same_thread=False,  # HTTP 请求在线程池中执行，连接对象仍只在创建它的请求块内使用。
        factory=ManagedConnection,
    )
    connection.row_factory = sqlite3.Row  # 业务层按列名取值，避免 SQL 列顺序变化破坏代码。
    connection.execute("PRAGMA foreign_keys = ON")  # SQLite 默认不强制外键，每个新连接都必须显式开启。
    return connection
