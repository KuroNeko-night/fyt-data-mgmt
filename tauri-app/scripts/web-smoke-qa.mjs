#!/usr/bin/env node
/*
 * Web 前端构建产物冒烟测试。
 *
 * 脚本先执行正式构建，再启动 Vite preview，并用 Playwright 拦截同源 API 请求。
 * 合成响应覆盖登录、角色权限、工作台、日清批次弹窗和业务结果投影，
 * 因而可以在不读写真实 web-data、不依赖后端服务的前提下验证前端发布产物。
 * 这里验证的是页面协议和响应式布局，不替代服务端接口与 core 业务回归测试。
 */
import { mkdirSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url)); // 以脚本文件定位项目，避免依赖调用者当前目录。
const webRoot = path.resolve(scriptDir, "..", "..", "web-app");
const port = 4173; // 使用固定 preview 端口，便于路由拦截和失败诊断。
const base = `http://127.0.0.1:${port}`;
const screenshotDir = process.env.FYT_QA_OUTPUT || path.join(tmpdir(), "fyt-web-smoke");
mkdirSync(screenshotDir, { recursive: true });

/** 同步执行构建命令并把输出原样转发到终端，非零退出码立即终止冒烟流程。 */
function run(command, args, cwd) {
  const result = spawnSync(`${command} ${args.join(" ")}`, { cwd, shell: true, stdio: "inherit" });
  if (result.status !== 0) throw new Error(`${command} 退出码 ${result.status}`);
}

/** 轮询 preview 首页，区分“进程已创建”和“HTTP 服务已经可以接收请求”。 */
async function waitForServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      /* 服务未就绪，继续等待。 */
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`服务未在 ${timeoutMs}ms 内启动：${url}`);
}

let smokeRole = "team_leader"; // 同一页面先验收班组长可见的团队数据库，再切换管理员。

/** 按当前冒烟角色构造认证用户，角色切换后所有相关接口自动保持一致。 */
function currentUser() {
  return {
    id: smokeRole === "admin" ? 2 : 1,
    username: smokeRole === "admin" ? "smoke-admin" : "smoke-leader",
    display_name: smokeRole === "admin" ? "冒烟管理员" : "冒烟班组长",
    role: smokeRole,
    status: "approved",
    created_at: "2026-07-01T08:00:00+08:00",
    approved_at: "2026-07-01T08:10:00+08:00",
  };
}

// 只提供工作台和业务模块渲染所需的最小目录，避免测试夹带服务端目录实现。
const features = [
  { key: "attendance", title: "考勤填报", group: "人事", description: "整理考勤记录并生成填报结果。" },
  { key: "reconcile", title: "工时对账", group: "财务", description: "核对工时与劳务对账资料。" },
  { key: "arrival", title: "到料明细", group: "业务", description: "上传送货计划，自动统计到料与未收料。" },
  { key: "pivot", title: "销售透视", group: "销售", description: "按业务字段汇总销售数据。" },
];

