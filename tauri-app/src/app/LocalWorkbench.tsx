/**
 * Tauri 本地工作台壳层。
 *
 * 本组件集中管理导航、主题、快捷面板、页面引导和启动摘要；具体业务页只通过桥接 Hook
 * 调用 Python Core。页面切换不使用路由地址，所有可用入口来自 `NAV_ITEMS` 单一事实源。
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import GuidedTour from "../components/GuidedTour";
import { NAV_ITEMS } from "../data/navigation";
import type { NavItem } from "../data/navigation";
import { bridgeRequest, isTauriRuntime, syncRuntimeSettings } from "../lib/bridge";
import type { AppSettings, HealthInfo, LibrarySummary, TaskResult } from "../lib/bridge";
import { AboutPage, CurrencyPage, HomePage, SettingsPage, TaskCenterPage } from "../pages/pages";
import { ArrivalPage, AttendancePage, AttendanceArchivePage, DeliveryPage, InvoicePage, PivotPage, PurchasePage, PurchasePlanPage, ReconcilePage, ReconcileStatementPage, ShippingReviewPage, SupplierBatchPage } from "../pages/business-pages";
import { ComparePage, ExcelToolsPage, PdfPage, RenamePage, TextPage } from "../pages/tool-pages";
import { DataLibraryPage, CatalogPage, BatchTrackPage, ReportPage, MappingPage, TemplatePage } from "../pages/data-pages";
import AppSidebar from "./AppSidebar";
import AppTopbar from "./AppTopbar";
import ContextPanel from "./ContextPanel";
import { getPageHeading } from "./navigation";

/**
 * 把稳定导航键映射到对应页面，并只向页面传递它实际需要的共享摘要。
 *
 * 业务算法不在此处分支；页面组件仍通过统一桥接调用 Core。未知键回退工作台，避免旧
 * 本地状态或未来导航配置导致整个桌面端白屏。
 */
function renderPage(activeItem: NavItem, navigate: (key: string) => void, library: LibrarySummary | null, health: HealthInfo | null, tasks: TaskResult | null, settings: AppSettings | null, onLibrarySummary: (summary: LibrarySummary) => void, onSettingsSaved: (next: AppSettings) => void) {
  switch (activeItem.key) {
    case "home": return <HomePage navigate={navigate} library={library} health={health} tasks={tasks} />;
    case "attendance": return <AttendancePage />;
    case "attendance_archive": return <AttendanceArchivePage />;
    case "reconcile_statement": return <ReconcileStatementPage />;
    case "reconcile": return <ReconcilePage />;
    case "arrival": return <ArrivalPage />;
    case "pivot": return <PivotPage />;
    case "purchase": return <PurchasePage />;
    case "shipping_review": return <ShippingReviewPage />;
    case "delivery": return <DeliveryPage />;
    case "supplier_batch": return <SupplierBatchPage />;
    case "purchase_plan": return <PurchasePlanPage />;
    case "library": return <DataLibraryPage initial={library} onSummary={onLibrarySummary} />;
    case "tasks": return <TaskCenterPage />;
    case "mappings": return <MappingPage />;
    case "catalog": return <CatalogPage />;
    case "batch_track": return <BatchTrackPage />;
    case "report_center": return <ReportPage />;
    case "templates": return <TemplatePage />;
    case "invoice": return <InvoicePage />;
    case "currency": return <CurrencyPage />;
    case "rename": return <RenamePage />;
    case "text": return <TextPage />;
    case "pdf": return <PdfPage />;
    case "excel": return <ExcelToolsPage />;
    case "compare": return <ComparePage />;
    case "settings": return <SettingsPage settings={settings} onSaved={onSettingsSaved} />;
    case "about": return <AboutPage health={health} />;
    default: return <HomePage navigate={navigate} library={library} health={health} tasks={tasks} />;
  }
}

/**
 * 组合桌面导航、顶栏、业务页面、快捷面板和按页引导，并维护应用级共享状态。
 *
 * 启动数据并行读取，单项失败不会阻断其他摘要；主题跟随系统时只订阅一个媒体查询。
 * 页面切换优先使用浏览器 View Transition，在减少动态效果或 API 不可用时直接切换。
 */
