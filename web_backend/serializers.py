"""数据库 JSON 字段的兼容读取工具。

这些函数对损坏或历史格式数据采用显式回退，避免前端接口因单条旧记录失败。
"""

from __future__ import annotations

import json


def json_list(value: object, fallback: list[object] | None = None) -> list[object]:
    """读取数据库中的 JSON 列表；格式不正确时返回调用方给出的回退值。"""
    default = fallback or []  # 不把可变空列表放在函数默认参数中，避免跨请求共享状态。
    try:
        parsed = json.loads(str(value or "[]"))  # SQLite 可能返回 None、字符串或历史脏值，统一转文本解析。
    except (TypeError, json.JSONDecodeError):
        parsed = default  # 单条旧数据损坏不应让整个列表接口返回 500。
    return parsed if isinstance(parsed, list) else default  # JSON 合法但类型错误时仍执行结构级回退。


def json_value(value: object, fallback: object = None) -> object:
    """读取数据库中的任意 JSON 值；空值或损坏值回退到指定值。"""
    if value is None or value == "":
        return fallback  # 空数据库字段表示“尚无结果”，与 JSON null 的业务含义保持一致。
    try:
        return json.loads(str(value))  # 此函数允许标量、列表和对象，因此不额外限制解析结果类型。
    except (TypeError, ValueError):
        return fallback


def json_object(value: object, fallback: dict[str, object] | None = None) -> dict[str, object]:
    """读取数据库中的 JSON 对象；格式不正确时返回空对象或指定回退值。"""
    default = fallback or {}  # 每次调用创建独立空对象，调用方可以安全继续补字段。
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        parsed = default
    return parsed if isinstance(parsed, dict) else default  # 防止历史字段被误写成列表后污染对象型 API。