// 结构化业务结果直接模拟 business_result_core 的投影协议，前端不重新解析表格。
const arrivalPresentation = {
  kind: "arrival",
  title: "到料明细结果",
  summary: "共 2 个批次，到料完成率 85.0%，仍有 3 类未收料。 已列出 2 条未到物料明细。",
  metrics: [
    { key: "batches", label: "批次数", value: "2", note: "", tone: "info" },
    { key: "completion", label: "到料完成率", value: "85.0%", note: "17 / 20 类", tone: "warning" },
    { key: "arrived", label: "已到货类数", value: "17", note: "", tone: "success" },
    { key: "missing", label: "未收料类数", value: "3", note: "", tone: "danger" },
  ],
  notices: [],
  sections: [
    {
      key: "batches", title: "批次完成情况", description: "完成率按已到货类数除以主料总类数计算。",
      columns: [
        { key: "batch_no", label: "批次" }, { key: "total_count", label: "主料总类数" },
        { key: "arrived_count", label: "已到货" }, { key: "missing_count", label: "未收料" },
        { key: "completion_label", label: "完成率" },
      ],
      rows: [
        { batch_no: "26035-01", total_count: "10", arrived_count: "8", missing_count: "2", completion_label: "80.0%" },
        { batch_no: "26035-02", total_count: "10", arrived_count: "9", missing_count: "1", completion_label: "90.0%" },
      ],
      total: 2, truncated: false,
    },
    {
      key: "missing_materials", title: "未到物料明细", description: "逐项列出尚未到齐的物料及数量缺口。",
      columns: [
        { key: "batch_no", label: "批次" }, { key: "material_code", label: "物料编码" },
        { key: "material_name", label: "物料名称" }, { key: "supplier", label: "供应商" },
        { key: "demand_quantity", label: "需求数" }, { key: "received_quantity", label: "已收数" },
        { key: "shortage_quantity", label: "缺口数" },
      ],
      rows: [
        { batch_no: "26035-01", material_code: "A-01", material_name: "固定螺栓", supplier: "供应商甲", demand_quantity: "12", received_quantity: "9", shortage_quantity: "3" },
        { batch_no: "26035-02", material_code: "B-02", material_name: "防护垫片", supplier: "供应商乙", demand_quantity: "20", received_quantity: "18", shortage_quantity: "2" },
      ],
      total: 2, truncated: false,
    },
  ],
};

// 同一完成任务同时供任务接口、日清来源和业务结果详情复用，确保关联 ID 一致。
const arrivalJob = {
  id: "smoke-arrival-job",
  action: "web.arrival",
  title: "冒烟到料明细",
  status: "completed",
  progress: 100,
  logs: ["到料明细处理完成"],
  result: { results: [["26035-01", 2, 8, 10], ["26035-02", 1, 9, 10]] },
  presentation: arrivalPresentation,
  error: null,
  files: [],
  review_pending: false,
  created_at: "2026-08-05T02:30:00+00:00",
  updated_at: "2026-08-05T02:35:00+00:00",
  versions: [],
};

// 日清合成数据刻意包含两个批次和多个缺料项，用于验证汇总与下钻信息同时存在。
const dailyReportData = {
  date: "2026-08-05",
  generated_at: "2026-08-05T03:00:00+00:00",
  timezone: "Asia/Shanghai",
  scope: "all",
  definitions: {
    arrival: "到料按任务完成时间归入 Asia/Shanghai 业务日期。",
    workshop: "现场问题按填写的问题日期统计，只包含已发布记录。",
  },
  arrival: {
    job_count: 1, batch_count: 2, total_categories: 20, arrived_categories: 17,
    missing_categories: 3, missing_material_detail_count: 2, completion_rate: 85,
    invalid_batch_count: 0,
    batches: [
      {
        id: "daily-1", job_id: arrivalJob.id, job_title: arrivalJob.title, uploader: "冒烟管理员",
        completed_at: arrivalJob.updated_at, batch_no: "26035-01", missing_count: 2,
        arrived_count: 8, total_count: 10, completion_rate: 80, completion_label: "80.0%", data_valid: true,
        missing_materials: [
          { material_code: "A-01", material_name: "固定螺栓", supplier: "供应商甲", demand_quantity: 12, received_quantity: 9, shortage_quantity: 3 },
          { material_code: "A-02", material_name: "定位销", supplier: "供应商甲", demand_quantity: 8, received_quantity: 6, shortage_quantity: 2 },
        ],
      },
      {
        id: "daily-2", job_id: arrivalJob.id, job_title: arrivalJob.title, uploader: "冒烟管理员",
        completed_at: arrivalJob.updated_at, batch_no: "26035-02", missing_count: 1,
        arrived_count: 9, total_count: 10, completion_rate: 90, completion_label: "90.0%", data_valid: true,
        missing_materials: [
          { material_code: "B-02", material_name: "防护垫片", supplier: "供应商乙", demand_quantity: 20, received_quantity: 18, shortage_quantity: 2 },
        ],
      },
    ],
  },
  workshop: {
    issue_count: 1, image_count: 0, owner_count: 1,
    owner_distribution: [{ owner: "张工", count: 1 }],
    issues: [{
      id: "issue-1", issue_date: "2026-08-05", cause: "设备防护罩固定螺栓松动",
      primary_owner: "张工", secondary_owner: "李工", notes: "下午复查", created_at: "2026-08-05T04:00:00+00:00",
      uploader: "冒烟管理员", images: [], image_count: 0,
    }],
  },
};

