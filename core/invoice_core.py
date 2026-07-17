# -*- coding: utf-8 -*-
"""增值税发票筛选统计 —— 核心引擎。

递归扫描资料文件夹里的 PDF，识别“增值税专用发票”，按开票月份筛选，
抽取字段汇总。可靠字段全自动；费用项目/备注给“PDF 原始种子”供人工精修。
另把所有专用发票原始 PDF 复制到复核文件夹（宽松判定，含存疑清单），供人工二次核对。
仅用 pypdf + openpyxl，兼容 Win7 + Python 3.8。

对外主接口：
  scan(root, log=None)                 -> ScanResult      （扫描+抽取，不筛月份）
  filter_month(items, ym)              -> list[Invoice]
  detect_month(items)                  -> "YYYY-MM"
  generate(result, rows, ym, out_dir=None, log=None) -> dict
        （统一出口：写汇总表 + 导出复核文件夹，输出目录经 paths 统一解析）
"""
import os
import re
import glob

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

BUYER = "重庆峰运通供应链管理有限公司"

_COMPANY = re.compile(
    r"[一-龥A-Za-z0-9（）()]{2,45}"
    r"(?:有限责任公司|有限公司|股份公司|分公司|公司|银行|事务所|合作社|个体工商户|中心)")
_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")   # 月/日放宽为1-2位,"6月1日"也能取到(取值后补零归一)
_NUM = re.compile(r"发票号码[:：]?(\d{20}|\d{8})")          # 优先"发票号码"锚点,全电20位/老票8位
_NUM_LOOSE = re.compile(r"\d{20}|\d{8}")                    # 无锚点时兜底:全电20位或老版8位票号
_MONEY = re.compile(r"¥\s*([\d\s]+\.\s*\d\s*\d)")
_RATE = re.compile(r"(\d+)%")
_SKIP_LINE = ("开户", "账号", "地址", "电话")


class Invoice(object):
    """一张发票的抽取结果。字段全部为可 JSON 化的基础类型。"""
    __slots__ = ("path", "num", "date", "seller", "amount", "tax", "total",
                 "rate", "item_seed", "note_seed", "special")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def as_row(self):
        """转成写表用的 dict（费用项目/备注先用种子，供界面覆盖）。"""
        return dict(num=self.num, date=self.date, seller=self.seller,
                    item=self.item_seed or "", amount=self.amount,
                    tax=self.tax, total=self.total, rate=self.rate,
                    note=self.note_seed or "")


def _norm(t):
    return re.sub(r"[ \t]+", "", t or "")


def _seller(raw):
    """抬头块里第一个非买方公司名（跳过开户行/账号/地址行）。"""
    for ln in raw.splitlines():
        if any(k in ln for k in _SKIP_LINE):
            continue
        for m in _COMPANY.finditer(ln):
            c = re.sub(r"^[0-9A-Za-z]+", "", m.group(0))  # 去粘连的税号前缀
            if not c or "峰运通" in c or c == BUYER:
                continue
            return c
    return ""


def _money3(raw):
    """合计行的 金额/税额/价税合计：取全文最后三个 ¥ 金额（去数字间空格）。"""
    vals = [float(re.sub(r"\s+", "", m.group(1))) for m in _MONEY.finditer(raw)]
    if len(vals) >= 3:
        return vals[-3], vals[-2], vals[-1]
    return None, None, None


_RATE2 = ("17", "16", "13", "11", "10")   # 合法两位税率
_RATE1 = ("9", "6", "5", "3", "1", "0")   # 合法一位税率


def _one_rate(numstr):
    """把可能粘连了型号数字的百分数(如 '019713')还原成合法增值税税率。"""
    for v in _RATE2:
        if numstr.endswith(v):
            return v
    for v in _RATE1:
        if numstr.endswith(v):
            return v
    return None


