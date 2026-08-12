# -*- coding: utf-8 -*-
"""
办公文本处理核心
================
提供按行去重、排序、删除空行、清理空白、大小写转换、编号、倒序、统计以及邮箱、
中国大陆手机号和 HTTP(S) 网址提取。每个入口都是无状态纯函数，既不访问文件系统，
也不依赖桌面或 Web 界面，适合直接组合和单元测试。

所有按行操作先把不同平台换行符统一为 LF，并用 LF 输出；除明确删除空行的函数外，
末尾换行会表现为末尾空字符串并尽量保留。数值排序提取每行首个可识别数字，无法
提取的行保持原相对顺序并统一放在数值行之后。

提取正则只覆盖常用格式，不承担严格的邮箱、手机号归属或网址安全验证；结果用于办公
整理，不能直接作为认证、通信或自动访问依据。
"""
import re

_LINESEP = "\n"


def _lines(text):
    """按行拆分,统一 \\r\\n / \\r 为 \\n,不丢末尾空行信息。"""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def dedup_lines(text, keep_order=True, ignore_case=False):
    """按整行内容去重，默认保留首次出现顺序。

    ``ignore_case`` 只改变比较键，输出仍保留首次出现行的原始大小写。当前实现始终
    使用首次出现顺序；``keep_order`` 为历史接口参数，保留以兼容既有调用。
    """
    seen = set()
    out = []
    for ln in _lines(text):
        key = ln.lower() if ignore_case else ln
        if key not in seen:
            # 先记录比较键，再保留原行文本，避免忽略大小写时改写用户内容。
            seen.add(key)
            out.append(ln)
    return _LINESEP.join(out)


def sort_lines(text, reverse=False, numeric=False, ignore_case=False):
    """按文本或每行首个数字排序，并返回 LF 连接结果。

    数值模式把能提取数字的行与其他行分组，只对数值行排序；非数值行始终追加在后，
    即使 ``reverse=True`` 也不会移动到数值行之前。文本模式可忽略大小写比较。
    """
    lines = _lines(text)
    if numeric:
        def key(ln):
            """提取行中首个带可选负号和小数部分的数字，缺失返回 ``None``。"""
            m = re.search(r"-?\d+(?:\.\d+)?", ln)
            return float(m.group()) if m else None
        numeric_lines = [line for line in lines if key(line) is not None]
        other_lines = [line for line in lines if key(line) is None]
        numeric_lines.sort(key=key, reverse=reverse)
        lines = numeric_lines + other_lines
    else:
        lines.sort(key=lambda s: s.lower() if ignore_case else s, reverse=reverse)
    return _LINESEP.join(lines)


def remove_empty_lines(text):
    """删除空串和只含空白字符的行。"""
    return _LINESEP.join(ln for ln in _lines(text) if ln.strip())


def trim_lines(text):
    """独立去除每行首尾全部 Unicode 空白，不改变行数。"""
    return _LINESEP.join(ln.strip() for ln in _lines(text))


def collapse_spaces(text):
    """把每行内连续空格或制表符压成一个空格，并清理行首尾。

    不处理其他 Unicode 空白，也不跨行合并，因此段落结构保持不变。
    """
    return _LINESEP.join(re.sub(r"[ \t]+", " ", ln).strip() for ln in _lines(text))


def to_upper(text):
    """使用 Python Unicode 规则把全文转换为大写。"""
    return text.upper()


def to_lower(text):
    """使用 Python Unicode 规则把全文转换为小写。"""
    return text.lower()


def add_line_numbers(text, start=1, sep=". ", pad=False):
    """从 ``start`` 起为每行添加序号和分隔符。

    ``pad=True`` 时按最后一个序号的字符宽度左侧补零；序号数量包含空行，因为编号是
    对原文本行结构的标记，不会自动跳过空白内容。
    """
    lines = _lines(text)
    width = len(str(start + len(lines) - 1)) if pad else 0
    out = []
    for i, ln in enumerate(lines):
        num = str(start + i).rjust(width, "0") if pad else str(start + i)
        out.append("%s%s%s" % (num, sep, ln))
    return _LINESEP.join(out)


def reverse_lines(text):
    """反转行顺序，保持每行内容原样。"""
    return _LINESEP.join(reversed(_lines(text)))


# 提取规则面向常见办公文本：不执行域名、号码归属或网络可达性验证。
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_RE_URL = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def extract(text, kind, unique=True):
    """按类型提取邮箱、手机号或网址，并以每项一行返回。

    未知类型返回空串。默认按首次出现顺序精确去重，大小写不同仍视为不同文本；关闭
    ``unique`` 时保留全部重复匹配。
    """
    rx = {"email": _RE_EMAIL, "phone": _RE_PHONE, "url": _RE_URL}.get(kind)
    if rx is None:
        return ""
    found = rx.findall(text)
    if unique:
        seen = set(); uniq = []
        for x in found:
            if x not in seen:
                # 保留首次出现的原始文本和顺序，不对提取结果再做大小写规范化。
                seen.add(x); uniq.append(x)
        found = uniq
    return _LINESEP.join(found)


def stats(text):
    """返回字符、非空白字符、总行、非空行和空白分词数量。

    字符数按 Python Unicode 码点计数；词数使用连续非空白片段，不进行中文分词。
    空文本经拆分后仍计为一行，这是文本编辑器常见的行结构口径。
    """
    lines = _lines(text)
    chars = len(text)
    chars_no_ws = len(re.sub(r"\s", "", text))
    nonempty = sum(1 for ln in lines if ln.strip())
    words = len(re.findall(r"\S+", text))
    return {"chars": chars, "chars_no_ws": chars_no_ws,
            "lines": len(lines), "nonempty_lines": nonempty, "words": words}
