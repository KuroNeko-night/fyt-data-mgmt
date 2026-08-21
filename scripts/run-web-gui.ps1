param(
  [switch]$NoExit
)

# 用 pythonw 启动 Tkinter 服务控制台：pythonw 本身没有控制台窗口，因此不能再加
# `-WindowStyle Hidden`，否则会把 GUI 主窗口也一起隐藏。-NoExit 仅供脚本调用方等待
# GUI 退出并取得退出码，默认立即返回，让用户可以关闭当前 PowerShell 窗口而不影响控制台进程。
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$ProjectRoot = Split-Path $PSScriptRoot -Parent  # 脚本位于 scripts/，仓库根目录在上一级。

$python = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"  # GUI 必须使用 pythonw，避免额外命令窗口。
if (-not (Test-Path -LiteralPath $python)) {
  throw "尚未安装现代环境，请先运行 scripts\setup-modern.ps1"
}
$script = Join-Path $ProjectRoot "web_control_gui.py"
$logDir = Join-Path $ProjectRoot "web-data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null  # 诊断日志目录与运行数据一起创建，不依赖 GUI 先成功启动。
$stdoutLog = Join-Path $logDir "gui-launcher.stdout.log"
$stderrLog = Join-Path $logDir "gui-launcher.stderr.log"
$launcherLog = Join-Path $logDir "gui-launcher.log"
$process = Start-Process -FilePath $python `
  -ArgumentList ('"{0}"' -f $script) `
  -WorkingDirectory $ProjectRoot `
  -WindowStyle Normal `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru
try {
  Add-Content -Path $launcherLog -Value ("{0} python={1} pid={2} cwd={3}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $python, $process.Id, $ProjectRoot)
} catch { }
if ($NoExit) { $process.WaitForExit(); exit $process.ExitCode }  # 显式等待只影响调用脚本，不改变 GUI 生命周期。
