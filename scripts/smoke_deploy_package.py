# -*- coding: utf-8 -*-
"""对 Windows Web 部署目录执行接近真实使用路径的端到端冒烟检查。

测试先验证桥接程序和前端静态文件确实包含指定业务，再使用独立临时数据目录启动打包后的
服务端，依次覆盖健康检查、管理员初始化与登录、文件上传、任务执行和结果下载。所有运行
数据都写入系统临时目录，结束时删除；不会读取或修改项目及生产环境的 ``web-data``。

该脚本面向构建产物而非源码服务，因此使用打包后的 EXE，并在 Windows 上设置无控制台
创建标志。任一环节失败都会保留当前异常向上抛出，同时 ``finally`` 负责终止子进程和清理
临时文件，避免失败冒烟留下占用端口的服务。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.version import VERSION  # noqa: E402

BUNDLE = os.path.join(ROOT, "dist", "deploy", "windows", f"峰运通服务端_windows_v{VERSION}")
BASE = "http://127.0.0.1:8791"


def request(path, method="GET", body=None, token=None):
    """向本次冒烟服务发送 JSON 请求，并把 HTTP 错误响应也解析为状态码与正文。

    参数：
        path: 以 ``/`` 开头的 API 路径。
        method: HTTP 方法，默认 GET。
        body: 可 JSON 序列化的请求体；``None`` 表示无正文。
        token: 可选会话令牌，写入 ``X-Session-Token`` 请求头。
    返回值：
        ``(状态码, 解析后的 JSON)`` 元组；空响应体解析为 ``None``。
    副作用：
        只发起本机 HTTP 请求，不修改仓库数据。
    异常：
        连接失败或响应不是 JSON 时向上抛出，由调用方定位服务未启动或协议变更。
    """

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Session-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        # API 的预期拒绝也有结构化 JSON；返回而不是吞掉，便于调用处同时断言状态和消息。
        return exc.code, json.loads(exc.read())


def _smoke_environment(tmp: str) -> dict[str, str]:
    """构造仅指向临时数据根的服务环境，避免冒烟读取正式 Web 数据。

    参数：
        tmp: 本次冒烟的临时目录，``FYT_WEB_DATA`` 指向其下的 ``data``。
    返回值：
        继承当前进程环境后叠加冒烟变量的副本。
    副作用：
        无；返回字典，不修改 ``os.environ``。
    """
    # 复制环境而非直接修改，保证冒烟结束后父进程环境不受污染。
    env = os.environ.copy()
    env.update({
        "FYT_WEB_DATA": os.path.join(tmp, "data"),
        "FYT_ADMIN_PASSWORD": "admin123456",  # 仅供临时数据库首次建库，目录清理后凭据随之消失。
        "FYT_WEB_PORT": "8791",
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _verify_bridge_actions(flags: int) -> None:
    """确认新增业务动作已进入部署包桥接白名单。

    参数：
        flags: 子进程创建标志；Windows 上传入 ``CREATE_NO_WINDOW``，避免测试时弹出控制台。
    返回值：
        无。
    异常：
        桥接程序非零退出、标准输出不是 JSON 或白名单未包含动作时，抛出 ``AssertionError``
        或 ``subprocess.CalledProcessError``。
    """
    bridge = os.path.join(BUNDLE, "桥接", "bridge_worker.exe")
    for action, payload in (
        ("purchase_plan.run", {}),
        ("reconcile_statement.scan", {"paths": []}),
    ):
        checked = subprocess.run(
            [bridge], input=json.dumps({"action": action, "payload": payload}),
            text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=flags, timeout=30, check=False,
        )
        response = json.loads(checked.stdout)  # 桥接标准输出必须始终是一条可解析 JSON 响应。
        assert "不支持的桥接动作" not in str(response.get("error") or ""), response


def _verify_static_assets() -> None:
    """检查真实构建产物中同时包含本轮要求的 Web 功能键。

    返回值：
        无。
    副作用：
        只读 ``BUNDLE/web-app/dist``；构建文件带内容哈希，因此按扩展名遍历而非依赖固定文件名。
    异常：
        功能键缺失时抛出 ``AssertionError``。
    """
    static_root = os.path.join(BUNDLE, "web-app", "dist")
    fragments: list[str] = []
    # 构建文件名带哈希，遍历入口与脚本比依赖具体文件名稳定。
    for root, _, names in os.walk(static_root):
        for name in names:
            if not name.endswith((".js", ".html")):
                continue
            with open(os.path.join(root, name), "r", encoding="utf-8", errors="ignore") as handle:
                fragments.append(handle.read())
    static_text = "".join(fragments)
    assert "purchase_plan" in static_text and "reconcile_statement" in static_text
    print("[0] 新增功能已包含在桥接程序和 Web 页面中")


def _start_server(tmp: str, env: dict[str, str], flags: int):
    """启动无控制台部署服务，并返回进程和保持打开的日志句柄。

    参数：
        tmp: 临时目录，服务日志写入其下 ``server.log``。
        env: 已指向临时数据根的运行环境。
        flags: 子进程创建标志；Windows 上传入 ``CREATE_NO_WINDOW``。
    返回值：
        ``(Popen 进程, 日志文件句柄)`` 元组；调用方负责在 ``finally`` 中关闭句柄并终止进程。
    副作用：
        启动部署服务子进程并持续写日志。
    异常：
        可执行文件缺失或启动失败时由 ``Popen`` 抛出 ``OSError``。
    """
    server_log = open(os.path.join(tmp, "server.log"), "wb")
    process = subprocess.Popen(
        [os.path.join(BUNDLE, "服务端", "web_server.exe")],
        cwd=BUNDLE, env=env,
        stdin=subprocess.DEVNULL, stdout=server_log, stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    return process, server_log


def _wait_for_server() -> None:
    """等待服务完成首次建库和静态资源初始化，最多三十秒。

    返回值：
        无。
    异常：
        30 秒内健康检查未返回 200 时抛出 ``RuntimeError``；启动窗口内的连接拒绝被忽略。
    """
    for _ in range(60):
        try:
            status, _ = request("/api/health")
            if status == 200:
                print("[1] health OK")
                return
        except Exception:
            pass  # 启动窗口内连接拒绝属于预期，耗尽重试后再给出统一错误。
        time.sleep(0.5)
    raise RuntimeError("服务未在 30 秒内启动")


def _verify_frontend_page() -> None:
    """确认部署服务实际托管了可挂载 React 的前端入口。

    返回值：
        无。
    异常：
        页面缺失挂载节点时抛出 ``AssertionError``，通常表示前端未构建或路由被改动。
    """
    with urllib.request.urlopen(BASE + "/", timeout=10) as response:
        html = response.read().decode("utf-8", errors="replace")
    assert '<div id="root"></div>' in html, "前端静态页面未找到（可能提示前端未构建）"
    print("[1.5] 前端页面 OK")


def _login_admin() -> str:
    """登录临时数据库的初始化管理员并返回短生命周期会话令牌。

    返回值：
        会话令牌字符串，用于后续上传、任务与下载请求。
    异常：
        登录状态非 200 或响应缺少 ``token`` 时抛出 ``AssertionError``。
    """
    status, login = request(
        "/api/auth/login", "POST", {"username": "admin", "password": "admin123456"},
    )
    assert status == 200 and login.get("token"), login
    print("[2] 登录 OK")
    return login["token"]


def _synthetic_attendance_file(tmp: str) -> str:
    """创建最小合成考勤表，覆盖真实 Excel 上传和业务处理链路。

    参数：
        tmp: 临时目录，合成表写入其下。
    返回值：
        合成 XLSX 文件路径。
    异常：
        工作簿写入失败时抛出 ``openpyxl`` 异常；``finally`` 确保工作簿关闭。
    """
    path = os.path.join(tmp, "考勤表.xlsx")
    workbook = openpyxl.Workbook()
    try:
        worksheet = workbook.active
        worksheet.append(["姓名", "日期", "工时"])
        worksheet.append(["张三", "2026-08-03", 8])
        worksheet.append(["李四", "2026-08-03", 7.5])
        workbook.save(path)
    finally:
        workbook.close()
    return path


def _upload_file(path: str, token: str) -> str:
    """以原始二进制协议上传合成表，并返回服务端不透明句柄。

    参数：
        path: 待上传文件路径。
        token: 会话令牌。
    返回值：
        服务端分配的文件句柄字符串。
    异常：
        上传失败或响应缺少 ``handle`` 时抛出相应异常。
    """
    with open(path, "rb") as handle:
        body = handle.read()
    upload_request = urllib.request.Request(
        BASE + "/api/files/upload?name=" + urllib.parse.quote(os.path.basename(path)),
        data=body, method="POST",
    )
    upload_request.add_header("Content-Type", "application/octet-stream")
    upload_request.add_header("X-Session-Token", token)
    with urllib.request.urlopen(upload_request, timeout=60) as response:
        upload = json.loads(response.read())
    assert upload.get("handle"), upload
    print("[3] 上传 OK:", upload["handle"])
    return upload["handle"]


def _create_archive_job(handle: str, token: str) -> str:
    """创建考勤归档长任务并返回持久化任务编号。

    参数：
        handle: 上传接口返回的文件句柄。
        token: 会话令牌。
    返回值：
        job_id 任务编号。
    异常：
        状态非 202 或缺少 ``job_id`` 时抛出 ``AssertionError``。
    """
    status, job = request("/api/jobs", "POST", {
        "action": "attendance_archive.run",
        "payload": {"paths": [handle]},
    }, token)
    assert status == 202 and job.get("job_id"), (status, job)
    print("[4] 任务已创建:", job["job_id"])
    return job["job_id"]


def _server_log_tail(tmp: str, server_log) -> str:
    """读取临时服务日志末尾，失败时提供有限且足够的诊断信息。

    参数：
        tmp: 临时目录。
        server_log: 由 ``_start_server`` 返回的日志句柄；先刷新保证已缓冲内容落盘。
    返回值：
        日志末尾至多 3000 字节的 UTF-8 文本。
    """
    server_log.flush()
    with open(os.path.join(tmp, "server.log"), "rb") as handle:
        return handle.read()[-3000:].decode("utf-8", errors="replace")


def _wait_for_job(job_id: str, token: str, tmp: str, server_log) -> dict[str, object]:
    """轮询长任务直到终态，只在状态变化时输出进度。

    参数：
        job_id: 任务编号。
        token: 会话令牌。
        tmp: 临时目录，失败诊断时读取服务日志。
        server_log: 日志句柄。
    返回值：
        终态任务对象字典。
    异常：
        任务未在 120 秒内完成或缺少输出文件时抛出 ``AssertionError``。
    """
    last = None
    job: dict[str, object] = {}
    for _ in range(120):
        _status, data = request(f"/api/jobs/{job_id}", token=token)
        job = (data or {}).get("job") or {}
        if job.get("status") != last:
            print("[5] job status:", job.get("status"), job.get("progress"))
            last = job.get("status")
        if last in ("completed", "failed", "cancelled"):
            break
        time.sleep(1)
    if last != "completed":
        print("JOB:", json.dumps(job, ensure_ascii=False, indent=1)[:1500])
        print("SERVER LOG tail:")
        print(_server_log_tail(tmp, server_log))
    assert job.get("status") == "completed", job
    assert job.get("files"), job
    print("[5] 任务完成，输出文件:", [item["name"] for item in job["files"]])
    return job


def _verify_result_download(job_id: str, token: str) -> None:
    """下载首个结果，并用 XLSX 的 ZIP 文件头拦截 JSON 错误页。

    参数：
        job_id: 已完成任务编号。
        token: 会话令牌。
    返回值：
        无。
    异常：
        状态非 200 或响应不是 ZIP 文件头时抛出 ``AssertionError``。
    """
    download = urllib.request.Request(BASE + f"/api/jobs/{job_id}/files/0/download")
    download.add_header("X-Session-Token", token)
    with urllib.request.urlopen(download, timeout=60) as response:
        blob = response.read()
        status = response.status
    assert status == 200 and blob[:2] == b"PK"
    print("[6] 结果下载 OK,", len(blob), "bytes")


def _stop_server(process: subprocess.Popen, server_log) -> None:
    """无论冒烟成功或失败都关闭日志并回收服务进程。

    参数：
        process: 待回收的服务进程。
        server_log: 已打开的日志句柄。
    副作用：
        先终止进程，超时后升级为强制杀死；设计为可在 ``finally`` 中调用，不掩盖主流程异常。
    """
    server_log.close()
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()  # 正常终止超时后强制回收，防止遗留进程继续占用 8791 端口。
        process.wait(timeout=5)


def _run_server_smoke(tmp: str, env: dict[str, str], flags: int) -> None:
    """覆盖健康检查、前端、认证、上传、任务执行和结果下载。

    参数：
        tmp: 临时目录。
        env: 冒烟运行环境。
        flags: 子进程创建标志。
    副作用：
        启动并最终回收部署服务；任意步骤失败都会先执行 ``finally`` 清理再向上抛异常。
    """
    process, server_log = _start_server(tmp, env, flags)
    try:
        _wait_for_server()
        _verify_frontend_page()
        token = _login_admin()
        handle = _upload_file(_synthetic_attendance_file(tmp), token)
        job_id = _create_archive_job(handle, token)
        _wait_for_job(job_id, token, tmp, server_log)
        _verify_result_download(job_id, token)
        print("SMOKE ALL OK")
    finally:
        _stop_server(process, server_log)


def main():
    """编排部署包静态检查与隔离服务端端到端冒烟。

    返回值：
        无。
    副作用：
        在系统临时目录创建冒烟数据，结束后递归删除；不读取项目或生产环境 ``web-data``。
    异常：
        部署包目录缺失时抛出 ``FileNotFoundError``；冒烟失败向上传播。
    """

    if not os.path.isdir(BUNDLE):
        raise FileNotFoundError("未找到 Windows 部署包目录：%s" % BUNDLE)
    tmp = tempfile.mkdtemp(prefix="fyt_smoke_")  # 与真实及仓库数据完全隔离的短生命周期目录。
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 非 Windows 环境回退为 0，保持脚本可被静态检查。
    try:
        _verify_bridge_actions(flags)
        _verify_static_assets()
        _run_server_smoke(tmp, _smoke_environment(tmp), flags)
    finally:
        # 临时目录位于系统 temp，保存失败诊断不受影响；这里兜底清理避免残留服务日志与数据。
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
