# -*- coding: utf-8 -*-
"""
PDF 页级文件工具核心
====================
基于纯 Python 的 pypdf 提供合并、逐页/按范围拆分、提取指定页和删除指定页。模块只
复制 PDF 页面对象，不进行渲染、OCR、图片转换或转 Excel，避免引入额外原生运行库。
输出目录统一由 ``core.paths`` 管理，错误统一包装为面向用户的 ``PdfError``。

页码范围使用用户看到的 1 基页码，例如 ``1,3,5-8,12-``；内部转换为有序去重的
0 基索引。越界页码忽略，反向范围自动交换端点，开口范围默认延伸到首页或末页；
完全无效时明确报错，不静默选择全部页面。

读取时先把源 PDF 放入内存 BytesIO，再交给 pypdf，确保 Windows 文件句柄立即释放，
处理完成后用户可以移动或删除源文件。只尝试空密码解密；需要真实密码的文件暂不处理。
"""
import os
import io

from . import paths as _paths

try:
    from pypdf import PdfReader, PdfWriter
    _HAS_PYPDF = True
except Exception:
    # PDF 工具是可选模块；缺少依赖时应用其他业务仍可正常启动。
    _HAS_PYPDF = False


class PdfError(Exception):
    """缺少组件、文件损坏、加密或页码错误等可直接展示的业务异常。"""


def _ensure_lib():
    """确认 pypdf 可用，否则抛出带安装建议的业务异常。"""
    if not _HAS_PYPDF:
        raise PdfError("未安装 PDF 组件(pypdf),无法处理 PDF。请联系管理员或重新安装程序。")


def _page_range(part: str, total: int) -> list[int]:
    """解析一个页码片段并返回合法的 0 基页码。"""

    if "-" in part:
        left, _, right = part.partition("-")
        left, right = left.strip(), right.strip()
        # 两端都不是数字时不能把任意文本解释成“全选范围”。
        if not left.isdigit() and not right.isdigit():
            return []
        start = int(left) if left.isdigit() else 1
        end = int(right) if right.isdigit() else total
        if start > end:
            start, end = end, start
        return [page - 1 for page in range(start, end + 1) if 1 <= page <= total]
    if part.isdigit():
        page = int(part)
        return [page - 1] if 1 <= page <= total else []
    return []


def parse_pages(spec, total):
    """把用户页码表达式解析为有序、去重的 0 基索引列表。

    同时接受中文逗号和全角减号。范围缺少左端时从第一页开始，缺少右端时延伸到
    ``total``；起点大于终点时自动交换。越界页逐个忽略，重复页只保留首次出现位置，
    因此输出顺序遵循用户各段的书写顺序。空表达式或最终无有效页抛 ``PdfError``。
    """
    if not spec or not spec.strip():
        raise PdfError("请填写页码范围,例如 1,3,5-8")
    out = []
    seen = set()
    for part in spec.replace("，", ",").replace("－", "-").split(","):
        part = part.strip()
        if not part:
            continue
        for index in _page_range(part, total):
            if index not in seen:
                seen.add(index)
                out.append(index)
    if not out:
        raise PdfError("页码范围无效或超出文档页数(共 %d 页)" % total)
    return out


def _open_reader(path):
    """将 PDF 读入内存并返回已可访问页面的 ``PdfReader``。

    ``PdfReader(path)`` 可能持有底层句柄直到垃圾回收，在 Windows 上锁住源文件；
    BytesIO 方案在读完字节后立即关闭系统句柄。加密文件只尝试空密码，失败则给出
    明确提示，不向调用层泄漏 pypdf 的底层异常类型。
    """
    try:
        with open(path, "rb") as fh:
            # 页级办公 PDF 规模可接受整文件入内存，以换取可靠释放 Windows 文件锁。
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
    """返回 PDF 页数，供界面校验和提示页码范围。"""
    _ensure_lib()
    return len(_open_reader(path).pages)


def merge(files, out_dir=None, out_name="合并结果.pdf", log=None):
    """按输入文件与原页顺序合并至少两份 PDF。

    每份源文件先独立验证并读取，所有页面追加到一个 ``PdfWriter``；输出完成后返回
    单文件路径、目录和统一 ``out_files`` 列表。函数不覆盖或修改任何源文件。
    """
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
    """按给定 0 基索引顺序把页面复制到一个新 PDF。"""
    w = PdfWriter()
    for i in indices:
        w.add_page(reader.pages[i])
    with open(out_file, "wb") as fh:
        w.write(fh)


def split(file, mode="each", spec="", out_dir=None, log=None):
    """把单个 PDF 逐页或按多个用户范围拆成独立文件。

    ``mode="each"`` 每页输出一份，页码按总页数宽度补零；其他模式按逗号先拆成范围
    组，每组再交给 ``parse_pages``，一个范围对应一个“第 N 段”文件。返回所有输出，
    ``out_file`` 兼容指向第一份结果。
    """
    _ensure_lib()
    log = log or (lambda *_: None)
    r = _open_reader(file)
    total = len(r.pages)
    out_dir = out_dir or _paths.resolve_output_dir("pdf_tools")
    stem = os.path.splitext(os.path.basename(file))[0]
    outs = []
    if mode == "each":
        # 补零保证文件管理器按名称排序时仍保持自然页序。
        width = len(str(total))
        for i in range(total):
            name = "%s_第%s页.pdf" % (stem, str(i + 1).rjust(width, "0"))
            of = os.path.join(out_dir, name)
            _write_pages(r, [i], of)
            outs.append(of)
        log("已按单页拆分为 %d 个文件" % total)
    else:  # ranges
        # 外层逗号决定输出文件数量，组内仍可使用 parse_pages 支持单页和范围。
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
    """按用户书写顺序提取指定页到一份新 PDF。"""
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
    """删除指定页并按原顺序导出所有剩余页面。

    如果用户选择了全部页面则取消操作并报错，避免生成结构无意义或无法打开的空 PDF。
    """
    _ensure_lib()
    log = log or (lambda *_: None)
    r = _open_reader(file)
    total = len(r.pages)
    drop = set(parse_pages(spec, total))
    # 删除只关心成员关系，转集合后按原页顺序构造 keep。
    keep = [i for i in range(total) if i not in drop]
    if not keep:
        raise PdfError("删除后没有剩余页面,已取消")
    out_dir = out_dir or _paths.resolve_output_dir("pdf_tools")
    stem = os.path.splitext(os.path.basename(file))[0]
    of = os.path.join(out_dir, "%s_删除%d页.pdf" % (stem, len(drop)))
    _write_pages(r, keep, of)
    log("已删除 %d 页,保留 %d 页 → %s" % (len(drop), len(keep), of))
    return {"out_file": of, "out_dir": out_dir, "out_files": [of]}
