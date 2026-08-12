# 把 Python 业务桥接打包为 Tauri sidecar，并按 Rust 主机目标三元组命名最终可执行文件。
# PyInstaller 输出先落入项目 build 暂存目录，只有成功生成 FYTCoreBridge.exe 后才复制到
# src-tauri/binaries。窗口隐藏、模块白名单和排除 GUI 依赖由 packaging/tauri_bridge.spec 定义。
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path  # 从脚本位置回到仓库根目录。
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$buildRoot = Join-Path $projectRoot "build\tauri-sidecar"
$sourcePath = Join-Path $buildRoot "dist\FYTCoreBridge.exe"
$binaryDir = Join-Path $projectRoot "tauri-app\src-tauri\binaries"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Project virtual environment not found. Run setup-modern.ps1 first."
}

# 优先使用 PATH 中的 Rust；rustup 默认目录作为 Windows 新安装环境的兼容回退。
$rustcCommand = Get-Command rustc -ErrorAction SilentlyContinue
if ($null -eq $rustcCommand) {
    $cargoRustc = Join-Path $env:USERPROFILE ".cargo\bin\rustc.exe"
    if (Test-Path -LiteralPath $cargoRustc -PathType Leaf) {
        $rustcPath = $cargoRustc
    } else {
        throw "rustc not found. Install the Rust MSVC toolchain first."
    }
} else {
    $rustcPath = $rustcCommand.Source
}

# Tauri externalBin 要求文件名包含目标三元组，不能只根据操作系统猜测 amd64/aarch64。
$hostLine = & $rustcPath -vV | Where-Object { $_ -like "host:*" } | Select-Object -First 1
if (-not $hostLine) {
    throw "Unable to read the Rust host target triple."
}
$targetTriple = ($hostLine -replace "^host:\s*", "").Trim()
if (-not $targetTriple) {
    throw "The Rust host target triple is empty."
}

Write-Host "[1/2] Building Python sidecar: $targetTriple"
Push-Location $projectRoot
try {
    # --clean 防止旧 hidden import 或二进制残留进入新 sidecar；dist/work 都限制在 build 下。
    & $pythonPath -m PyInstaller "packaging\tauri_bridge.spec" `
        --noconfirm --clean `
        --distpath (Join-Path $buildRoot "dist") `
        --workpath (Join-Path $buildRoot "work")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
} finally {
    # 即使 PyInstaller 失败也恢复调用者工作目录，避免后续 npm 命令在错误目录执行。
    Pop-Location
}

if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "PyInstaller did not produce FYTCoreBridge.exe."
}

New-Item -ItemType Directory -Force -Path $binaryDir | Out-Null
$targetPath = Join-Path $binaryDir ("FYTCoreBridge-{0}.exe" -f $targetTriple)  # 与 tauri.conf.json externalBin 解析规则一致。
Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force

Write-Host "[2/2] Tauri sidecar ready: $targetPath"