// 八条任务覆盖完成、运行、失败、排队和待复核状态，并验证移动端数量收敛规则。
const recentJobs = Array.from({ length: 8 }, (_, index) => ({
  id: `smoke-job-${index + 1}`,
  action: index % 2 ? "reconcile.run" : "attendance.run",
  title: `冒烟任务 ${index + 1}`,
  status: index === 0 ? "completed" : index === 1 ? "running" : index === 2 ? "failed" : "queued",
  progress: index === 1 ? 48 : 100,
  error: index === 2 ? "合成失败提示" : null,
  created_at: `2026-08-0${Math.min(index + 1, 4)}T0${index}:30:00+08:00`,
  updated_at: `2026-08-0${Math.min(index + 1, 4)}T0${index}:35:00+08:00`,
  review_pending: index === 3,
}));

// 工作台数据包含趋势、任务、文件和四条通知，可同时覆盖桌面完整展示和移动端截断。
const dashboard = {
  user: currentUser(),
  generated_at: "2026-08-04T10:30:00+08:00",
  metrics: { pending_users: smokeRole === "admin" ? 2 : 0, approved_users: 4, total_jobs: 8, completed_jobs: 1, running_jobs: 1, failed_jobs: 1 },
  status_breakdown: { queued: 4, running: 1, review: 1, completed: 1, failed: 1, interrupted: 1 },
  trend: [
    { date: "2026-07-29", total: 2, completed: 1, failed: 0 },
    { date: "2026-07-30", total: 3, completed: 2, failed: 1 },
    { date: "2026-07-31", total: 1, completed: 1, failed: 0 },
    { date: "2026-08-01", total: 4, completed: 2, failed: 1 },
    { date: "2026-08-02", total: 2, completed: 1, failed: 0 },
    { date: "2026-08-03", total: 5, completed: 3, failed: 1 },
    { date: "2026-08-04", total: 8, completed: 1, failed: 1 },
  ],
  feature_usage: [{ key: "attendance", title: "考勤填报", count: 4 }, { key: "reconcile", title: "工时对账", count: 2 }],
  recent_jobs: recentJobs,
  recent_files: [{ name: "冒烟结果.xlsx", size: 4096, url: "/api/files/smoke", job_id: recentJobs[0].id, title: "冒烟任务 1", created_at: recentJobs[0].created_at }],
  notifications: [
    { id: 1, kind: "announcement", title: "系统公告", content: "第一条重要通知", created_at: "2026-08-04T09:00:00+08:00", expires_at: null, read_at: null },
    { id: 2, kind: "message", title: "任务提醒", content: "第二条重要通知", created_at: "2026-08-04T08:00:00+08:00", expires_at: null, read_at: null },
    { id: 3, kind: "announcement", title: "资料提醒", content: "第三条重要通知", created_at: "2026-08-03T17:00:00+08:00", expires_at: null, read_at: null },
    { id: 4, kind: "message", title: "第四条通知", content: "移动端不应显示这一条", created_at: "2026-08-03T16:00:00+08:00", expires_at: null, read_at: null },
  ],
};

/** 为管理员各子页返回结构完整的空数据，重点验证入口和权限而非管理操作。 */
function adminPayload(pathname) {
  const user = currentUser();
  return {
    "/api/admin/data": {
      summary: { users: 2, approved_users: 2, admins: 1, pending_users: 0, disabled_users: 0, jobs: 0, uploads: 0, job_files: 0, job_bytes: 0, upload_bytes: 0 },
      users: [{ ...user, job_count: 0, session_count: 1, is_primary_admin: user.role === "admin" }],
      jobs: [],
      uploads: [],
    },
    "/api/admin/announcements": { announcements: [] },
    "/api/admin/audit": { audit: [] },
    "/api/admin/backups": { backups: [] },
    "/api/admin/trash": { trash: [] },
  }[pathname];
}

