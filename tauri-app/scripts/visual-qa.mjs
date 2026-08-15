/*
 * Tauri 桌面前端视觉与可用性回归脚本。
 *
 * 脚本遍历全部正式导航页面，在多种视口下检查内容完整性、滚动边界、表单皮肤、
 * 主题令牌、响应式导航、减少动画和新手引导的焦点管理。截图写入临时目录供人工
 * 复核；断言只依赖可访问名称和稳定样式契约，不以像素截图差异代替功能判断。
 */
import { existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

// 优先接受显式 Chrome 路径，再兼容 Windows 常见的系统级和用户级安装位置。
const chromePaths = [
  process.env.CHROME_PATH,
  join(process.env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
].filter(Boolean);
const chromePath = chromePaths.find((candidate) => existsSync(candidate));
if (!chromePath) {
  throw new Error("未找到 Chrome，请通过 CHROME_PATH 指定 chrome.exe。");
}

const baseUrl = process.env.FYT_QA_URL || "http://127.0.0.1:1420"; // 页面服务由外层命令启动，本脚本只负责浏览器验收。
const outputDir = process.env.FYT_QA_OUTPUT || join(tmpdir(), "fyt-tauri-visual-qa"); // 避免把每次 QA 截图写入仓库。
mkdirSync(outputDir, { recursive: true });

// 每项依次保存页面引导键、导航按钮可访问名称和页面主标题，三者是独立契约。
const navigationPages = [
  ["home", "首页", "工作台"],
  ["attendance", "考勤数据填报", "考勤数据填报"],
  ["attendance_archive", "考勤月度归档", "考勤月度归档"],
  ["reconcile", "工时对账", "工时对账"],
  ["reconcile_statement", "对账单制作", "对账单制作"],
  ["arrival", "到料明细表", "到料明细表"],
  ["pivot", "销售表透视", "销售表透视"],
  ["purchase", "采购数对账", "采购数对账"],
  ["delivery", "送货计划表", "送货计划表"],
  ["supplier_batch", "供应商批次表", "供应商批次表"],
  ["purchase_plan", "采购计划导入", "采购计划导入"],
  ["library", "数据库", "数据库"],
  ["tasks", "任务中心", "任务中心"],
  ["mappings", "字段映射中心", "字段映射中心"],
  ["catalog", "主数据档案", "主数据档案"],
  ["batch_track", "批次跟踪", "批次跟踪"],
  ["report_center", "报表中心", "报表中心"],
  ["templates", "模板中心", "模板中心"],
  ["invoice", "增值税发票统计", "增值税发票统计"],
  ["currency", "金额大写", "金额大写"],
  ["rename", "批量重命名", "批量重命名"],
  ["text", "文本工具箱", "文本工具箱"],
  ["pdf", "PDF 工具箱", "PDF 工具箱"],
  ["excel", "Excel 工具箱", "Excel 工具箱"],
  ["compare", "表格比对", "表格比对"],
  ["settings", "设置", "设置"],
  ["about", "关于", "关于"],
];

/** 失败时立即抛出带页面名称的诊断信息，避免继续生成无意义截图。 */
function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

/**
 * 在指定视口创建隔离页面，执行公共健康检查和调用方提供的页面场景。
 *
 * @param {import("playwright").Browser} browser 已经启动的无头 Chrome 浏览器实例。
 * @param {{ width: number, height: number }} viewport 本用例的视口尺寸。
 * @param {string} name 页面场景名，同时用于错误消息和截图文件名。
 * @param {(page: import("playwright").Page) => Promise<void>} exercise 该视口特有的操作。
 * @returns {Promise<string>} 当前页面截图的完整路径。
 *
 * exercise 只描述该视口特有的操作；地址、标题、占位文本、横向溢出、控制台错误
 * 和截图清理由此函数统一处理，保证所有视觉用例采用相同验收口径。
 */
async function openPage(browser, viewport, name, exercise) {
  const page = await browser.newPage({ viewport });
  await page.addInitScript((keys) => {
    localStorage.setItem("fyt-desktop-mode", "local"); // 强制使用桌面本机模式，不依赖 Web 会话。
    localStorage.setItem("fyt-guide-seen-v2", "1");
    // 常规页面巡检跳过新手引导；引导交互在后面的独立页面中专门验证。
    keys.forEach((key) => localStorage.setItem(`fyt-page-guide-v1:${key}`, "1"));
  }, navigationPages.map(([key]) => key));
  const errors = [];
  // 浏览器警告通常意味着资源、React 键或样式兼容问题，因此与错误一起纳入失败条件。
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) errors.push(`控制台：${message.text()}（${message.location().url || "未知资源"}）`);
  });
  page.on("pageerror", (error) => errors.push(`页面：${error.message}`));
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  ensure(new URL(page.url()).origin === new URL(baseUrl).origin, `${name} 页面地址不正确`);
  ensure((await page.title()).includes("峰运通"), `${name} 页面标题不正确`);
  await page.getByRole("heading", { name: "工作台" }).waitFor();
  ensure(await page.locator(".fyt-tauri-notice").count() === 0, `${name} 出现全局错误提示`);
  ensure(await page.getByText(/适配进行中|Internal Server Error|Vite Error/).count() === 0, `${name} 出现占位页或框架错误覆盖层`);
  await exercise(page); // 先执行场景操作，再检查操作后的最终布局和运行错误。
  await page.waitForTimeout(350);
  // 允许一个像素的浏览器取整差，超过后说明页面确实产生了横向滚动。
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ensure(overflow <= 1, `${name} 存在 ${overflow}px 水平溢出`);
  ensure(errors.length === 0, `${name} 出现前端错误：${errors.join("；")}`);
  const screenshot = join(outputDir, `${name}.png`);
  await page.screenshot({ path: screenshot });
  await page.close(); // 每个视口独立关闭，防止 localStorage 和媒体模拟互相污染。
  return screenshot;
}

