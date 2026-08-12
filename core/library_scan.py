# -*- coding: utf-8 -*-
"""本机文件库分类前的轻量表头扫描。"""

from __future__ import annotations

import os

from . import common_core
from .library_classification import normalize_keyword_text


def _token_set(rows, max_rows: int, max_cells: int) -> set[str]:
    """从二维行迭代器中收集有限范围内的非空分类关键词。"""

    tokens: set[str] = set()
    for row_index, row in enumerate(rows):
        if row_index >= max_rows:
            break
        # 限制扫描宽度，避免历史格式把 max_column 扩展到极右侧拖慢分类。
        for value in row[:max_cells]:
            token = normalize_keyword_text(value)
            if token:
                tokens.add(token)
    return tokens


def _scan_modern(path: str, max_rows: int, max_cells: int) -> dict[str, set[str]]:
    """以只读流式方式扫描 xlsx/xlsm，并修复错误 dimension 声明。"""

    workbook = common_core.load_data_only_stream(path)
    try:
        return {
            worksheet.title: _token_set(
                worksheet.iter_rows(values_only=True), max_rows, max_cells,
            )
            for worksheet in workbook.worksheets
        }
    finally:
        # Windows 下必须及时关闭 ZIP 句柄，否则后续归档覆盖可能遇到文件占用。
        workbook.close()


def _scan_legacy(path: str, max_rows: int, max_cells: int) -> dict[str, set[str]]:
    """直接扫描旧 xls 顶部区域，不复制整本工作簿到中间列表。"""

    import xlrd

    book = xlrd.open_workbook(path)
    result: dict[str, set[str]] = {}
    for sheet in book.sheets():
        rows = (
            [sheet.cell(row, column).value for column in range(min(max_cells, sheet.ncols))]
            for row in range(min(max_rows, sheet.nrows))
        )
        result[sheet.name] = _token_set(rows, max_rows, max_cells)
    return result


def _report_failure(log, path: str, error: Exception) -> None:
    """尽力记录读取失败；日志回调故障不能把可归档文件改为失败。"""

    if not log:
        return
    try:
        log(
            "⚠ 无法读取 %s(%s: %s),将按未识别处理"
            % (os.path.basename(path), type(error).__name__, error)
        )
    except Exception:
        pass


def scan_headers(
    path: str,
    max_rows: int = 15,
    max_cells: int = 60,
    log=None,
) -> dict[str, set[str]]:
    """提取每个页签顶部关键词；失败时返回空结果并记录可读原因。"""

    extension = os.path.splitext(path)[1].lower()
    try:
        if extension in (".xlsx", ".xlsm"):
            return _scan_modern(path, max_rows, max_cells)
        if extension == ".xls":
            return _scan_legacy(path, max_rows, max_cells)
        return {}
    except Exception as error:
        # 分类失败不阻断归档；调用方会继续使用文件名信号或归入“未识别”。
        _report_failure(log, path, error)
        return {}


__all__ = ["scan_headers"]
