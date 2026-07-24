# -*- coding: utf-8 -*-
"""
PDF 工具箱核心 —— 合并 / 拆分 / 提取·删除页,基于 pypdf(纯 Python)
====================================================================
只做"页级"操作,不涉及渲染成图片或转 Excel(那些需带原生库,旧版 Windows 风险高)。
所有函数接受 log 回调(与各核心功能同构),输出写入统一 paths 目录。

页码范围文本(供提取/删除): 用户按"看到的页码"从 1 数起,如
    "1,3,5-8,12-"   ->  第1、3、5~8、12到末页
内部转成 0-based 索引集合。
兼容 Windows 10/11 + Python 3.13。pypdf==6.14.2。
"""
import os
import io

from . import paths as _paths

try:
    from pypdf import PdfReader, PdfWriter
    _HAS_PYPDF = True
except Exception:
    _HAS_PYPDF = False


class PdfError(Exception):
    """PDF 操作的业务异常(缺库/加密/损坏等),消息面向用户。"""


def _ensure_lib():
    if not _HAS_PYPDF:
        raise PdfError("未安装 PDF 组件(pypdf),无法处理 PDF。请联系管理员或重新安装程序。")


def parse_pages(spec, total):
    """把页码范围文本解析成有序、去重的 0-based 索引列表。

    spec 例: "1,3,5-8,12-"; total 为总页数。越界的页码被裁剪/忽略。
    解析失败(空/全非法)抛 PdfError。"""
    if not spec or not spec.strip():
        raise PdfError("请填写页码范围,例如 1,3,5-8")
    out = []
    seen = set()
    for part in spec.replace("，", ",").replace("－", "-").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            a = a.strip(); b = b.strip()
            # 两端都不是数字(如 "-"、"a-b")视为非法段,跳过,避免回退成静默全选
            if not a.isdigit() and not b.isdigit():
                continue
            start = int(a) if a.isdigit() else 1
            end = int(b) if b.isdigit() else total
            if start > end:
                start, end = end, start
            for p in range(start, end + 1):
                i = p - 1
                if 0 <= i < total and i not in seen:
                    seen.add(i); out.append(i)
        elif part.isdigit():
            i = int(part) - 1
            if 0 <= i < total and i not in seen:
                seen.add(i); out.append(i)
    if not out:
        raise PdfError("页码范围无效或超出文档页数(共 %d 页)" % total)
    return out


