$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$buildRoot = Join-Path $projectRoot "build\tauri-sidecar"
$sourcePath = Join-Path $buildRoot "dist\FYTCoreBridge.exe"
$binaryDir = Join-Path $projectRoot "tauri-app\src-tauri\binaries"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Project virtual environment not found. Run setup-modern.ps1 first."
}

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
    & $pythonPath -m PyInstaller "packaging\tauri_bridge.spec" `
        --noconfirm --clean `
        --distpath (Join-Path $buildRoot "dist") `
        --workpath (Join-Path $buildRoot "work")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "PyInstaller did not produce FYTCoreBridge.exe."
}

New-Item -ItemType Directory -Force -Path $binaryDir | Out-Null
$targetPath = Join-Path $binaryDir ("FYTCoreBridge-{0}.exe" -f $targetTriple)
Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force

Write-Host "[2/2] Tauri sidecar ready: $targetPath"
