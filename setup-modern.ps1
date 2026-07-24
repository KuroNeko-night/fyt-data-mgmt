$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    py -3.13 -m venv (Join-Path $ProjectRoot ".venv")
}

& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install --retries 12 --timeout 120 -r (Join-Path $ProjectRoot "requirements.txt")
Write-Host "[完成] 现代运行环境已安装：$PythonPath"