export default function LocalWorkbench() {
  const [activeKey, setActiveKey] = useState("home");
  const [collapsed, setCollapsed] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [library, setLibrary] = useState<LibrarySummary | null>(null);
  const [tasks, setTasks] = useState<TaskResult | null>(null);
  const [bridgeError, setBridgeError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [systemDark, setSystemDark] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState("");
  const [tourOpen, setTourOpen] = useState(false);
  const contentScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true; // Promise 本身不可取消，用布尔门闩阻止组件卸载后继续写入状态。
    // 四项启动查询互不依赖，并行发起可避免串行等待；allSettled 允许部分资料正常展示。
    Promise.allSettled([
      bridgeRequest<HealthInfo>("system.health"),
      bridgeRequest<AppSettings>("settings.get"),
      bridgeRequest<LibrarySummary>("library.summary"),
      bridgeRequest<TaskResult>("tasks.list", { limit: 8 }),
    ]).then((results) => {
      if (!active) return;
      const [healthResult, settingsResult, libraryResult, tasksResult] = results;
      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      if (settingsResult.status === "fulfilled") setSettings(settingsResult.value);
      if (libraryResult.status === "fulfilled") setLibrary(libraryResult.value);
      if (tasksResult.status === "fulfilled") setTasks(tasksResult.value);
      setBridgeError(results.some((result) => result.status === "rejected") ? "部分业务资料暂时无法读取，请重试。" : "");
    });
    return () => { active = false; };
  }, [refreshToken]);

  useEffect(() => {
    if (!settings || localStorage.getItem(`fyt-page-guide-v1:${activeKey}`)) return;
    // 首次进入页面稍后再打开引导，让页面布局和美术资源先稳定；减少动态效果时缩短等待。
    const timer = window.setTimeout(() => setTourOpen(true), settings.reduce_motion ? 80 : 420);
    return () => window.clearTimeout(timer);
  }, [activeKey, settings]);

  useLayoutEffect(() => {
    // 在浏览器绘制新页面前回到内容顶部，避免用户看到上一页滚动位置再瞬间跳动。
    contentScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [activeKey]);

  useEffect(() => {
    // Rust 只需要窗口关闭行为这一原生设置；保存配置仍由设置页通过 Python Core 完成。
    if (settings) void syncRuntimeSettings(settings).catch((reason) => setBridgeError(reason instanceof Error ? reason.message : String(reason)));
  }, [settings]);

  useEffect(() => {
    if (!settings?.check_update_on_start || !isTauriRuntime()) return;
    // 更新检查属于辅助启动动作，失败保持静默，不影响本地业务页面可用性。
    void bridgeRequest<{ result: null | { status: string; version?: string } }>("updater.check")
      .then((response) => { if (response.result?.status === "update") setUpdateAvailable(response.result.version || "新版"); })
      .catch(() => undefined);
  }, [settings?.check_update_on_start]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    update();
    // 全局媒体监听器在工作台卸载时解除，服务器模式和本地模式切换不会累积监听。
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const activeItem = useMemo(() => NAV_ITEMS.find((item) => item.key === activeKey) ?? NAV_ITEMS[0], [activeKey]); // 只在导航键变化时重新查找配置对象。
  const header = getPageHeading(activeItem);
  const dark = settings?.theme_mode === "dark" || (settings?.theme_mode === "auto" && systemDark);

  const navigateTo = useCallback((nextKey: string) => {
    if (nextKey === activeKey) return;
    setTourOpen(false);
    const documentWithTransition = document as Document & { startViewTransition?: (callback: () => void) => void };
    if (settings?.reduce_motion || !documentWithTransition.startViewTransition) {
      setActiveKey(nextKey);
      return;
    }
    // View Transition 要求回调内同步提交 DOM 变化，flushSync 只包住这一项非紧急导航状态。
    documentWithTransition.startViewTransition(() => flushSync(() => setActiveKey(nextKey)));
  }, [activeKey, settings?.reduce_motion]);

  const closeTour = useCallback(() => {
    // 完成记录按页面键保存，同一版本的引导不会在之后每次访问时重复弹出。
    localStorage.setItem(`fyt-page-guide-v1:${activeKey}`, "1");
    setTourOpen(false);
    contentScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [activeKey]);

  const toggleTheme = useCallback(async () => {
    if (!settings) return;
    const next = { ...settings, theme_mode: dark ? "light" as const : "dark" as const };
    setSettings(next); // 先乐观更新主题减少视觉延迟，Core 返回后再用规范化设置覆盖。
    try { setSettings(await bridgeRequest<AppSettings>("settings.update", { values: next })); }
    catch (reason) { setBridgeError(reason instanceof Error ? reason.message : String(reason)); }
  }, [dark, settings]);

  return (
    <div className="fyt-tauri-shell" data-theme={dark ? "dark" : "light"} data-panel-open={panelOpen ? "true" : "false"} data-nav-collapsed={collapsed ? "true" : "false"} data-reduce-motion={settings?.reduce_motion ? "true" : "false"}>
      <AppSidebar activeKey={activeKey} collapsed={collapsed} items={NAV_ITEMS} onNavigate={navigateTo} onToggle={() => setCollapsed((value) => !value)} />
      <main className="fyt-tauri-main-stage">
        <AppTopbar title={header.title} description={header.description} updateAvailable={updateAvailable} dark={dark} panelOpen={panelOpen} onOpenGuide={() => setTourOpen(true)} onToggleTheme={() => void toggleTheme()} onTogglePanel={() => setPanelOpen((value) => !value)} onOpenUpdate={() => navigateTo("about")} />
        {bridgeError ? <div className="fyt-tauri-notice" role="status" aria-live="polite"><strong>业务资料读取不完整</strong><span>{bridgeError}</span><button className="fyt-tauri-text-button" type="button" onClick={() => setRefreshToken((value) => value + 1)}>重新读取</button></div> : null}
        <div ref={contentScrollRef} className="fyt-tauri-content-scroll"><div className="fyt-tauri-content-column" data-tour="page-content" data-page-key={activeKey} key={activeKey}><div className="fyt-tauri-route-stage">{renderPage(activeItem, navigateTo, library, health, tasks, settings, setLibrary, setSettings)}</div></div></div>
      </main>
      <ContextPanel activeItem={activeItem} tasks={tasks} open={panelOpen} onClose={() => setPanelOpen(false)} onNavigate={navigateTo} />
      <GuidedTour open={tourOpen} pageKey={activeKey} pageTitle={activeItem.title} pageDescription={activeItem.description} reduceMotion={Boolean(settings?.reduce_motion)} onClose={closeTour} refreshKey={`${activeKey}:${panelOpen}`} />
    </div>
  );
}
