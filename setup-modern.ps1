$ErrorActionPreference = "Stop"
# 为源码运行创建项目私有 Python 3.13 虚拟环境并安装锁定依赖。
# 脚本不修改系统 Python；已有 .venv 时直接复用。pip 命令失败会因 Stop 策略终止流程。
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    # 明确请求 Python 3.13，与 Windows 开发和打包技术基线保持一致。
    py -3.13 -m venv (Join-Path $ProjectRoot ".venv")
}

& $PythonPath -m pip install --upgrade pip
# 较长超时与重试适配不稳定企业网络，依赖版本仍完全由 requirements.txt 决定。
& $PythonPath -m pip install --retries 12 --timeout 120 -r (Join-Path $ProjectRoot "requirements.txt")
Write-Host "[完成] 现代运行环境已安装：$PythonPath"
