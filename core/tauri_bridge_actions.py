# -*- coding: utf-8 -*-
"""Tauri/Web 桥接的动作处理器与参数收敛层。

本模块从 ``tauri_bridge.py`` 拆出，集中维护载荷校验、长任务包装和全部白名单动作实现。
协议入口 ``tauri_bridge.py`` 只保留标准流配置、JSON 安全化、分派和 main 入口，并从此处
导入动作注册表；两模块都不导入 UI 或 Web/Tauri 运行时。
"""
import inspect
import json
import os
import sys

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
"""允许前端读写的设置白名单；未列出的内部配置不得经桥接修改。"""


def _jsonable(value):
    """把 Core 返回值递归转换成 JSON 可序列化结构。

    业务结果可能包含元组、集合、具名槽对象或 dataclass 实例；桥接不依赖具体类型，
    依次检查常见容器、``__slots__`` 和 ``__dict__``，最后以字符串作为安全回退。
    """
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
    """读取并校验一组必须已经存在的文件路径。

    单字符串为兼容旧调用自动包装成列表；所有路径先转绝对路径再检查文件类型。所属账号
    与目录穿越校验由 Tauri 文件选择器或 Web 上传句柄层完成，本层只保证 Core 不收到
    空值、目录或不存在路径。
    """
    values = (payload or {}).get(key)
    if isinstance(values, str):
        values = [values]
    if values is None and not required:
        return []
    if not isinstance(values, list) or (required and not values):
        raise ValueError("%s 必须是非空路径列表" % key)
    paths = [os.path.abspath(str(value)) for value in values if str(value).strip()]  # 保持前端顺序，某些业务以文件顺序决定主辅表。
    if required and not paths:
        raise ValueError("%s 必须包含有效文件路径" % key)
    missing = [path for path in paths if not os.path.isfile(path)]
    if missing:
        raise FileNotFoundError("找不到文件：%s" % missing[0])
    return paths


def _payload_file(payload, key, required=True):
    """复用列表校验读取单个文件；可选文件缺失时返回 ``None``。"""
    values = _payload_list(payload, key, required=required)
    return values[0] if values else None


def _payload_dir(payload, key):
    """读取并校验目录路径，供需要递归扫描文件的业务使用。"""
    raw = str((payload or {}).get(key) or "").strip()
    if not raw:
        raise ValueError("%s 不能为空" % key)
    path = os.path.abspath(raw)
    if not os.path.isdir(path):
        raise NotADirectoryError("找不到目录：%s" % path)
    return path


def _options(values=None):
    """从 JSON 构造考勤/对账共用 ``Options``，忽略未登记字段。

    白名单防止前端把任意键注入 dataclass 构造函数；具体数值范围仍由 ``common_core``
    负责校验，使桌面和 Web 使用相同参数语义。
    """
    from . import common_core
    values = values if isinstance(values, dict) else {}
    allowed = {
        "workday_hours", "overtime", "conflict", "header_row", "sheet_name",
        "tolerance", "data_start", "skip_extra", "columns", "auto_actual",
        "night_shift", "night_start_hour", "night_workday_hours", "night_max_hours",
        "day_max_hours",
    }
    return common_core.Options(**{key: value for key, value in values.items()
                                  if key in allowed})  # 未知字段不透传，保持旧前端请求向后兼容。