/** 用统一 JSON 响应包裹 Playwright 的 fulfill，避免每个处理分支重复状态与头信息。 */
async function fulfillJson(route, body) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

// 管理端接口固定路径，用于避免在 mockApi 中重复书写长条件表达式。
const adminApiPaths = new Set([
  "/api/admin/data",
  "/api/admin/announcements",
  "/api/admin/audit",
  "/api/admin/backups",
  "/api/admin/trash",
]);

// 有序路由表：match 只做路径判断，body 延迟到命中后才构造，避免无关接口触发现有合成数据。
const apiResponseHandlers = [
  { match: (pathname) => pathname === "/api/auth/me", body: () => ({ user: currentUser() }) },
  {
    match: (pathname) => pathname === "/api/overview",
    body: () => ({ user: currentUser(), features, metrics: { pending_users: smokeRole === "admin" ? 2 : 0, approved_users: 4, output_jobs: 1 } }),
  },
  {
    match: (pathname) => pathname === "/api/dashboard",
    body: () => ({ ...dashboard, user: currentUser(), metrics: { ...dashboard.metrics, pending_users: smokeRole === "admin" ? 2 : 0 } }),
  },
  { match: (pathname) => pathname === "/api/daily-report", body: () => dailyReportData },
  { match: (pathname) => pathname === "/api/jobs", body: () => ({ jobs: [arrivalJob] }) },
  { match: (pathname) => pathname === `/api/jobs/${arrivalJob.id}`, body: () => ({ job: arrivalJob }) },
  { match: (pathname) => pathname === "/api/templates", body: () => ({ templates: [] }) },
  { match: (pathname) => pathname === "/api/notifications", body: () => ({ notifications: dashboard.notifications, unread_count: 4 }) },
  {
    match: (pathname) => pathname === "/api/library/files",
    body: () => ({ files: [], pagination: { page: 1, page_size: 20, total: 0, pages: 1 }, summary: { visible_count: 0, team_count: 0, own_count: 0, own_bytes: 0, quota_bytes: 1, category_counts: {} }, categories: [] }),
  },
  { match: (pathname) => adminApiPaths.has(pathname), body: (url) => adminPayload(url.pathname) },
];

/** 判断请求是否携带合成会话，优先请求头，其次兼容同源请求自动携带的会话 Cookie。 */
function hasSession(request) {
  if (request.headers()["x-session-token"]) return true;
  const cookie = request.headers()["cookie"] || "";
  return cookie.split("; ").some((part) => part.startsWith("fyt_session="));
}

/**
 * 拦截前端同源 API，并返回与服务端契约一致的合成 JSON。
 *
 * 未登录判定依赖请求头或 Cookie 中的会话令牌；已登录响应统一读取 smokeRole。
 * 路由表未覆盖的接口继续交给 preview，使意外新增请求暴露为控制台或网络错误，
 * 而不是被一个宽泛的成功响应掩盖。
 */
async function mockApi(route) {
  const request = route.request();
  const url = new URL(request.url());
  if (!url.pathname.startsWith("/api/")) return route.continue(); // 静态资源必须由真实构建产物提供。
  if (url.pathname === "/api/auth/me" && !hasSession(request)) {
    await fulfillJson(route, { user: null });
    return;
  }
  const handler = apiResponseHandlers.find(({ match }) => match(url.pathname));
  if (!handler) return route.continue(); // 未声明接口不伪造结果，便于发现前端协议新增或路径拼写错误。
  await fulfillJson(route, handler.body(url));
}

