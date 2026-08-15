/*
 * Tauri 桌面前端功能回归脚本。
 *
 * 本脚本连接已经启动的 Vite 页面，并在浏览器初始化阶段注入最小 Tauri 运行时，
 * 用确定性的文件选择、桥接响应和设置数据验证前端状态机。这里不验证 Python
 * 业务算法本身，重点防止换文件后沿用旧分析结果、重复执行时残留旧输出，以及
 * 设置异步载入期间页面访问空状态等桌面交互回归。
 */
import { existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

// Windows 安装位置并不统一，环境变量优先，随后检查系统级和用户级常见目录。
const chromePaths = [
  process.env.CHROME_PATH,
  join(process.env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
].filter(Boolean);
const chromePath = chromePaths.find((candidate) => existsSync(candidate));
if (!chromePath) throw new Error("未找到 Chrome，请通过 CHROME_PATH 指定 chrome.exe。");

const baseUrl = process.env.FYT_QA_URL || "http://127.0.0.1:1420"; // 允许 CI 或本地脚本复用已经启动的开发服务。
const outputDir = process.env.FYT_QA_OUTPUT || join(tmpdir(), "fyt-tauri-functional-qa"); // 默认写临时目录，避免把截图混入源码。
mkdirSync(outputDir, { recursive: true });

/** 在首个不满足的业务断言处立即终止，保留最贴近根因的错误信息。 */
function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

/**
 * 创建带有模拟 Tauri 桥接的独立页面。
 *
 * @param {import("playwright").Browser} browser 已经启动的无头 Chrome 浏览器实例。
 * @param {{ settingsDelay?: number }} [options] 可选配置；settingsDelay 专门模拟桌面
 *   设置读取较慢的情况，大于 0 时页面会在设置返回前先渲染出来。
 * @returns {Promise<{ page: import("playwright").Page, errors: string[] }>}
 *   返回隔离页面与运行期间收集到的控制台错误列表。
 *
 * 每次调用均创建新页面和新模拟状态，防止前一个用例的 localStorage、文件选择队列
 * 或任务执行次数污染后续断言。
 */
async function createMockPage(browser, { settingsDelay = 0 } = {}) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(({ delay }) => {
    // Tauri 前端会持有回调编号；模拟层只需保存注册关系，不主动触发原生事件。
    const callbacks = new Map();
    let callbackId = 1;
    let eventId = 1;
    let pdfRuns = 0;
    // 同一标题对应一个先进先出队列，用于验证再次选文件后旧分析状态必须作废。
    const dialogSelections = {
      "选择A 表": [["C:\\mock\\A-old.xlsx"], ["C:\\mock\\A-new.xlsx"]],
      "选择B 表": [["C:\\mock\\B.xlsx"]],
      "选择待重命名文件": [["C:\\mock\\原文件.txt"]],
      "选择PDF 文件": [["C:\\mock\\one.pdf", "C:\\mock\\two.pdf"]],
    };
    // 使用可变对象模拟持久设置，使 settings.update 后的再次读取能看到更新结果。
    const settings = {
      output_mode: "unified", custom_output_root: "", theme_mode: "light",
      reduce_motion: true, check_update_on_start: false, auto_open_output: false,
      show_done_dialog: false, minimize_to_tray: false, enable_incremental_cache: true,
    };
    // 统一构造与真实桥接形状一致的已完成任务，测试只关心前端消费协议。
    const task = (result, outDir = "C:\\mock\\output") => ({
      result, logs: [], task_id: `mock-${Date.now()}`, out_dir: outDir,
    });
    // 桥接动作按真实白名单逐一返回合成结果；未声明的动作抛错，保证测试与桥接同步演进。
    const bridge = async (request) => {
      const { action, payload = {} } = request;
      if (action === "system.health") return { app_name: "峰运通数据管理系统", version: "1.3.0", python: "mock", platform: "win32", project_root: "C:\\mock", features: [] };
      if (action === "settings.get") {
        // 延迟发生在设置数据返回前，用来覆盖页面先渲染、数据后抵达的真实启动时序。
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
        return settings;
      }
      if (action === "settings.update") return Object.assign(settings, payload.values || {});
      if (action === "library.summary") return { counts: { a: 2, b: 2 }, storage: { files: 3, bytes: 1024 }, titles: {}, items: [], library_dir: "C:\\mock\\library" };
      if (action === "system.sheets") {
        const path = String(payload.path || "");
        // 新旧 A 表返回不同工作表，确保换文件后不能误用上一份文件的选项。
        return { sheets: path.includes("A-old") || path.includes("B.xlsx") ? ["总览", "数据"] : ["新数据"] };
      }
      if (action === "compare.prepare") return { headers1: ["旧编号"], headers2: ["旧编号"], common: ["旧编号"] };
      if (action === "rename.preview") return { items: [{ old_path: payload.paths[0], old_name: "原文件.txt", new_name: "新_原文件.txt", status: "ok", note: "" }], summary: { ok: 1, blocked: 0, same: 0, total: 1 } };
      if (action === "pdf.info") return { pages: 2 };
      if (action === "pdf.run") {
        pdfRuns += 1;
        // 第二次运行故意放慢，以便断言任务开始时旧成功结果已经被清空。
        if (pdfRuns > 1) await new Promise((resolve) => setTimeout(resolve, 300));
        return task({ out_file: "C:\\mock\\output\\merged.pdf", out_files: ["C:\\mock\\output\\merged.pdf"], out_dir: "C:\\mock\\output" });
      }
      if (action === "cache.stats") return { entries: 0, hits: 0, bytes: 0 };
      if (action === "system.paths") return { app_data_dir: "C:\\mock", library_dir: "C:\\mock\\library", default_output_root: "C:\\mock\\output", crash_log: "C:\\mock\\crash.log", crash_log_exists: false };
      if (action === "tasks.list") return { summary: { total: 0, running: 0, ok: 0, failed: 0, interrupted: 0 }, items: [] };
      throw new Error(`未模拟桥接动作：${action}`);
    };

    // 仅实现当前页面实际调用的 Tauri 命令；出现新命令时主动报错，避免测试静默失真。
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
          const next = queue.shift() || []; // 每次弹窗消费一组选择结果，模拟用户重新选取文件。
          return args.options?.multiple ? next : next[0] || null;
        }
        if (command === "plugin:event|listen") return eventId++;
        if (command === "plugin:event|unlisten" || command === "set_minimize_to_tray" || command === "open_local_path") return null;
        if (command === "plugin:dialog|message") return null;
        throw new Error(`未模拟 Tauri 命令：${command}`);
      },
    };
    // 当前页面不消费 Tauri 事件插件，提供空实现以满足运行时初始化要求。
    window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
    localStorage.setItem("fyt-desktop-mode", "local"); // 明确进入本机桌面模式，避免误走 Web 登录协议。
    Object.keys(localStorage).forEach((key) => key.startsWith("fyt-page-guide-v1:") && localStorage.removeItem(key));
    // 当前回归不测试新手引导，预先标记已读，避免引导浮层遮挡业务控件。
    ["home", "compare", "rename", "pdf", "settings"].forEach((key) => localStorage.setItem(`fyt-page-guide-v1:${key}`, "1"));
  }, { delay: settingsDelay });
  const errors = [];
  // 警告也视为回归，防止 React 警告或资源异常长期隐藏在自动化成功结果中。
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  // 延迟设置用例不能等待 networkidle，否则会错过“设置仍在载入”的中间界面。
  await page.goto(baseUrl, { waitUntil: settingsDelay ? "domcontentloaded" : "networkidle" });
  return { page, errors };
}

