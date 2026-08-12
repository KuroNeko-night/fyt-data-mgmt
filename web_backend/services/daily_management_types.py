"""日清维护服务共享的依赖类型。

人员考勤、事项维护和文件资料被拆成独立模块后，三者仍需要同一组数据库、路径、Core
与展示能力。本文件只声明依赖契约，不导入任何领域实现，因此不会形成循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class DailyManagementDependencies:
    """日清维护与资料处理服务依赖。

    依赖对象显式传入数据库、锁、路径和 Core 模块，使各领域服务可以使用临时目录与
    固定业务日期进行合成测试。数据库锁保护 SQLite 复合事务；存储锁只包围文件与索引
    必须同步提交的场景，避免普通列表查询被大文件移动长时间阻塞。
    """

    db_lock: Any
    db: Callable[[], Any]
    storage_lock: Any
    data_root: Path
    request_max_upload_bytes: int
    max_upload_bytes: int
    person_types: set[str] | frozenset[str]
    brief_categories: set[str] | frozenset[str]
    brief_statuses: set[str] | frozenset[str]
    now_iso: Callable[[], str]
    business_today: Callable[[], Any]
    report_date: Callable[[object], str]
    safe_name: Callable[[object], str]
    daily_person_public: Callable[[Any], dict[str, object]]
    production_group_public: Callable[..., dict[str, object]]
    daily_attendance_public: Callable[[Any], dict[str, object]]
    production_attendance_public: Callable[[Any], dict[str, object]]
    daily_brief_public: Callable[[Any], dict[str, object]]
    production_plan_public: Callable[[Any], dict[str, object]]
    source_upload_public: Callable[[Any], dict[str, object]]
    production_plan_core: Any
    arrival_core: Any
    safety_check_core: Any
    daily_report_core: Any
    build_daily_report_snapshot: Callable[[str, Any], dict[str, object]]
    tree_size: Callable[[Path], int]
    write_audit: Callable[[int | None, str, int | None], None]
