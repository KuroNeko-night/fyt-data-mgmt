param(
  [int]$Port = 8787,
  [string]$HostAddress = "0.0.0.0",
  [string]$AdminPassword = "",
  [switch]$Foreground
)

$ErrorActionPreference = "Stop"
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
  Write-Host "[启动] 峰运通 Web 服务: http://$HostAddress`:$Port"
  & $python $server
  exit $LASTEXITCODE
}

$logDir = Join-Path $PSScriptRoot "web-data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stdoutLog = Join-Path $logDir "web-service.log"
$stderrLog = Join-Path $logDir "web-service-error.log"
$process = Start-Process -FilePath $pythonw `
  -ArgumentList ('"{0}"' -f $server) `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru
Set-Content -LiteralPath (Join-Path $logDir "web-service.pid") -Value $process.Id -Encoding ascii
Write-Host "[完成] Web 服务已在后台启动，进程号: $($process.Id)"
