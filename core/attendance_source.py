# -*- coding: utf-8 -*-
"""考勤系统打卡来源的表头识别、逐行读取与多文件合并。"""

from __future__ import annotations

import os
from collections.abc import Iterable

from . import common_core as cc


_SOURCE_ROLES = ("name", "date", "on", "off")


def _mapped_source_header(rows, opts, path):
    """人工列映射完整时直接返回，不再执行模糊表头识别。"""

    roles = opts.resolve_roles(path)
    if not roles or not all(role in roles for role in _SOURCE_ROLES):
        return None
    header = opts.resolve_header(path)
    # 角色列配置使用 0 基编号；表头行面向用户使用 1 基编号。
    return ((header - 1) if header else 0), {role: roles[role] for role in _SOURCE_ROLES}


def _source_columns(row):
    """从候选表头行中提取姓名、日期和第一组上下班打卡列。"""

    headers = [cc.norm_name(value) for value in row]
    has_name = any("姓名" in header for header in headers)
    has_punch = any("上班" in header and "打卡" in header for header in headers)
    if not has_name or not has_punch:
        return None
    columns = {}
    for column, header in enumerate(headers):
        # 每个角色只采用首个命中，避免“上班2打卡时间”覆盖第一组打卡记录。
        if "name" not in columns and "姓名" in header:
            columns["name"] = column
        elif "date" not in columns and "日期" in header:
            columns["date"] = column
        elif "on" not in columns and "上班" in header and "打卡" in header:
            columns["on"] = column
        elif "off" not in columns and "下班" in header and "打卡" in header:
            columns["off"] = column
    return columns if all(role in columns for role in _SOURCE_ROLES) else None


def detect_source_header(rows, opts, path=""):
    """按“人工映射 > 指定表头 > 前六行自动识别”定位源表字段。"""

    mapped = _mapped_source_header(rows, opts, path)
    if mapped is not None:
        return mapped
    header = opts.resolve_header(path)
    candidates: Iterable[int] = [header - 1] if header else range(min(6, len(rows)))
    for index in candidates:
        if index < 0 or index >= len(rows):
            continue
        columns = _source_columns(rows[index])
        if columns is not None:
            return index, columns
    return None


def _selected_sheets(path, opts):
    """应用人工页签选择，不存在时明确报错而不是静默改读其他页。"""

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
    """把有效正文行转换为 ``(姓名, 日期) -> (上班, 下班)`` 映射。"""

    records = {}
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
        records[(name, date_value)] = (on_text, off_text)
    return records


def load_source(path, opts=None):
    """读取首个可识别页签，返回按规范姓名和真实日期索引的打卡记录。"""

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
    """后文件只有提供真实打卡文本时才覆盖旧值，空串和横线视为缺失。"""

    return new_value if new_value and new_value not in ("-", "—") else old_value


def _merge_record(merged, key, punch, opts, log):
    """合并一条重复打卡记录，并返回是否发生冲突。"""

    if key not in merged:
        merged[key] = punch
        return False
    if opts.conflict == "warn":
        log("    ! 重复且不覆盖：%s %s" % (key[0], "-".join(map(str, key[1]))))
    elif opts.conflict == "last":
        old_on, old_off = merged[key]
        new_on, new_off = punch
        merged[key] = (
            _usable_punch(new_on, old_on),
            _usable_punch(new_off, old_off),
        )
    # first 和 warn 都保留首条；warn 只额外报告人工可见冲突。
    return True


def _warn_failed_sources(paths, merged, failed, log):
    """失败文件占比过高时提示结果可能不完整。"""

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
    """合并多个每日统计文件，并按配置处理重复姓名日期记录。"""

    opts = opts or cc.DEFAULTS
    log = log or (lambda *args, **kwargs: None)
    source_paths = [paths] if isinstance(paths, str) else list(paths)
    merged = {}
    conflicts = 0
    failed = 0
    for path in source_paths:
        cc.warn_if_uncached(path, log, what="打卡时间")
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
