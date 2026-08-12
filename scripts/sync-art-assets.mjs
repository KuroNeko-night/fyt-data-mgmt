import { cp, mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/*
 * 把 assets/generated 中已经验收的美术资源复制到 Web 与 Tauri public 目录。
 * 脚本不生成或重新处理图片；优化和透明通道检查由 optimize-art-assets.py 完成。manifest
 * 必须存在才开始复制，使双端资源始终能够追溯到同一批生成记录。
 */
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const generated = resolve(root, "assets", "generated");
const manifestPath = resolve(generated, "manifest.json");
// Web 与桌面各取自己的资源子目录，避免把仅单端使用的大图复制进另一端安装包。
const targets = [
  { source: resolve(generated, "web"), target: resolve(root, "web-app", "public", "illustrations", "generated") },
  { source: resolve(generated, "tauri"), target: resolve(root, "tauri-app", "public", "illustrations", "generated") },
];

await readFile(manifestPath, "utf8"); // 先验证清单可读；失败时不留下“图片已复制但清单缺失”的状态。
for (const { source, target } of targets) {
  await mkdir(target, { recursive: true });
  // force 只覆盖同名正式资产，不删除目标目录中的其他文件，保持同步操作可重复执行。
  await cp(source, target, { recursive: true, force: true });
}
// 双端分别复制同一份清单，运行时无需跨目录读取仓库级 assets。
await cp(manifestPath, resolve(root, "web-app", "public", "illustrations", "generated", "manifest.json"));
await cp(manifestPath, resolve(root, "tauri-app", "public", "illustrations", "generated", "manifest.json"));
console.log("已同步双端静态美术资源");
