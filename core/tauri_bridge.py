# -*- coding: utf-8 -*-
"""Tauri/Web 子进程与 Python 业务核心之间的受控单请求 JSON 桥接。

调用方通过标准输入发送 ``{"action": ..., "payload": ...}``，标准输出只返回一份最终
JSON；启用 ``FYT_BRIDGE_EVENTS=1`` 时，日志和进度以带前缀 JSON 行写入标准错误。所有
可执行动作必须登记在 ``_ACTIONS`` 白名单，前端不能传入模块名或函数名进行动态调用。

本模块只负责协议校验、路径存在性、参数收敛、任务历史和动作编排，实际 Excel/PDF 业务
规则仍位于各 ``*_core.py``。耗时动作统一包裹 ``_task``，以保证桌面端和 Web 子进程获得
一致的日志、进度、取消请求标识和结构化结果预览。
"""
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
"""允许前端读写的设置白名单；未列出的内部配置不得经桥接修改。"""


def _configure_stdio():
    """强制三条标准流使用 UTF-8，避免冻结程序继承 Windows 控制台 GBK。

    某些打包环境提供的流对象没有 ``reconfigure``，因此先能力检测；协议本身不输出
    GBK 专属或依赖控制台渲染的字符。
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


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


from .tauri_bridge_actions import (
    _ACTIONS, _options, _output_dir, _payload_dir, _payload_file, _payload_list, _task,
)


def dispatch(request):
    """验证请求信封，执行一个白名单动作并返回统一成功响应。

    ``payload`` 缺失按空对象处理，其他非对象输入明确拒绝。所有返回值最后经过
    ``_jsonable``，确保标准输出始终能被 Rust 或 Web 父进程解码。
    """
    if not isinstance(request, dict):
        raise ValueError("请求必须是 JSON 对象")
    action = str(request.get("action") or "")
    handler = _ACTIONS.get(action)  # 字典查找是唯一分派路径，不接受模块名或可执行表达式。
    if handler is None:
        raise ValueError("不支持的桥接动作：%s" % (action or "(空)"))
    payload = request.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON 对象")
    return {"ok": True, "data": _jsonable(handler(payload))}


def main():
    """从标准输入读取一条请求，标准输出只写一条 JSON 响应。

    异常堆栈写入 stderr 供本机诊断，stdout 仍保持协议 JSON；返回非零退出码让父进程即使
    未能解析响应也能判定失败。桥接采用“一进程一请求”，无需循环读取或自行管理并发。
    """
    _configure_stdio()
    try:
        raw = sys.stdin.read()  # 父进程写完单条请求后关闭 stdin，因此读到 EOF 即得到完整报文。
        response = dispatch(json.loads(raw))
    except Exception as error:
        traceback.print_exc(file=sys.stderr)  # 不写 stdout，避免破坏最终 JSON 信封。
        response = {"ok": False, "error": "%s: %s" %
                    (type(error).__name__, error)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
