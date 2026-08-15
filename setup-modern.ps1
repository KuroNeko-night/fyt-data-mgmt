$ErrorActionPreference = "Stop"
# 为源码运行创建项目私有 Python 3.13 虚拟环境并安装锁定依赖。
# 脚本不修改系统 Python；已有 .venv 时直接复用。pip 命令失败会因 Stop 策略终止流程。
$ProjectRoot = $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    # 明确请求 Python 3.13，与 Windows 开发和打包技术基线保持一致。
    py -3.13 -m venv (Join-Path $ProjectRoot ".venv")
    # 原生命令非零退出不会触发 Stop，这里显式检查，避免带着不存在的 Python 继续跑 pip。
    if ($LASTEXITCODE -ne 0) { throw "创建 Python 3.13 虚拟环境失败，请先安装 Python 3.13 并确认 py 启动器可用" }
}

& $PythonPath -m pip install --upgrade pip
# 较长超时与重试适配不稳定企业网络，依赖版本仍完全由 requirements.txt 决定。
& $PythonPath -m pip install --retries 12 --timeout 120 -r (Join-Path $ProjectRoot "requirements.txt")
Write-Host "[完成] 现代运行环境已安装：$PythonPath"