// 全部功能用例共用一个浏览器实例，结束时由 finally 统一关闭。
const browser = await chromium.launch({ executablePath: chromePath, headless: true });
try {
  const { page, errors } = await createMockPage(browser);
  const navigation = page.getByRole("navigation", { name: "主导航" });

  // 首页归档数按唯一文件计数，文件同时命中多个分类时不得被重复累计。
  ensure(await page.locator(".fyt-tauri-home-metric strong").first().innerText() === "3", "首页归档数不应重复累计多标签分类");

  // 表格比对采用“文件 -> 工作表 -> 公共列”的依赖链，上游变化必须清除下游派生状态。
  await navigation.getByRole("button", { name: "表格比对", exact: true }).click();
  const comparePickers = page.locator(".fyt-file-picker");
  await comparePickers.nth(0).getByRole("button", { name: "选择文件" }).click();
  await comparePickers.nth(1).getByRole("button", { name: "选择文件" }).click();
  await page.locator(".fyt-field-row select").nth(0).selectOption("数据");
  await page.locator(".fyt-field-row select").nth(1).selectOption("数据");
  await page.getByRole("button", { name: "读取公共列" }).click();
  await page.getByText("按此列配对").waitFor();
  ensure(await page.getByRole("button", { name: "开始比对" }).isEnabled(), "读取公共列后应可开始比对");
  await comparePickers.nth(0).getByRole("button", { name: "选择文件" }).click(); // 队列第二项切换为 A-new.xlsx。
  ensure(!await page.getByRole("button", { name: "开始比对" }).isEnabled(), "更换文件后不应沿用旧关键列");
  ensure(await page.getByText("按此列配对").count() === 0, "更换文件后旧公共列结果应清空");

  // 重命名预览是规则快照；前缀变化后必须重新生成，不能直接应用陈旧计划。
  await navigation.getByRole("button", { name: "批量重命名", exact: true }).click();
  await page.locator(".fyt-file-picker").getByRole("button", { name: "选择文件" }).click();
  await page.getByLabel("前缀").fill("新_");
  await page.getByRole("button", { name: "刷新预览" }).click();
  await page.getByText("可重命名 1 个").waitFor();
  ensure(await page.getByRole("button", { name: "应用重命名" }).isEnabled(), "有效预览后应允许应用重命名");
  await page.getByLabel("前缀").fill("再次_");
  ensure(await page.getByText("可重命名 1 个").count() === 0, "规则变化后旧预览必须失效");
  ensure(!await page.getByRole("button", { name: "应用重命名" }).isEnabled(), "规则变化后必须重新预览");

  // 重复执行 PDF 时先撤下旧结果，再展示本轮完成结果，避免用户误判任务已经完成。
  await navigation.getByRole("button", { name: "PDF 工具箱", exact: true }).click();
  await page.locator(".fyt-file-picker").getByRole("button", { name: "选择文件" }).click();
  await page.getByRole("button", { name: "开始处理" }).click();
  await page.getByText("已生成 1 个 PDF").waitFor();
  await page.getByRole("button", { name: "开始处理" }).click();
  ensure(await page.getByText("已生成 1 个 PDF").count() === 0, "重复运行开始时不应继续显示旧结果");
  await page.getByText("已生成 1 个 PDF").waitFor();

  ensure(errors.length === 0, `功能回归出现前端错误：${errors.join("；")}`);
  await page.screenshot({ path: join(outputDir, "functional-regression.png") });
  await page.close();

  // 单独页面覆盖冷启动时设置读取尚未完成、用户已经进入设置页的竞争条件。
  const delayed = await createMockPage(browser, { settingsDelay: 1200 });
  await delayed.page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置", exact: true }).click();
  await delayed.page.getByText("正在读取设置…").waitFor();
  await delayed.page.getByRole("heading", { name: "外观", exact: true }).waitFor();
  ensure(delayed.errors.length === 0, `设置异步载入出现前端错误：${delayed.errors.join("；")}`);
  await delayed.page.screenshot({ path: join(outputDir, "settings-delayed-load.png") });
  await delayed.page.close();

  console.log(`[完成] Chrome 功能回归通过：${outputDir}`);
} finally {
  // 即使任一断言失败也关闭浏览器，防止本地或 CI 残留无头 Chrome 进程。
  await browser.close();
}
