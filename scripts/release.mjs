#!/usr/bin/env node
/* 一键发版：以 core/version.py 为唯一版本源，同步各端版本号并构建。
 * 用法：
 *   node scripts/release.mjs            # 只校验并同步版本
 *   node scripts/release.mjs --build    # 同步版本后构建双端前端
 * 版本流程：先改 core/version.py → 跑本脚本 → 再打包安装包（tauri:build）。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

// 从模块 URL 定位仓库根目录，保证脚本被 npm 或任意工作目录调用时都操作同一组版本文件。
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const versionPy = readFileSync(path.join(root, "core", "version.py"), "utf8");
// 只读取 VERSION 常量；VERSION_TUPLE 和构建日期仍由 Python 版本模块自身维护。
const match = /VERSION\s*=\s*"([^"]+)"/.exec(versionPy);
if (!match) {
  console.error("[错误] 无法从 core/version.py 读取 VERSION");
  process.exit(1);
}
const version = match[1];

// JSON 目标可安全解析后重写；锁文件由各自包管理器根据主清单更新，不手工替换字符串。
const jsonTargets = [
  "web-app/package.json",
  "tauri-app/package.json",
  "tauri-app/src-tauri/tauri.conf.json",
];
const cargoTomlPath = path.join(root, "tauri-app", "src-tauri", "Cargo.toml");
const cargoText = readFileSync(cargoTomlPath, "utf8");
const cargoVersion = /^version\s*=\s*"([^"]+)"/m.exec(cargoText)?.[1]; // 锚定行首，避免命中依赖版本。

const changed = [];
for (const relative of jsonTargets) {
  const file = path.join(root, relative);
  const json = JSON.parse(readFileSync(file, "utf8"));
  if (json.version !== version) {
    json.version = version;
    writeFileSync(file, JSON.stringify(json, null, 2) + "\n"); // 固定两空格与末尾换行，减少无关格式差异。
    changed.push(relative);
  }
}
if (cargoVersion !== version) {
  // 只替换 Cargo.toml 顶层首个版本声明，不触碰依赖表中的同名 version 字段。
  writeFileSync(
    cargoTomlPath,
    cargoText.replace(/^version\s*=\s*"[^"]+"/m, `version = "${version}"`),
  );
  changed.push("tauri-app/src-tauri/Cargo.toml");
}

console.log(`[版本源] core/version.py = ${version}`);
if (changed.length) {
  console.log(`[同步] 已更新：${changed.join("、")}`);
} else {
  console.log("[同步] 各端版本已一致，无需更新。");
}
console.log("[提示] Cargo.lock 会在下次 cargo/tauri 构建时自动跟随 Cargo.toml。");

if (process.argv.includes("--build")) {
  // 构建是可选的耗时步骤；默认模式只做快速版本同步，便于发布前单独审阅变更。
  for (const dir of ["web-app", "tauri-app"]) {
    console.log(`\n[构建] ${dir} ...`);
    const result = spawnSync("npm", ["run", "build"], {
      cwd: path.join(root, dir),
      stdio: "inherit",
      shell: true,
    });
    if (result.status !== 0) process.exit(result.status ?? 1); // 保留子构建退出码，便于 CI 准确判定失败。
  }
  console.log("\n[完成] 双端前端构建成功。打包安装包请运行：npm --prefix tauri-app run tauri:build");
}