/** 记录单项验收结果；失败细节只写日志，汇总名称保持简洁。 */
function recordCheck(failures, name, passed, detail = "") {
  if (passed) {
    console.log(`  [通过] ${name}`);
    return;
  }
  failures.push(name);
  console.log(`  [失败] ${name}${detail ? `：${detail}` : ""}`);
}

/** 顺序执行命名检查，避免并行页面操作互相改变 DOM 状态。 */
async function runChecks(failures, checks) {
  for (const [name, check] of Object.entries(checks)) {
    recordCheck(failures, name, Boolean(await check()));
  }
}

/** 验收未登录页和班组长工作台，角色权限与工作台数据在同一登录状态下检查。 */
async function verifyLoginAndWorkbench(page, failures) {
  console.log("[3/4] 登录页与登录后工作台 ...");
  await page.goto(base, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  await runChecks(failures, {
    "登录页标题": async () => (await page.textContent("h1"))?.includes("让每一张业务表"),
    "品牌标识": async () => Boolean(await page.locator(".fyt-brand").count()),
    "登录卡片": async () => Boolean(await page.locator(".fyt-auth-card").count()),
    "登录表单": async () => Boolean(await page.locator(".fyt-auth-form input[type=password]").count()),
    "插画资源": async () => Boolean(await page.locator(".fyt-auth-story-illustration .fyt-art-asset, .fyt-auth-story-illustration .fyt-art-fallback").count()),
  });
  await page.screenshot({ path: path.join(screenshotDir, "web-login-1440.png") });

  // 浏览器端会话由 HttpOnly Cookie 自动携带；这里只注入同源 Cookie 进入合成登录态。
  await page.context().addCookies([{ name: "fyt_session", value: "smoke-token", url: base }]);
  await page.evaluate(() => { localStorage.setItem("fyt-web-guide-v1", "1"); });
  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".dsp-board").waitFor();
  await runChecks(failures, {
    "登录后工作台": async () => Boolean(await page.locator(".fyt-shell .dsp-board").count()),
    "非管理员隐藏系统管理": async () => (await page.getByRole("button", { name: "系统管理", exact: true }).count()) === 0,
    "工作台任务数量": async () => (await page.locator(".dsp-row").count()) === 8,
    "失败数量可见": async () => (await page.locator(".dsp-chart-foot em").count()) > 0,
  });
  await page.screenshot({ path: path.join(screenshotDir, "web-workbench-1440.png") });
}

/** 验收普通业务路由、主题状态以及平板和手机响应式布局。 */
async function verifyResponsiveRoutes(page, failures) {
  console.log("[4/4] 路由、主题、平板和移动端 ...");
  recordCheck(failures, "已下线入口不可见", (await page.getByRole("button", { name: "批次跟踪", exact: true }).count()) === 0);
  await page.locator(".dsp-board").waitFor();
  await page.getByRole("button", { name: "切换为深色", exact: true }).click();
  const darkTheme = await page.evaluate(() => document.documentElement.dataset.theme === "dark");
  recordCheck(failures, "深色主题", darkTheme);
  await page.getByRole("button", { name: "切换为浅色", exact: true }).click();

  await page.setViewportSize({ width: 1024, height: 768 });
  await page.locator(".dsp-board").waitFor();
  const tablet = await page.evaluate(() => {
    const sidebar = document.querySelector(".fyt-shell-sidebar")?.getBoundingClientRect();
    const board = document.querySelector(".dsp")?.getBoundingClientRect();
    return { sidebar: Math.round(sidebar?.width || 0), left: Math.round(board?.left || 0) };
  });
  recordCheck(failures, "1024px 图标侧栏", tablet.sidebar === 72, `${tablet.sidebar}px`);
  await page.locator('[data-guide="nav-library"]').click();
  await page.locator(".fyt-library-page").waitFor();
  const contentLeft = await page.locator(".fyt-library-page").evaluate((element) => Math.round(element.getBoundingClientRect().left));
  recordCheck(
    failures,
    "统一内容容器边界",
    Math.abs(contentLeft - tablet.left) <= 1,
    `工作台 ${tablet.left}px，数据库 ${contentLeft}px`,
  );
  await page.locator('[data-guide="nav-overview"]').click();
  await page.locator(".dsp-board").waitFor();
  await page.waitForTimeout(420);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".dsp-board").waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".dsp-row").length <= 4 && document.querySelectorAll(".dsp-alert-static").length <= 3);
  const mobile = await page.evaluate(() => {
    const order = [".dsp-alerts", ".dsp-launch", ".dsp-ledger", ".dsp-trend"].map((selector) => Math.round(document.querySelector(selector)?.getBoundingClientRect().top || 0));
    return { order, jobs: document.querySelectorAll(".dsp-row").length, notes: document.querySelectorAll(".dsp-alert-static").length, overflow: document.documentElement.scrollWidth > window.innerWidth || document.body.scrollWidth > window.innerWidth };
  });
  recordCheck(failures, "移动工作台行动顺序", mobile.order[0] < mobile.order[1] && mobile.order[1] < mobile.order[2]);
  recordCheck(failures, "移动任务和通知上限", mobile.jobs <= 4 && mobile.notes <= 3, `任务 ${mobile.jobs}，通知 ${mobile.notes}`);
  recordCheck(failures, "390px 无横向溢出", !mobile.overflow);
  await page.screenshot({ path: path.join(screenshotDir, "web-workbench-390.png") });
  await page.setViewportSize({ width: 360, height: 800 });
  const narrowOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth || document.body.scrollWidth > window.innerWidth);
  recordCheck(failures, "360px 无横向溢出", !narrowOverflow);
}