def _open_reader(path):
    """打开 PDF;加密的空密码尝试解密,失败则抛面向用户的异常。

    先把整份文件读进内存 BytesIO 再交给 pypdf —— PdfReader(路径) 会持有底层
    文件句柄直到 GC,Windows 上会锁住源文件(处理完删不掉/存不回)。读进内存后
    OS 句柄当即释放,发票级 PDF 内存开销可忽略。
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        r = PdfReader(io.BytesIO(data))
    except PdfError:
        raise
    except Exception as e:
        raise PdfError("无法读取「%s」:文件可能损坏或不是有效 PDF(%s)"
                       % (os.path.basename(path), e))
    if r.is_encrypted:
        try:
            if r.decrypt("") == 0:      # 0 = 密码错误
                raise PdfError("「%s」已加密,需要密码,暂不支持处理。"
                               % os.path.basename(path))
        except PdfError:
            raise
        except Exception:
            raise PdfError("「%s」已加密,暂不支持处理。" % os.path.basename(path))
    return r


def page_count(path):
    """返回 PDF 页数;失败抛 PdfError。供页面预览页码范围用。"""
    _ensure_lib()
    return len(_open_reader(path).pages)


def merge(files, out_dir=None, out_name="合并结果.pdf", log=None):
    """按顺序合并多个 PDF。返回 {out_file, out_dir}。"""
    _ensure_lib()
    log = log or (lambda *_: None)
    if len(files) < 2:
        raise PdfError("合并至少需要 2 个 PDF 文件")
    out_dir = out_dir or _paths.resolve_output_dir("pdf_tools")
    writer = PdfWriter()
    total = 0
    for f in files:
        r = _open_reader(f)
        n = len(r.pages)
        for pg in r.pages:
            writer.add_page(pg)
        total += n
        log("加入 %s(%d 页)" % (os.path.basename(f), n))
    out_file = os.path.join(out_dir, out_name)
    with open(out_file, "wb") as fh:
        writer.write(fh)
    log("已合并 %d 个文件、共 %d 页 → %s" % (len(files), total, out_file))
    return {"out_file": out_file, "out_dir": out_dir, "out_files": [out_file]}


def _write_pages(reader, indices, out_file):
    """把 reader 的若干页(0-based)写成一个新 PDF。"""
    w = PdfWriter()
    for i in indices:
        w.add_page(reader.pages[i])
    with open(out_file, "wb") as fh:
        w.write(fh)


def split(file, mode="each", spec="", out_dir=None, log=None):
    """拆分单个 PDF。

    mode="each"  : 每页导出成单独 PDF
    mode="ranges": 按 spec(如 "1-3,4-6")每个范围导出一个 PDF
    返回 {out_files, out_dir}。"""
    _ensure_lib()
    log = log or (lambda *_: None)
    r = _open_reader(file)
    total = len(r.pages)
    out_dir = out_dir or _paths.resolve_output_dir("pdf_tools")
    stem = os.path.splitext(os.path.basename(file))[0]
    outs = []
    if mode == "each":
        width = len(str(total))
        for i in range(total):
            name = "%s_第%s页.pdf" % (stem, str(i + 1).rjust(width, "0"))
            of = os.path.join(out_dir, name)
            _write_pages(r, [i], of)
            outs.append(of)
        log("已按单页拆分为 %d 个文件" % total)
    else:  # ranges
        groups = [g.strip() for g in spec.replace("，", ",").split(",") if g.strip()]
        if not groups:
            raise PdfError("请填写拆分范围,例如 1-3,4-6")
        for gi, g in enumerate(groups, 1):
            idx = parse_pages(g, total)
            name = "%s_第%s段.pdf" % (stem, gi)
            of = os.path.join(out_dir, name)
            _write_pages(r, idx, of)
            outs.append(of)
            log("段 %d(%s)→ %d 页" % (gi, g, len(idx)))
        log("已按 %d 个范围拆分" % len(groups))
    return {"out_files": outs, "out_dir": out_dir, "out_file": outs[0] if outs else ""}


def extract_pages(file, spec, out_dir=None, log=None):
    """提取指定页到一个新 PDF。返回 {out_file, out_dir}。"""
    _ensure_lib()
    log = log or (lambda *_: None)
    r = _open_reader(file)
    idx = parse_pages(spec, len(r.pages))
    out_dir = out_dir or _paths.resolve_output_dir("pdf_tools")
    stem = os.path.splitext(os.path.basename(file))[0]
    of = os.path.join(out_dir, "%s_提取%d页.pdf" % (stem, len(idx)))
    _write_pages(r, idx, of)
    log("已提取 %d 页 → %s" % (len(idx), of))
    return {"out_file": of, "out_dir": out_dir, "out_files": [of]}


def delete_pages(file, spec, out_dir=None, log=None):
    """删除指定页,保留其余页导出新 PDF。返回 {out_file, out_dir}。"""
    _ensure_lib()
    log = log or (lambda *_: None)
    r = _open_reader(file)
    total = len(r.pages)
    drop = set(parse_pages(spec, total))
    keep = [i for i in range(total) if i not in drop]
    if not keep:
        raise PdfError("删除后没有剩余页面,已取消")
    out_dir = out_dir or _paths.resolve_output_dir("pdf_tools")
    stem = os.path.splitext(os.path.basename(file))[0]
    of = os.path.join(out_dir, "%s_删除%d页.pdf" % (stem, len(drop)))
    _write_pages(r, keep, of)
    log("已删除 %d 页,保留 %d 页 → %s" % (len(drop), len(keep), of))
    return {"out_file": of, "out_dir": out_dir, "out_files": [of]}
