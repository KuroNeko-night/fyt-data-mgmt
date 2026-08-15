param(
  [switch]$NoExit
)

# 无命令窗口启动 Tkinter 服务控制台。-NoExit 仅供脚本调用方等待 GUI 退出并取得退出码，
# 默认立即返回，让用户可以关闭当前 PowerShell 窗口而不影响控制台进程。
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$python = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"  # GUI 必须使用 pythonw，避免额外命令窗口。
if (-not (Test-Path -LiteralPath $python)) {
  throw "尚未安装现代环境，请先运行 setup-modern.ps1"
}
$script = Join-Path $PSScriptRoot "web_control_gui.py"
$process = Start-Process -FilePath $python `
  -ArgumentList ('"{0}"' -f $script) `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -PassThru
if ($NoExit) { $process.WaitForExit(); exit $process.ExitCode }  # 显式等待只影响调用脚本，不改变 GUI 生命周期。
