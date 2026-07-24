# -*- coding: utf-8 -*-
"""Tauri 前端与 Python 业务核心之间的受控 JSON 桥接。"""
import json
import inspect
import os
import sys
import traceback

from . import currency_core
from . import library
from . import paths
from . import settings as settings_mod
from . import task_history
from . import version


_SETTING_KEYS = {
    "output_mode", "custom_output_root", "theme_mode", "reduce_motion",
    "check_update_on_start", "auto_open_output", "minimize_to_tray",
    "enable_incremental_cache", "show_done_dialog",
}


def _configure_stdio():
    """强制桥接协议使用 UTF-8，避免打包后继承 Windows 控制台 GBK。"""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _jsonable(value):
    """把 core 返回值递归转换成 JSON 安全结构。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    slots = getattr(value, "__slots__", None)
    if slots:
        return {str(key): _jsonable(getattr(value, key, None)) for key in slots}
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _payload_list(payload, key, required=True):
    """读取并校验路径列表。"""
    values = (payload or {}).get(key)
    if isinstance(values, str):
        values = [values]
    if values is None and not required:
        return []
    if not isinstance(values, list) or (required and not values):
        raise ValueError("%s 必须是非空路径列表" % key)
    paths = [os.path.abspath(str(value)) for value in values if str(value).strip()]
    if required and not paths:
        raise ValueError("%s 必须包含有效文件路径" % key)
    missing = [path for path in paths if not os.path.isfile(path)]
    if missing:
        raise FileNotFoundError("找不到文件：%s" % missing[0])
    return paths


def _payload_file(payload, key, required=True):
    """读取并校验单个文件路径。"""
    values = _payload_list(payload, key, required=required)
    return values[0] if values else None


def _payload_dir(payload, key):
    """读取并校验目录路径。"""
    raw = str((payload or {}).get(key) or "").strip()
    if not raw:
        raise ValueError("%s 不能为空" % key)
    path = os.path.abspath(raw)
    if not os.path.isdir(path):
        raise NotADirectoryError("找不到目录：%s" % path)
    return path


def _options(values=None):
    """从 JSON 构造考勤/对账共用 Options。"""
    from . import common_core
    values = values if isinstance(values, dict) else {}
    allowed = {
        "workday_hours", "overtime", "conflict", "header_row", "sheet_name",
        "tolerance", "data_start", "skip_extra", "columns", "auto_actual",
        "night_shift", "night_start_hour", "night_workday_hours", "night_max_hours",
    }
    return common_core.Options(**{key: value for key, value in values.items()
                                  if key in allowed})


def _output_dir(result):
    """从不同业务结果中提取任务输出目录。"""
    if not isinstance(result, dict):
        return ""
    direct = result.get("out_dir")
    if direct:
        return str(direct)
    for key in ("out_file", "filled_path", "summary_path", "report_path",
                "report", "plan_path", "xlsx", "out"):
        path = result.get(key)
        if path:
            return os.path.dirname(str(path))
    return ""


def _task(feature, title, callback):
    """统一执行长任务，收集日志并写任务历史。"""
    logs = []
    request_id = os.environ.get("FYT_REQUEST_ID", "")
    task_id = task_history.start_task(
        feature, title, {"frontend": "tauri", "request_id": request_id})

    def emit(kind, value):
        if os.environ.get("FYT_BRIDGE_EVENTS") != "1":
            return
        event = {"request_id": request_id, "kind": kind, "value": value}
        sys.stderr.write("__FYT_EVENT__" + json.dumps(
            event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stderr.flush()

    def log(message):
        text = str(message)
        logs.append(text)
        emit("log", text)

    def progress(value):
        try:
            percent = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            percent = 0
        emit("progress", percent)

    try:
        if len(inspect.signature(callback).parameters) >= 2:
            result = callback(log, progress)
        else:
            result = callback(log)
        out_dir = _output_dir(result)
        task_history.finish_task(task_id, "ok", "处理完成", out_dir)
        emit("progress", 100)
        return {"result": result, "logs": logs, "task_id": task_id,
                "out_dir": out_dir}
    except Exception as error:
        task_history.finish_task(task_id, "failed", str(error), "")
        raise


def _health(_payload):
    return {
        "app_name": version.APP_NAME,
        "version": version.VERSION,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "project_root": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "features": [
            "attendance", "reconcile", "arrival", "pivot", "purchase",
            "delivery", "library", "mappings", "templates", "invoice",
            "currency", "rename", "text", "pdf", "excel", "compare",
            "settings", "tasks",
        ],
    }


def _settings_get(_payload):
    settings = settings_mod.get_settings()
    return {key: _jsonable(settings.get(key)) for key in sorted(_SETTING_KEYS)}


def _settings_update(payload):
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        raise ValueError("设置参数必须是对象")
    unknown = sorted(set(values) - _SETTING_KEYS)
    if unknown:
        raise ValueError("不允许修改这些设置：%s" % "、".join(unknown))
    settings = settings_mod.get_settings()
    for key, value in values.items():
        settings.set(key, value)
    if not settings.save():
        raise OSError("设置保存失败，请检查配置目录是否可写")
    return _settings_get({})


def _tasks_list(payload):
    limit = int((payload or {}).get("limit", 100))
    return {"summary": task_history.summary(),
            "items": task_history.list_recent(limit)}


def _tasks_clear(_payload):
    return {"removed": task_history.clear_finished()}


def _tasks_cancel(payload):
    request_id = str((payload or {}).get("request_id") or "")
    return {"cancelled": task_history.cancel_request(request_id)}


def _library_summary(_payload):
    file_count, total_bytes = library.storage_stats()
    return {
        "counts": library.counts(),
        "storage": {"files": file_count, "bytes": total_bytes},
        "titles": library.CATEGORY_TITLES,
        "items": library.list_items(),
        "library_dir": paths.library_dir(),
    }


def _library_list(payload):
    category = str((payload or {}).get("category") or "") or None
    return {"items": library.list_items(category), "titles": library.CATEGORY_TITLES}


def _library_import(payload):
    paths = _payload_list(payload, "paths")
    return _task("library", "数据库导入", lambda log: {
        "items": library.import_many(paths, log=log),
    })


def _library_remove(payload):
    items = (payload or {}).get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("请选择要移除的数据库条目")
    removed = 0
    for item in items:
        if library.remove_item(str(item.get("category") or ""),
                               str(item.get("name") or ""), delete_file=True):
            removed += 1
    return {"removed": removed}


def _library_reclassify(payload):
    items = (payload or {}).get("items")
    category = str((payload or {}).get("category") or "")
    if category not in library.CATEGORIES + [library.UNKNOWN]:
        raise ValueError("数据库分类无效")
    if not isinstance(items, list) or not items:
        raise ValueError("请选择要重新分类的数据库条目")
    changed = 0
    for item in items:
        old_category = str(item.get("category") or "")
        name = str(item.get("name") or "")
        if old_category != category and library.reclassify(old_category, name, category):
            changed += 1
    return {"changed": changed}


def _currency_convert(payload):
    ok, text = currency_core.to_capital((payload or {}).get("amount"))
    return {"success": ok, "text": text}


def _system_sheets(payload):
    from . import preview_core
    path = _payload_file(payload, "path")
    return {"sheets": preview_core.list_sheets(path)}


def _system_preview(payload):
    from . import preview_core
    path = _payload_file(payload, "path")
    return preview_core.read_preview(
        path, sheet=(payload or {}).get("sheet") or None,
        max_rows=int((payload or {}).get("max_rows", 20)),
        max_cols=int((payload or {}).get("max_cols", 20)))


def _system_paths(_payload):
    crash_log = paths.crash_log_path()
    return {
        "app_data_dir": paths.app_data_dir(),
        "library_dir": paths.library_dir(),
        "default_output_root": paths.default_output_root(),
        "crash_log": crash_log,
        "crash_log_exists": os.path.isfile(crash_log),
    }


def _cache_stats(_payload):
    from . import incremental_cache
    return incremental_cache.stats()


def _cache_clear(_payload):
    from . import incremental_cache
    return {"removed": incremental_cache.clear()}


def _attendance_run(payload):
    from . import attendance_core
    targets = _payload_list(payload, "targets")
    sources = _payload_list(payload, "sources")
    opts = _options((payload or {}).get("options"))
    return _task("attendance", "考勤数据填报",
                 lambda log, progress: attendance_core.run(
                     targets, sources, opts=opts, log=log, progress=progress))


def _reconcile_analyze(payload):
    from . import reconcile_core
    target = _payload_file(payload, "target")
    sources = _payload_list(payload, "sources")
    labor = _payload_list(payload, "labor")
    opts = _options((payload or {}).get("options"))
    return reconcile_core.analyze(target, sources, labor, opts=opts)


def _reconcile_run(payload):
    from . import reconcile_core
    target = _payload_file(payload, "target")
    sources = _payload_list(payload, "sources")
    labor = _payload_list(payload, "labor")
    opts = _options((payload or {}).get("options"))
    choices = (payload or {}).get("choices")
    return _task("reconcile", "工时对账",
                 lambda log, progress: reconcile_core.run(
                     target, sources, labor, opts=opts, choices=choices,
                     log=log, progress=progress))


def _arrival_prepare(payload):
    from . import arrival_core
    paths = _payload_list(payload, "paths")
    settings = settings_mod.get_settings()
    memory = settings.arrival.get("batches", {})
    default_total = int(settings.arrival.get("last_total", arrival_core.DEFAULT_TOTAL))
    rows = []
    for path in paths:
        batch_no = arrival_core.detect_batch(path)
        saved = memory.get(batch_no, {})
        rows.append({"path": path, "batch_no": batch_no,
                     "total": saved.get("total", default_total),
                     "remark": saved.get("remark", ""), "include": True})
    return {"rows": rows, "top_label": settings.arrival.get(
        "top_label", arrival_core.DEFAULT_TOP_LABEL)}


def _arrival_run(payload):
    from . import arrival_core
    rows = (payload or {}).get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("请至少提供一个送货计划批次")
    for row in rows:
        path = os.path.abspath(str(row.get("path") or ""))
        if not os.path.isfile(path):
            raise FileNotFoundError("找不到文件：%s" % path)
        row["path"] = path
    top_label = str((payload or {}).get("top_label") or "") or None
    return _task("arrival", "到料明细表",
                 lambda log, progress: arrival_core.run(
                     rows, top_label=top_label, log=log, progress=progress))


def _pivot_analyze(payload):
    from . import pivot_core
    paths = _payload_list(payload, "paths")
    return _task("pivot", "销售表透视分析",
                 lambda log, progress: pivot_core.analyze(
                     paths, log=log, progress=progress))


def _pivot_choices(raw):
    """把前端数组形式的复核选择还原为 core 所需的元组键字典。"""
    if not isinstance(raw, dict):
        return None
    sheets = {}
    for key, value in dict(raw.get("sheets") or {}).items():
        try:
            key = int(key)
        except (TypeError, ValueError):
            pass
        sheets[key] = bool(value)
    choices = {"sheets": sheets, "held": {},
               "unit_overrides": {}, "spec_overrides": {}}
    for item in raw.get("held") or []:
        sid = item.get("sid")
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            sid = str(sid)
        choices["held"][(sid, int(item.get("ridx", 0)))] = bool(
            item.get("keep"))
    for name in ("unit_overrides", "spec_overrides"):
        for item in raw.get(name) or []:
            key = item.get("gk")
            if isinstance(key, list):
                key = tuple(key)
            choices[name][key] = str(item.get("value") or "")
    return choices


def _pivot_run(payload):
    from . import pivot_core
    paths = _payload_list(payload, "paths")
    choices = _pivot_choices((payload or {}).get("choices"))
    return _task("pivot", "销售表透视",
                 lambda log, progress: pivot_core.run(
                     paths, choices=choices, log=log, progress=progress))


def _purchase_run(payload):
    from . import purchase_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2")
    return _task("purchase", "采购数对账", lambda log, progress: purchase_core.run(
        file1, file2, sheet1=(payload or {}).get("sheet1") or None,
        sheet2=(payload or {}).get("sheet2") or None,
        name1=str((payload or {}).get("name1") or "我方"),
        name2=str((payload or {}).get("name2") or "供方"), log=log,
        progress=progress))


def _delivery_analyze(payload):
    from . import delivery_core
    path = _payload_file(payload, "path")
    return delivery_core.analyze(path, sheet=(payload or {}).get("sheet") or None)


def _delivery_run(payload):
    from . import delivery_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2", required=False)
    ref_plan = _payload_file(payload, "ref_plan", required=False)
    return _task("delivery", "送货计划表", lambda log: delivery_core.run(
        file1, file2, sheet_a=(payload or {}).get("sheet1") or None,
        sheet_b=(payload or {}).get("sheet2") or None,
        order_type=str((payload or {}).get("order_type") or "SUB"),
        ref_plan=ref_plan, log=log))


def _invoice_scan(payload):
    from . import invoice_core
    root = _payload_dir(payload, "root")

    def run(log, progress):
        result = invoice_core.scan(root, log=log, progress=progress)
        specials = [item for item in result.invoices if item.special]
        return {"invoices": [_jsonable(item) for item in result.invoices],
                "suspects": result.suspects,
                "suggested_month": invoice_core.detect_month(specials)}
    return _task("invoice", "增值税发票扫描", run)


def _invoice_generate(payload):
    from . import invoice_core
    scan = (payload or {}).get("scan")
    rows = (payload or {}).get("rows")
    ym = str((payload or {}).get("month") or "")
    if not isinstance(scan, dict) or not isinstance(rows, list) or not rows:
        raise ValueError("发票扫描结果或复核行为空")
    invoices = [invoice_core.Invoice(**item) for item in scan.get("invoices") or []]
    suspects = [tuple(item) for item in scan.get("suspects") or []]
    result = invoice_core.ScanResult(invoices, suspects)
    return _task("invoice", "增值税发票统计",
                 lambda log, progress: invoice_core.generate(
                     result, rows, ym, log=log, progress=progress))


def _rename_rule(payload):
    from . import rename_core
    values = (payload or {}).get("rule")
    values = values if isinstance(values, dict) else {}
    allowed = {"find", "replace", "use_regex", "prefix", "suffix", "base_name",
               "seq_enabled", "seq_start", "seq_digits", "seq_sep", "ext_lower"}
    return rename_core.RenameRule(**{key: value for key, value in values.items()
                                     if key in allowed})


def _rename_preview(payload):
    from . import rename_core
    paths = _payload_list(payload, "paths")
    plan = rename_core.build_plan(paths, _rename_rule(payload))
    return {"items": plan, "summary": rename_core.summarize(plan)}


def _rename_apply(payload):
    from . import rename_core
    paths = _payload_list(payload, "paths")
    rule = _rename_rule(payload)

    def run(log):
        plan = rename_core.build_plan(paths, rule)
        count, failed, undo_map = rename_core.apply_plan(plan, log=log)
        moved = {old: new for new, old in undo_map}
        return {"count": count, "failed": failed, "undo_map": undo_map,
                "paths": [moved.get(path, path) for path in paths]}
    return _task("rename", "批量重命名", run)


def _rename_undo(payload):
    from . import rename_core
    undo_map = [tuple(item) for item in (payload or {}).get("undo_map") or []]
    if not undo_map:
        raise ValueError("没有可撤销的重命名记录")
    count, failed = rename_core.undo(undo_map)
    return {"count": count, "failed": failed}


def _text_transform(payload):
    from . import text_core
    text = str((payload or {}).get("text") or "")
    operation = str((payload or {}).get("operation") or "")
    options = (payload or {}).get("options") or {}
    handlers = {
        "dedup": lambda: text_core.dedup_lines(text, ignore_case=bool(options.get("ignore_case"))),
        "sort": lambda: text_core.sort_lines(text, reverse=bool(options.get("reverse")),
                                              numeric=bool(options.get("numeric")),
                                              ignore_case=bool(options.get("ignore_case"))),
        "reverse": lambda: text_core.reverse_lines(text),
        "remove_empty": lambda: text_core.remove_empty_lines(text),
        "trim": lambda: text_core.trim_lines(text),
        "collapse": lambda: text_core.collapse_spaces(text),
        "upper": lambda: text_core.to_upper(text),
        "lower": lambda: text_core.to_lower(text),
        "line_numbers": lambda: text_core.add_line_numbers(text, pad=bool(options.get("pad"))),
        "email": lambda: text_core.extract(text, "email"),
        "phone": lambda: text_core.extract(text, "phone"),
        "url": lambda: text_core.extract(text, "url"),
    }
    if operation not in handlers:
        raise ValueError("不支持的文本操作：%s" % operation)
    result = handlers[operation]()
    return {"text": result, "stats": text_core.stats(result)}


def _pdf_info(payload):
    from . import pdf_core
    path = _payload_file(payload, "path")
    return {"pages": pdf_core.page_count(path)}


def _pdf_run(payload):
    from . import pdf_core
    paths = _payload_list(payload, "paths")
    mode = str((payload or {}).get("mode") or "")
    spec = str((payload or {}).get("spec") or "")
    split_mode = str((payload or {}).get("split_mode") or "each")

    def run(log):
        if mode == "merge":
            return pdf_core.merge(paths, log=log)
        if mode == "split":
            return pdf_core.split(paths[0], mode=split_mode, spec=spec, log=log)
        if mode == "extract":
            return pdf_core.extract_pages(paths[0], spec, log=log)
        if mode == "delete":
            return pdf_core.delete_pages(paths[0], spec, log=log)
        raise ValueError("不支持的 PDF 操作：%s" % mode)
    return _task("pdf", "PDF 工具箱", run)


def _excel_run(payload):
    from . import excel_tools_core
    paths = _payload_list(payload, "paths")
    mode = str((payload or {}).get("mode") or "")

    def run(log):
        if mode == "merge":
            return excel_tools_core.merge_books(
                paths, keep_formula=bool((payload or {}).get("keep_formula")), log=log)
        if mode == "split":
            return excel_tools_core.split_sheets(paths[0], log=log)
        if mode == "convert":
            return excel_tools_core.convert(
                paths, str((payload or {}).get("target") or "xlsx"), log=log)
        if mode == "stack":
            return excel_tools_core.stack_tables(
                paths, has_header=bool((payload or {}).get("has_header", True)), log=log)
        raise ValueError("不支持的 Excel 操作：%s" % mode)
    return _task("excel", "Excel 工具箱", run)


def _compare_prepare(payload):
    from . import compare_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2")
    headers1 = compare_core.read_headers(file1, sheet=(payload or {}).get("sheet1") or None)
    headers2 = compare_core.read_headers(file2, sheet=(payload or {}).get("sheet2") or None)
    return {"headers1": headers1, "headers2": headers2,
            "common": compare_core.common_columns(headers1, headers2)}


def _compare_run(payload):
    from . import compare_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2")
    key = str((payload or {}).get("key") or "")
    if not key:
        raise ValueError("请选择关键列")
    columns = (payload or {}).get("columns")
    return _task("compare", "表格比对", lambda log, progress: compare_core.run(
        file1, file2, key=key, sheet_a=(payload or {}).get("sheet1") or None,
        sheet_b=(payload or {}).get("sheet2") or None, columns=columns, log=log,
        progress=progress))


def _mappings_list(_payload):
    from . import mapping_store
    return {"items": mapping_store.list_mappings()}


def _mappings_delete(payload):
    from . import mapping_store
    return {"removed": bool(mapping_store.delete_mapping(
        str((payload or {}).get("id") or "")))}


def _mappings_clear(_payload):
    from . import mapping_store
    return {"removed": mapping_store.clear_mappings()}


def _templates_list(_payload):
    from . import template_store
    return {"items": template_store.list_templates()}


def _templates_rule(payload):
    from . import template_store
    template_id = str((payload or {}).get("id") or "")
    rules = (payload or {}).get("rules")
    if not isinstance(rules, dict):
        raise ValueError("迁移规则必须是对象")
    return template_store.save_migration_rule(
        template_id, int((payload or {}).get("from_version", 1)),
        int((payload or {}).get("to_version", 1)), rules)


def _templates_delete(payload):
    from . import template_store
    return {"removed": bool(template_store.delete_template(
        str((payload or {}).get("id") or "")))}


def _templates_clear(_payload):
    from . import template_store
    return {"removed": template_store.clear_templates()}


def _updater_check(_payload):
    from . import updater
    return {"configured": updater.is_configured(),
            "result": updater.check_update()}


def _updater_download(payload):
    from . import updater
    url = str((payload or {}).get("url") or "")
    sha256 = str((payload or {}).get("sha256") or "") or None
    if not url:
        raise ValueError("更新下载地址为空")
    return _task("updater", "下载程序更新", lambda log: {
        "path": updater.download_installer(url, sha256=sha256, log=log),
    })


def _updater_install(payload):
    from . import updater
    path = _payload_file(payload, "path")
    updater.run_installer(path)
    return {"started": True}


_ACTIONS = {
    "system.health": _health,
    "system.sheets": _system_sheets,
    "system.preview": _system_preview,
    "system.paths": _system_paths,
    "settings.get": _settings_get,
    "settings.update": _settings_update,
    "tasks.list": _tasks_list,
    "tasks.clear": _tasks_clear,
    "tasks.cancel": _tasks_cancel,
    "cache.stats": _cache_stats,
    "cache.clear": _cache_clear,
    "library.summary": _library_summary,
    "library.list": _library_list,
    "library.import": _library_import,
    "library.remove": _library_remove,
    "library.reclassify": _library_reclassify,
    "currency.convert": _currency_convert,
    "attendance.run": _attendance_run,
    "reconcile.analyze": _reconcile_analyze,
    "reconcile.run": _reconcile_run,
    "arrival.prepare": _arrival_prepare,
    "arrival.run": _arrival_run,
    "pivot.analyze": _pivot_analyze,
    "pivot.run": _pivot_run,
    "purchase.run": _purchase_run,
    "delivery.analyze": _delivery_analyze,
    "delivery.run": _delivery_run,
    "invoice.scan": _invoice_scan,
    "invoice.generate": _invoice_generate,
    "rename.preview": _rename_preview,
    "rename.apply": _rename_apply,
    "rename.undo": _rename_undo,
    "text.transform": _text_transform,
    "pdf.info": _pdf_info,
    "pdf.run": _pdf_run,
    "excel.run": _excel_run,
    "compare.prepare": _compare_prepare,
    "compare.run": _compare_run,
    "mappings.list": _mappings_list,
    "mappings.delete": _mappings_delete,
    "mappings.clear": _mappings_clear,
    "templates.list": _templates_list,
    "templates.rule": _templates_rule,
    "templates.delete": _templates_delete,
    "templates.clear": _templates_clear,
    "updater.check": _updater_check,
    "updater.download": _updater_download,
    "updater.install": _updater_install,
}


def dispatch(request):
    """执行一个白名单动作并返回统一响应。"""
    if not isinstance(request, dict):
        raise ValueError("请求必须是 JSON 对象")
    action = str(request.get("action") or "")
    handler = _ACTIONS.get(action)
    if handler is None:
        raise ValueError("不支持的桥接动作：%s" % (action or "(空)"))
    payload = request.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON 对象")
    return {"ok": True, "data": _jsonable(handler(payload))}


def main():
    """从标准输入读取一条请求，标准输出只写一条 JSON 响应。"""
    _configure_stdio()
    try:
        raw = sys.stdin.read()
        response = dispatch(json.loads(raw))
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        response = {"ok": False, "error": "%s: %s" %
                    (type(error).__name__, error)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
