# -*- coding: utf-8 -*-
"""
文本工具箱核心 —— 办公通用文本处理,纯标准库零依赖
==================================================
面向"把一段文本按行处理"的高频场景:去重、排序、去空行、去首尾空格、
大小写转换、加行号、统计,以及从文本里提取邮箱/手机号/网址。

设计:每个操作是一个纯函数 (text, **opts) -> text 或 -> 统计 dict,
页面按钮直接调用,不持有状态,便于测试与组合。
兼容 Windows 7 + Python 3.8。
"""
import re

_LINESEP = "\n"


def _lines(text):
    """按行拆分,统一 \\r\\n / \\r 为 \\n,不丢末尾空行信息。"""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def dedup_lines(text, keep_order=True, ignore_case=False):
    """行去重。keep_order 保持首次出现顺序;ignore_case 忽略大小写比较。"""
    seen = set()
    out = []
    for ln in _lines(text):
        key = ln.lower() if ignore_case else ln
        if key not in seen:
            seen.add(key)
            out.append(ln)
    return _LINESEP.join(out)


def sort_lines(text, reverse=False, numeric=False, ignore_case=False):
    """行排序。numeric 时按行首数字排序(取不到数字的排到最后)。"""
    lines = _lines(text)
    if numeric:
        def key(ln):
            m = re.search(r"-?\d+(?:\.\d+)?", ln)
            return (0, float(m.group())) if m else (1, 0.0)
        lines.sort(key=key, reverse=reverse)
    else:
        lines.sort(key=lambda s: s.lower() if ignore_case else s, reverse=reverse)
    return _LINESEP.join(lines)


def remove_empty_lines(text):
    """删除空行(仅空白也算空)。"""
    return _LINESEP.join(ln for ln in _lines(text) if ln.strip())


def trim_lines(text):
    """去掉每行首尾空白。"""
    return _LINESEP.join(ln.strip() for ln in _lines(text))


def collapse_spaces(text):
    """把每行内连续空白压成单个空格(不动行结构)。"""
    return _LINESEP.join(re.sub(r"[ \t]+", " ", ln).strip() for ln in _lines(text))


def to_upper(text):
    return text.upper()


def to_lower(text):
    return text.lower()


def add_line_numbers(text, start=1, sep=". ", pad=False):
    """给每行加行号。pad 时按总行数补零对齐。"""
    lines = _lines(text)
    width = len(str(start + len(lines) - 1)) if pad else 0
    out = []
    for i, ln in enumerate(lines):
        num = str(start + i).rjust(width, "0") if pad else str(start + i)
        out.append("%s%s%s" % (num, sep, ln))
    return _LINESEP.join(out)


def reverse_lines(text):
    """行倒序。"""
    return _LINESEP.join(reversed(_lines(text)))


# 提取类:邮箱 / 手机号(中国) / 网址
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_RE_URL = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def extract(text, kind, unique=True):
    """从文本提取 kind in {'email','phone','url'},每个一行返回。"""
    rx = {"email": _RE_EMAIL, "phone": _RE_PHONE, "url": _RE_URL}.get(kind)
    if rx is None:
        return ""
    found = rx.findall(text)
    if unique:
        seen = set(); uniq = []
        for x in found:
            if x not in seen:
                seen.add(x); uniq.append(x)
        found = uniq
    return _LINESEP.join(found)


def stats(text):
    """统计:字符数(含/不含空白)、行数、非空行数、词数。返回 dict。"""
    lines = _lines(text)
    chars = len(text)
    chars_no_ws = len(re.sub(r"\s", "", text))
    nonempty = sum(1 for ln in lines if ln.strip())
    words = len(re.findall(r"\S+", text))
    return {"chars": chars, "chars_no_ws": chars_no_ws,
            "lines": len(lines), "nonempty_lines": nonempty, "words": words}
