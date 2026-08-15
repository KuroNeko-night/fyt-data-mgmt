$ErrorActionPreference = "Stop"
# 停止由项目脚本记录的 Web 与 Tunnel 后台进程。
# 脚本只读取数据目录 logs 下的数字 PID，不按进程名批量结束其他 Python 或 cloudflared 实例；
# 无论进程是否仍存在，都会清理陈旧 PID 和临时公网地址文件。
$ProjectRoot = Split-Path $PSScriptRoot -Parent  # 脚本位于 scripts/，仓库根目录在上一级。
$dataRoot = if ($env:FYT_WEB_DATA) { $env:FYT_WEB_DATA } else { Join-Path $ProjectRoot "web-data" }  # 与 run-web.ps1 保持同一数据根解析。
$logDir = Join-Path $dataRoot "logs"
$stopped = $false

# Tunnel 先停、Web 后停，缩短后端停止后公网入口仍接受请求的窗口。
foreach ($entry in @(
  @{ Path = Join-Path $logDir "cloudflare-tunnel.pid"; Label = "Cloudflare Tunnel" },
  @{ Path = Join-Path $logDir "web-service.pid"; Label = "Web 服务" }
)) {
  if (-not (Test-Path -LiteralPath $entry.Path)) { continue }
  $value = Get-Content -LiteralPath $entry.Path -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($value -match '^\d+$') {  # 非数字内容直接忽略，避免把被篡改的 PID 文件当作参数。
    $process = Get-Process -Id ([int]$value) -ErrorAction SilentlyContinue
    if ($process) {
      Stop-Process -Id $process.Id -Force  # 这是用户明确执行的停止入口，确保后台进程立即回收。
      Write-Host "[完成] 已关闭 $($entry.Label)，进程号：$($process.Id)"
      $stopped = $true
    }
  }
  Remove-Item -LiteralPath $entry.Path -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath (Join-Path $logDir "cloudflare-tunnel.url") -Force -ErrorAction SilentlyContinue
if (-not $stopped) { Write-Host "[提示] 没有找到由本项目启动的公网服务。" }

