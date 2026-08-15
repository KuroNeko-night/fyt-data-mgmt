﻿param([switch]$ForceDownload)

# 安装或定位 Windows Cloudflare Tunnel 客户端。
# 默认优先复用 PATH、标准安装目录或项目 tools 中已有的可执行文件；随后尝试 winget，最后
# 才从 Cloudflare 官方发行地址下载。-ForceDownload 会跳过复用与 winget，便于修复损坏文件。
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent  # 脚本位于 scripts/，tools 位于仓库根目录，不受当前 PowerShell 路径影响。
$toolsDir = Join-Path $root "tools"

# 1. 先检查命令搜索路径和项目已知目录，避免每次运行都下载 latest。
$existing = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $existing) {
  $knownPaths = @(
    (Join-Path ${env:ProgramFiles} "cloudflared\cloudflared.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
    (Join-Path $toolsDir "cloudflared.exe")
  )
  # LiteralPath 防止安装路径中的方括号等字符被 PowerShell 当作通配符解释。
  $knownPath = $knownPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if ($knownPath) { $existing = Get-Item -LiteralPath $knownPath }
}
if ($existing -and -not $ForceDownload) {
  $source = if ($existing.PSObject.Properties.Name -contains "Source") { $existing.Source } else { $existing.FullName }
  Write-Host "[完成] 已找到 cloudflared：$source"
  & $source --version
  exit 0
}

# 2. 优先尝试 winget；由系统包管理器负责安装位置、升级和来源元数据。
if (-not $ForceDownload -and (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "[安装] 正在通过 winget 安装 cloudflared …"
  winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) {
    throw "cloudflared 安装失败，请检查 winget 输出或改用直接下载方式（本脚本会自动尝试）。"
  }
  Write-Host "[完成] cloudflared 安装完成。请重新打开 PowerShell 后再启动隧道。"
  exit 0
}

# 3. 无 winget或强制下载时，把官方 amd64 客户端放入项目 tools，服务控制台可直接发现。
Write-Host "[下载] 未使用 winget，改为直接下载 cloudflared …"
New-Item -ItemType Directory -Force $toolsDir | Out-Null
$target = Join-Path $toolsDir "cloudflared.exe"
$mirror = $env:CLOUDFLARED_MIRROR
if (-not $mirror) { $mirror = "https://gh-proxy.com/" }
$url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
if ($mirror -ne "-") { $url = $mirror + $url }  # “-”显式表示绕过镜像并直连 GitHub。

if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
  Write-Host "[下载] curl.exe $url"
  & curl.exe -L --fail --connect-timeout 30 --max-time 600 -o $target $url
  if ($LASTEXITCODE -ne 0) { throw "下载失败（curl 退出码 $LASTEXITCODE）。可设置 CLOUDFLARED_MIRROR 更换镜像后重试。" }
} else {
  Write-Host "[下载] Invoke-WebRequest $url"
  Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
}

# 成功执行版本命令才视为安装完成，可拦截代理返回的 HTML 错误页或损坏文件。
& $target --version
Write-Host "[完成] cloudflared 已安装：$target"
Write-Host "       控制台会自动识别该位置（无需重启电脑），也可手动把 exe 加入 PATH。"
Write-Host "       提示：国内网络下载失败时，可用 CLOUDFLARED_MIRROR=https://ghfast.top/ 或 https://ghproxy.net/ 重试。"
