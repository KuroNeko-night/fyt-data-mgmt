import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import Icon from "./components/Icon";
import GuidedTour from "./components/GuidedTour";
import { NAV_ITEMS } from "./data/navigation";
import type { NavItem } from "./data/navigation";
import { bridgeRequest, isTauriRuntime, syncRuntimeSettings } from "./lib/bridge";
import type { AppSettings, HealthInfo, LibrarySummary } from "./lib/bridge";
import { AboutPage, CurrencyPage, HomePage, SettingsPage, TaskCenterPage } from "./pages/pages";
import { ArrivalPage, AttendancePage, DeliveryPage, InvoicePage, PivotPage, PurchasePage, ReconcilePage } from "./pages/business-pages";
import { ComparePage, ExcelToolsPage, PdfPage, RenamePage, TextPage } from "./pages/tool-pages";
import { DataLibraryPage, MappingPage, TemplatePage } from "./pages/data-pages";

function pageTitle(item: NavItem) {
  if (item.key === "home") return { title: "欢迎使用", description: "峰运通业务处理、数据归档与任务追踪的一体化工作台。" };
  return { title: item.title, description: item.description };
}

export default function App() {
  const [activeKey, setActiveKey] = useState("home");
  const [collapsed, setCollapsed] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [library, setLibrary] = useState<LibrarySummary | null>(null);
  const [bridgeError, setBridgeError] = useState("");
  const [systemDark, setSystemDark] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState("");
  const [tourOpen, setTourOpen] = useState(false);
  const contentScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      bridgeRequest<HealthInfo>("system.health"),
      bridgeRequest<AppSettings>("settings.get"),
      bridgeRequest<LibrarySummary>("library.summary"),
    ]).then(([healthData, settingsData, libraryData]) => {
      if (!active) return;
      setHealth(healthData); setSettings(settingsData); setLibrary(libraryData);
    }).catch((reason) => {
      if (active) setBridgeError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!settings || localStorage.getItem(`fyt-page-guide-v1:${activeKey}`)) return;
    const timer = window.setTimeout(() => setTourOpen(true), settings.reduce_motion ? 80 : 420);
    return () => window.clearTimeout(timer);
  }, [activeKey, settings]);

  useLayoutEffect(() => {
    contentScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [activeKey]);

  useEffect(() => {
    if (settings) void syncRuntimeSettings(settings).catch((reason) => {
      setBridgeError(reason instanceof Error ? reason.message : String(reason));
    });
  }, [settings]);

  useEffect(() => {
    if (!settings?.check_update_on_start || !isTauriRuntime()) return;
    void bridgeRequest<{ result: null | { status: string; version?: string } }>("updater.check")
      .then((response) => {
        if (response.result?.status === "update") setUpdateAvailable(response.result.version || "新版");
      })
      .catch(() => undefined);
  }, [settings?.check_update_on_start]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const activeItem = useMemo(() => NAV_ITEMS.find((item) => item.key === activeKey) ?? NAV_ITEMS[0], [activeKey]);
  const header = pageTitle(activeItem);
  const theme = settings?.theme_mode === "dark" || (settings?.theme_mode === "auto" && systemDark) ? "dark" : "light";

  const navigateTo = useCallback((nextKey: string) => {
    if (nextKey === activeKey) return;
    setTourOpen(false);
    const documentWithTransition = document as Document & {
      startViewTransition?: (callback: () => void) => void;
    };
    if (settings?.reduce_motion || !documentWithTransition.startViewTransition) {
      setActiveKey(nextKey);
      return;
    }
    documentWithTransition.startViewTransition(() => flushSync(() => setActiveKey(nextKey)));
  }, [activeKey, settings?.reduce_motion]);

  const closeTour = useCallback(() => {
    localStorage.setItem(`fyt-page-guide-v1:${activeKey}`, "1");
    setTourOpen(false);
  }, [activeKey]);

  async function toggleTheme() {
    if (!settings) return;
    const next = { ...settings, theme_mode: theme === "dark" ? "light" as const : "dark" as const };
    setSettings(next);
    try { setSettings(await bridgeRequest<AppSettings>("settings.update", { values: next })); }
    catch (reason) { setBridgeError(reason instanceof Error ? reason.message : String(reason)); }
  }

  function renderPage() {
    switch (activeItem.key) {
      case "home": return <HomePage navigate={navigateTo} library={library} health={health} />;
      case "attendance": return <AttendancePage />;
      case "reconcile": return <ReconcilePage />;
      case "arrival": return <ArrivalPage />;
      case "pivot": return <PivotPage />;
      case "purchase": return <PurchasePage />;
      case "delivery": return <DeliveryPage />;
      case "library": return <DataLibraryPage initial={library} onSummary={setLibrary} />;
      case "tasks": return <TaskCenterPage />;
      case "mappings": return <MappingPage />;
      case "templates": return <TemplatePage />;
      case "invoice": return <InvoicePage />;
      case "currency": return <CurrencyPage />;
      case "rename": return <RenamePage />;
      case "text": return <TextPage />;
      case "pdf": return <PdfPage />;
      case "excel": return <ExcelToolsPage />;
      case "compare": return <ComparePage />;
      case "settings": return <SettingsPage settings={settings} onSaved={setSettings} />;
      case "about": return <AboutPage health={health} />;
      default: return <HomePage navigate={navigateTo} library={library} health={health} />;
    }
  }

  return (
    <div className={`app-shell ${collapsed ? "nav-collapsed" : ""} ${panelOpen ? "panel-open" : ""}`} data-theme={theme} data-reduce-motion={settings?.reduce_motion ? "true" : "false"}>
      <aside className="sidebar" data-tour="navigation">
        <div className="brand-block"><div className="brand-symbol">峰</div><div className="brand-text"><strong>峰运通</strong><span>数据管理系统</span></div></div>
        <nav aria-label="主导航">
          {NAV_ITEMS.map((item, index) => {
            const previousGroup = index > 0 ? NAV_ITEMS[index - 1].group : null;
            const showGroup = item.group && item.group !== previousGroup;
            return <div key={item.key}>{showGroup ? <div className="nav-group">{item.group}</div> : null}<button className={`nav-item ${activeKey === item.key ? "active" : ""}`} aria-current={activeKey === item.key ? "page" : undefined} aria-label={item.title} title={collapsed ? item.title : undefined} onClick={() => navigateTo(item.key)}>{activeKey === item.key ? <span className="nav-active-rail" /> : null}<Icon name={item.icon} /><span>{item.title}</span></button></div>;
          })}
        </nav>
        <button className="sidebar-toggle" aria-label={collapsed ? "展开导航" : "收起导航"} onClick={() => setCollapsed((value) => !value)}><Icon name="collapse" /><span>{collapsed ? "展开导航" : "收起导航"}</span></button>
      </aside>

      <main className="main-stage">
        <header className="topbar">
          <div className="topbar-title" data-tour="page-heading"><h1>{header.title}</h1><p>{header.description}</p></div>
          <div className="topbar-actions">
            {updateAvailable ? <button className="update-pill" onClick={() => navigateTo("about")}>发现新版 v{updateAvailable}</button> : null}
            <span className={`runtime-pill ${isTauriRuntime() ? "connected" : ""}`}><i />{isTauriRuntime() ? "Python 核心已连接" : "浏览器预览"}</span>
            <button className="icon-button guide-button" aria-label="查看当前页面使用引导" title="查看当前页面使用引导" onClick={() => setTourOpen(true)}><Icon name="help" /></button>
            <button className="icon-button" data-tour="appearance" aria-label="切换主题" onClick={() => void toggleTheme()}><Icon name="sun" /></button>
            <button className={`icon-button ${panelOpen ? "active" : ""}`} aria-label="切换状态面板" onClick={() => setPanelOpen((value) => !value)}><Icon name="panel" /></button>
          </div>
        </header>
        {bridgeError ? <div className="global-notice"><strong>Python 核心连接失败</strong><span>{bridgeError}</span></div> : null}
        <div ref={contentScrollRef} className="content-scroll"><div className="content-column" data-tour="page-content" data-page-key={activeKey} key={activeKey}>{renderPage()}</div></div>
      </main>

      <aside className="context-panel" data-tour="status-panel">
        <div className="context-header"><div><strong>运行状态</strong><span>桌面核心与迁移进度</span></div><button aria-label="关闭状态面板" onClick={() => setPanelOpen(false)}>×</button></div>
        <div className="context-body">
          <section><h3>核心连接</h3><dl><div><dt>状态</dt><dd className={bridgeError ? "error-text" : "ok-text"}>{bridgeError ? "异常" : "正常"}</dd></div><div><dt>Python</dt><dd>{health?.python ?? "检测中"}</dd></div><div><dt>版本</dt><dd>{health?.version ?? "—"}</dd></div></dl></section>
          <section><h3>当前页面</h3><p>{activeItem.title}</p><span className="phase ready">已接入桥接</span></section>
          <section><h3>迁移原则</h3><ul><li>业务逻辑继续由 Python core 负责</li><li>React 仅管理界面和状态</li><li>Tauri 通过白名单命令调用 sidecar</li><li>输出目录与配置保持兼容</li></ul></section>
        </div>
      </aside>
      <GuidedTour
        open={tourOpen}
        pageKey={activeKey}
        pageTitle={activeItem.title}
        pageDescription={activeItem.description}
        reduceMotion={Boolean(settings?.reduce_motion)}
        onClose={closeTour}
        refreshKey={`${activeKey}:${panelOpen}`}
      />
    </div>
  );
}