def _output_dir(result):
    """从不同历史业务结果键中提取任务输出目录。

    新 Core 应优先返回 ``out_dir``；其余键用于兼容尚未统一返回结构的功能。任务历史只
    保存目录而非任意结果对象，便于打开输出与统计文件数量。
    """
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
    """统一执行长任务，收集日志、进度、任务历史和结果投影。

    回调可声明 ``(log)`` 或 ``(log, progress)`` 两种签名。业务成功先完成任务历史，再
    尝试生成前端展示投影；投影属于辅助层，失败只追加提示，不能把已经成功的业务任务
    改成失败。业务异常则记录失败状态并继续向上抛，由协议入口构造统一错误响应。
    """
    logs = []
    request_id = os.environ.get("FYT_REQUEST_ID", "")
    task_id = task_history.start_task(
        feature, title, {"frontend": "tauri", "request_id": request_id})

    def emit(kind, value):
        """在事件协议启用时向 stderr 输出一行不可与最终响应混淆的 JSON。"""
        if os.environ.get("FYT_BRIDGE_EVENTS") != "1":
            return
        event = {"request_id": request_id, "kind": kind, "value": value}
        sys.stderr.write("__FYT_EVENT__" + json.dumps(
            event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stderr.flush()

    def log(message):
        """同时积累最终日志数组并实时发送日志事件。"""
        text = str(message)
        logs.append(text)
        emit("log", text)

    def progress(value):
        """把任意进度输入收敛到 0～100 的整数后发送。"""
        try:
            percent = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            percent = 0
        emit("progress", percent)

    try:
        if len(inspect.signature(callback).parameters) >= 2:  # 兼容尚未支持进度回调的旧 Core。
            result = callback(log, progress)
        else:
            result = callback(log)
        out_dir = _output_dir(result)
        task_history.finish_task(task_id, "ok", "处理完成", out_dir)
        emit("progress", 100)  # 只有业务完成且任务历史写入成功后才宣布 100%。
        envelope = {"result": result, "logs": logs, "task_id": task_id,
                    "out_dir": out_dir}
        try:
            from . import business_result_core
            presentation = business_result_core.present(feature, result)
        except Exception as error:
            logs.append("结果摘要暂时无法生成：%s" % error)
            presentation = None  # 投影失败不破坏业务结果和输出文件。
        if presentation is not None:
            envelope["presentation"] = presentation
        return envelope
    except Exception as error:
        task_history.finish_task(task_id, "failed", str(error), "")
        raise


def _health(_payload):
    """返回桥接运行环境和可用功能概览，用于前端启动自检。"""
    return {
        "app_name": version.APP_NAME,
        "version": version.VERSION,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "project_root": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # 仅桌面本机诊断使用，Web 不直接暴露此响应。
        "features": [
            "attendance", "reconcile", "arrival", "pivot", "purchase", "shipping_review",
            "delivery", "supplier_batch", "purchase_plan", "library", "mappings", "templates", "invoice",
            "currency", "rename", "text", "pdf", "excel", "compare",
            "settings", "tasks",
        ],
    }


def _settings_get(_payload):
    """读取设置白名单中的公开值，屏蔽内部配置和未知历史字段。"""
    settings = settings_mod.get_settings()
    return {key: _jsonable(settings.get(key)) for key in sorted(_SETTING_KEYS)}


def _settings_update(payload):
    """批量更新允许前端修改的设置，并在全部赋值后一次持久化。"""
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        raise ValueError("设置参数必须是对象")
    unknown = sorted(set(values) - _SETTING_KEYS)  # 明确拒绝而非静默忽略，便于发现前后端版本不匹配。
    if unknown:
        raise ValueError("不允许修改这些设置：%s" % "、".join(unknown))
    settings = settings_mod.get_settings()
    for key, value in values.items():
        settings.set(key, value)
    if not settings.save():
        raise OSError("设置保存失败，请检查配置目录是否可写")
    return _settings_get({})


def _tasks_list(payload):
    """返回本机任务汇总和受上限保护的最近任务列表。"""
    try:
        limit = int((payload or {}).get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(1000, limit))  # 防止前端误传极大值导致任务历史全表加载。
    return {"summary": task_history.summary(),
            "items": task_history.list_recent(limit)}


def _tasks_clear(_payload):
    """清除已结束任务，运行中任务由任务历史层保留。"""
    return {"removed": task_history.clear_finished()}


def _tasks_cancel(payload):
    """按请求编号登记取消意图，由 Rust/Web 进程层精确终止对应子进程。"""
    request_id = str((payload or {}).get("request_id") or "")
    return {"cancelled": task_history.cancel_request(request_id)}


def _library_summary(_payload):
    """返回本机业务数据库分类、容量、条目和目录汇总。"""
    file_count, total_bytes = library.storage_stats()
    return {
        "counts": library.counts(),
        "storage": {"files": file_count, "bytes": total_bytes},
        "titles": library.CATEGORY_TITLES,
        "items": library.list_items(),
        "library_dir": paths.library_dir(),
    }


def _library_list(payload):
    """按可选分类返回数据库条目。"""
    category = str((payload or {}).get("category") or "") or None
    return {"items": library.list_items(category), "titles": library.CATEGORY_TITLES}


def _library_import(payload):
    """把多个本地文件导入业务数据库，并纳入统一长任务记录。"""
    paths = _payload_list(payload, "paths")
    return _task("library", "数据库导入", lambda log: {
        "items": library.import_many(paths, log=log),
    })


def _library_remove(payload):
    """删除选中的数据库条目及其受管文件，返回实际成功数量。"""
    items = (payload or {}).get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("请选择要移除的数据库条目")
    removed = 0
    for item in items:  # 单项失败由 library 返回 False，其余条目仍继续处理。
        if library.remove_item(str(item.get("category") or ""),
                               str(item.get("name") or ""), delete_file=True):
            removed += 1
    return {"removed": removed}


def _library_reclassify(payload):
    """把选中条目移动到已登记分类，跳过本就属于目标分类的条目。"""
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
    """把金额转换为中文大写，并保留 Core 的成功标志与用户提示。"""
    ok, text = currency_core.to_capital((payload or {}).get("amount"))
    return {"success": ok, "text": text}


def _system_sheets(payload):
    """列出 Excel 工作表名称，为前端人工选择提供轻量预检。"""
    from . import preview_core
    path = _payload_file(payload, "path")
    return {"sheets": preview_core.list_sheets(path)}


def _system_preview(payload):
    """读取受行列上限保护的表格预览，不在前端自行解析 Excel。"""
    from . import preview_core
    path = _payload_file(payload, "path")
    return preview_core.read_preview(
        path, sheet=(payload or {}).get("sheet") or None,
        max_rows=int((payload or {}).get("max_rows", 20)),
        max_cols=int((payload or {}).get("max_cols", 20)))


def _system_paths(_payload):
    """返回桌面端可展示或打开的应用数据路径及崩溃日志状态。"""
    crash_log = paths.crash_log_path()
    return {
        "app_data_dir": paths.app_data_dir(),
        "library_dir": paths.library_dir(),
        "default_output_root": paths.default_output_root(),
        "crash_log": crash_log,
        "crash_log_exists": os.path.isfile(crash_log),
    }


def _cache_stats(_payload):
    """返回增量缓存统计。"""
    from . import incremental_cache
    return incremental_cache.stats()


def _cache_clear(_payload):
    """清空增量缓存并返回删除数量。"""
    from . import incremental_cache
    return {"removed": incremental_cache.clear()}


def _attendance_run(payload):
    """规范考勤目标、来源和可调参数后执行考勤填报。"""
    from . import attendance_core
    targets = _payload_list(payload, "targets")
    sources = _payload_list(payload, "sources")
    opts = _options((payload or {}).get("options"))
    return _task("attendance", "考勤数据填报",
                 lambda log, progress: attendance_core.run(
                     targets, sources, opts=opts, log=log, progress=progress))


def _reconcile_analyze(payload):
    """只读分析工时对账输入，生成待人工确认的计划。"""
    from . import reconcile_core
    target = _payload_file(payload, "target")
    sources = _payload_list(payload, "sources")
    labor = _payload_list(payload, "labor")
    opts = _options((payload or {}).get("options"))
    return reconcile_core.analyze(target, sources, labor, opts=opts)


def _reconcile_run(payload):
    """应用人工复核选择执行工时对账，并记录进度与输出。"""
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
    """识别到料批次、完整主料类数和非零未到料，并加载人工备注。

    此阶段不写输出文件，返回的每一行由前端复核后再提交 ``arrival.run``。批次记忆来自
    设置文件；自动识别的本次总类数优先于历史数值，用户仍可在复核表中逐批覆盖。
    """
    from . import arrival_core
    paths = _payload_list(payload, "paths")
    settings = settings_mod.get_settings()
    memory = settings.arrival.get("batches", {})
    default_total = int(settings.arrival.get("last_total", arrival_core.DEFAULT_TOTAL))
    rows = []
    for path in paths:
        batch_no = arrival_core.detect_batch(path)
        inspection = arrival_core.inspect_plan(path)
        auto_total = int(inspection.get("total", 0) or 0)
        saved = memory.get(batch_no, {})  # 历史记录只补自动识别不到的总数，并继续带出人工备注。
        rows.append({"path": path, "batch_no": batch_no,
                     "total": auto_total or saved.get("total", default_total),
                     "auto_total": auto_total,
                     "missing_count": len(inspection.get("materials", [])),
                     "remark": saved.get("remark", ""), "include": True})
    return {"rows": rows, "top_label": settings.arrival.get(
        "top_label", arrival_core.DEFAULT_TOP_LABEL)}


def _arrival_run(payload):
    """再次验证复核行文件存在后生成每日到料明细。"""
    from . import arrival_core
    rows = (payload or {}).get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("请至少提供一个送货计划批次")
    for row in rows:
        path = os.path.abspath(str(row.get("path") or ""))
        if not os.path.isfile(path):
            raise FileNotFoundError("找不到文件：%s" % path)
        row["path"] = path  # 把规范绝对路径写回本次内存请求，Core 不再处理相对路径。
    top_label = str((payload or {}).get("top_label") or "") or None
    return _task("arrival", "到料明细表",
                 lambda log, progress: arrival_core.run(
                     rows, top_label=top_label, log=log, progress=progress))


def _pivot_analyze(payload):
    """只读分析销售表透视结构，返回工作表、暂存行和字段覆盖计划。"""
    from . import pivot_core
    paths = _payload_list(payload, "paths")
    return _task("pivot", "销售表透视分析",
                 lambda log, progress: pivot_core.analyze(
                     paths, log=log, progress=progress))


def _pivot_choices(raw):
    """把 JSON 可表示的复核选择还原为 Core 所需的元组键字典。

    JSON 对象键只能是字符串，元组键则被前端编码成数组条目；这里恢复工作表编号、
    ``(sheet_id, row_index)`` 暂存键和分组覆盖键，避免 Core 感知前端传输格式。
    """
    if not isinstance(raw, dict):
        return None
    sheets = {}
    for key, value in dict(raw.get("sheets") or {}).items():
        try:
            key = int(key)
        except (TypeError, ValueError):
            pass  # 非数字工作表标识保留原字符串，兼容按名称索引的分析结果。
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
                key = tuple(key)  # 列表只因 JSON 传输产生，Core 继续使用可哈希元组键。
            choices[name][key] = str(item.get("value") or "")
    return choices


def _pivot_run(payload):
    """把复核选择还原后执行销售表透视输出。"""
    from . import pivot_core
    paths = _payload_list(payload, "paths")
    choices = _pivot_choices((payload or {}).get("choices"))
    return _task("pivot", "销售表透视",
                 lambda log, progress: pivot_core.run(
                     paths, choices=choices, log=log, progress=progress))


def _purchase_run(payload):
    """执行双方采购数量对账，并透传工作表与显示名称参数。"""
    from . import purchase_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2")
    return _task("purchase", "采购数对账", lambda log, progress: purchase_core.run(
        file1, file2, sheet1=(payload or {}).get("sheet1") or None,
        sheet2=(payload or {}).get("sheet2") or None,
        name1=str((payload or {}).get("name1") or "我方"),
        name2=str((payload or {}).get("name2") or "供方"), log=log,
        progress=progress))


def _shipping_review_run(payload):
    """执行包装日计划与发运评审表的汇总对比。"""

    from . import shipping_review_core
    package_plan = _payload_file(payload, "package_plan")
    review_workbook = _payload_file(payload, "review_workbook")
    return _task(
        "shipping_review",
        "发运评审对比",
        lambda log, progress: shipping_review_core.run(
            package_plan,
            review_workbook,
            package_sheet=(payload or {}).get("package_sheet") or None,
            review_sheet=(payload or {}).get("review_sheet") or None,
            log=log,
            progress=progress,
        ),
    )


def _delivery_analyze(payload):
    """只读分析送货计划输入结构，供前端选择工作表和确认输入。"""
    from . import delivery_core
    path = _payload_file(payload, "path")
    return delivery_core.analyze(path, sheet=(payload or {}).get("sheet") or None)


def _delivery_run(payload):
    """执行送货计划制作；第二数据表和参考计划均允许缺省。"""
    from . import delivery_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2", required=False)
    ref_plan = _payload_file(payload, "ref_plan", required=False)
    return _task("delivery", "送货计划表", lambda log: delivery_core.run(
        file1, file2, sheet_a=(payload or {}).get("sheet1") or None,
        sheet_b=(payload or {}).get("sheet2") or None,
        order_type=str((payload or {}).get("order_type") or "SUB"),
        ref_plan=ref_plan, log=log))


def _supplier_batch_analyze(payload):
    """扫描批次表和可选历史表，生成供应商与批次交付日期复核计划。"""
    from . import supplier_batch_core
    batch_paths = _payload_list(payload, "batch_paths")
    history_paths = _payload_list(payload, "history_paths", required=False)
    return _task("supplier_batch", "供应商批次分析", lambda log, progress: supplier_batch_core.analyze(
        batch_paths, history_paths=history_paths, log=log, progress=progress))


def _supplier_batch_run(payload):
    """校验人工选择后生成指定供应商的批次表。

    ``suppliers`` 可为 ``None``，表示沿用 Core 的默认全选；交付日期必须是对象，确保每个
    批次由键明确关联日期，不能依赖数组顺序。
    """
    from . import supplier_batch_core
    batch_paths = _payload_list(payload, "batch_paths")
    history_paths = _payload_list(payload, "history_paths", required=False)
    choices = (payload or {}).get("choices")
    selected = choices.get("suppliers") if isinstance(choices, dict) else None
    batch_dates = choices.get("batch_dates") if isinstance(choices, dict) else None
    if selected is not None and not isinstance(selected, list):
        raise ValueError("供应商复核选择必须是列表")
    if not isinstance(batch_dates, dict):
        raise ValueError("批次交付日期必须是对象")
    return _task("supplier_batch", "供应商批次表", lambda log, progress: supplier_batch_core.run(
        batch_paths, history_paths=history_paths, selected_suppliers=selected,
        batch_dates=batch_dates, log=log, progress=progress))


def _purchase_plan_run(payload):
    """把采购计划模板与批次数据配对后执行导入。"""
    from . import purchase_plan_core
    template_paths = _payload_list(payload, "template_paths")
    batch_paths = _payload_list(payload, "batch_paths")
    return _task("purchase_plan", "采购计划导入", lambda log, progress: purchase_plan_core.run(
        template_paths, batch_paths, log=log, progress=progress))


def _purchase_plan_diff(payload):
    """从批次数据生成实收差异清单。"""
    from . import purchase_plan_core
    batch_paths = _payload_list(payload, "batch_paths")
    return _task("purchase_plan", "实收差异清单", lambda log, progress: purchase_plan_core.diff(
        batch_paths, log=log, progress=progress))


def _invoice_match_run(payload):
    """匹配发票与采购记录，输出票货关联结果和可信度信息。"""
    from . import invoice_match_core
    invoice_paths = _payload_list(payload, "invoice_paths")
    purchase_paths = _payload_list(payload, "purchase_paths")
    return _task("invoice_match", "票货匹配", lambda log, progress: invoice_match_core.match(
        invoice_paths, purchase_paths, log=log, progress=progress))


def _attendance_archive_run(payload):
    """把多份考勤文件汇总为月度归档。"""
    from . import attendance_archive_core
    paths = _payload_list(payload, "paths")
    return _task("attendance_archive", "考勤月度归档", lambda log, progress: attendance_archive_core.archive(
        paths, log=log, progress=progress))


def _reconcile_statement_scan(payload):
    """只读扫描对账单来源，返回可选择账套和供应商信息。"""
    from . import reconcile_statement_core
    paths = _payload_list(payload, "paths")
    return reconcile_statement_core.scan(paths)


def _reconcile_statement_build(payload):
    """根据人工选择、月份和供应商映射生成标准对账单。"""
    from . import reconcile_statement_core
    paths = _payload_list(payload, "paths")
    raw_selected = (payload or {}).get("selected") or []
    selected = [str(value) for value in raw_selected] if isinstance(raw_selected, list) else []  # 非列表输入降级为空，由 Core 给出业务提示。
    month = str((payload or {}).get("month") or "")
    supplier_map = (payload or {}).get("supplier_map") or {}
    return _task("reconcile_statement", "对账单制作", lambda log, progress: reconcile_statement_core.build(
        paths, selected, month, supplier_map=supplier_map, log=log, progress=progress))


def _catalog_list(_payload):
    """返回供应商与物料主数据的当前完整视图。"""
    from . import material_catalog
    return material_catalog.list_all()


def _catalog_upsert_supplier(payload):
    """新增或更新供应商名称与编码，并返回更新后的目录。"""
    from . import material_catalog
    material_catalog.upsert_supplier(
        str((payload or {}).get("name") or ""),
        str((payload or {}).get("code") or ""))
    return material_catalog.list_all()


def _catalog_delete_supplier(payload):
    """删除指定供应商主数据，并返回更新后的目录。"""
    from . import material_catalog
    material_catalog.delete_supplier(str((payload or {}).get("name") or ""))
    return material_catalog.list_all()


def _catalog_upsert_material(payload):
    """新增或更新物料名称、规格、单位和供应商关系。"""
    from . import material_catalog
    material_catalog.upsert_material(
        str((payload or {}).get("code") or ""),
        str((payload or {}).get("name") or ""),
        spec=str((payload or {}).get("spec") or ""),
        unit=str((payload or {}).get("unit") or ""),
        supplier=str((payload or {}).get("supplier") or ""))
    return material_catalog.list_all()


def _catalog_delete_material(payload):
    """按物料编码删除主数据，并返回更新后的目录。"""
    from . import material_catalog
    material_catalog.delete_material(str((payload or {}).get("code") or ""))
    return material_catalog.list_all()


def _batch_track_search(payload):
    """在受管数据库中搜索批次、物料或订单关键词。"""
    from . import batch_track_core
    keyword = str((payload or {}).get("keyword") or "")
    return batch_track_core.search(keyword)


def _report_file_count(output_dir: str) -> int:
    """统计任务输出目录第一层普通文件数量；目录异常时返回零。"""

    import os as _os

    if not output_dir or not _os.path.isdir(output_dir):
        return 0
    try:
        return sum(
            1
            for name in _os.listdir(output_dir)
            if _os.path.isfile(_os.path.join(output_dir, name))
        )
    except OSError:
        # 目录可能已被移动或当前进程无权限；保留任务记录但不伪造输出文件数。
        return 0


def _report_task_item(task: dict[str, object], start) -> dict[str, object] | None:
    """将一条任务历史转换为报表中心使用的安全字段。"""

    from . import report_center_core

    started_at = str(task.get("started_at") or "")
    started = report_center_core._parse_time(started_at)
    if started is None or started < start:
        return None
    return {
        "feature": task.get("feature") or "",
        "title": task.get("title") or "",
        "status": task.get("status") or "",
        "started_at": started_at,
        "files": _report_file_count(str(task.get("output_dir") or "")),
    }


def _collect_report_tasks(limit: int, start) -> list[dict[str, object]]:
    """按时间范围读取任务历史，并裁剪为报表所需字段。"""

    from . import report_center_core

    items = []
    for task in task_history.list_recent(limit):
        item = _report_task_item(task, start)
        if item is not None:
            items.append(item)
    return items


def _report_build(payload):
    """从本机任务历史生成指定时间范围的业务汇总报表。

    任务历史只保存输出目录，因此这里实时统计目录第一层普通文件数量。读取失败按零文件
    处理，不让已存在的任务记录阻止整份报表生成。
    """
    from . import paths as _paths, report_center_core
    range_key = str((payload or {}).get("range") or "30d")
    if range_key not in ("7d", "30d", "month", "all"):
        raise ValueError("报表范围参数无效")
    limit = 10000 if range_key == "all" else 2000  # “全部”仍设硬上限，避免无限加载历史数据库。
    start = report_center_core.range_start(range_key)
    items = _collect_report_tasks(limit, start)
    if not items:
        raise ValueError("所选时间范围内没有任务记录")
    out_dir = _paths.resolve_output_dir("report_center", **settings_mod.get_settings().output_kwargs())
    range_label = {"7d": "近 7 天", "30d": "近 30 天", "month": "本月", "all": "全部"}[range_key]
    target = report_center_core.unique_report_path(out_dir, range_label)
    report_center_core.build_report(items, target, range_label)
    return {"path": target, "rows": len(items)}


def _invoice_scan(payload):
    """扫描目录内发票并返回可供人工复核的结构化字段与建议月份。"""
    from . import invoice_core
    root = _payload_dir(payload, "root")

    def run(log, progress):
        """把 Core 数据类转换为 JSON，并只用专票推断统计月份。"""
        result = invoice_core.scan(root, log=log, progress=progress)
        specials = [item for item in result.invoices if item.special]  # 普通发票不参与专票统计月份推断。
        return {"invoices": [_jsonable(item) for item in result.invoices],
                "suspects": result.suspects,
                "suggested_month": invoice_core.detect_month(specials)}
    return _task("invoice", "增值税发票扫描", run)


def _invoice_generate(payload):
    """把前端复核后的 JSON 重建为发票数据类并生成统计表。"""
    from . import invoice_core
    scan = (payload or {}).get("scan")
    rows = (payload or {}).get("rows")
    ym = str((payload or {}).get("month") or "")
    if not isinstance(scan, dict) or not isinstance(rows, list) or not rows:
        raise ValueError("发票扫描结果或复核行为空")
    invoices = [invoice_core.Invoice(**item) for item in scan.get("invoices") or []]  # 恢复 Core 强类型数据，避免生成逻辑依赖前端字典。
    suspects = [tuple(item) for item in scan.get("suspects") or []]  # JSON 数组还原为 Core 约定元组。
    result = invoice_core.ScanResult(invoices, suspects)
    return _task("invoice", "增值税发票统计",
                 lambda log, progress: invoice_core.generate(
                     result, rows, ym, log=log, progress=progress))


def _rename_rule(payload):
    """从受控字段构造批量重命名规则，忽略前端未知扩展键。"""
    from . import rename_core
    values = (payload or {}).get("rule")
    values = values if isinstance(values, dict) else {}
    allowed = {"find", "replace", "use_regex", "prefix", "suffix", "base_name",
               "seq_enabled", "seq_start", "seq_digits", "seq_sep", "ext_lower"}
    return rename_core.RenameRule(**{key: value for key, value in values.items()
                                     if key in allowed})


def _rename_preview(payload):
    """只生成重命名计划和冲突摘要，不修改任何文件。"""
    from . import rename_core
    paths = _payload_list(payload, "paths")
    plan = rename_core.build_plan(paths, _rename_rule(payload))
    return {"items": plan, "summary": rename_core.summarize(plan)}


def _rename_apply(payload):
    """重新构建计划并执行重命名，同时返回可用于撤销的路径映射。"""
    from . import rename_core
    paths = _payload_list(payload, "paths")
    rule = _rename_rule(payload)

    def run(log):
        """在同一任务中计算并应用计划，避免预览后文件状态变化导致使用陈旧计划。"""
        plan = rename_core.build_plan(paths, rule)
        count, failed, undo_map = rename_core.apply_plan(plan, log=log)
        moved = {old: new for new, old in undo_map}  # Core 撤销表是“新->旧”，这里反转后更新前端当前路径。
        return {"count": count, "failed": failed, "undo_map": undo_map,
                "paths": [moved.get(path, path) for path in paths]}
    return _task("rename", "批量重命名", run)


def _rename_undo(payload):
    """按上一次执行返回的映射撤销批量重命名。"""
    from . import rename_core
    undo_map = [tuple(item) for item in (payload or {}).get("undo_map") or []]
    if not undo_map:
        raise ValueError("没有可撤销的重命名记录")
    count, failed = rename_core.undo(undo_map)
    return {"count": count, "failed": failed}


def _text_transform(payload):
    """通过固定操作表执行纯文本转换，并返回结果统计。

    操作名称只在本地 ``handlers`` 中查找，不使用 ``eval`` 或动态属性访问；每个选项显式
    转为布尔值，保持桥接输入边界清晰。
    """
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
    result = handlers[operation]()  # 到此已通过白名单验证，不执行任意前端代码。
    return {"text": result, "stats": text_core.stats(result)}


def _pdf_info(payload):
    """读取 PDF 页数，为拆分和页码范围输入提供预检。"""
    from . import pdf_core
    path = _payload_file(payload, "path")
    return {"pages": pdf_core.page_count(path)}


def _pdf_run(payload):
    """按白名单模式执行 PDF 合并、拆分、提取或删除页面。"""
    from . import pdf_core
    paths = _payload_list(payload, "paths")
    mode = str((payload or {}).get("mode") or "")
    spec = str((payload or {}).get("spec") or "")
    split_mode = str((payload or {}).get("split_mode") or "each")

    def run(log):
        """在任务日志上下文内分派具体 PDF 操作。"""
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
    """按白名单模式执行通用 Excel 合并、拆分、转换或纵向堆叠。"""
    from . import excel_tools_core
    paths = _payload_list(payload, "paths")
    mode = str((payload or {}).get("mode") or "")

    def run(log):
        """在任务日志上下文内分派具体 Excel 工具操作。"""
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
    """读取两表表头并返回公共列，作为人工选择关键列的只读准备阶段。"""
    from . import compare_core
    file1 = _payload_file(payload, "file1")
    file2 = _payload_file(payload, "file2")
    headers1 = compare_core.read_headers(file1, sheet=(payload or {}).get("sheet1") or None)
    headers2 = compare_core.read_headers(file2, sheet=(payload or {}).get("sheet2") or None)
    return {"headers1": headers1, "headers2": headers2,
            "common": compare_core.common_columns(headers1, headers2)}


def _compare_run(payload):
    """使用人工选择的关键列和比较列生成表格差异报告。"""
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
    """返回业务处理中学习到的字段映射。"""
    from . import mapping_store
    return {"items": mapping_store.list_mappings()}


def _mappings_delete(payload):
    """按映射编号删除一条学习记录。"""
    from . import mapping_store
    return {"removed": bool(mapping_store.delete_mapping(
        str((payload or {}).get("id") or "")))}


def _mappings_clear(_payload):
    """清空全部学习映射，并返回删除数量。"""
    from . import mapping_store
    return {"removed": mapping_store.clear_mappings()}


def _templates_list(_payload):
    """返回已登记模板版本与迁移规则。"""
    from . import template_store
    return {"items": template_store.list_templates()}


def _templates_rule(payload):
    """保存指定模板两个版本之间的结构迁移规则。"""
    from . import template_store
    template_id = str((payload or {}).get("id") or "")
    rules = (payload or {}).get("rules")
    if not isinstance(rules, dict):
        raise ValueError("迁移规则必须是对象")
    return template_store.save_migration_rule(
        template_id, int((payload or {}).get("from_version", 1)),
        int((payload or {}).get("to_version", 1)), rules)


def _templates_delete(payload):
    """删除指定模板及其迁移规则。"""
    from . import template_store
    return {"removed": bool(template_store.delete_template(
        str((payload or {}).get("id") or "")))}


def _templates_clear(_payload):
    """清空全部模板索引。"""
    from . import template_store
    return {"removed": template_store.clear_templates()}


def _updater_check(_payload):
    """检查更新配置并查询可用版本；未配置时也返回明确状态。"""
    from . import updater
    return {"configured": updater.is_configured(),
            "result": updater.check_update()}


def _updater_download(payload):
    """下载更新安装包并可选校验 SHA-256，过程纳入任务日志。"""
    from . import updater
    url = str((payload or {}).get("url") or "")
    sha256 = str((payload or {}).get("sha256") or "") or None
    if not url:
        raise ValueError("更新下载地址为空")
    return _task("updater", "下载程序更新", lambda log: {
        "path": updater.download_installer(url, sha256=sha256, log=log),
    })


def _updater_install(payload):
    """校验安装包路径后启动系统安装程序；不会等待安装完成。"""
    from . import updater
    path = _payload_file(payload, "path")
    updater.run_installer(path)
    return {"started": True}


# 唯一可调用动作注册表。新增业务必须显式加入此处，并同时评估 Tauri/Web 的二次白名单、
# 人工复核协议、权限和测试；不得根据前端字符串动态 import 或 getattr。
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
    "shipping_review.run": _shipping_review_run,
    "delivery.analyze": _delivery_analyze,
    "delivery.run": _delivery_run,
    "supplier_batch.analyze": _supplier_batch_analyze,
    "supplier_batch.run": _supplier_batch_run,
    "purchase_plan.run": _purchase_plan_run,
    "purchase_plan.diff": _purchase_plan_diff,
    "invoice_match.run": _invoice_match_run,
    "attendance_archive.run": _attendance_archive_run,
    "reconcile_statement.scan": _reconcile_statement_scan,
    "reconcile_statement.build": _reconcile_statement_build,
    "catalog.list": _catalog_list,
    "catalog.upsert_supplier": _catalog_upsert_supplier,
    "catalog.delete_supplier": _catalog_delete_supplier,
    "catalog.upsert_material": _catalog_upsert_material,
    "catalog.delete_material": _catalog_delete_material,
    "batch_track.search": _batch_track_search,
    "report.build": _report_build,
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
