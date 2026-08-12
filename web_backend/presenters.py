"""把数据库记录转换为稳定、可公开的 Web API 数据结构。

本模块只负责字段整理、兼容旧数据和计算前端权限，不执行数据库查询或文件写入。
这样领域服务可以复用同一套输出结构，服务入口也无需了解每张表的展示细节。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from urllib.parse import quote

from core import library as core_library
from core import workshop_issue_core

from web_backend.config import WORKSHOP_ISSUE_TEMPLATE_FIELDS
from web_backend.serializers import json_list, json_object


def user_public(row: sqlite3.Row) -> dict[str, object]:
    """输出不包含密码摘要、盐值等敏感字段的账号信息。"""
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
        "approved_at": row["approved_at"],
    }


def daily_person_public(row: sqlite3.Row) -> dict[str, object]:
    """把参会人员主数据转换为前端稳定字段。"""
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "person_type": row["person_type"],
        "unit": row["unit"],
        "shift": row["shift"],
        "sort_order": int(row["sort_order"] or 0),
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def daily_attendance_public(
    row: sqlite3.Row,
    person: sqlite3.Row | None = None,
) -> dict[str, object]:
    """组合参会人员主数据与指定日期的考勤记录。"""
    keys = set(row.keys())  # 部分查询包含人员 JOIN 字段，兼容只传考勤表行的内部调用。
    return {
        "id": int(row["id"]) if row["id"] is not None else None,
        "report_date": row["report_date"],
        "person_id": int(row["person_id"]),
        "name": row["name"] if "name" in keys else (person["name"] if person else ""),
        "person_type": (
            row["person_type"]
            if "person_type" in keys
            else (person["person_type"] if person else "participant")
        ),
        "unit": row["unit"] if "unit" in keys else (person["unit"] if person else ""),
        "shift": row["shift"] if "shift" in keys else (person["shift"] if person else ""),
        "present": bool(row["present"]),
        "status": row["status"],
        "reason": row["reason"],
        "updated_by": int(row["updated_by"]) if row["updated_by"] is not None else None,
        "updated_at": row["updated_at"],
    }


def daily_production_shift_public(row: sqlite3.Row) -> dict[str, object]:
    """输出生产班组下的班次和编制信息。"""
    return {
        "id": int(row["id"]),
        "group_id": int(row["group_id"]),
        "name": row["name"],
        "staffing_count": int(row["staffing_count"] or 0),
        "sort_order": int(row["sort_order"] or 0),
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def daily_production_group_public(
    row: sqlite3.Row,
    shifts: Sequence[sqlite3.Row] = (),
) -> dict[str, object]:
    """输出生产班组及其班次列表，供管理页维护。"""
    shift_values = [daily_production_shift_public(item) for item in shifts]  # 先统一班次字段，再由规范化结果计算有效编制。
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "sort_order": int(row["sort_order"] or 0),
        "active": bool(row["active"]),
        "staffing_count": sum(
            int(item["staffing_count"])
            for item in shift_values
            if bool(item["active"])
        ),
        "shifts": shift_values,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def daily_production_attendance_public(row: sqlite3.Row) -> dict[str, object]:
    """输出生产班组当日出勤、编制和差异。"""
    staffing_count = int(row["staffing_count"] or 0)
    attendance_count = int(row["attendance_count"] or 0)
    return {
        "id": int(row["id"]) if row["id"] is not None else None,
        "report_date": row["report_date"],
        "group_id": int(row["group_id"]),
        "group_name": row["group_name"],
        "shift_id": int(row["shift_id"]),
        "shift_name": row["shift_name"],
        "staffing_count": staffing_count,
        "attendance_count": attendance_count,
        "difference": staffing_count - attendance_count,  # 正数表示缺员，负数表示实际出勤超过编制。
        "note": row["note"],
        "updated_by": int(row["updated_by"]) if row["updated_by"] is not None else None,
        "updated_at": row["updated_at"],
    }


def daily_brief_public(row: sqlite3.Row) -> dict[str, object]:
    """输出重大事项、通报和会议待办的公共字段。"""
    return {
        "id": row["id"],
        "report_date": row["report_date"],
        "category": row["category"],
        "unit": row["unit"],
        "owner": row["owner"],
        "title": row["title"],
        "description": row["description"],
        "due_date": row["due_date"],
        "progress": row["progress"],
        "status": row["status"],
        "created_by": int(row["created_by"]) if row["created_by"] is not None else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def production_plan_public(row: sqlite3.Row) -> dict[str, object]:
    """输出生产计划上传记录及其解析摘要。"""
    try:
        summary = json.loads(row["summary"] or "{}")  # 解析结果存为 JSON 文本，展示层负责兼容历史空值和损坏值。
    except (TypeError, json.JSONDecodeError):
        summary = {}
    return {
        "id": row["id"],
        "report_date": row["report_date"],
        "data_month": row["data_month"] if "data_month" in row.keys() else str(row["report_date"])[:7],
        "original_name": row["original_name"],
        "size": int(row["size"] or 0),
        "content_type": row["content_type"],
        "summary": summary if isinstance(summary, dict) else {},
        "uploaded_by": int(row["uploaded_by"]) if row["uploaded_by"] is not None else None,
        "uploaded_by_name": row["uploaded_by_name"] if "uploaded_by_name" in row.keys() else "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "download_url": f"/api/admin/daily-production-plans/{quote(str(row['id']))}/download",
    }


def daily_source_upload_public(row: sqlite3.Row) -> dict[str, object]:
    """输出日清人工资料，并把安全检查图片转换为受控下载地址。

    解析摘要从历史 JSON 安全读取；安全检查图片元数据中的服务器文件名仅用于组装权限
    接口，绝对路径不会下发。顶层图片和记录内图片通过编号建立同一 URL 映射，避免前端
    依赖两种不同图片结构。
    """
    try:
        summary = json.loads(row["summary"] or "{}")
    except (TypeError, json.JSONDecodeError):
        summary = {}
    if not isinstance(summary, dict):
        summary = {}
    upload_id = str(row["id"])  # URL 始终使用字符串编号，避免不同数据库驱动的数值类型差异。
    if str(row["kind"]) == "safety":
        images = summary.get("images") if isinstance(summary.get("images"), list) else []  # 安全检查解析器把图片元数据集中放在顶层列表。
        for image in images:
            if not isinstance(image, dict):
                continue
            file_name = str(image.get("file_name") or "")
            if file_name:
                image["url"] = (  # 原始服务器路径不下发，浏览器只使用受权限控制的下载地址。
                    f"/api/admin/daily-source-uploads/{quote(upload_id)}/images/{quote(file_name)}"
                )
        records = summary.get("records") if isinstance(summary.get("records"), list) else []
        image_urls = {  # 记录中的图片只保存编号，通过映射补回相同的受控 URL。
            str(image.get("id")): image.get("url")
            for image in images
            if isinstance(image, dict)
        }
        for record in records:
            if not isinstance(record, dict):
                continue
            record_images = record.get("images") if isinstance(record.get("images"), list) else []
            for image in record_images:
                if isinstance(image, dict) and image.get("id") in image_urls:
                    image["url"] = image_urls[str(image["id"])]
    return {
        "id": upload_id,
        "kind": row["kind"],
        "report_date": row["report_date"],
        "data_month": row["data_month"],
        "original_name": row["original_name"],
        "size": int(row["size"] or 0),
        "content_type": row["content_type"],
        "summary": summary,
        "uploaded_by": int(row["uploaded_by"]) if row["uploaded_by"] is not None else None,
        "uploaded_by_name": row["uploaded_by_name"] if "uploaded_by_name" in row.keys() else "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "download_url": f"/api/admin/daily-source-uploads/{quote(upload_id)}/download",
    }


def notification_public(row: sqlite3.Row, kind: str) -> dict[str, object]:
    """统一消息与公告的通知中心字段。"""
    keys = set(row.keys())
    return {
        "id": row["id"],
        "kind": kind,
        "title": row["title"],
        "content": row["content"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"] if "expires_at" in keys else None,
        "read_at": row["read_at"] if "read_at" in keys else None,
    }


def announcement_public(row: sqlite3.Row) -> dict[str, object]:
    """输出全局公告的前端字段。"""
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "active": bool(row["active"]),
    }


def library_file_public(row: sqlite3.Row, user: sqlite3.Row) -> dict[str, object]:
    """输出共享文件、分类证据、上传者信息和当前账号操作权限。

    历史或淘汰分类会按当前 Core 注册表过滤，主分类始终补入多分类列表并稳定去重；
    JSON 损坏时由兼容解析器降级。班组长可读取团队文件，但编辑、替换和删除只授予
    所有者或管理员，权限结果随每条记录显式下发供界面渲染。
    """
    can_manage = int(row["owner_id"]) == int(user["id"]) or user["role"] == "admin"  # 班组长可查看团队文件，但只有所有者和管理员可修改。
    keys = set(row.keys())
    valid_categories = set(core_library.CATEGORIES) | {core_library.UNKNOWN}  # 过滤数据库中的淘汰分类，前端只看到当前注册表内容。
    category = str(row["category"] or core_library.UNKNOWN) if "category" in keys else core_library.UNKNOWN
    if category not in valid_categories:
        category = core_library.UNKNOWN  # 未知历史值安全回退，不让前端筛选器出现无法维护的类别。
    categories = [
        str(value)
        for value in json_list(row["categories"] if "categories" in keys else "[]")
        if str(value) in valid_categories
    ]
    if category not in categories:
        categories.insert(0, category)
    categories = list(dict.fromkeys(categories))  # 保留自动识别优先顺序并去除重复分类。
    return {
        "id": row["id"],
        "name": row["name"],
        "size": int(row["size"] or 0),
        "content_type": row["content_type"],
        "description": row["description"],
        "scope": row["scope"],
        "category": category,
        "category_title": core_library.CATEGORY_TITLES.get(category, category),
        "categories": categories,
        "confidence": int(row["confidence"] or 0) if "confidence" in keys else 0,
        "signals": [
            str(value)
            for value in json_list(row["signals"] if "signals" in keys else "[]")
        ],
        "sheet": str(row["sheet"] or "") if "sheet" in keys else "",
        "category_sheets": json_object(
            row["category_sheets"] if "category_sheets" in keys else "{}"
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "uploader": {
            "id": row["owner_id"],
            "username": row["owner_username"] if "owner_username" in keys else "",
            "display_name": row["owner_display_name"] if "owner_display_name" in keys else "",
        },
        "updated_by": {
            "id": row["updated_by"],
            "username": row["editor_username"] if "editor_username" in keys else "",
            "display_name": row["editor_display_name"] if "editor_display_name" in keys else "",
        } if row["updated_by"] is not None else None,
        "permissions": {
            "can_download": True,
            "can_edit": can_manage,
            "can_replace": can_manage,
            "can_delete": can_manage,
        },
    }


def workshop_issue_can_edit(row: sqlite3.Row, user: sqlite3.Row) -> bool:
    """草稿由发布者维护；已发布内容仅班组长本人或管理员可编辑。"""
    is_owner = int(row["user_id"]) == int(user["id"])  # 权限比较使用内部数字编号，不依赖可修改的显示名。
    if user["role"] == "admin":
        return True
    return is_owner and (row["status"] != "published" or user["role"] == "team_leader")


def workshop_issue_can_resolve(row: sqlite3.Row, user: sqlite3.Row) -> bool:
    """已发布问题由班组长本人或管理员推进闭环。"""
    return (
        row["status"] == "published"
        and (
            user["role"] == "admin"
            or (
                user["role"] == "team_leader"
                and int(row["user_id"]) == int(user["id"])
            )
        )
    )


def workshop_issue_can_delete(row: sqlite3.Row, user: sqlite3.Row) -> bool:
    """草稿由发布者维护；已发布问题由班组长本人或管理员移入回收站。"""
    is_owner = int(row["user_id"]) == int(user["id"])
    return user["role"] == "admin" or (
        is_owner and (row["status"] != "published" or user["role"] == "team_leader")
    )


def workshop_issue_public(
    row: sqlite3.Row,
    images: list[sqlite3.Row],
    user: sqlite3.Row,
) -> dict[str, object]:
    """把现场问题记录转换为符合现行模板、权限和图片协议的公开结构。

    只导出 Core 注册的模板字段，旧类别、负责人和严重程度在展示前重新归一化；闭环字段
    对历史记录提供安全默认值。每张图片只暴露受控接口地址，编辑、闭环和删除权限按当前
    用户与发布状态分别计算，前端无需复制角色矩阵。
    """
    template_values = {  # 只导出当前标准模板注册的字段，数据库新增内部列不会意外暴露给前端。
        field: row[field] if field in row.keys() else ""
        for field in WORKSHOP_ISSUE_TEMPLATE_FIELDS
    }
    semantic_values = {  # 兼容旧通用字段，让 Core 能按当前类别重新推断负责人和问题类型。
        **template_values,
        "cause": row["cause"],
        "primary_owner": row["primary_owner"],
        "notes": row["notes"],
    }
    category = workshop_issue_core.normalize_workshop_category(  # 历史别名或旧记录在输出时统一映射为现行五类标准。
        row["category"] if "category" in row.keys() else "",
        semantic_values,
    )
    primary_owner = workshop_issue_core.workshop_issue_primary_owner(  # 不同类别负责人来源不同，由 Core 的模板规则统一决定。
        category,
        semantic_values,
        row["primary_owner"],
    )
    return {
        "id": row["id"],
        "issue_date": row["issue_date"],
        "cause": row["cause"],
        "primary_owner": primary_owner,
        "secondary_owner": row["secondary_owner"],
        "notes": row["notes"],
        "category": category,
        "severity": workshop_issue_core.workshop_issue_severity(
            template_values,
            row["severity"] if "severity" in row.keys() else "normal",
        ),
        **template_values,
        "status": row["status"],
        "resolution_status": (
            row["resolution_status"]
            if "resolution_status" in row.keys()
            and row["resolution_status"] in {"open", "resolved"}
            else "open"
        ),
        "resolution_note": row["resolution_note"] if "resolution_note" in row.keys() else "",
        "resolved_at": row["resolved_at"] if "resolved_at" in row.keys() else "",
        "resolved_by": {
            "id": row["resolved_by"] if "resolved_by" in row.keys() else None,
            "display_name": row["resolved_by_name"] if "resolved_by_name" in row.keys() else "",
        },
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "uploader": {
            "id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
        },
        "images": [
            {
                "id": image["id"],
                "name": image["name"],
                "size": int(image["size"] or 0),
                "content_type": image["content_type"],
                "width": int(image["width"] or 0),
                "height": int(image["height"] or 0),
                "url": f"/api/workshop/issues/{row['id']}/images/{image['id']}",
            }
            for image in images
        ],
        "permissions": {
            "can_edit": workshop_issue_can_edit(row, user),
            "can_resolve": workshop_issue_can_resolve(row, user),
            "can_delete": workshop_issue_can_delete(row, user),
        },
    }
