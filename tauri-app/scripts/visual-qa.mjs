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
if (!chromePath) {
  throw new Error("未找到 Chrome，请通过 CHROME_PATH 指定 chrome.exe。");
}

const baseUrl = process.env.FYT_QA_URL || "http://127.0.0.1:1420";
const outputDir = process.env.FYT_QA_OUTPUT || join(tmpdir(), "fyt-tauri-visual-qa");
mkdirSync(outputDir, { recursive: true });

const navigationPages = [
  ["home", "首页", "欢迎使用"],
  ["attendance", "考勤数据填报", "考勤数据填报"],
  ["reconcile", "工时对账", "工时对账"],
  ["arrival", "到料明细表", "到料明细表"],
  ["pivot", "销售表透视", "销售表透视"],
  ["purchase", "采购数对账", "采购数对账"],
  ["delivery", "送货计划表", "送货计划表"],
  ["library", "数据库", "数据库"],
  ["tasks", "任务中心", "任务中心"],
  ["mappings", "字段映射中心", "字段映射中心"],
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

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

async function openPage(browser, viewport, name, exercise) {
  const page = await browser.newPage({ viewport });
  await page.addInitScript((keys) => {
    localStorage.setItem("fyt-guide-seen-v2", "1");
    keys.forEach((key) => localStorage.setItem(`fyt-page-guide-v1:${key}`, "1"));
  }, navigationPages.map(([key]) => key));
  const errors = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) errors.push(`控制台：${message.text()}（${message.location().url || "未知资源"}）`);
  });
  page.on("pageerror", (error) => errors.push(`页面：${error.message}`));
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  ensure(new URL(page.url()).origin === new URL(baseUrl).origin, `${name} 页面地址不正确`);
  ensure((await page.title()).includes("峰运通"), `${name} 页面标题不正确`);
  await page.getByRole("heading", { name: "欢迎使用" }).waitFor();
  ensure(await page.locator(".global-notice").count() === 0, `${name} 出现全局错误提示`);
  ensure(await page.getByText(/适配进行中|Internal Server Error|Vite Error/).count() === 0, `${name} 出现占位页或框架错误覆盖层`);
  await exercise(page);
  await page.waitForTimeout(350);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ensure(overflow <= 1, `${name} 存在 ${overflow}px 水平溢出`);
  ensure(errors.length === 0, `${name} 出现前端错误：${errors.join("；")}`);
  const screenshot = join(outputDir, `${name}.png`);
  await page.screenshot({ path: screenshot });
  await page.close();
  return screenshot;
}

