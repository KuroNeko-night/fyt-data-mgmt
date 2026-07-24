param(
  [switch]$NoExit
)

$ErrorActionPreference = "Stop"
$env:QT_API = "pyside6"
$env:PYTHONIOENCODING = "utf-8"

$python = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "尚未安装现代环境，请先运行 setup-modern.ps1"
}
$script = Join-Path $PSScriptRoot "web_control_gui.py"
$process = Start-Process -FilePath $python `
  -ArgumentList ('"{0}"' -f $script) `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -PassThru
if ($NoExit) { $process.WaitForExit(); exit $process.ExitCode }
