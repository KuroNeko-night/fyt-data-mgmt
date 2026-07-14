# -*- coding: utf-8 -*-
"""
金额转中文大写 —— 财务/开票/合同常用,纯标准库零依赖
====================================================
把阿拉伯数字金额转成规范的人民币大写,遵循财政部《正式票据填写规范》习惯:

    1000000        -> 壹佰万元整
    12345.6        -> 壹万贰仟叁佰肆拾伍元陆角
    0.05           -> 伍分
    10800.09       -> 壹万零捌佰元零玖分
    -320           -> 负叁佰贰拾元整

规则要点:
· 数字用 零壹贰叁肆伍陆柒捌玖;权位 个十百千 / 万 / 亿;
· 连续的 0 合并成一个"零",节权位(万/亿)照写;
· 元位为 0 但有角分时写"零";整数金额末尾加"整";
· 分及以下四舍五入到两位小数(角、分)。
支持范围到"万亿"级(足够业务用),超出会退化为普通串并提示。
兼容 Windows 7 + Python 3.8。
"""
from decimal import Decimal, ROUND_HALF_UP

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNITS = ["", "拾", "佰", "仟"]          # 组内四位的权位
_GROUPS = ["", "万", "亿", "兆"]         # 每四位一组的节权位


def _four(seg):
    """把 0..9999 的整数段转成大写(不含节权位),内部合并连续零。

    返回如 '壹仟贰佰'、'壹佰零伍'、'伍拾'。空段(0)返回 ''。"""
    s = ""
    zero = False                        # 是否有待补的"零"
    has = False                         # 段内是否已出现过非零位
    for i in range(3, -1, -1):
        d = (seg // (10 ** i)) % 10
        if d == 0:
            if has:                     # 前面已有非零,标记需要一个零(后续补)
                zero = True
        else:
            if zero:
                s += _DIGITS[0]         # 补一个"零"
                zero = False
            s += _DIGITS[d] + _UNITS[i]
            has = True
    return s


def _integer(n):
    """非负整数 n 转大写(不含'元')。0 返回 '零'。"""
    if n == 0:
        return _DIGITS[0]
    # 拆成四位一组,低位在前
    groups = []
    while n > 0:
        groups.append(n % 10000)
        n //= 10000
    if len(groups) > len(_GROUPS):
        return None                     # 超出兆级,交给调用方退化处理
    parts = []
    for gi in range(len(groups) - 1, -1, -1):
        seg = groups[gi]
        seg_cn = _four(seg)
        if seg == 0:
            continue                    # 整段为 0,节权位不写,零由相邻段决定
        # 高段已有内容,而本段不足四位(有前导零),需补"零"
        # 例:1 0005 -> 壹万零伍;1 0000 0005 -> 壹亿零伍
        if parts and seg < 1000:
            parts.append(_DIGITS[0])
        parts.append(seg_cn + _GROUPS[gi])
    return "".join(parts)


def to_capital(amount):
    """把金额(数字或字符串)转成中文大写人民币。

    返回 (成功?, 结果字符串)。失败时结果为错误说明,供页面提示。
    四舍五入到分;支持负数;整数末尾加"整"。"""
    if amount is None or str(amount).strip() == "":
        return False, "请输入金额"
    try:
        d = Decimal(str(amount).replace(",", "").strip())
    except Exception:
        return False, "不是有效的数字"
    neg = d < 0
    d = abs(d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    yuan = int(d)                       # 元(整数部分)
    cents = int((d - yuan) * 100)       # 角分合成的两位
    jiao = cents // 10
    fen = cents % 10

    int_cn = _integer(yuan)
    if int_cn is None:
        return False, "金额过大,超出可转换范围(兆级)"

    out = ""
    if yuan > 0:
        out += int_cn + "元"
    # 小数部分
    if jiao == 0 and fen == 0:
        out += "整" if yuan > 0 else ""     # 纯 0 元在下方兜底
    else:
        # 元为0时不写"元";元>0但角为0而分不为0,补"零"
        if jiao > 0:
            out += _DIGITS[jiao] + "角"
        if fen > 0:
            if yuan > 0 and jiao == 0:
                out += _DIGITS[0]
            out += _DIGITS[fen] + "分"
        elif jiao > 0:
            pass                            # 只有角、无分,不加"整"(角分习惯不加)
    if not out:
        out = "零元整"                       # 金额为 0
    return True, ("负" + out if neg else out)
