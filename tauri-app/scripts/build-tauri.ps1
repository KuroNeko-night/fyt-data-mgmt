# 构建正式 Tauri 安装程序前校验四处发布版本一致，并先重建 Python sidecar。
# 版本不一致会在耗时的 Rust/安装包构建之前失败，避免生成文件名与应用元数据互相矛盾的产物。
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$packageJsonPath = Join-Path $projectRoot "tauri-app\package.json"
$tauriConfigPath = Join-Path $projectRoot "tauri-app\src-tauri\tauri.conf.json"
$cargoTomlPath = Join-Path $projectRoot "tauri-app\src-tauri\Cargo.toml"
$versionModulePath = Join-Path $projectRoot "core\version.py"

$utf8 = [Text.Encoding]::UTF8  # 显式 UTF-8 读取中文路径下的配置，避免依赖 Windows 默认代码页。
$packageVersion = ([IO.File]::ReadAllText($packageJsonPath, $utf8) | ConvertFrom-Json).version
$tauriVersion = ([IO.File]::ReadAllText($tauriConfigPath, $utf8) | ConvertFrom-Json).version
# Cargo.toml 与 Python 版本模块不是 JSON，使用锚定行首的正则只读取顶层版本声明。
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
    # 桌面启动的 Codex/PowerShell 可能尚未刷新 PATH，显式加入 rustup 默认 bin 目录。
    $env:PATH = "$cargoBin;$env:PATH"
}

if (-not $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR_TEMPLATE) {
    # 仅在管理员未指定镜像时设置默认值，不覆盖企业内网已有下载策略。
    $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR_TEMPLATE = "https://ghfast.top/https://github.com/<owner>/<repo>/releases/download/<version>/<asset>"
}

# sidecar 必须先生成，因为 Tauri 打包会在 externalBin 阶段立即校验目标文件是否存在。
& npm.cmd run build:sidecar
if ($LASTEXITCODE -ne 0) {
    throw "Sidecar build failed with exit code $LASTEXITCODE."
}

& npx.cmd tauri build
if ($LASTEXITCODE -ne 0) {
    throw "Tauri build failed with exit code $LASTEXITCODE."
}