def _rate(nn):
    """税率：单税率→小数(0.13)；多税率→'9%+6%'（去重后按大到小拼接）。"""
    found = []
    for m in _RATE.finditer(nn):
        v = _one_rate(m.group(1))
        if v is not None and v not in found:
            found.append(v)
    if not found:
        return ""
    if len(found) == 1:
        return round(int(found[0]) / 100.0, 2)
    return "+".join(v + "%" for v in sorted(found, key=lambda x: -int(x)))


_STD_RATES = (0.17, 0.16, 0.13, 0.11, 0.10, 0.09, 0.06, 0.05, 0.03, 0.01)


def _deduction(nn):
    m = re.search(r"扣除额[:：]([\d.]+)元", nn)
    return float(m.group(1)) if m else None


def _snap(r):
    """把算得的税率吸附到最接近的标准税率（容差 0.006）。"""
    if r is None or r <= 0:
        return None
    best = min(_STD_RATES, key=lambda s: abs(s - r))
    return best if abs(best - r) <= 0.006 else None


def _derive_rate(amount, tax, total, ded):
    """未印税率时反推：差额征税用扣除额公式，否则用 税额/不含税额。"""
    if not tax:
        return None
    if ded and total:
        base = total - ded            # 差额（含税）
        if base > 0:
            ratio = tax / base
            if ratio < 1:
                return _snap(ratio / (1 - ratio))
    if amount:
        return _snap(tax / amount)
    return None


def _item_seed(raw):
    """费用项目种子：取开票人后那行 *类目*货物名 里的中文片段，去开票人姓名。"""
    for ln in raw.splitlines():
        s = ln.strip()
        if s.count("*") >= 2 and "服务" not in s[:1]:
            # 形如  葛亚茹*生产生活服务*设备租赁费徐工XCB35...
            parts = [p for p in s.split("*") if p.strip()]
            # 丢掉首段开票人姓名（2-4 个纯汉字），拼出“类目/品名”
            if parts and re.match(r"^[一-龥]{2,4}$", parts[0]):
                parts = parts[1:]
            seg = "/".join(p.strip() for p in parts[:2] if p.strip())
            seg = re.sub(r"[0-9A-Za-z]+.*$", "", seg).strip("/ ")
            if seg:
                return seg
    return ""


def _note_seed(raw):
    """备注种子：抓 PDF 备注区常见信息（扣除额 / 库区 / 租期），拼成一句。"""
    n = _norm(raw)
    bits = []
    m = re.search(r"扣除额[:：]([\d.]+)元", n)
    if m:
        bits.append("扣除额 %s 元" % m.group(1))
    m = re.search(r"库区[:：]?([A-Za-z0-9\-]+)", n)
    if m:
        bits.append("库区 " + m.group(1))
    return "；".join(bits)


def _find_num(nn):
    """发票号码:先按"发票号码"锚点取(全电20位/老票8位),无锚点再全文兜底(优先20位)。"""
    m = _NUM.search(nn)
    if m:
        return m.group(1)
    m20 = re.search(r"\d{20}", nn)       # 兜底:优先全电20位,保持旧行为
    if m20:
        return m20.group(0)
    m8 = _NUM_LOOSE.search(nn)           # 再退老版8位票号
    return m8.group(0) if m8 else ""


def _extract_one(raw, path):
    """从单页文本 raw 解析出一张发票;不是增值税发票则返回 None。"""
    nn = _norm(raw)
    # 兼容老版“增值税专用/普通发票”与新版全电“电子发票（专用/普通发票）”
    special = "专用发票" in nn
    normal = ("普通发票" in nn) and not special
    if not (special or normal):
        return None
    md = _DATE.search(nn)
    # 月/日按1-2位取到后补零归一,保证 filter_month 前缀匹配不被"6月1日"漏掉
    date = "%s-%02d-%02d" % (md.group(1), int(md.group(2)), int(md.group(3))) if md else ""
    amount, tax, total = _money3(raw)
    rate = _rate(nn)
    if rate == "":                    # 差额征税等未印税率的，反推
        d = _derive_rate(amount, tax, total, _deduction(nn))
        if d is not None:
            rate = round(d, 2)
    return Invoice(
        path=path, num=_find_num(nn), date=date,
        seller=_seller(raw), amount=amount, tax=tax, total=total,
        rate=rate, item_seed=_item_seed(raw),
        note_seed=_note_seed(raw), special=special)


