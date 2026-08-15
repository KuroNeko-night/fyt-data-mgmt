"""日清维护服务兼容门面。

具体职责已经拆分为人员考勤、事项维护和资料文件三个模块。本文件保留原导入路径和公开
函数名称，使 Web 入口、测试与部署脚本无需同时修改；新增逻辑应进入对应领域模块。
"""

from web_backend.services.daily_management_types import DailyManagementDependencies
from web_backend.services.daily_people import (
    attendance_rows,
    create_daily_person,
    create_daily_production_group,
    delete_daily_person,
    delete_daily_production_group,
    list_daily_attendance,
    list_daily_people,
    list_daily_production_groups,
    production_attendance_rows,
    save_daily_attendance,
    update_daily_person,
    update_daily_production_group,
)
from web_backend.services.daily_briefs import (
    create_daily_brief_item,
    delete_daily_brief_item,
    list_daily_brief_items,
    update_daily_brief_item,
)
from web_backend.services.daily_files import (
    daily_report,
    delete_daily_production_plan,
    delete_daily_source,
    download_daily_production_plan,
    download_daily_source,
    download_daily_source_image,
    export_daily_report,
    list_daily_production_plans,
    list_daily_sources,
    upload_daily_production_plan,
    upload_daily_source,
)


# 兼容门面白名单：路由、测试和部署脚本只从这里导入稳定名称，不直接依赖拆分模块。
__all__ = [
    "DailyManagementDependencies",
    "attendance_rows",
    "production_attendance_rows",
    "list_daily_people",
    "create_daily_person",
    "update_daily_person",
    "delete_daily_person",
    "list_daily_production_groups",
    "create_daily_production_group",
    "update_daily_production_group",
    "delete_daily_production_group",
    "list_daily_attendance",
    "save_daily_attendance",
    "list_daily_brief_items",
    "create_daily_brief_item",
    "update_daily_brief_item",
    "delete_daily_brief_item",
    "upload_daily_production_plan",
    "list_daily_production_plans",
    "download_daily_production_plan",
    "delete_daily_production_plan",
    "upload_daily_source",
    "list_daily_sources",
    "download_daily_source",
    "download_daily_source_image",
    "delete_daily_source",
    "daily_report",
    "export_daily_report",
]