/** 切换管理员角色，验收日清下钻、结构化业务结果和系统管理入口。 */
async function verifyAdminPages(page, failures) {
  smokeRole = "admin"; // 重载后所有合成接口统一切换管理员身份，避免前后端角色不一致。
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".dsp-board").waitFor();

  await page.getByRole("button", { name: "日清看板", exact: true }).click();
  await page.locator(".fyt-daily-page").waitFor();
  const dailyChecks = await page.evaluate(() => ({
    metrics: document.querySelectorAll(".fyt-daily-metrics > div").length,
    batches: document.querySelectorAll(".fyt-daily-batch-list > button").length,
    issues: document.querySelectorAll(".fyt-daily-issue-list article").length,
  }));
  recordCheck(
    failures,
    "日清看板核心数据",
    dailyChecks.metrics === 6 && dailyChecks.batches === 2 && dailyChecks.issues === 1,
    JSON.stringify(dailyChecks),
  );
  await page.getByRole("button", { name: /26035-01 冒烟管理员/ }).click();
  await page.locator(".fyt-daily-batch-dialog").waitFor();
  const batchDialogChecks = await page.evaluate(() => ({
    dialogWidth: Math.round(document.querySelector('.fyt-dialog[data-size="large"]')?.getBoundingClientRect().width || 0),
    materials: document.querySelectorAll(".fyt-daily-material-table tbody tr").length,
    shortage: document.querySelector(".fyt-daily-material-table tbody tr td:last-child")?.textContent?.trim(),
  }));
  recordCheck(
    failures,
    "大号批次浮窗展示未到物料与缺口数",
    batchDialogChecks.dialogWidth > 900 && batchDialogChecks.materials === 2 && batchDialogChecks.shortage === "3",
    JSON.stringify(batchDialogChecks),
  );
  await page.screenshot({ path: path.join(screenshotDir, "web-daily-1440.png") });

  await page.setViewportSize({ width: 360, height: 800 });
  const dailyNarrow = await page.evaluate(() => {
    const cards = [...document.querySelectorAll(".fyt-daily-metrics > div")].map((element) => element.getBoundingClientRect());
    const materialRow = document.querySelector(".fyt-daily-material-table tbody tr");
    return {
      rows: new Set(cards.map((rect) => Math.round(rect.top))).size,
      materialLayout: materialRow ? getComputedStyle(materialRow).display : "",
      shortageVisible: document.querySelector('.fyt-daily-material-table td[data-label="缺口数"]')?.textContent?.trim(),
      overflow: document.documentElement.scrollWidth > window.innerWidth || document.body.scrollWidth > window.innerWidth,
    };
  });
  recordCheck(
    failures,
    "360px 日清单列与缺料卡片无溢出",
    dailyNarrow.rows === 6 && dailyNarrow.materialLayout === "grid" && dailyNarrow.shortageVisible === "3" && !dailyNarrow.overflow,
    JSON.stringify(dailyNarrow),
  );
  await page.screenshot({ path: path.join(screenshotDir, "web-daily-360.png") });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "关闭弹窗", exact: true }).click();
  await page.getByRole("button", { name: "业务模块", exact: true }).click();
  const arrivalCard = page.getByRole("heading", { name: "到料明细", exact: true }).locator("..");
  await arrivalCard.getByRole("button", { name: "打开模块", exact: true }).click();
  await page.getByRole("button", { name: /已完成 冒烟到料明细/ }).click();
  await page.locator(".fyt-business-result").waitFor();
  const resultLayout = await page.evaluate(() => {
    const result = document.querySelector(".fyt-business-result")?.getBoundingClientRect();
    return {
      width: Math.round(result?.width || 0),
      metrics: document.querySelectorAll(".fyt-business-result-metrics > div").length,
      sections: document.querySelectorAll(".fyt-business-result-section").length,
      materialRows: document.querySelectorAll(".fyt-business-result-section:nth-of-type(2) tbody tr").length,
      overflow: document.documentElement.scrollWidth > window.innerWidth || document.body.scrollWidth > window.innerWidth,
    };
  });
  recordCheck(
    failures,
    "到料业务结果全宽结构化展示",
    resultLayout.width > 900 && resultLayout.metrics === 4 && resultLayout.sections === 2 && !resultLayout.overflow,
    JSON.stringify(resultLayout),
  );
  recordCheck(failures, "业务结果未到物料明细", resultLayout.materialRows === 2 && Boolean(await page.getByText("A-01", { exact: true }).count()));
  await page.locator(".fyt-business-result").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(screenshotDir, "web-arrival-result-1440.png") });

  await page.locator('[data-guide="nav-users"]').click();
  await page.locator(".fyt-admin-page").waitFor();
  recordCheck(failures, "管理员系统管理入口", Boolean(await page.getByRole("heading", { name: "系统管理", exact: true }).count()));
}