def extract(path):
    """解析单个 PDF 的所有页,返回 (发票列表, 存疑原因列表)。

    多页 PDF(含多张发票)逐页识别,避免只抽第一页而漏计;
    无文本层的页(扫描件)与"像发票却没认出"的页,以原因文本回传供 scan 列入存疑。
    """
    if PdfReader is None:
        raise RuntimeError("缺少 pypdf 依赖")
    reader = PdfReader(path)              # 读取失败(损坏/加密)抛异常,由 scan 捕获记录
    invoices = []
    notes = []
    pages = reader.pages
    multi = len(pages) > 1
    for pno, page in enumerate(pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as e:            # 单页读取异常也要暴露,不静默吞成空串
            notes.append("第%d页文本读取异常:%s" % (pno, e))
            continue
        if not raw.strip():               # 文本层为空:疑似扫描件/无文本层,列入存疑供人工核对
            notes.append("第%d页无文本层(疑似扫描件),请人工核对" % pno)
            continue
        inv = _extract_one(raw, path)
        if inv is not None:
            invoices.append(inv)
        elif _looks_like_invoice(raw):    # 像发票却没认出类型,存疑兜底
            notes.append("第%d页疑似发票但未能确认类型" % pno)
    return invoices, notes


class ScanResult(object):
    """一次扫描的结果：识别到的发票 + 存疑文件清单。

    invoices : 去重后的 Invoice（含专用/普通，供界面按 special 过滤）
    suspects : list[(path, reason)] —— 解析失败、或疑似发票但字段残缺的文件，
               供人工二次核对，避免漏掉一张专用发票。
    """
    __slots__ = ("invoices", "suspects")

    def __init__(self, invoices, suspects):
        self.invoices = invoices
        self.suspects = suspects


# 宽松判定：像发票但不该漏的信号（用于识别“存疑”文件）
_LOOSE_HINT = ("电子发票", "增值税", "发票号码", "价税合计", "税率")


def _looks_like_invoice(raw):
    nn = _norm(raw)
    return sum(1 for k in _LOOSE_HINT if k in nn) >= 2


def scan(root, log=None):
    """递归扫描 root 下所有 PDF。返回 ScanResult（发票去重、按日期排序 + 存疑清单）。"""
    def _lg(m):
        if log:
            log(m)
    pdfs = sorted(glob.glob(os.path.join(root, "**", "*.pdf"), recursive=True))
    _lg("发现 %d 个 PDF，开始识别…" % len(pdfs))
    by_num = {}
    suspects = []
    n_err = n_dup = 0
    for p in pdfs:
        try:
            invs, notes = extract(p)      # 现返回(多页发票列表, 存疑原因列表)
        except Exception as e:
            n_err += 1
            _lg("  跳过（解析失败）：%s —— %s" % (os.path.basename(p), e))
            suspects.append((p, "解析失败：%s" % e))
            continue
        # 无文本层/疑似漏网的页,以及读取异常页,都列入存疑并 log,不再静默丢弃
        for note in notes:
            _lg("  存疑：%s —— %s" % (os.path.basename(p), note))
            suspects.append((p, note))
        for inv in invs:
            if not inv.num:
                suspects.append((p, "识别为发票但缺发票号码"))
                continue
            if inv.special and (inv.amount is None or inv.total is None):
                suspects.append((p, "专用发票但金额字段残缺"))
            # 校验 金额+税额≈价税合计,不符则列入存疑(仍计数,供人工核对是否取错金额)
            elif (inv.amount is not None and inv.tax is not None
                    and inv.total is not None
                    and abs(inv.amount + inv.tax - inv.total) > 0.01):
                suspects.append((p, "金额+税额与价税合计不符,请核对是否取错金额"))
            if inv.num in by_num:
                n_dup += 1
                _lg("  重复发票号 %s，已忽略：%s" % (inv.num, os.path.basename(p)))
                continue
            by_num[inv.num] = inv
    items = sorted(by_num.values(), key=lambda i: (i.date or "", i.num))
    n_spec = sum(1 for i in items if i.special)
    _lg("识别发票 %d 张（专用 %d ·普通 %d）；去重 %d，失败 %d，存疑 %d。"
        % (len(items), n_spec, len(items) - n_spec, n_dup, n_err, len(suspects)))
    return ScanResult(items, suspects)


def filter_month(items, ym):
    """保留开票日期属于 ym（'2026-06'）的发票。ym 为空则不筛。"""
    if not ym:
        return list(items)
    return [i for i in items if (i.date or "").startswith(ym)]


def export_review_folder(result, out_dir, log=None):
    """把所有【专用发票】原始 PDF 复制到 out_dir 下的复核文件夹（全部月份），
    并写一份《存疑清单.txt》。返回复核文件夹路径。

    专用发票按“月份/文件名”归档，便于核对 6 月没漏收、非 6 月排对了。
    重名自动加序号，不覆盖。
    """
    import shutil

    def _lg(m):
        if log:
            log(m)
    review = os.path.join(out_dir, "专用发票复核")
    specials = [i for i in result.invoices if i.special]
    n = 0
    for inv in specials:
        ym = (inv.date or "未知月份")[:7] or "未知月份"
        sub = os.path.join(review, ym.replace("-", "年") + "月" if "-" in ym else ym)
        if not os.path.isdir(sub):
            os.makedirs(sub)
        dst = _unique_path(os.path.join(sub, os.path.basename(inv.path)))
        try:
            shutil.copy2(inv.path, dst)
            n += 1
        except Exception as e:
            _lg("  复制失败：%s —— %s" % (os.path.basename(inv.path), e))
    _write_suspects(review, result.suspects, specials)
    _lg("已导出专用发票 %d 张到复核文件夹，存疑 %d 个。"
        % (n, len(result.suspects)))
    return review


def _unique_path(path):
    """目标已存在时追加 (2)/(3)…，避免覆盖不同发票的同名文件。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists("%s (%d)%s" % (base, i, ext)):
        i += 1
    return "%s (%d)%s" % (base, i, ext)


def _write_suspects(review, suspects, specials):
    """写《存疑清单.txt》：列出解析失败/疑似漏网文件，供人工二次核对。"""
    if not os.path.isdir(review):
        os.makedirs(review)
    path = os.path.join(review, "存疑清单.txt")
    lines = ["增值税专用发票复核 —— 存疑清单",
             "（下列文件程序未纳入统计，请人工确认是否有被漏掉的专用发票）", ""]
    if suspects:
        for p, reason in suspects:
            lines.append("· %s\n    原因：%s\n    路径：%s" %
                         (os.path.basename(p), reason, p))
    else:
        lines.append("（无存疑文件）")
    lines += ["", "本次已导出专用发票 %d 张。" % len(specials)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def detect_month(items):
    """探测主月份：出现最多的 'YYYY-MM'。"""
    from collections import Counter
    c = Counter((i.date or "")[:7] for i in items if i.date)
    return c.most_common(1)[0][0] if c else ""


HEADERS = ["序号", "发票号码", "开票日期", "销售方名称", "费用项目",
           "不含税金额（元）", "税额（元）", "价税合计（元）",
           "税率/征收方式", "备注"]
_WIDTHS = [5.1, 22.6, 10.4, 35.5, 23.9, 17.1, 10.9, 15.0, 16.2, 24.6]


def write_xlsx(rows, out_path, ym=""):
    """把最终确认的行（dict 列表）写成与模板一致的汇总表。"""
    import datetime
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (ym or "").replace("-", "") or "增值税发票"
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    song = "宋体"

    ws.merge_cells("A1:J1")
    t = ws.cell(1, 1, "增值税发票")
    t.font = Font(name=song, bold=True, size=16)
    t.alignment = center
    ws.row_dimensions[1].height = 20.25
    ws.row_dimensions[2].height = 16.5
    for c, (h, w) in enumerate(zip(HEADERS, _WIDTHS), start=1):
        cell = ws.cell(2, c, h)
        cell.font = Font(name=song, size=11)
        cell.alignment = center
        cell.border = box
        ws.column_dimensions[chr(64 + c)].width = w

    r = 3
    for i, row in enumerate(rows, start=1):
        vals = [i, row.get("num", ""), _as_date(row.get("date"), datetime),
                row.get("seller", ""), row.get("item", ""), row.get("amount"),
                row.get("tax"), row.get("total"), row.get("rate", ""),
                row.get("note", "")]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(r, c, v)
            cell.font = Font(name=song, size=11)
            cell.alignment = center
            cell.border = box
            if c == 3 and isinstance(v, datetime.datetime):
                cell.number_format = "yyyy-mm-dd"
            elif c == 9 and isinstance(v, float):
                cell.number_format = "0%"
        r += 1

    _write_total(ws, r, rows, box, center, song, Font)
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    wb.save(out_path)
    return out_path


def _as_date(s, datetime):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    if m:
        return datetime.datetime(*[int(x) for x in m.groups()])
    return s or ""


def _write_total(ws, r, rows, box, center, song, Font):
    """合计行：A:E 合并写“合计”，F/G/H 求和，I/J 填 '-'。"""
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    c = ws.cell(r, 1, "合计")
    c.font = Font(name=song, bold=True, size=11)
    c.alignment = center
    for col, key in ((6, "amount"), (7, "tax"), (8, "total")):
        s = sum(x.get(key) or 0 for x in rows)
        cell = ws.cell(r, col, round(s, 2))
        cell.font = Font(name=song, bold=True, size=11)
        cell.alignment = center
    for col in (9, 10):
        ws.cell(r, col, "-").alignment = center
    for col in range(1, 11):
        ws.cell(r, col).border = box


# ---------------------------------------------------------------------------
# 统一出口（与其余功能一致：generate(...) -> dict，输出目录经 paths 统一解析）
# ---------------------------------------------------------------------------
def generate(result, rows, ym, out_dir=None, log=None):
    """写汇总表 + 导出专用发票复核文件夹，返回结果 dict。

    result : scan() 的 ScanResult（用于导出复核文件夹与存疑清单）
    rows   : 复核对话框最终确认的行 dict 列表（已含人工精修的费用项目/备注）
    ym     : 目标月份 'YYYY-MM'，决定 sheet 名与汇总表文件名
    out_dir: 不传则经 settings + paths 统一解析到 <文档>/…/输出/增值税发票统计/<时间戳>/
    """
    def _lg(msg):
        if log:
            log(msg)
    if out_dir is None:
        from . import paths as _paths, settings as _settings
        st = _settings.get_settings()
        out_dir = _paths.resolve_output_dir("invoice", **st.output_kwargs())
    elif not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    _lg("输出文件夹：%s" % out_dir)

    mm = "%d月" % int(ym[5:7]) if ym and len(ym) >= 7 else ""
    xlsx = os.path.join(out_dir, "%s统计增值税发票.xlsx" % mm)
    write_xlsx(rows, xlsx, ym)
    _lg("已生成汇总表：%s（%d 张专用发票）" % (os.path.basename(xlsx), len(rows)))

    review = export_review_folder(result, out_dir, log=log)
    return {"xlsx": xlsx, "review_dir": review, "out_dir": out_dir,
            "count": len(rows), "suspects": len(result.suspects)}
