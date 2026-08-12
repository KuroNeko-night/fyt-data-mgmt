[CmdletBinding()]
param(
  [string]$Message = "同步源码",
  [switch]$Push,
  [string]$Branch = "main",
  [string]$RemoteUrl = ""
)

# 安全同步源码到 GitHub。默认只创建本地提交，只有显式传入 -Push 才会推送。
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $repoRoot

function Invoke-Git {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  & git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Git 命令失败：git $($Arguments -join ' ')"
  }
}

function Test-ForbiddenPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  $normalized = $Path.Replace("\", "/")
  if ($normalized -match '(^|/)(web-data|docker-data|dist|build|target|node_modules|\.venv|tmp|\.playwright-mcp|\.codex-audit|\.reasonix)(/|$)') {
    return $true
  }
  if ($normalized -match '(^|/)secrets/' -and $normalized -ne 'secrets/admin-password.example.txt') {
    return $true
  }
  if ($normalized -match '(^|/)\.env($|\.)' -and $normalized -notmatch '(^|/)\.env\.example$') {
    return $true
  }
  return $normalized -match '\.(sqlite|sqlite3|db|log|pem|key|cer|crt|pfx|p12|zip|bak|secret|token)$'
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "未找到 Git，请先安装 Git for Windows。"
}

$gitDirectory = Join-Path $repoRoot ".git"
if (-not (Test-Path -LiteralPath $gitDirectory)) {
  Invoke-Git -Arguments @("init")
}

Invoke-Git -Arguments @("branch", "-M", $Branch)

$defaultRemoteUrl = "https://github.com/KuroNeko-night/fyt-data-mgmt.git"
$remoteNames = @(& git remote)
if ($LASTEXITCODE -ne 0) {
  throw "无法读取 Git 远程仓库列表。"
}
if ($remoteNames -notcontains "origin") {
  $remote = if ($RemoteUrl) { $RemoteUrl } else { $defaultRemoteUrl }
  Invoke-Git -Arguments @("remote", "add", "origin", $remote)
}
else {
  $remote = & git remote get-url origin
  if ($LASTEXITCODE -ne 0 -or -not $remote) {
    throw "无法读取 origin 的远程地址。"
  }
  if ($RemoteUrl -and $remote.Trim() -ne $RemoteUrl) {
    Invoke-Git -Arguments @("remote", "set-url", "origin", $RemoteUrl)
    $remote = $RemoteUrl
  }
}

Invoke-Git -Arguments @("add", "--all")
$staged = @(& git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
  throw "无法读取待提交文件列表。"
}

$forbidden = @($staged | Where-Object { Test-ForbiddenPath -Path $_ })
if ($forbidden.Count -gt 0) {
  # 发现敏感文件时撤销本轮暂存，避免用户随后误提交。
  & git reset --quiet
  throw "检测到不允许同步的运行数据或敏感文件：$($forbidden -join ', ')"
}

if ($staged.Count -eq 0) {
  if ($Push) {
    & git rev-parse --verify HEAD *> $null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "当前仓库还没有可推送的提交。"
      exit 0
    }
    Invoke-Git -Arguments @("push", "-u", "origin", $Branch)
    Write-Host "已有本地提交已推送到 $($remote.Trim()) 的 $Branch 分支。"
    exit 0
  }
  Write-Host "没有需要提交的源码变更。"
  exit 0
}

Write-Host "将要提交的文件："
$staged | ForEach-Object { Write-Host "  $_" }
Invoke-Git -Arguments @("commit", "-m", $Message)

if ($Push) {
  Invoke-Git -Arguments @("push", "-u", "origin", $Branch)
  Write-Host "源码已推送到 $($remote.Trim()) 的 $Branch 分支。"
}
else {
  Write-Host "本地提交已完成；如需推送，请追加 -Push。"
}