/** 串联构建、服务启动、页面验收和资源回收，最终统一汇总失败项。 */
async function main() {
  console.log("[1/4] 构建 web-app ...");
  run("npm", ["run", "build"], webRoot);

  console.log("[2/4] 启动 preview 服务 ...");
  const preview = spawn(`npm run preview -- --port ${port}`, { cwd: webRoot, shell: true, stdio: "ignore" });
  const failures = [];
  let browser;
  try {
    await waitForServer(base);
    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.route("**/api/**", mockApi); // 首次导航前注册，认证请求不会误发到不存在的真实后端。
    const consoleErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => consoleErrors.push(String(error)));

    await verifyLoginAndWorkbench(page, failures);
    await verifyResponsiveRoutes(page, failures);
    await verifyAdminPages(page, failures);
    recordCheck(failures, "无控制台错误", consoleErrors.length === 0, `${consoleErrors.length} 条`);
    for (const error of consoleErrors.slice(0, 5)) console.error(`    - ${error.slice(0, 240)}`);
  } finally {
    if (browser) await browser.close(); // 任一场景抛错也先回收浏览器，再停止 preview 子进程。
    preview.kill();
  }
  if (failures.length) {
    console.error(`\n冒烟测试未通过：${failures.join("、")}`);
    process.exit(1);
  }
  console.log(`\n[完成] Web 前端冒烟测试全部通过，截图已写入：${screenshotDir}`);
}

main().catch((error) => {
  // 顶层只输出简洁错误；具体失败项和构建日志已经在前序步骤中写入终端。
  console.error("[错误]", error.message);
  process.exit(1);
});
