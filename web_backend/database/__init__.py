"""Web SQLite 数据库基础设施。

本包导出连接管理、事务锁和短连接工厂。业务层通过 :data:`DB_LOCK` 串行化读改写复合操作，
通过 :func:`db` 获取已开启外键和行对象的短生命周期连接，并由 ``ManagedConnection`` 在
``with`` 块结束时立即释放 SQLite 文件句柄，保证 Windows 下备份、恢复和临时目录清理不被占用。
"""

from .connection import DB_LOCK, ManagedConnection, db

__all__ = ["DB_LOCK", "ManagedConnection", "db"]

