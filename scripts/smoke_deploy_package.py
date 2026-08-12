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
    """向本次冒烟服务发送 JSON 请求，并把 HTTP 错误响应也解析为状态码与正文。"""

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


def main():
    """运行桥接、静态资源、认证、任务和下载的完整部署包冒烟流程。"""

    if not os.path.isdir(BUNDLE):
        raise FileNotFoundError("未找到 Windows 部署包目录：%s" % BUNDLE)
    tmp = tempfile.mkdtemp(prefix="fyt_smoke_")  # 与真实及仓库数据完全隔离的短生命周期目录。
    env = os.environ.copy()
    env.update({
        "FYT_WEB_DATA": os.path.join(tmp, "data"),
        "FYT_ADMIN_PASSWORD": "admin123456",  # 仅供临时数据库首次建库，目录清理后凭据随之消失。
        "FYT_WEB_PORT": "8791",
        "PYTHONIOENCODING": "utf-8",
    })
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 非 Windows 环境回退为 0，保持脚本可被静态检查。
    bridge = os.path.join(BUNDLE, "桥接", "bridge_worker.exe")
    # 只需确认动作已进入打包白名单；输入故意不满足业务要求，业务级校验错误不视为缺失动作。
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
        response = json.loads(checked.stdout)  # 桥接标准输出必须始终是一条可解析的 JSON 响应。
        assert "不支持的桥接动作" not in str(response.get("error") or ""), response
    static_root = os.path.join(BUNDLE, "web-app", "dist")
    # 构建后的文件名包含哈希，遍历所有入口和脚本比依赖具体文件名更稳定。
    static_text = "".join(
        open(os.path.join(root, name), "r", encoding="utf-8", errors="ignore").read()
        for root, _, names in os.walk(static_root)
        for name in names if name.endswith((".js", ".html"))
    )
    assert "purchase_plan" in static_text and "reconcile_statement" in static_text
    print("[0] 新增功能已包含在桥接程序和 Web 页面中")

    server_log = open(os.path.join(tmp, "server.log"), "wb")
    proc = subprocess.Popen(
        [os.path.join(BUNDLE, "服务端", "web_server.exe")],
        cwd=BUNDLE, env=env,
        stdin=subprocess.DEVNULL, stdout=server_log, stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    try:
        # 最多等待三十秒，覆盖低配构建机首次创建数据库和加载静态资源的时间。
        for _ in range(60):
            try:
                status, _ = request("/api/health")
                if status == 200:
                    break
            except Exception:
                pass  # 启动窗口内连接拒绝属于预期状态，超时后再给出统一错误。
            time.sleep(0.5)
        else:
            raise RuntimeError("服务未在 30 秒内启动")
        print("[1] health OK")

        with urllib.request.urlopen(BASE + "/", timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        assert '<div id="root"></div>' in html, '前端静态页面未找到（可能提示前端未构建）'
        print("[1.5] 前端页面 OK")

        status, login = request("/api/auth/login", "POST", {"username": "admin", "password": "admin123456"})
        assert status == 200 and login.get("token"), login
        token = login["token"]
        print("[2] 登录 OK")

        # 使用最小合成表覆盖二进制上传与真实 Excel 业务链路，不依赖任何客户文件。
        path = os.path.join(tmp, "考勤表.xlsx")
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["姓名", "日期", "工时"])
        ws.append(["张三", "2026-08-03", 8])
        ws.append(["李四", "2026-08-03", 7.5])
        wb.save(path); wb.close()
        with open(path, "rb") as handle:
            payload = handle.read()
        body = payload
        req = urllib.request.Request(
            BASE + "/api/files/upload?name=" + urllib.parse.quote("考勤表.xlsx"),
            data=body, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("X-Session-Token", token)
        with urllib.request.urlopen(req, timeout=60) as resp:
            upload = json.loads(resp.read())
        assert upload.get("handle"), upload
        print("[3] 上传 OK:", upload["handle"])

        status, job = request("/api/jobs", "POST", {
            "action": "attendance_archive.run",
            "payload": {"paths": [upload["handle"]]},
        }, token)
        assert status == 202 and job.get("job_id"), (status, job)
        job_id = job["job_id"]
        print("[4] 任务已创建:", job_id)

        last = None
        # 大约等待两分钟；状态变化才打印，避免轮询日志淹没真正的任务诊断。
        for _ in range(120):
            status, data = request(f"/api/jobs/{job_id}", token=token)
            job = (data or {}).get("job") or {}
            if job.get("status") != last:
                print("[5] job status:", job.get("status"), job.get("progress"))
                last = job.get("status")
            if last in ("completed", "failed", "cancelled"):
                break
            time.sleep(1)
        if last != "completed":
            # 失败时只输出临时日志末尾，既提供诊断信息，也避免大量日志污染构建输出。
            print("JOB:", json.dumps(job, ensure_ascii=False, indent=1)[:1500])
            print("SERVER LOG tail:")
            server_log.flush()
            with open(os.path.join(tmp, "server.log"), "rb") as h:
                print(h.read()[-3000:].decode("utf-8", errors="replace"))
        assert job.get("status") == "completed", job
        files = job.get("files") or []
        assert files, job
        print("[5] 任务完成，输出文件:", [f["name"] for f in files])

        dl = urllib.request.Request(BASE + f"/api/jobs/{job_id}/files/0/download")
        dl.add_header("X-Session-Token", token)
        with urllib.request.urlopen(dl, timeout=60) as resp:
            blob = resp.read()
        assert resp.status == 200 and blob[:2] == b"PK"  # XLSX 是 ZIP 容器，PK 文件头可拦截 JSON 错误页。
        print("[6] 结果下载 OK,", len(blob), "bytes")
        print("SMOKE ALL OK")
    finally:
        # 无论哪项断言失败，都先关闭日志句柄并终止服务，再删除 Windows 上仍可能被占用的目录。
        server_log.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()  # 正常终止超时后强制回收，防止遗留进程继续占用 8791 端口。
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
