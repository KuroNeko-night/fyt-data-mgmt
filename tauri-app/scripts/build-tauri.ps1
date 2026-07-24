$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$packageJsonPath = Join-Path $projectRoot "tauri-app\package.json"
$tauriConfigPath = Join-Path $projectRoot "tauri-app\src-tauri\tauri.conf.json"
$cargoTomlPath = Join-Path $projectRoot "tauri-app\src-tauri\Cargo.toml"
$versionModulePath = Join-Path $projectRoot "core\version.py"

$utf8 = [Text.Encoding]::UTF8
$packageVersion = ([IO.File]::ReadAllText($packageJsonPath, $utf8) | ConvertFrom-Json).version
$tauriVersion = ([IO.File]::ReadAllText($tauriConfigPath, $utf8) | ConvertFrom-Json).version
$cargoVersionMatch = [regex]::Match([IO.File]::ReadAllText($cargoTomlPath, $utf8), '(?m)^version\s*=\s*"([^"]+)"')
$coreVersionMatch = [regex]::Match([IO.File]::ReadAllText($versionModulePath, $utf8), '(?m)^VERSION\s*=\s*"([^"]+)"')
if (-not $cargoVersionMatch.Success -or -not $coreVersionMatch.Success) {
    throw "Unable to read the Cargo or Python application version."
}
$cargoVersion = $cargoVersionMatch.Groups[1].Value
$coreVersion = $coreVersionMatch.Groups[1].Value
$versions = @($packageVersion, $tauriVersion, $cargoVersion, $coreVersion) | Select-Object -Unique
if ($versions.Count -ne 1) {
    throw "Version mismatch: package=$packageVersion tauri=$tauriVersion cargo=$cargoVersion core=$coreVersion"
}

$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path -LiteralPath $cargoBin -PathType Container) {
    $env:PATH = "$cargoBin;$env:PATH"
}

if (-not $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR_TEMPLATE) {
    $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR_TEMPLATE = "https://ghfast.top/https://github.com/<owner>/<repo>/releases/download/<version>/<asset>"
}

& npm.cmd run build:sidecar
if ($LASTEXITCODE -ne 0) {
    throw "Sidecar build failed with exit code $LASTEXITCODE."
}

& npx.cmd tauri build
if ($LASTEXITCODE -ne 0) {
    throw "Tauri build failed with exit code $LASTEXITCODE."
}
