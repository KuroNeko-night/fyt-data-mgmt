# -*- coding: utf-8 -*-
"""跨业务模块共用的文本、日期、时间与数字解析。

函数只接收值并返回规范结果，不访问文件、配置或界面。集中维护这些规则可以避免
考勤、对账、采购等业务各自解释全角字符、Excel 日期序列和假休标记。
"""

from __future__ import annotations

import datetime
import math
import re
import unicodedata

from openpyxl.utils.datetime import from_excel


SKIP_MARKS = {"假", "休", "旷", "缺", "调休", "病假", "事假", "年假", ""}

# translate 的值为 None 表示删除字符。零宽字符和软连字符肉眼不可见，却会导致同值失配。
_INVISIBLE = dict.fromkeys([0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD, 0x2060], None)
# 业务允许的日期序列约为 1990-01-01 至 2100-12-31；下界高于 31，避免误认日号。
_EXCEL_SERIAL_MIN = 32874
_EXCEL_SERIAL_MAX = 73415


def clean_str(value: object) -> str:
    """执行 Unicode NFKC 归一、删除不可见字符并清理首尾空白。"""

    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).translate(_INVISIBLE).strip()


def portable_basename(value: object) -> str:
    """从 Windows 或 POSIX 路径文本中提取文件名，不依赖当前运行系统。

    Web 任务历史和字段映射可能由另一种操作系统生成。Linux 上的 ``os.path.basename``
    不会把反斜杠视为分隔符，因此这里先统一两类分隔符，保证展示裁剪和映射复用采用
    同一个文件主名口径。
    """

    return clean_str(value).replace("\\", "/").rsplit("/", 1)[-1]


def num_str(value: object) -> str:
    """生成可交给 ``float`` 的文本，只在整体合法时移除千分位逗号。"""

    value_text = clean_str(value)
    if "," not in value_text:
        return value_text
    without_commas = value_text.replace(",", "")
    # 规格和业务编号也可能含逗号；只有纯十进制数才执行千分位转换。
    return without_commas if re.fullmatch(r"[+-]?\d+(\.\d+)?", without_commas) else value_text


def norm_name(value: object) -> str:
    """移除姓名中的全部空白，使不同录入形式使用同一匹配键。"""

    return "" if value is None else re.sub(r"\s+", "", str(value))


def serial_to_date(value: object) -> datetime.date | None:
    """把合理范围内的 Excel 日期序列号转换为日期，失败返回 ``None``。"""

    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    if not _EXCEL_SERIAL_MIN <= serial <= _EXCEL_SERIAL_MAX:
        return None
    try:
        converted = from_excel(serial)
    except Exception:
        # openpyxl 对越界日期制的异常属于输入问题，公共解析层统一按无效日期处理。
        return None
    return converted.date() if isinstance(converted, datetime.datetime) else converted


def _date_tuple(year: object, month: object, day: object) -> tuple[int, int, int] | None:
    """使用标准库验证真实日历日期，并返回规范三元组。"""

    try:
        parsed = datetime.date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None
    return parsed.year, parsed.month, parsed.day


def _date_from_text(value_text: str) -> tuple[int, int, int] | None:
    """按明确格式解析日期文本，不从任意数字串中猜测日期。"""

    digits = "".join(char for char in value_text if char.isdigit())
    if len(digits) == 8:
        parsed = _date_tuple(digits[0:4], digits[4:6], digits[6:8])
        if parsed is not None:
            return parsed
    chinese = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", value_text)
    if chinese:
        return _date_tuple(*chinese.groups())
    for separator in ("-", "/", "."):
        parts = value_text.split(separator)
        if len(parts) == 3:
            parsed = _date_tuple(*parts)
            if parsed is not None:
                return parsed
    return None


def norm_date(value: object) -> tuple[int, int, int] | None:
    """把日期对象、Excel 序列号和常见日期文本统一为 ``(年, 月, 日)``。"""

    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.year, value.month, value.day
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        converted = serial_to_date(value)
        return (converted.year, converted.month, converted.day) if converted else None
    value_text = clean_str(value)
    if not value_text or value_text == "-":
        return None
    # 只取空白前的日期段，避免日期后的时间数字干扰八位日期判断。
    date_text = value_text.split()[0]
    parsed = _date_from_text(date_text)
    if parsed is not None:
        return parsed
    if date_text.isdigit():
        converted = serial_to_date(int(date_text))
        if converted:
            return converted.year, converted.month, converted.day
    return None


def day_of(value: object) -> int | None:
    """把完整日期、Excel 序列号或月度表头中的 1～31 转换为日号。"""

    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.day
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        day = int(value)
        if 1 <= day <= 31:
            return day
        converted = serial_to_date(value)
        return converted.day if converted else None
    value_text = clean_str(value)
    date_text = value_text.split()[0] if value_text else ""
    parsed = norm_date(date_text)
    if parsed:
        return parsed[2]
    day_match = re.fullmatch(r"(\d{1,2})\s*日?", date_text)
    if not day_match:
        return None
    day = int(day_match.group(1))
    return day if 1 <= day <= 31 else None


def parse_time(value: object) -> datetime.time | None:
    """把 time、datetime 或冒号分隔文本解析为 ``datetime.time``。"""

    if value is None:
        return None
    if isinstance(value, datetime.time):
        return value
    if isinstance(value, datetime.datetime):
        return value.time()
    value_text = clean_str(value)
    if not value_text or value_text in ("-", "—") or ":" not in value_text:
        return None
    parts = value_text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
        return datetime.time(hour, minute, second)
    except ValueError:
        return None


def to_hours(value: datetime.time | None) -> float | None:
    """把一天内时间转换为带小数的小时数；空值保持 ``None``。"""

    if value is None:
        return None
    return value.hour + value.minute / 60.0 + value.second / 3600.0


def round_half_hour(value: datetime.time | None, mode: str) -> datetime.time | None:
    """按半小时向上或向下取整，并把结果限制在当天可表示范围。"""

    if value is None:
        return None
    total_seconds = value.hour * 3600 + value.minute * 60 + value.second
    step = 1800
    if mode == "up":
        rounded = int(math.ceil(total_seconds / float(step))) * step
    else:
        rounded = (total_seconds // step) * step
    # datetime.time 不支持 24:00；跨日夜班由考勤业务层结合班次单独修正。
    rounded = max(0, min(rounded, 86400 - step))
    return datetime.time(rounded // 3600, (rounded % 3600) // 60)


def fmt_time(value: datetime.time | None) -> str:
    """把时间格式化为固定两位 ``HH:MM``，空值返回空串。"""

    return "" if value is None else f"{value.hour:02d}:{value.minute:02d}"


def parse_rest(value: object) -> float:
    """把休息时长解析为小时数，空白、破折号和无效文本按零处理。"""

    if value is None:
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    value_text = clean_str(value)
    if not value_text or value_text in ("-", "—"):
        return 0.0
    try:
        return float(num_str(value))
    except ValueError:
        return 0.0


def to_num(value: object, skip: set[str] | None = None) -> float | None:
    """把单元格转换为数值；空白、假休标记和无效文本返回 ``None``。"""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value_text = clean_str(value)
    marks = skip if skip is not None else SKIP_MARKS
    if not value_text or value_text in marks:
        return None
    try:
        return float(num_str(value))
    except ValueError:
        return None


__all__ = [
    "SKIP_MARKS",
    "clean_str",
    "day_of",
    "fmt_time",
    "norm_date",
    "norm_name",
    "num_str",
    "parse_rest",
    "parse_time",
    "portable_basename",
    "round_half_hour",
    "serial_to_date",
    "to_hours",
    "to_num",
]