// 所有视觉场景共用同一个浏览器实例，结束时由 finally 统一回收。
const browser = await chromium.launch({ executablePath: chromePath, headless: true });
try {
  // 汇总全部截图路径，既供最后输出，也便于后续人工按需查看。
  const screenshots = [];
  // 首页先做轻量独立检查，确保常用业务入口在导航全量遍历前已经渲染。
  screenshots.push(await openPage(browser, { width: 1440, height: 900 }, "home-light-1440", async (page) => {
    await page.getByRole("heading", { name: "今天先处理什么" }).waitFor();
    ensure(await page.locator(".fyt-tauri-home-action").count() >= 6, "首页常用业务未完整渲染");
  }));
  screenshots.push(await openPage(browser, { width: 1440, height: 900 }, "desktop-1440", async (page) => {
    const navigation = page.getByRole("navigation", { name: "主导航" });
    // 逐页访问全部正式入口，同时验证内容、视口边界和内部滚动容器的职责分离。
    for (const [key, label, heading] of navigationPages) {
      await navigation.getByRole("button", { name: label, exact: true }).click();
      await page.getByRole("heading", { name: heading, exact: true }).first().waitFor();
      await page.waitForTimeout(320);
      const text = (await page.locator(".fyt-tauri-content-column").innerText()).trim();
      ensure(text.length >= 20, `${label} 页面内容为空`);
      ensure(!text.includes("适配进行中"), `${label} 仍是迁移占位页`);
      const layout = await page.evaluate(() => {
        const root = document.querySelector("#root");
        const shell = document.querySelector(".fyt-tauri-shell");
        const stage = document.querySelector(".fyt-tauri-main-stage");
        const content = document.querySelector(".fyt-tauri-content-scroll");
        return { // 同时采集根容器和内容容器，便于区分“页面撑破视口”和“内容区正常滚动”。
          rootClient: root?.clientHeight || 0,
          rootScroll: root?.scrollHeight || 0,
          shellClient: shell?.clientHeight || 0,
          stageClient: stage?.clientHeight || 0,
          contentClient: content?.clientHeight || 0,
          contentScroll: content?.scrollHeight || 0,
          contentOverflowY: content ? getComputedStyle(content).overflowY : "",
          contentScrollbarColor: content ? getComputedStyle(content).scrollbarColor : "",
        };
      });
      ensure(layout.rootScroll <= layout.rootClient + 1, `${label} 把根容器撑出视口，页面会被截断`);
      ensure(layout.stageClient <= layout.shellClient + 1, `${label} 主舞台高度超过应用视口`);
      ensure(["auto", "scroll"].includes(layout.contentOverflowY), `${label} 未启用内容区滚动能力`);
      ensure(layout.contentScrollbarColor && layout.contentScrollbarColor !== "auto", `${label} 内容区仍使用默认滚动条配色`);
      const shouldScroll = layout.contentScroll > layout.contentClient + 1;
      if (shouldScroll) {
        const moved = await page.locator(".fyt-tauri-content-scroll").evaluate((element) => {
          const previousBehavior = element.style.scrollBehavior;
          element.style.scrollBehavior = "auto"; // 测量期间关闭平滑滚动，立即读取真实 scrollTop。
          element.scrollTop = element.scrollHeight;
          const value = element.scrollTop;
          element.scrollTop = 0;
          element.style.scrollBehavior = previousBehavior;
          return value;
        });
        ensure(moved > 0, `${label} 内容超出后仍无法滚动`);
      }
      if (label === "考勤数据填报") {
        // 复选框、参数卡和拖放反馈是共用表单皮肤的代表性抽样，不必在每页重复检查。
        const skin = await page.evaluate(() => {
          const checkbox = document.querySelector('input[type="checkbox"]');
          const card = document.querySelector(".fyt-option-card");
          const checkboxStyle = checkbox ? getComputedStyle(checkbox) : null;
          const cardStyle = card ? getComputedStyle(card) : null;
          return {
            checkboxAppearance: checkboxStyle?.appearance || "",
            checkboxBackground: checkboxStyle?.backgroundImage || "",
            checkboxWidth: checkboxStyle?.width || "",
            cardBackground: cardStyle?.backgroundColor || "",
            cardBackdrop: cardStyle?.backdropFilter || "",
          };
        });
        ensure(skin.checkboxAppearance === "none" && skin.checkboxWidth === "18px", "考勤复选框仍使用原生尺寸或外观");
        ensure(skin.checkboxBackground.includes("svg"), "考勤复选框未使用统一勾选图形");
        ensure(skin.cardBackground && skin.cardBackground !== "rgba(0, 0, 0, 0)", "业务参数卡未应用表面颜色");
        const filePicker = page.locator(".fyt-file-picker").first();
        await filePicker.dispatchEvent("dragenter");
        ensure(await filePicker.evaluate((element) => element.classList.contains("is-drag-active")), "文件拖放区未进入吸附状态");
        ensure((await filePicker.evaluate((element) => getComputedStyle(element).boxShadow)) !== "none", "文件拖放区缺少吸附反馈");
        const dragScreenshot = join(outputDir, "drag-active-1440.png");
        await page.screenshot({ path: dragScreenshot });
        screenshots.push(dragScreenshot);
        await filePicker.dispatchEvent("dragleave");
        ensure(!await filePicker.evaluate((element) => element.classList.contains("is-drag-active")), "文件拖放区离开后未恢复");
      }
      if (label === "PDF 工具箱") {
        // PDF 拆分下拉框覆盖自定义箭头及选项驱动附加输入框两类交互。
        await page.getByRole("button", { name: "拆分", exact: true }).click();
        const select = page.locator(".fyt-option-card select");
        const selectSkin = await select.evaluate((element) => {
          const style = getComputedStyle(element);
          return { appearance: style.appearance, backgroundImage: style.backgroundImage, paddingRight: style.paddingRight };
        });
        ensure(selectSkin.appearance === "none" && selectSkin.backgroundImage.includes("svg"), "PDF 下拉框仍使用浏览器默认箭头");
        ensure(selectSkin.paddingRight === "34px", "PDF 下拉框未给自定义箭头保留空间");
        await select.selectOption("ranges");
        ensure(await page.locator(".fyt-option-card input").count() === 1, "PDF 拆分方式切换后未显示页码范围输入框");
        const selectScreenshot = join(outputDir, "form-controls-1440.png");
        await page.screenshot({ path: selectScreenshot });
        screenshots.push(selectScreenshot);
      }
    }
    // 主题切换既要改变状态属性，也要真正替换语义颜色令牌。
    const themeBefore = await page.locator(".fyt-tauri-shell").getAttribute("data-theme");
    const canvasBefore = await page.locator(".fyt-tauri-shell").evaluate((element) => getComputedStyle(element).getPropertyValue("--fyt-canvas"));
    await page.getByRole("button", { name: /切换.*主题/ }).click();
    await page.waitForFunction((previous) => document.querySelector(".fyt-tauri-shell")?.getAttribute("data-theme") !== previous, themeBefore);
    ensure(await page.locator(".fyt-tauri-shell").evaluate((element, previous) => getComputedStyle(element).getPropertyValue("--fyt-canvas") !== previous, canvasBefore), "主题切换后语义画布令牌未变化");
    const themeScreenshot = join(outputDir, "theme-toggled-1440.png");
    await page.screenshot({ path: themeScreenshot });
    screenshots.push(themeScreenshot);
    // 桌面布局同时覆盖侧栏收起与右侧快捷面板关闭，防止状态属性和视觉面板脱节。
    await page.getByRole("button", { name: "收起导航" }).click();
    await page.locator('.fyt-tauri-shell[data-nav-collapsed="true"]').waitFor();
    await page.getByRole("main").getByRole("button", { name: "关闭快捷工作台" }).click();
    ensure(await page.locator('.fyt-tauri-shell[data-panel-open="false"]').count() === 1, "桌面状态面板未关闭");
  }));
  screenshots.push(await openPage(browser, { width: 1280, height: 640 }, "scroll-pages-1280x640", async (page) => {
    const navigation = page.getByRole("navigation", { name: "主导航" });
    // 矮视口容易暴露底部操作区不可达的问题，选择表单页和设置页作为代表。
    for (const [label, heading] of [["考勤数据填报", "考勤数据填报"], ["设置", "设置"]]) {
      await navigation.getByRole("button", { name: label, exact: true }).click();
      await page.getByRole("heading", { name: heading, exact: true }).first().waitFor();
      const moved = await page.locator(".fyt-tauri-content-scroll").evaluate((element) => {
        const previousBehavior = element.style.scrollBehavior;
        element.style.scrollBehavior = "auto";
        element.scrollTop = element.scrollHeight;
        const value = element.scrollTop;
        element.style.scrollBehavior = previousBehavior;
        return value;
      });
      ensure(moved > 0, `${label} 在较矮视口下仍无法滚动到底部`);
      await page.locator(".fyt-tauri-content-scroll").evaluate((element) => { element.scrollTop = 0; });
    }
  }));
  screenshots.push(await openPage(browser, { width: 920, height: 820 }, "compact-920", async (page) => {
    // 紧凑布局通过顶部按钮展开导航，再验证目标页面可以正常切换。
    await page.locator(".fyt-tauri-context-header > button").click();
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "任务中心" }).click();
    await page.getByRole("heading", { name: "任务中心" }).waitFor();
  }));
  screenshots.push(await openPage(browser, { width: 640, height: 760 }, "compact-640", async (page) => {
    await page.locator(".fyt-tauri-context-header > button").click();
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "金额大写" }).click();
    await page.getByRole("heading", { name: "金额大写" }).waitFor();
    await page.locator("#amount").fill("12345.67");
  }));
  screenshots.push(await openPage(browser, { width: 920, height: 820 }, "reduced-motion-920", async (page) => {
    // 先验证操作系统媒体偏好，再验证应用内设置；两条路径都应移除明显位移动画。
    await page.emulateMedia({ reducedMotion: "reduce" });
    ensure(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches), "系统减少动画媒体查询未生效");
    const systemDuration = await page.locator(".fyt-tauri-shell").evaluate((element) => parseFloat(getComputedStyle(element).transitionDuration) || 0);
    ensure(systemDuration <= 0.01, "系统减少动画仍保留长动画");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.locator(".fyt-tauri-context-header > button").click();
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置" }).click();
    await page.getByRole("heading", { name: "设置" }).waitFor();
    await page.getByRole("button", { name: /减少动画/ }).click();
    await page.getByRole("button", { name: "保存设置" }).click();
    await page.locator('.fyt-tauri-shell[data-reduce-motion="true"]').waitFor();
    const reducedTransition = await page.locator(".fyt-tauri-context-panel").evaluate((element) => getComputedStyle(element).transitionProperty);
    ensure(!reducedTransition.includes("transform"), "应用减少动画仍保留抽屉位移过渡");
  }));
  // 新手引导必须在没有“已读”标记的新页面中测试，否则常规巡检状态会将其跳过。
  const tourPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await tourPage.addInitScript(() => localStorage.setItem("fyt-desktop-mode", "local"));
  const tourErrors = [];
  tourPage.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) tourErrors.push(message.text());
  });
  tourPage.on("pageerror", (error) => tourErrors.push(error.message));
  await tourPage.goto(baseUrl, { waitUntil: "networkidle" });
  const tourDialog = tourPage.getByRole("dialog", { name: "认识首页" });
  await tourDialog.waitFor();
  ensure(await tourPage.locator(".fyt-tour-focus-ring").count() === 1, "首页引导未显示聚光灯");
  ensure(await tourDialog.getByRole("button", { name: "结束本页引导" }).evaluate((button) => document.activeElement === button), "首页引导未把焦点移入弹层");
  await tourPage.keyboard.press("Shift+Tab");
  // 从首个按钮反向制表应回到末尾按钮，证明焦点被约束在模态引导内部。
  ensure(await tourDialog.getByRole("button", { name: "下一步" }).evaluate((button) => document.activeElement === button), "首页引导焦点未在弹层内循环");
  const tourScreenshot = join(outputDir, "page-guide-home.png");
  await tourPage.screenshot({ path: tourScreenshot });
  screenshots.push(tourScreenshot);
  await tourDialog.getByRole("button", { name: "结束本页引导" }).click();
  await tourPage.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "考勤数据填报", exact: true }).click();
  const attendanceGuide = tourPage.getByRole("dialog", { name: "认识考勤数据填报" });
  await attendanceGuide.waitFor();
  await attendanceGuide.getByRole("button", { name: "下一步" }).click();
  const fileStep = tourPage.getByRole("dialog", { name: "放置：系统数据（打卡来源）" });
  await fileStep.waitFor();
  await tourPage.getByRole("heading", { name: "考勤数据填报" }).waitFor();
  ensure((await tourPage.locator(".fyt-tour-count").innerText()).startsWith("02 /"), "考勤引导步骤进度未更新");
  await tourPage.waitForFunction(() => {
    const target = document.querySelector('[data-tour="file-input"]')?.getBoundingClientRect();
    const ring = document.querySelector(".fyt-tour-focus-ring")?.getBoundingClientRect();
    if (!target || !ring) return false;
    // 聚光框应比目标四周各扩展八像素，允许两像素渲染取整差。
    return Math.abs(ring.left - (target.left - 8)) <= 2
      && Math.abs(ring.top - (target.top - 8)) <= 2
      && Math.abs(ring.width - (target.width + 16)) <= 2
      && Math.abs(ring.height - (target.height + 16)) <= 2;
  });
  const fileStepScreenshot = join(outputDir, "page-guide-attendance-file.png");
  await tourPage.screenshot({ path: fileStepScreenshot });
  screenshots.push(fileStepScreenshot);
  await fileStep.getByRole("button", { name: "结束本页引导" }).click();
  ensure(await tourPage.locator(".fyt-tour").count() === 0, "考勤引导结束后未关闭");
  await tourPage.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "PDF 工具箱", exact: true }).click();
  await tourPage.getByRole("dialog", { name: "认识PDF 工具箱" }).waitFor();
  const pdfGuideScreenshot = join(outputDir, "page-guide-pdf.png");
  await tourPage.screenshot({ path: pdfGuideScreenshot });
  screenshots.push(pdfGuideScreenshot);
  await tourPage.keyboard.press("Escape");
  ensure(await tourPage.locator(".fyt-tour").count() === 0, "PDF 引导未响应 Escape");
  await tourPage.getByRole("button", { name: "查看当前页面使用引导" }).click();
  await tourPage.getByRole("dialog", { name: "认识PDF 工具箱" }).waitFor();
  await tourPage.keyboard.press("Escape");
  ensure(tourErrors.length === 0, `页面引导出现前端错误：${tourErrors.join("；")}`);
  await tourPage.close();
  console.log(`[完成] Chrome 视觉回归通过：${screenshots.join("；")}`);
} finally {
  // 无论断言还是截图失败都回收浏览器进程，避免影响下一轮桌面构建。
  await browser.close();
}
