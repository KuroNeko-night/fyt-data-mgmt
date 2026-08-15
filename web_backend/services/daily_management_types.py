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

    # 锁域分工：db_lock 串行化 SQLite 事务；storage_lock 只包围“文件移动 + 索引删除”的补偿段。
    db_lock: Any
    db: Callable[[], Any]
    storage_lock: Any
    data_root: Path
    # request_max_upload_bytes 是服务端统一请求体上限；max_upload_bytes 是日清资料/计划的 50 MB 业务上限。
    request_max_upload_bytes: int
    max_upload_bytes: int
    # 人员、事项类别和状态白名单来自配置，服务端拒绝客户端提交的未定义值。
    person_types: set[str] | frozenset[str]
    brief_categories: set[str] | frozenset[str]
    brief_statuses: set[str] | frozenset[str]
    # 时间与业务日期统一走配置模块的时区口径；safe_name 用于剔除上传文件名中的目录分隔符。
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
    # Core 模块只被调用、不被复制，表格解析与 Excel 算法仍以 core/ 为唯一事实源。
    production_plan_core: Any
    arrival_core: Any
    safety_check_core: Any
    daily_report_core: Any
    # 快照构造、目录体积统计和审计回调由组合根注入，领域模块保持纯组合。
    build_daily_report_snapshot: Callable[[str, Any], dict[str, object]]
    tree_size: Callable[[Path], int]
    write_audit: Callable[[int | None, str, int | None], None]
