param(
  [int]$Port = 8787,
  [string]$AdminPassword = "",
  [string]$TunnelName = ""
)

# 同时启动源码版 Web 服务和 Cloudflare Tunnel，并把两个后台进程的 PID 与日志写入数据目录。
# Web 仅监听 127.0.0.1，公网流量只能经 Tunnel 进入。未指定 TunnelName 时使用地址会变化的
# Quick Tunnel；指定名称时由 cloudflared 读取用户已有的固定隧道配置。
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent  # 脚本位于 scripts/，仓库根目录在上一级。
# 查找顺序与安装脚本一致：PATH 优先，其次项目 tools 和系统标准安装目录。
$cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflaredCommand) {
  $candidates = @(
    (Join-Path $root "tools\cloudflared.exe"),
    (Join-Path ${env:ProgramFiles} "cloudflared\cloudflared.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe")
  )
  $cloudflaredPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (-not $cloudflaredPath) {
    throw "未找到 cloudflared。请先运行 scripts\install-cloudflared.ps1。"
  }
} else {
  $cloudflaredPath = $cloudflaredCommand.Source
}

$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$server = Join-Path $root "web_server.py"
if (-not (Test-Path -LiteralPath $pythonw) -or -not (Test-Path -LiteralPath $server)) {
  throw "尚未安装现代环境，请先运行 scripts\setup-modern.ps1。"
}

# 本入口沿用项目默认数据根；运行状态文件与业务日志分目录存放，不进入发布源码包。
$logDir = Join-Path $root "web-data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$webPidPath = Join-Path $logDir "web-service.pid"
$tunnelPidPath = Join-Path $logDir "cloudflare-tunnel.pid"
$webLog = Join-Path $logDir "web-service.log"
$webErrorLog = Join-Path $logDir "web-service-error.log"
$tunnelLog = Join-Path $logDir "cloudflare-tunnel.log"
$tunnelErrorLog = Join-Path $logDir "cloudflare-tunnel-error.log"

$env:FYT_WEB_HOST = "127.0.0.1"  # Tunnel 场景不直接监听公网网卡，减少绕过代理的暴露面。
$env:FYT_WEB_PORT = "$Port"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
# 公网启动必须显式具备首次管理员密码；服务端已有数据库时该变量不会重置现有账号。
$effectivePassword = if ($AdminPassword) { $AdminPassword } else { $env:FYT_ADMIN_PASSWORD }
if (-not $effectivePassword) {
  throw "公网访问必须显式设置管理员密码，请使用 -AdminPassword 或环境变量 FYT_ADMIN_PASSWORD。"
}
$env:FYT_ADMIN_PASSWORD = $effectivePassword

$existingWeb = $null
if (Test-Path -LiteralPath $webPidPath) {
  # PID 文件只作为候选，再用 Get-Process 验证进程仍存在，避免把陈旧记录当成运行状态。
  $oldId = Get-Content -LiteralPath $webPidPath -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($oldId -match '^\d+$') { $existingWeb = Get-Process -Id ([int]$oldId) -ErrorAction SilentlyContinue }
}
if (-not $existingWeb) {
  # pythonw 与 Hidden 避免桌面出现命令窗口，标准输出和错误分别保留便于定位启动失败。
  $webProcess = Start-Process -FilePath $pythonw -ArgumentList ('"{0}"' -f $server) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $webLog -RedirectStandardError $webErrorLog -PassThru
  Set-Content -LiteralPath $webPidPath -Value $webProcess.Id -Encoding ascii
  Write-Host "[完成] Web 服务已启动，进程号：$($webProcess.Id)"
} else {
  Write-Host "[提示] Web 服务已经运行，进程号：$($existingWeb.Id)"
}
Remove-Item Env:FYT_ADMIN_PASSWORD -ErrorAction SilentlyContinue  # 首次建库密码仅供 Web 服务启动读取，随后立即清理本进程环境。

# 命名隧道由本机既有凭据决定路由；快速隧道则明确代理到当前 Web 回环端口。
$tunnelArguments = if ($TunnelName) {
  @("tunnel", "run", $TunnelName)
} else {
  @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port")
}
$tunnelProcess = Start-Process -FilePath $cloudflaredPath -ArgumentList $tunnelArguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErrorLog -PassThru
Set-Content -LiteralPath $tunnelPidPath -Value $tunnelProcess.Id -Encoding ascii
Write-Host "[完成] Cloudflare Tunnel 已启动，进程号：$($tunnelProcess.Id)"

if (-not $TunnelName) {
  # 地址出现和连接注册都满足后才向用户报告可用，避免复制尚未路由成功的临时 URL。
  $publicUrl = ""
  $registered = $false
  $tunnelLogPaths = @($tunnelLog, $tunnelErrorLog)
  for ($attempt = 0; $attempt -lt 40; $attempt++) {  # 每半秒一次，最多等待约二十秒。
    Start-Sleep -Milliseconds 500
    foreach ($logPath in $tunnelLogPaths) {
      if (-not (Test-Path -LiteralPath $logPath)) {
        continue
      }
      # 只提取官方 trycloudflare 域名，并取日志中的最后一次分配结果。
      $match = Select-String -LiteralPath $logPath -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches | Select-Object -Last 1
      if ($match -and $match.Matches.Count) {
        $publicUrl = $match.Matches[0].Value
      }
      if (Select-String -LiteralPath $logPath -Pattern 'Registered tunnel connection' -Quiet) {
        $registered = $true
      }
    }
    if ($publicUrl -and $registered) { break }
    if ($tunnelProcess.HasExited) { break }  # 客户端提前退出时不再无意义等待完整超时。
  }
  if ($publicUrl -and $registered) {
    Set-Content -LiteralPath (Join-Path $logDir "cloudflare-tunnel.url") -Value $publicUrl -Encoding utf8
    Write-Host "[访问] 公网地址：$publicUrl"
    Write-Host "[提示] Quick Tunnel 地址每次重启可能变化；固定域名请使用 -TunnelName。"
  } else {
    Write-Host "[提示] 已创建公网地址，但 Tunnel 尚未确认连接，请稍后重试或查看 web-data\logs\cloudflare-tunnel-error.log。"
  }
}

