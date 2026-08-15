param(
  [int]$Port = 8787,
  [string]$HostAddress = "0.0.0.0",
  [string]$AdminPassword = "",
  [switch]$Foreground
)

# 启动源码版 Web 服务。默认通过 pythonw 后台运行并隐藏命令窗口，-Foreground 则使用
# python 前台输出日志，便于开发排错。首次建库密码只通过当前进程环境传递，不写入页面。
$ErrorActionPreference = "Stop"
# 子进程从环境读取监听参数，与打包服务端和 GUI 控制台保持同一配置协议。
$env:FYT_WEB_PORT = "$Port"
$env:FYT_WEB_HOST = $HostAddress
$env:PYTHONUNBUFFERED = "1"
if ($AdminPassword) { $env:FYT_ADMIN_PASSWORD = $AdminPassword }

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pythonw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "尚未安装现代环境，请先运行 setup-modern.ps1"
}
$server = Join-Path $PSScriptRoot "web_server.py"
if ($Foreground) {
  # 前台模式有意使用 python.exe，使终端可直接接收标准输出、错误和 Ctrl+C。
  Write-Host "[启动] 峰运通 Web 服务: http://$HostAddress`:$Port"
  & $python $server
  $code = $LASTEXITCODE
  Remove-Item Env:FYT_ADMIN_PASSWORD -ErrorAction SilentlyContinue  # 服务进程已在启动时读取密码，立即清理本进程环境。
  exit $code
}

# 日志与 PID 跟随实际数据根，避免自定义 FYT_WEB_DATA 后停止脚本找不到进程记录。
$dataRoot = if ($env:FYT_WEB_DATA) { $env:FYT_WEB_DATA } else { Join-Path $PSScriptRoot "web-data" }
$logDir = Join-Path $dataRoot "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stdoutLog = Join-Path $logDir "web-service.log"
$stderrLog = Join-Path $logDir "web-service-error.log"
# pythonw 与 Hidden 双重保证桌面启动不出现命令窗口；标准流重定向保留故障诊断能力。
$process = Start-Process -FilePath $pythonw `
  -ArgumentList ('"{0}"' -f $server) `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru
Remove-Item Env:FYT_ADMIN_PASSWORD -ErrorAction SilentlyContinue  # 子进程已继承密码副本，立即清理本进程环境，避免后续进程读取明文密码。
Set-Content -LiteralPath (Join-Path $logDir "web-service.pid") -Value $process.Id -Encoding ascii  # 仅记录数字 PID，供受控停止脚本使用。
Write-Host "[完成] Web 服务已在后台启动，进程号: $($process.Id)"
