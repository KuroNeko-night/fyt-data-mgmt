import { existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

const chromePaths = [
  process.env.CHROME_PATH,
  join(process.env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
].filter(Boolean);
const chromePath = chromePaths.find((candidate) => existsSync(candidate));
if (!chromePath) throw new Error("未找到 Chrome，请通过 CHROME_PATH 指定 chrome.exe。");

const baseUrl = process.env.FYT_QA_URL || "http://127.0.0.1:1420";
const outputDir = process.env.FYT_QA_OUTPUT || join(tmpdir(), "fyt-tauri-functional-qa");
mkdirSync(outputDir, { recursive: true });

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

async function createMockPage(browser, { settingsDelay = 0 } = {}) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(({ delay }) => {
    const callbacks = new Map();
    let callbackId = 1;
    let eventId = 1;
    let pdfRuns = 0;
    const dialogSelections = {
      "选择A 表": [["C:\\mock\\A-old.xlsx"], ["C:\\mock\\A-new.xlsx"]],
      "选择B 表": [["C:\\mock\\B.xlsx"]],
      "选择待重命名文件": [["C:\\mock\\原文件.txt"]],
      "选择PDF 文件": [["C:\\mock\\one.pdf", "C:\\mock\\two.pdf"]],
    };
    const settings = {
      output_mode: "unified", custom_output_root: "", theme_mode: "light",
      reduce_motion: true, check_update_on_start: false, auto_open_output: false,
      show_done_dialog: false, minimize_to_tray: false, enable_incremental_cache: true,
    };
    const task = (result, outDir = "C:\\mock\\output") => ({
      result, logs: [], task_id: `mock-${Date.now()}`, out_dir: outDir,
    });
    const bridge = async (request) => {
      const { action, payload = {} } = request;
      if (action === "system.health") return { app_name: "峰运通数据管理系统", version: "1.3.0", python: "mock", platform: "win32", project_root: "C:\\mock", features: [] };
      if (action === "settings.get") {
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
        return settings;
      }
      if (action === "settings.update") return Object.assign(settings, payload.values || {});
      if (action === "library.summary") return { counts: { a: 2, b: 2 }, storage: { files: 3, bytes: 1024 }, titles: {}, items: [], library_dir: "C:\\mock\\library" };
      if (action === "system.sheets") {
        const path = String(payload.path || "");
        return { sheets: path.includes("A-old") || path.includes("B.xlsx") ? ["总览", "数据"] : ["新数据"] };
      }
      if (action === "compare.prepare") return { headers1: ["旧编号"], headers2: ["旧编号"], common: ["旧编号"] };
      if (action === "rename.preview") return { items: [{ old_path: payload.paths[0], old_name: "原文件.txt", new_name: "新_原文件.txt", status: "ok", note: "" }], summary: { ok: 1, blocked: 0, same: 0, total: 1 } };
      if (action === "pdf.info") return { pages: 2 };
      if (action === "pdf.run") {
        pdfRuns += 1;
        if (pdfRuns > 1) await new Promise((resolve) => setTimeout(resolve, 300));
        return task({ out_file: "C:\\mock\\output\\merged.pdf", out_files: ["C:\\mock\\output\\merged.pdf"], out_dir: "C:\\mock\\output" });
      }
      if (action === "cache.stats") return { entries: 0, hits: 0, bytes: 0 };
      if (action === "system.paths") return { app_data_dir: "C:\\mock", library_dir: "C:\\mock\\library", default_output_root: "C:\\mock\\output", crash_log: "C:\\mock\\crash.log", crash_log_exists: false };
      if (action === "tasks.list") return { summary: { total: 0, running: 0, ok: 0, failed: 0, interrupted: 0 }, items: [] };
      throw new Error(`未模拟桥接动作：${action}`);
    };

    window.__TAURI_INTERNALS__ = {
      metadata: { currentWindow: { label: "main" }, currentWebview: { label: "main" } },
      transformCallback(callback, once = false) {
        const id = callbackId++;
        callbacks.set(id, { callback, once });
        return id;
      },
      unregisterCallback(id) { callbacks.delete(id); },
      async invoke(command, args = {}) {
        if (command === "bridge_request") return bridge(args.request);
        if (command === "plugin:dialog|open") {
          const queue = dialogSelections[args.options?.title] || [];
          const next = queue.shift() || [];
          return args.options?.multiple ? next : next[0] || null;
        }
        if (command === "plugin:event|listen") return eventId++;
        if (command === "plugin:event|unlisten" || command === "set_minimize_to_tray" || command === "open_local_path") return null;
        if (command === "plugin:dialog|message") return null;
        throw new Error(`未模拟 Tauri 命令：${command}`);
      },
    };
    window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
    Object.keys(localStorage).forEach((key) => key.startsWith("fyt-page-guide-v1:") && localStorage.removeItem(key));
    ["home", "compare", "rename", "pdf", "settings"].forEach((key) => localStorage.setItem(`fyt-page-guide-v1:${key}`, "1"));
  }, { delay: settingsDelay });
  const errors = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(baseUrl, { waitUntil: settingsDelay ? "domcontentloaded" : "networkidle" });
  return { page, errors };
}

const browser = await chromium.launch({ executablePath: chromePath, headless: true });
try {
  const { page, errors } = await createMockPage(browser);
  const navigation = page.getByRole("navigation", { name: "主导航" });

  ensure(await page.locator(".hero-metric strong").innerText() === "3", "首页归档数不应重复累计多标签分类");

  await navigation.getByRole("button", { name: "表格比对", exact: true }).click();
  const comparePickers = page.locator(".file-picker-field");
  await comparePickers.nth(0).getByRole("button", { name: "选择文件" }).click();
  await comparePickers.nth(1).getByRole("button", { name: "选择文件" }).click();
  await page.locator(".field-row select").nth(0).selectOption("数据");
  await page.locator(".field-row select").nth(1).selectOption("数据");
  await page.getByRole("button", { name: "读取公共列" }).click();
  await page.getByText("按此列配对").waitFor();
  ensure(await page.getByRole("button", { name: "开始比对" }).isEnabled(), "读取公共列后应可开始比对");
  await comparePickers.nth(0).getByRole("button", { name: "选择文件" }).click();
  ensure(!await page.getByRole("button", { name: "开始比对" }).isEnabled(), "更换文件后不应沿用旧关键列");
  ensure(await page.getByText("按此列配对").count() === 0, "更换文件后旧公共列结果应清空");

  await navigation.getByRole("button", { name: "批量重命名", exact: true }).click();
  await page.locator(".file-picker-field").getByRole("button", { name: "选择文件" }).click();
  await page.getByLabel("前缀").fill("新_");
  await page.getByRole("button", { name: "刷新预览" }).click();
  await page.getByText("可重命名 1 个").waitFor();
  ensure(await page.getByRole("button", { name: "应用重命名" }).isEnabled(), "有效预览后应允许应用重命名");
  await page.getByLabel("前缀").fill("再次_");
  ensure(await page.getByText("可重命名 1 个").count() === 0, "规则变化后旧预览必须失效");
  ensure(!await page.getByRole("button", { name: "应用重命名" }).isEnabled(), "规则变化后必须重新预览");

  await navigation.getByRole("button", { name: "PDF 工具箱", exact: true }).click();
  await page.locator(".file-picker-field").getByRole("button", { name: "选择文件" }).click();
  await page.getByRole("button", { name: "开始处理" }).click();
  await page.getByText("已生成 1 个 PDF").waitFor();
  await page.getByRole("button", { name: "开始处理" }).click();
  ensure(await page.getByText("已生成 1 个 PDF").count() === 0, "重复运行开始时不应继续显示旧结果");
  await page.getByText("已生成 1 个 PDF").waitFor();

  ensure(errors.length === 0, `功能回归出现前端错误：${errors.join("；")}`);
  await page.screenshot({ path: join(outputDir, "functional-regression.png") });
  await page.close();

  const delayed = await createMockPage(browser, { settingsDelay: 1200 });
  await delayed.page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置", exact: true }).click();
  await delayed.page.getByText("正在读取设置…").waitFor();
  await delayed.page.getByRole("heading", { name: "外观", exact: true }).waitFor();
  ensure(delayed.errors.length === 0, `设置异步载入出现前端错误：${delayed.errors.join("；")}`);
  await delayed.page.screenshot({ path: join(outputDir, "settings-delayed-load.png") });
  await delayed.page.close();

  console.log(`[完成] Chrome 功能回归通过：${outputDir}`);
} finally {
  await browser.close();
}
