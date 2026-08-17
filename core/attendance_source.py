# -*- coding: utf-8 -*-
"""考勤来源识别与合并模块。

职责：
- 识别考勤打卡源表的表头（人工列映射 > 指定表头行 > 前六行自动识别）。
- 逐行读取源表，把姓名、日期规范化为 ``(姓名, 日期) -> (上班文本, 下班文本)``。
- 合并多个每日统计文件，并按配置处理重复的“姓名+日期”记录。

边界：
- 只负责来源表的结构识别与文本提取；时间解析、半小时取整和写表由后续考勤流程处理。
- 单文件只采用首个有效数据页，避免汇总页与明细页重复计入。
- 与 common_core 的表头/工作表配置解析和表格读取能力配合使用。
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from . import common_core as cc


_SOURCE_ROLES = ("name", "date", "on", "off")


def _mapped_source_header(rows, opts, path):
    """返回人工映射完整时的表头定位结果，跳过模糊表头识别。

    当 opts 对 path 解析出完整的姓名/日期/上班/下班角色列时直接采用；
    表头行序号由 1 基展示值换算为 0 基索引。任一角色缺失时返回 None，
    交由调用方继续自动识别。
    """

    roles = opts.resolve_roles(path)
    if not roles or not all(role in roles for role in _SOURCE_ROLES):
        return None
    header = opts.resolve_header(path)
    # 角色列配置使用 0 基编号；表头行面向用户使用 1 基编号。
    return ((header - 1) if header else 0), {role: roles[role] for role in _SOURCE_ROLES}


def _source_columns(row):
    """从候选表头行中提取姓名、日期和第一组上下班打卡列。

    参数 row 为候选表头行；返回 dict(role->0 基列号)，仅当四个角色
    （姓名/日期/上班打卡/下班打卡）全部命中时返回，否则返回 None。
    每个角色只采用首个命中列，防止“上班2打卡时间”覆盖第一组打卡记录。
    """
    headers = [cc.norm_name(value) for value in row]
    if not any("姓名" in header for header in headers):
        return None
    if not any("上班" in header and "打卡" in header for header in headers):
        return None
    role_rules = (
        ("name", lambda header: "姓名" in header),
        ("date", lambda header: "日期" in header),
        ("on", lambda header: "上班" in header and "打卡" in header),
        ("off", lambda header: "下班" in header and "打卡" in header),
    )
    columns = {}
    for column, header in enumerate(headers):
        # 每个角色只采用首个命中，避免“上班2打卡时间”覆盖第一组打卡记录。
        for role, matches in role_rules:
            if role not in columns and matches(header):
                columns[role] = column
                break
    return columns if all(role in columns for role in _SOURCE_ROLES) else None


def detect_source_header(rows, opts, path=""):
    """按“人工映射 > 指定表头 > 前六行自动识别”定位源表字段。

    参数 rows 为工作表二维行数据，opts 提供按 path 解析的人工配置。
    返回 ``(header_index, columns)``，header_index 为 0 基表头行号，
    columns 为角色到列号的映射；无法识别时返回 None。
    """

    mapped = _mapped_source_header(rows, opts, path)
    if mapped is not None:
        return mapped
    header = opts.resolve_header(path)
    # 未指定表头行时仅扫描前六行，避免把正文数据误判为表头。
    candidates: Iterable[int] = [header - 1] if header else range(min(6, len(rows)))
    for index in candidates:
        if index < 0 or index >= len(rows):
            continue
        columns = _source_columns(rows[index])
        if columns is not None:
            return index, columns
    return None


def _selected_sheets(path, opts):
    """应用人工页签选择并返回 ``(页签名, 行数据)`` 列表。

    未指定页签时返回全部页签；指定页签不存在时抛出 ValueError，
    避免把用户明确选择的文件静默读成其它页。
    """

    sheets = cc.read_sheets(path)
    requested = opts.resolve_sheet(path)
    if not requested:
        return sheets
    selected = [(name, rows) for name, rows in sheets if name == requested]
    if not selected:
        raise ValueError("文件 %s 中找不到工作表 '%s'" % (os.path.basename(path), requested))
    return selected


def _row_value(row, column):
    """安全读取可能短于表头宽度的行，缺列按空值处理。"""

    return row[column] if column < len(row) else None


def _source_records(rows, header_index, columns, data_start):
    """把有效正文行转换为 ``(姓名, 日期) -> (上班, 下班)`` 映射。

    跳过姓名为空或日期无法规范化的行；上下班保留源表展示文本，
    时间解析与半小时取整统一延后到写表阶段。data_start 采用 1 基行号，
    未配置时默认从表头下一行开始。
    """

    records = {}
    # data_start 面向用户为 1 基行号；未配置时从表头下一行开始读取正文。
    start = (data_start - 1) if data_start else header_index + 1
    for row in rows[start:]:
        name = cc.norm_name(_row_value(row, columns["name"]))
        date_value = cc.norm_date(_row_value(row, columns["date"]))
        if not name or date_value is None:
            continue
        on_value = _row_value(row, columns["on"])
        off_value = _row_value(row, columns["off"])
        # 保留源表展示文本，时间解析与半小时取整统一延后到写表阶段。
        on_text = "" if on_value is None else str(on_value).strip()
        off_text = "" if off_value is None else str(off_value).strip()
        # 同一文件内重复的“姓名+日期”由末行覆盖；跨文件冲突在 load_source_multi 中处理。
        records[(name, date_value)] = (on_text, off_text)
    return records


def load_source(path, opts=None):
    """读取单文件首个可识别页签，返回打卡记录映射。

    参数 opts 缺省时使用 common_core.DEFAULTS；返回
    ``(姓名, 日期) -> (上班文本, 下班文本)``。只采用第一个能识别表头
    的数据页，防止汇总页与明细页被重复计入；全部页签都无法识别时抛出
    ValueError。
    """

    opts = opts or cc.DEFAULTS
    data_start = opts.resolve_data_start(path)
    for _sheet_name, rows in _selected_sheets(path, opts):
        detected = detect_source_header(rows, opts, path)
        if detected is None:
            continue
        header_index, columns = detected
        # 一个文件只采用首个有效数据页，防止汇总页和明细页被重复计入。
        return _source_records(rows, header_index, columns, data_start)
    raise ValueError(
        "源表 %s 未找到表头（需含'姓名'列与'上班/下班打卡'列）。"
        % os.path.basename(path)
    )


def _usable_punch(new_value, old_value):
    """返回新值中真实可用的打卡文本，否则沿用旧值。

    空串以及横线（半角“-”或全角“—”）视为缺失，避免后文件用空值
    覆盖前文件已读到的打卡时间。
    """

    return new_value if new_value and new_value not in ("-", "—") else old_value


def _merge_record(merged, key, punch, opts, log):
    """把一条记录并入 merged，并返回该键是否与已有记录冲突。

    冲突策略由 opts.conflict 决定：first/warn 保留首条，last 用后文件
    真实打卡文本覆盖空值或横线；warn 额外通过 log 报告冲突。
    """

    if key not in merged:
        merged[key] = punch
        return False
    if opts.conflict == "warn":
        log("    ! 重复且不覆盖：%s %s" % (key[0], "-".join(map(str, key[1]))))
    elif opts.conflict == "last":
        old_on, old_off = merged[key]
        new_on, new_off = punch
        # 后文件仅覆盖空串和横线，已有真实打卡时间不被覆盖。
        merged[key] = (
            _usable_punch(new_on, old_on),
            _usable_punch(new_off, old_off),
        )
    # first 和 warn 都保留首条；warn 只额外报告人工可见冲突。
    return True


def _warn_failed_sources(paths, merged, failed, log):
    """失败文件占比过高时通过 log 提示结果可能不完整。

    合并后无任何记录时只要发生失败就警告；有记录时失败数占比达到一半
    及以上才警告。
    """

    total = len(paths)
    if not failed or (merged and failed != total and failed / float(total) < 0.5):
        return
    if not merged:
        log("⚠ 警告：%d 个文件全部读取失败（合并后无任何打卡记录），请检查表头/格式/是否选错文件。" % failed)
    else:
        log(
            "⚠ 警告：%d/%d 个文件读取失败（占比过半），结果可能不完整，请检查这些文件的表头/格式。"
            % (failed, total)
        )


def load_source_multi(paths, opts=None, log=None):
    """合并多个每日统计文件，返回 ``(merged, 统计信息)``。

    单个文件读取失败只跳过并计数，不中断整体合并；重复的“姓名+日期”
    按 opts.conflict 处理。返回统计信息包含文件数、合并后记录数、
    冲突数和失败数。
    """

    opts = opts or cc.DEFAULTS
    log = log or (lambda *args, **kwargs: None)
    source_paths = [paths] if isinstance(paths, str) else list(paths)
    merged = {}
    conflicts = 0
    failed = 0
    for path in source_paths:
        cc.warn_if_uncached(path, log, what="打卡时间")
        # 单个文件失败只跳过并计数，保留其它文件已合并的结果。
        try:
            records = load_source(path, opts)
        except Exception as error:
            failed += 1
            log("  · [跳过] %s（读取失败：%s）" % (os.path.basename(path), error))
            continue
        log("  · [读取] %s：%d 条打卡记录" % (os.path.basename(path), len(records)))
        conflicts += sum(
            _merge_record(merged, key, punch, opts, log)
            for key, punch in records.items()
        )
    if conflicts:
        names = {"last": "后者覆盖", "first": "先者优先", "warn": "不覆盖仅提示"}
        log("  注意：%d 条(姓名+日期)重复，按【%s】处理。" % (conflicts, names[opts.conflict]))
    _warn_failed_sources(source_paths, merged, failed, log)
    return merged, {
        "files": len(source_paths),
        "records": len(merged),
        "conflicts": conflicts,
        "failed": failed,
    }


__all__ = ["detect_source_header", "load_source", "load_source_multi"]
