"""独立 Core 桥接子进程的生命周期与标准流协议。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping


@dataclass(frozen=True)
class BridgeDependencies:
    """桥接执行器需要的运行路径、进程索引和任务状态回调。"""

    root: Path
    data_root: Path
    job_lock: Any
    job_processes: MutableMapping[str, subprocess.Popen[str]]
    append_job_log: Callable[[str, str], None]
    update_job: Callable[..., None]


def bridge_command() -> list[str]:
    """返回开发环境或 PyInstaller 部署环境使用的桥接命令。

    冻结服务端不能再用 ``-m core.tauri_bridge``，因此依次检查服务端同目录和部署包的
    “桥接”目录。错误信息保留全部候选路径，便于定位部署包内容不完整的问题。
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "core.tauri_bridge"]
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        executable_dir / "bridge_worker.exe",
        executable_dir.parent / "桥接" / "bridge_worker.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate)]
    raise RuntimeError(
        "找不到桥接程序（frozen=%s，exe=%s），已尝试：%s"
        % (
            getattr(sys, "frozen", False),
            sys.executable,
            "、".join(str(candidate) for candidate in candidates),
        )
    )


def _bridge_runtime_paths(job_id: str, user_id: int, deps: BridgeDependencies):
    """创建账号隔离的输出、缓存和运行目录，并选择可写工作目录。"""
    user_root = deps.data_root / "users" / str(user_id)
    output_root = user_root / "jobs" / job_id / "outputs"
    cache_path = user_root / "cache" / "增量缓存.json"
    runtime_root = user_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # Linux 服务账号通常只读程序目录。工作目录必须既可进入又可写，否则业务开始后才会
    # 以 PermissionError 失败；数据根不可写时使用系统临时目录作为最后兜底。
    work_dir = (
        deps.data_root
        if os.access(deps.data_root, os.X_OK | os.W_OK)
        else Path(tempfile.gettempdir())
    )
    return output_root, cache_path, runtime_root, work_dir


def _bridge_environment(job_id: str, user_id: int, deps: BridgeDependencies):
    """构造单个账号任务的 Core 环境，不修改服务端进程自身环境。"""
    output_root, cache_path, runtime_root, work_dir = _bridge_runtime_paths(
        job_id, user_id, deps,
    )
    environment = os.environ.copy()
    inherited_python_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(deps.root), inherited_python_path) if item
    )
    environment.update({
        "PYTHONIOENCODING": "utf-8",
        "FYT_BRIDGE_EVENTS": "1",
        "FYT_REQUEST_ID": job_id,
        "FYT_WEB_OUTPUT_ROOT": str(output_root),
        "FYT_INCREMENTAL_CACHE_PATH": str(cache_path),
        "FYT_CATALOG_PATH": str(deps.data_root / "catalog.json"),
        # HOME 只存在于子进程副本中，用于兼容仍从用户目录推导配置的旧 Core 路径逻辑。
        "HOME": str(runtime_root),
        "FYT_CONFIG_PATH": str(runtime_root / "配置.json"),
        "FYT_TASK_HISTORY_PATH": str(runtime_root / "任务历史.db"),
    })
    return environment, work_dir


def _start_bridge_process(job_id: str, user_id: int, deps: BridgeDependencies):
    """启动桥接进程并登记句柄，使取消接口能按任务编号精确终止。"""
    environment, work_dir = _bridge_environment(job_id, user_id, deps)
    command = bridge_command()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(work_dir),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise RuntimeError(
            "无法启动任务进程：%s（命令：%r，工作目录：%s，frozen=%s）"
            % (exc, command, work_dir, getattr(sys, "frozen", False))
        ) from exc
    # 登记必须与启动在同一临界区可见：取消接口随时可能按任务编号查找句柄，漏登记会让取消失效。
    with deps.job_lock:
        deps.job_processes[job_id] = process
    return process


def _consume_bridge_events(
    process: subprocess.Popen[str],
    job_id: str,
    stderr_lines: list[str],
    deps: BridgeDependencies,
) -> None:
    """持续消费 stderr，把结构化日志、进度和诊断文本分流保存。"""
    assert process.stderr is not None
    event_prefix = "__FYT_EVENT__"
    for raw_line in process.stderr:
        line = raw_line.rstrip()
        if line.startswith(event_prefix):
            try:
                event = json.loads(line[len(event_prefix):])
                if event.get("kind") == "log":
                    deps.append_job_log(job_id, str(event.get("value", "")))
                elif event.get("kind") == "progress":
                    # 100 只由主进程在结果和版本记录持久化成功后写入。
                    value = max(0, min(99, int(event.get("value", 0))))
                    deps.update_job(job_id, progress=value)
            except (TypeError, ValueError, json.JSONDecodeError):
                # 单条损坏事件不应中断后续 stderr 消费，否则子进程可能因管道写满而阻塞。
                continue
        elif line:
            stderr_lines.append(line)


def _close_bridge_streams(process: subprocess.Popen[str], job_id: str,
                          deps: BridgeDependencies) -> None:
    """关闭已经建立的标准流并从活动进程索引移除任务句柄。"""
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    with deps.job_lock:
        deps.job_processes.pop(job_id, None)


def run_bridge(
    job_id: str,
    user_id: int,
    action: str,
    payload: dict[str, object],
    deps: BridgeDependencies,
) -> object:
    """通过单请求单进程协议执行一个 Core 动作并返回响应数据。"""
    process = _start_bridge_process(job_id, user_id, deps)
    stderr_lines: list[str] = []
    reader = threading.Thread(
        target=_consume_bridge_events,
        args=(process, job_id, stderr_lines, deps),
        daemon=True,
    )
    try:
        request = json.dumps(
            {"action": action, "payload": payload}, ensure_ascii=False,
        )
        assert process.stdin is not None
        process.stdin.write(request)
        process.stdin.close()
        # 先关闭子进程 stdin，再启动 stderr 消费线程，最后阻塞读取 stdout。stderr 若无人
        # 读取会写满管道并导致子进程阻塞；stdout 必须由主线程同步读回完整响应。
        reader.start()
        assert process.stdout is not None
        raw_output = process.stdout.read()
        return_code = process.wait()
        reader.join(timeout=2)
    finally:
        # 即使读取、等待或 JSON 解码失败，也必须释放管道并清除取消接口使用的进程索引。
        _close_bridge_streams(process, job_id, deps)
    if return_code != 0:
        detail = stderr_lines[-1] if stderr_lines else "业务核心进程执行失败"
        raise RuntimeError(detail)
    response = json.loads(raw_output or "{}")
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "业务核心返回失败"))
    return response.get("data")

