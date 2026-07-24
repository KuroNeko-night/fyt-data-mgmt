# -*- coding: utf-8 -*-
"""数据形态兜底识别引擎。

当 header_detect.detect_layout 因"表头文字完全不同/缺失/被翻译"而找不到表头时,
退一步**看数据本身的形态**来猜列:某列几乎全是数字→像数量;几乎全是"含多位数字
的短标识"→像编码;几乎全是含中文的文本→像名称/描述。据此把各"角色"按 dtype
兼容性与列顺序贪心指派到实际列,并给出 0~1 的置信度。

各 core 传自己的 SHAPE_PROFILE(有序的角色-类型清单)做薄封装。兜底命中后
**不静默采用**——调用方(UI)应把候选映射交给用户确认再落盘(见 v1.2 设计)。

只读数据、不改动工作簿;与 header_detect 一样对 read_only/data_only 的 ws 工作。
运行于 Windows 10/11 + Python 3.13。
"""
import re
import datetime

# 列类型(角色期望的数据形态)
NUMBER = "number"      # 数量/金额:几乎全是数值
TEXT = "text"          # 名称/描述/规格:含中文或较长文本
CODE = "code"          # 物料编码/供应商代码:含多位数字的短标识(可含少量字母/连字符)
ANY = "any"            # 任意非空列(占位,不参与打分加权)

# "像编码"的判据:纯数字(≥3 位),或字母数字混合且含数字(如 A1234、KD-001)
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{2,}$")
_HAS_DIGIT = re.compile(r"\d")
_HAS_CJK = re.compile(r"[一-鿿]")


def classify_value(v):
    """把单元格值归到一个基本形态标签之一:'empty'/'number'/'date'/'code'/'text'。

    数值型整浮点(123.0)与"看起来像数字的字符串"都算 number;编码是 number/text
    之外那类"含多位数字的短标识"。分类互斥,便于按列统计各形态占比。
    """
    if v is None:
        return "empty"
    if isinstance(v, bool):                      # bool 是 int 子类,先挡掉
        return "text"
    if isinstance(v, (datetime.datetime, datetime.date)):
        return "date"
    if isinstance(v, (int, float)):
        return "number"
    s = str(v).strip()
    if not s:
        return "empty"
    # 纯数字字符串(含千分位/小数/负号)当 number
    if re.match(r"^-?[\d,]+(\.\d+)?$", s):
        return "number"
    if _HAS_CJK.search(s):
        return "text"
    if _HAS_DIGIT.search(s) and _CODE_RE.match(s):
        return "code"
    return "text"


def profile_column(ws, col, data_start, data_end, sample=60):
    """统计某列 [data_start, data_end] 区间各形态占比。返回 dict。

    只采样最多 sample 行(大表提速);空行不计入分母。返回:
      {'n': 非空样本数, 'number':.., 'code':.., 'text':.., 'date':.., 'fill': 非空占比}
    占比均为对"非空样本"的比例(fill 例外,是非空/总采样)。
    """
    counts = {"number": 0, "code": 0, "text": 0, "date": 0}
    total = 0
    nonempty = 0
    r = data_start
    step = max(1, (data_end - data_start + 1) // sample) if data_end >= data_start else 1
    while r <= data_end and total < sample:
        v = ws.cell(r, col).value
        total += 1
        kind = classify_value(v)
        if kind != "empty":
            nonempty += 1
            counts[kind] += 1
        r += step
    n = nonempty or 1
    return {"n": nonempty,
            "number": counts["number"] / n,
            "code": counts["code"] / n,
            "text": counts["text"] / n,
            "date": counts["date"] / n,
            "fill": (nonempty / total) if total else 0.0}


def _score_role(role_type, prof):
    """列形态 prof 对期望类型 role_type 的契合度(0~1)。空列(n==0)判 0。"""
    if prof["n"] == 0:
        return 0.0
    if role_type == NUMBER:
        return prof["number"]
    if role_type == CODE:
        # 编码列常被 openpyxl 读成 number(纯数字编码),故 code 与 number 都算数,
        # 但 code 形态权重更高;含中文则明显不像编码。
        return min(1.0, prof["code"] + 0.6 * prof["number"]) * (1.0 - prof["text"])
    if role_type == TEXT:
        return prof["text"]
    if role_type == ANY:
        return 1.0 if prof["fill"] > 0.3 else 0.0
    return 0.0


def _guess_data_region(ws, scan_rows, max_cols):
    """猜数据起始行:取"非空单元格最多"的前若干行之后第一行为数据起点的近似。

    表头文字未知,故不能靠关键词。策略:把第 1..scan_rows 行里"看起来最像表头
    (文本多、几乎无纯数字)"的那行当表头,其后即数据。找不到就假定第 1 行是表头。
    """
    best_r, best_textiness = 1, -1.0
    limit = min(scan_rows, ws.max_row or 0)
    for r in range(1, limit + 1):
        texts = nums = 0
        for c in range(1, max_cols + 1):
            k = classify_value(ws.cell(r, c).value)
            if k == "text":
                texts += 1
            elif k in ("number", "date"):
                nums += 1
        textiness = texts - 0.5 * nums
        if textiness > best_textiness:
            best_textiness, best_r = textiness, r
    return best_r


def detect_by_shape(ws, profile, scan_rows=12, min_conf=0.5, log=None):
    """按数据形态兜底识别列。返回 (header_row, {角色:列号}, confidence)。

    - profile: 有序列表 [(role, role_type, required_bool)],顺序即"典型出现次序",
      用于在多列同分时按左→右就近指派(贴合真实表列序)。
    - min_conf: 平均契合度低于此值视为"没把握",返回 (None, {}, conf)。
    识别不到必需角色也返回 (None, {}, conf)。此函数不改动工作簿。
    """
    max_cols = ws.max_column or 0
    max_row = ws.max_row or 0
    if max_cols == 0 or max_row == 0:
        return None, {}, 0.0
    header_row = _guess_data_region(ws, scan_rows, max_cols)
    data_start = header_row + 1
    if data_start > max_row:
        return None, {}, 0.0
    profs = {c: profile_column(ws, c, data_start, max_row) for c in range(1, max_cols + 1)}

    col_map = {}
    used = set()
    conf_sum = 0.0
    weighted = [p for p in profile if p[1] != ANY]     # ANY 不计入置信度
    for role, rtype, _req in profile:
        best_c, best_s = None, 0.0
        for c in range(1, max_cols + 1):
            if c in used:
                continue
            s = _score_role(rtype, profs[c])
            if s > best_s:
                best_s, best_c = s, c
        if best_c is not None and best_s > 0.0:
            col_map[role] = best_c
            used.add(best_c)
            if rtype != ANY:
                conf_sum += best_s
    conf = conf_sum / len(weighted) if weighted else 0.0

    required = [r for r, _t, req in profile if req]
    if not all(r in col_map for r in required) or conf < min_conf:
        if log:
            try:
                log("· 形态兜底:置信度 %.2f%s,未采用" % (
                    conf, "(缺必需列)" if not all(r in col_map for r in required) else ""))
            except Exception:
                pass
        return None, {}, conf
    if log:
        try:
            log("· 形态兜底:按数据形态推断列映射(置信度 %.2f),请在预览面板核对后再生成"
                % conf)
        except Exception:
            pass
    return header_row, col_map, conf