const browser = await chromium.launch({ executablePath: chromePath, headless: true });
try {
  const screenshots = [];
  screenshots.push(await openPage(browser, { width: 1440, height: 900 }, "home-light-1440", async (page) => {
    await page.getByRole("heading", { name: "峰运通数据管理系统" }).waitFor();
    ensure(await page.locator(".shortcut-card").count() >= 6, "首页快捷工作流未完整渲染");
  }));
  screenshots.push(await openPage(browser, { width: 1440, height: 900 }, "desktop-1440", async (page) => {
    const navigation = page.getByRole("navigation", { name: "主导航" });
    for (const [key, label, heading] of navigationPages) {
      await navigation.getByRole("button", { name: label, exact: true }).click();
      await page.getByRole("heading", { name: heading, exact: true }).first().waitFor();
      await page.waitForTimeout(320);
      const text = (await page.locator(".content-column").innerText()).trim();
      ensure(text.length >= 20, `${label} 页面内容为空`);
      ensure(!text.includes("适配进行中"), `${label} 仍是迁移占位页`);
      const layout = await page.evaluate(() => {
        const root = document.querySelector("#root");
        const shell = document.querySelector(".app-shell");
        const stage = document.querySelector(".main-stage");
        const content = document.querySelector(".content-scroll");
        return {
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
        const moved = await page.locator(".content-scroll").evaluate((element) => {
          const previousBehavior = element.style.scrollBehavior;
          element.style.scrollBehavior = "auto";
          element.scrollTop = element.scrollHeight;
          const value = element.scrollTop;
          element.scrollTop = 0;
          element.style.scrollBehavior = previousBehavior;
          return value;
        });
        ensure(moved > 0, `${label} 内容超出后仍无法滚动`);
      }
      if (label === "考勤数据填报") {
        const skin = await page.evaluate(() => {
          const checkbox = document.querySelector('input[type="checkbox"]');
          const card = document.querySelector(".option-card");
          const stage = document.querySelector(".main-stage");
          const checkboxStyle = checkbox ? getComputedStyle(checkbox) : null;
          const cardStyle = card ? getComputedStyle(card) : null;
          const ambientStyle = stage ? getComputedStyle(stage, "::before") : null;
          return {
            checkboxAppearance: checkboxStyle?.appearance || "",
            checkboxBackground: checkboxStyle?.backgroundImage || "",
            checkboxWidth: checkboxStyle?.width || "",
            cardBackground: cardStyle?.backgroundColor || "",
            cardBackdrop: cardStyle?.backdropFilter || "",
            ambientAnimation: ambientStyle?.animationName || "",
            ambientDuration: ambientStyle?.animationDuration || "",
            ambientWillChange: ambientStyle?.willChange || "",
          };
        });
        ensure(skin.checkboxAppearance === "none" && skin.checkboxWidth === "18px", "考勤复选框仍使用原生尺寸或外观");
        ensure(skin.checkboxBackground.includes("svg"), "考勤复选框未使用统一勾选图形");
        ensure(skin.cardBackground.includes("rgba") && skin.cardBackdrop.includes("blur"), "业务参数卡未应用毛玻璃表面");
        ensure(skin.ambientAnimation === "ambient-light-drift" && skin.ambientDuration === "20s", "动态环境光未按低频节奏运行");
        ensure(skin.ambientWillChange.includes("transform") && skin.ambientWillChange.includes("opacity"), "动态环境光未限制在合成层属性");
        const filePicker = page.locator(".file-picker-field").first();
        await filePicker.dispatchEvent("dragenter");
        ensure(await filePicker.evaluate((element) => element.classList.contains("drag-active")), "文件拖放区未进入吸附状态");
        ensure((await filePicker.evaluate((element) => getComputedStyle(element).transform)) !== "none", "文件拖放区缺少抬升反馈");
        const dragScreenshot = join(outputDir, "drag-active-1440.png");
        await page.screenshot({ path: dragScreenshot });
        screenshots.push(dragScreenshot);
        await filePicker.dispatchEvent("dragleave");
        ensure(!await filePicker.evaluate((element) => element.classList.contains("drag-active")), "文件拖放区离开后未恢复");
      }
      if (label === "PDF 工具箱") {
        await page.getByRole("button", { name: "拆分", exact: true }).click();
        const select = page.locator(".option-card select");
        const selectSkin = await select.evaluate((element) => {
          const style = getComputedStyle(element);
          return { appearance: style.appearance, backgroundImage: style.backgroundImage, paddingRight: style.paddingRight };
        });
        ensure(selectSkin.appearance === "none" && selectSkin.backgroundImage.includes("svg"), "PDF 下拉框仍使用浏览器默认箭头");
        ensure(selectSkin.paddingRight === "34px", "PDF 下拉框未给自定义箭头保留空间");
        await select.selectOption("ranges");
        ensure(await page.locator(".option-card input").count() === 1, "PDF 拆分方式切换后未显示页码范围输入框");
        const selectScreenshot = join(outputDir, "form-controls-1440.png");
        await page.screenshot({ path: selectScreenshot });
        screenshots.push(selectScreenshot);
      }
    }
    const themeBefore = await page.locator(".app-shell").getAttribute("data-theme");
    await page.getByRole("button", { name: "切换主题" }).click();
    await page.waitForFunction((previous) => document.querySelector(".app-shell")?.getAttribute("data-theme") !== previous, themeBefore);
    const toggledGlass = await page.locator(".about-card").evaluate((element) => {
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, backdrop: style.backdropFilter };
    });
    ensure(toggledGlass.background.includes("rgba") && toggledGlass.backdrop.includes("blur"), "主题切换后毛玻璃表面失效");
    const themeScreenshot = join(outputDir, "glass-theme-toggled-1440.png");
    await page.screenshot({ path: themeScreenshot });
    screenshots.push(themeScreenshot);
    await page.getByRole("button", { name: "收起导航" }).click();
    await page.locator(".app-shell.nav-collapsed").waitFor();
    await page.getByRole("button", { name: "切换状态面板" }).click();
    ensure(!(await page.locator(".app-shell").getAttribute("class")).includes("panel-open"), "桌面状态面板未关闭");
  }));
  screenshots.push(await openPage(browser, { width: 1280, height: 640 }, "scroll-pages-1280x640", async (page) => {
    const navigation = page.getByRole("navigation", { name: "主导航" });
    for (const [label, heading] of [["考勤数据填报", "考勤数据填报"], ["设置", "设置"]]) {
      await navigation.getByRole("button", { name: label, exact: true }).click();
      await page.getByRole("heading", { name: heading, exact: true }).first().waitFor();
      const moved = await page.locator(".content-scroll").evaluate((element) => {
        const previousBehavior = element.style.scrollBehavior;
        element.style.scrollBehavior = "auto";
        element.scrollTop = element.scrollHeight;
        const value = element.scrollTop;
        element.style.scrollBehavior = previousBehavior;
        return value;
      });
      ensure(moved > 0, `${label} 在较矮视口下仍无法滚动到底部`);
      await page.locator(".content-scroll").evaluate((element) => { element.scrollTop = 0; });
    }
  }));
  screenshots.push(await openPage(browser, { width: 920, height: 820 }, "compact-920", async (page) => {
    await page.locator(".context-header > button").click();
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "任务中心" }).click();
    await page.getByRole("heading", { name: "任务中心" }).waitFor();
  }));
  screenshots.push(await openPage(browser, { width: 640, height: 760 }, "compact-640", async (page) => {
    await page.locator(".context-header > button").click();
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "金额大写" }).click();
    await page.getByRole("heading", { name: "金额大写" }).waitFor();
    await page.locator("#amount").fill("12345.67");
  }));
  screenshots.push(await openPage(browser, { width: 920, height: 820 }, "reduced-motion-920", async (page) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    ensure(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches), "系统减少动画媒体查询未生效");
    const systemDuration = await page.locator(".page-flow").evaluate((element) => parseFloat(getComputedStyle(element).animationDuration) || 0);
    ensure(systemDuration <= 0.001, "系统减少动画仍保留长动画");
    const systemAmbientDuration = await page.locator(".main-stage").evaluate((element) => parseFloat(getComputedStyle(element, "::before").animationDuration) || 0);
    ensure(systemAmbientDuration <= 0.001, "系统减少动画未停止动态环境光");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.locator(".context-header > button").click();
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置" }).click();
    await page.getByRole("heading", { name: "设置" }).waitFor();
    await page.getByRole("button", { name: /减少动画/ }).click();
    await page.getByRole("button", { name: "保存设置" }).click();
    await page.locator('.app-shell[data-reduce-motion="true"]').waitFor();
    ensure((await page.locator(".page-flow").evaluate((element) => getComputedStyle(element).animationName)) === "none", "应用减少动画未关闭页面位移动画");
    const reducedTransition = await page.locator(".context-panel").evaluate((element) => getComputedStyle(element).transitionProperty);
    ensure(!reducedTransition.includes("transform"), "应用减少动画仍保留抽屉位移过渡");
    const reducedAmbient = await page.locator(".main-stage").evaluate((element) => {
      const style = getComputedStyle(element, "::before");
      return { animation: style.animationName, transform: style.transform, willChange: style.willChange };
    });
    ensure(reducedAmbient.animation === "none" && reducedAmbient.transform === "none", "应用减少动画未关闭动态背景位移");
    ensure(reducedAmbient.willChange === "auto", "应用减少动画仍为动态背景保留合成层");
  }));
  const tourPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const tourErrors = [];
  tourPage.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) tourErrors.push(message.text());
  });
  tourPage.on("pageerror", (error) => tourErrors.push(error.message));
  await tourPage.goto(baseUrl, { waitUntil: "networkidle" });
  const tourDialog = tourPage.getByRole("dialog", { name: "认识首页" });
  await tourDialog.waitFor();
  ensure(await tourPage.locator(".tour-focus-ring").count() === 1, "首页引导未显示聚光灯");
  ensure(await tourDialog.getByRole("button", { name: "结束本页引导" }).evaluate((button) => document.activeElement === button), "首页引导未把焦点移入弹层");
  await tourPage.keyboard.press("Shift+Tab");
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
  ensure((await tourPage.locator(".tour-count").innerText()).startsWith("02 /"), "考勤引导步骤进度未更新");
  await tourPage.waitForFunction(() => {
    const target = document.querySelector('[data-tour="file-input"]')?.getBoundingClientRect();
    const ring = document.querySelector(".tour-focus-ring")?.getBoundingClientRect();
    if (!target || !ring) return false;
    return Math.abs(ring.left - (target.left - 8)) <= 2
      && Math.abs(ring.top - (target.top - 8)) <= 2
      && Math.abs(ring.width - (target.width + 16)) <= 2
      && Math.abs(ring.height - (target.height + 16)) <= 2;
  });
  const fileStepScreenshot = join(outputDir, "page-guide-attendance-file.png");
  await tourPage.screenshot({ path: fileStepScreenshot });
  screenshots.push(fileStepScreenshot);
  await fileStep.getByRole("button", { name: "结束本页引导" }).click();
  ensure(await tourPage.locator(".guided-tour").count() === 0, "考勤引导结束后未关闭");
  await tourPage.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "PDF 工具箱", exact: true }).click();
  await tourPage.getByRole("dialog", { name: "认识PDF 工具箱" }).waitFor();
  const pdfGuideScreenshot = join(outputDir, "page-guide-pdf.png");
  await tourPage.screenshot({ path: pdfGuideScreenshot });
  screenshots.push(pdfGuideScreenshot);
  await tourPage.keyboard.press("Escape");
  ensure(await tourPage.locator(".guided-tour").count() === 0, "PDF 引导未响应 Escape");
  await tourPage.getByRole("button", { name: "查看当前页面使用引导" }).click();
  await tourPage.getByRole("dialog", { name: "认识PDF 工具箱" }).waitFor();
  await tourPage.keyboard.press("Escape");
  ensure(tourErrors.length === 0, `页面引导出现前端错误：${tourErrors.join("；")}`);
  await tourPage.close();
  console.log(`[完成] Chrome 视觉回归通过：${screenshots.join("；")}`);
} finally {
  await browser.close();
}
