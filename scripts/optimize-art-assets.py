# -*- coding: utf-8 -*-
"""把对话中生成的原始图片转换为双端可直接使用的美术资源。

脚本依据 ``scripts/art-prompts/manifest.json`` 决定资源名称、输出格式、使用端和是否需要
去除色键背景。原图只从项目临时缓存读取，最终文件写入 ``assets/generated``；前端引用
仍由资源同步脚本处理，本模块不修改 React 页面或设计令牌。

对于需要透明背景的图片，会调用本机 imagegen 技能附带的抠图工具，并验证四角透明度，
以尽早发现背景残留。资源清单记录来源尺寸、生成时间和用途，供后续同步与审计使用。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]  # 所有相对资源位置都锚定仓库根目录，而非当前终端目录。
CACHE_ROOT = ROOT / "tmp" / "art-generation"
OUTPUT_ROOT = ROOT / "assets" / "generated"
REMOVE_CHROMA_KEY = Path.home() / ".codex" / "skills" / ".system" / "imagegen" / "scripts" / "remove_chroma_key.py"


def selected_ids(value: str | None) -> set[str]:
    """解析资源编号；未指定时只选择缓存中本阶段的 A01～A07 原图。

    参数：
        value: 逗号分隔的资源编号串，允许空串或 ``None``。
    返回值：
        去重后的编号集合；默认按缓存文件名首段推断，空项与重复项不影响处理顺序。
    """

    if not value:
        # 文件名约定为“编号-资源名.png”，这里只取首段编号并去重，且限制在本阶段 A01～A07 范围内。
        return {path.stem.split("-", 1)[0] for path in CACHE_ROOT.glob("A0[1-7]-*.png")}
    return {item.strip() for item in value.split(",") if item.strip()}


def remove_chroma_key(source: Path, target: Path) -> None:
    """调用统一抠图工具生成透明 PNG，失败时保留原始图片并向上抛错。

    参数：
        source: 对话生成的原始图片路径。
        target: 透明 PNG 输出路径，父目录不存在时自动创建。
    返回值：
        无。
    副作用：
        启动 Python 子进程运行抠图工具；不捕获标准流，便于操作者直接看到诊断信息。
    异常：
        工具脚本缺失时抛出 ``RuntimeError``；抠图进程非零退出时抛出
        ``subprocess.CalledProcessError``。
    """

    if not REMOVE_CHROMA_KEY.exists():
        raise RuntimeError("找不到本地抠图工具 remove_chroma_key.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(REMOVE_CHROMA_KEY),
        "--input",
        str(source),
        "--out",
        str(target),
        "--auto-key",
        "border",
        "--soft-matte",
        "--transparent-threshold",
        "12",
        "--opaque-threshold",
        "220",
        "--despill",
    ]
    subprocess.run(command, check=True)  # 不捕获标准流，便于操作者直接看到抠图工具的诊断信息。


def validate_transparency(path: Path) -> None:
    """检查图片四角是否完全透明，拦截最常见的色键去除失败。

    参数：
        path: 待验证的 PNG 图片路径。
    返回值：
        无。
    异常：
        四角任一像素 alpha 不为 0 时抛出 ``RuntimeError``。
    不变量：
        只读检查，不修改图片；四角通常只包含纯背景，不会误判主体半透明边缘。
    """

    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        # 四角通常只包含纯背景；检查透明通道不会误判主体内部需要保留的半透明边缘。
        corners = [rgba.getpixel(point)[3] for point in [(0, 0), (rgba.width - 1, 0), (0, rgba.height - 1), (rgba.width - 1, rgba.height - 1)]]
        if not all(alpha == 0 for alpha in corners):
            raise RuntimeError(f"{path.name} 四角没有完全透明")


def write_webp(source: Path, target: Path) -> None:
    """输出带透明通道的 WebP 副本，以降低 Web 和桌面静态资源体积。

    参数：
        source: 已准备好的 PNG 源文件。
        target: WebP 输出路径。
    返回值：
        无。
    副作用：
        在目标路径写入新文件。
    异常：
        图片读取或编码失败时抛出 ``PIL`` 异常。
    """

    with Image.open(source) as image:
        image.convert("RGBA").save(target, "WEBP", quality=88, method=6)


def output_targets(asset: dict, base_name: str) -> list[Path]:
    """根据清单用途计算资源需要落入 Web、Tauri 或双端的目标路径。

    参数：
        asset: 清单中的资源条目，必须包含 ``usage`` 与可选 ``output`` 字段。
        base_name: 资源文件名（不含扩展名）。
    返回值：
        目标路径列表；Web 总是包含，仅明确标记桌面用途时才追加 Tauri，避免安装包膨胀。
    """

    extension = str(asset.get("output", "png")).lower()
    targets = [OUTPUT_ROOT / "web" / f"{base_name}.{extension}"]
    # 只有明确标记桌面使用场景的资源才复制到 Tauri，避免无关资产扩大安装包。
    if "tauri-home" in asset["usage"] or "tauri-task-center" in asset["usage"] or "tauri-mode-picker" in asset["usage"]:
        targets.append(OUTPUT_ROOT / "tauri" / f"{base_name}.{extension}")
    return targets


def clear_old_outputs(base_name: str) -> None:
    """删除同名资源的旧格式变体，防止同步脚本继续拾取过期文件。

    参数：
        base_name: 资源文件名（不含扩展名）。
    返回值：
        无。
    副作用：
        删除 ``assets/generated/web`` 与 ``assets/generated/tauri`` 下同名任意后缀文件。
    异常：
        删除失败时由 ``Path.unlink`` 抛出 ``OSError``。
    """

    for directory in (OUTPUT_ROOT / "web", OUTPUT_ROOT / "tauri"):
        for path in directory.glob(f"{base_name}.*"):
            path.unlink()


def save_primary(source: Path, target: Path, chroma_key: bool) -> None:
    """按清单格式保存主文件，透明资源保留 RGBA，非透明资源转为 RGB。

    参数：
        source: 已准备好的源图片路径。
        target: 输出文件路径；输出格式由目标扩展名决定。
        chroma_key: 为真时保留透明通道，为假时丢弃 alpha 以减小体积。
    返回值：
        无。
    副作用：
        写入主文件，父目录须已存在。
    异常：
        图片读写失败时抛出 ``PIL`` 异常。
    """

    with Image.open(source) as image:
        prepared = image.convert("RGBA" if chroma_key else "RGB")
        prepared.save(target, target.suffix.lstrip(".").upper(), optimize=True)


def _process_asset(asset_id: str, asset: dict, prompt_manifest: dict) -> dict:
    """处理单个美术资源并返回清单记录。"""
    if not asset or not asset_id.startswith("A0") or int(asset_id[1:]) > 7:
        raise RuntimeError(f"本阶段不处理资源 {asset_id}")
    source_path = CACHE_ROOT / f"{asset_id}-{asset['name']}.png"
    if not source_path.exists():
        # 允许原图文件名的中文说明发生变化，但编号必须保持稳定且唯一。
        source_path = next(CACHE_ROOT.glob(f"{asset_id}-*.png"), None)
    if not source_path or not source_path.exists():
        raise RuntimeError(f"缺少 {asset_id} 的对话生成图片，请先复制到 {CACHE_ROOT}")
    with Image.open(source_path) as source_image:
        source_size = f"{source_image.width}x{source_image.height}"
    generated_at = datetime.fromtimestamp(source_path.stat().st_mtime, timezone.utc).isoformat()
    base_name = asset["name"]
    clear_old_outputs(base_name)  # 在写新格式前清理旧后缀，保证清单只列出当前有效版本。
    if asset["chromaKey"]:
        prepared = CACHE_ROOT / f"{asset_id}-{base_name}-alpha.png"
        remove_chroma_key(source_path, prepared)
        validate_transparency(prepared)
    else:
        prepared = source_path
    for target in output_targets(asset, base_name):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".png":
            save_primary(prepared, target, asset["chromaKey"])
        else:
            write_webp(prepared, target)
    if str(asset.get("output", "png")).lower() == "png":
        # PNG 作为无损主文件时额外生成 WebP，让不同前端可按体积与兼容性选择。
        for directory in (OUTPUT_ROOT / "web", OUTPUT_ROOT / "tauri"):
            if directory.exists() and (directory / f"{base_name}.png").exists():
                write_webp(prepared, directory / f"{base_name}.webp")
    # 清单统一使用正斜杠，确保在 Windows 生成后仍可被 Linux 和前端工具稳定解析。
    final_files = [str(path.relative_to(OUTPUT_ROOT)).replace("\\", "/") for path in sorted(OUTPUT_ROOT.rglob(f"{base_name}.*"))]
    return {
        "id": asset_id,
        "version": prompt_manifest["version"],
        "prompt_file": f"scripts/art-prompts/{asset['promptFile']}",
        "source_size": source_size,
        "final_files": final_files,
        "background": "chroma-key-removed" if asset["chromaKey"] else "opaque",
        "usage": asset["usage"],
        "alt": asset["alt"],
        "generated_at": generated_at,
    }


def _write_manifest(records: list[dict]) -> None:
    """把本批处理结果写入输出根目录的清单文件。"""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    # 每次只记录本次实际处理的资源，避免把磁盘上无法追溯来源的旧文件伪装成已验收资产。
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "assets": records,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """按资源清单完成筛选、抠图、格式转换并重建本批资源记录。

    参数：
        命令行参数：``--assets`` 可指定逗号分隔的资源编号。
    返回值：
        无。
    副作用：
        读取 ``scripts/art-prompts/manifest.json``，写入 ``assets/generated`` 及
        ``assets/generated/manifest.json``；不修改 React 页面与设计令牌。
    异常：
        资源编号越界、原图缺失、抠图或透明度验证失败时抛出对应异常。
    """

    parser = argparse.ArgumentParser(description="优化离线生成的峰运通静态美术资源")
    parser.add_argument("--assets", help="逗号分隔的资源编号，默认处理缓存中的 A01～A07")
    args = parser.parse_args()
    # 资源清单是本脚本唯一事实源；读取失败会直接抛出 JSON/OSError，不进入半处理状态。
    prompt_manifest = json.loads((ROOT / "scripts" / "art-prompts" / "manifest.json").read_text(encoding="utf-8"))
    assets = {item["id"]: item for item in prompt_manifest["assets"]}
    records = [
        _process_asset(asset_id, assets.get(asset_id), prompt_manifest)
        for asset_id in sorted(selected_ids(args.assets))
    ]
    _write_manifest(records)
    print(f"已优化 {len(records)} 个资源，并写入 {OUTPUT_ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
