/**
 * Web 应用的认证入口、页面路由状态和顶层数据装配。
 *
 * 项目没有引入浏览器路由库，当前页面由受控 `active` 键决定；所有受保护页面在
 * 渲染前再次检查角色可见性，但真正权限仍由服务端接口强制执行。各业务区域使用
 * 独立错误边界，单个页面异常不会让整个登录会话失去操作能力。
 */
import { useCallback, useEffect, useState } from "react";
import { clearToken, logout, me, type User } from "./api";
import { FeatureWorkspace } from "./FeatureWorkspace";
import { DispatchBoard } from "./DispatchBoard";
import { TaskCenterPage, type TaskFilter } from "./TaskCenterPage";
import { GuidedTour } from "./GuidedTour";
import { AdminPage } from "./AdminPage";
import { AccountSecurityPage } from "./AccountSecurityPage";
import { NotificationCenterPage } from "./NotificationCenterPage";
import { FileLibraryPage } from "./FileLibraryPage";
import { WorkshopIssuePage } from "./WorkshopIssuePage";
import { BatchTrackPage } from "./BatchTrackPage";
import { ReportPage } from "./ReportPage";
import { DailyReportPage } from "./DailyReportPage";
import { FeaturesPage } from "./pages/FeaturesPage";
import AuthScreen from "./app/AuthScreen";
import WebShell from "./app/WebShell";
import { SectionErrorBoundary } from "./components/SectionErrorBoundary";
import { useDashboardData } from "./hooks/useDashboardData";
import { getNavigationItem, isNavigationAllowed, type WebRouteKey } from "./app/navigation";
import Skeleton from "./ui/Skeleton";

/** 全屏加载态：用于登录校验和工作台首次读取，不承载任何业务数据逻辑。 */
function PageLoading({ text = "正在加载工作台..." }: { text?: string }) {
  return <div className="fyt-page-state" role="status" aria-live="polite"><div className="fyt-skeleton-group" aria-hidden="true"><Skeleton variant="title" /><Skeleton variant="rect" /></div><strong>{text}</strong></div>;
}

/** 展示可局部恢复的页面错误，重试动作由拥有数据来源的父组件提供。 */
function PageError({ title, message, onRetry }: { title: string; message?: string; onRetry: () => void }) {
  return <section className="fyt-page-state fyt-page-state-error" role="alert"><strong>{title}</strong><p>{message || "这部分数据暂时无法读取，其他页面仍可继续使用。"}</p><button type="button" onClick={onRetry}>重新加载</button></section>;
}

/**
 * 已登录后的应用控制器：维护当前入口、任务筛选、主题和首次引导状态，
 * 并将共享概览、消息与连接状态传递给壳层和各页面。
 */
function Dashboard({ initialUser, onLogout }: { initialUser: User; onLogout: () => void }) {
  const [active, setActive] = useState<string>("overview");
  const [selectedJobId, setSelectedJobId] = useState("");
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("all");
  const [moreOpen, setMoreOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() => localStorage.getItem("fyt-web-theme") === "dark" ? "dark" : "light");
  const [tourOpen, setTourOpen] = useState(false);
  const { overviewData, dashboardData, errors, loading, refreshing, online, user, unreadCount, refresh } = useDashboardData(initialUser);
  // 消息已读后复用同一个顶层刷新入口，使侧栏未读数和工作台通知同时更新。
  const handleNotificationChanged = useCallback(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    // 主题写在根节点数据属性上，所有设计令牌可在一次切换中同步生效。
    document.documentElement.dataset.theme = theme;  // 根节点数据属性驱动令牌切换，避免逐组件换肤
    localStorage.setItem("fyt-web-theme", theme);  // 持久化主题偏好，下次访问保持相同外观
  }, [theme]);

  useEffect(() => {
    if (!loading && overviewData && !localStorage.getItem("fyt-web-guide-v1")) {
      // 稍作延迟让首页布局稳定后再测量引导目标，避免聚光位置使用加载骨架尺寸。
      const timer = window.setTimeout(() => setTourOpen(true), 700);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [loading, overviewData]);

  const features = overviewData?.features ?? [];
  const featureKey = active.startsWith("feature:") ? active.slice(8) : ""; // 业务工作区沿用一个前缀路由承载具体功能键。
  const feature = features.find((item) => item.key === featureKey);
  const title = feature?.title || getNavigationItem(active)?.label || "工作台";
  const pendingUsers = user.role === "admin" ? (overviewData?.metrics.pending_users ?? dashboardData?.metrics.pending_users ?? 0) : 0;
  const pendingReviews = dashboardData?.status_breakdown.review ?? 0;

  /** 切换一级页面，并清除仅属于任务或业务工作区的临时定位状态。 */
  function navigate(key: string) {
    if (!isNavigationAllowed(getNavigationItem(key), user.role)) {  // 越权入口直接回工作台，隐藏导航不能替代后端鉴权
      setMoreOpen(false);
      setActive("overview");
      return;
    }
    setSelectedJobId("");
    setTaskFilter("all");
    setMoreOpen(false);
    setActive(key);
  }

  /** 从业务模块列表进入指定功能的新任务工作区。 */
  function openFeature(key: string) {
    setSelectedJobId("");
    setActive(`feature:${key}`);
  }

  /** 打开任务中心的待确认筛选，集中处理两阶段业务计划。 */
  function openReviews() {
    setSelectedJobId("");
    setTaskFilter("review");
    setActive("tasks");
  }

  /** 从工作台指标直接进入对应任务筛选。 */
  function openTaskFilter(filter: TaskFilter) {
    setSelectedJobId("");
    setTaskFilter(filter);
    setActive("tasks");
  }

  /**
   * 根据任务动作反向定位业务模块，并携带任务编号恢复对应结果或复核界面。
   * 复核动作名称与基础动作不同，因此先使用显式映射，再回退通用前缀规则。
   */
  function openAction(action: string, jobId: string) {
    const reviewFeatures: Record<string, string> = {
      "web.reconcile.review": "reconcile",
      "web.pivot.review": "pivot",
      "web.invoice.review": "invoice",
      "web.compare.review": "compare",
      "web.supplier_batch.review": "supplier_batch",
    };
    const key = reviewFeatures[action] || (action.startsWith("web.") ? action.slice(4) : action.split(".")[0]);  // 复核动作名特殊，先查显式映射再退回前缀规则
    setSelectedJobId(jobId);
    setActive(`feature:${key}`);
  }

  /** 关闭首次引导并持久记录，后续会话不再自动弹出。 */
  function closeTour() {
    localStorage.setItem("fyt-web-guide-v1", "1");
    setTourOpen(false);
  }

  /** 重新并行加载共享数据；若业务入口已失效，则回退到工作台。 */
  function retrySection(section: "overview" | "dashboard" | "notifications") {
    void refresh();
    if (section === "overview" && active !== "overview" && !feature) setActive("overview");
  }

  /**
   * 按当前路由键渲染页面，并在内容渲染前处理初始加载、完全失败和角色越权。
   * 每个大型区域单独包裹错误边界，避免组件渲染异常扩散到壳层导航。
   */
  function renderPage() {
    if (loading && !overviewData && !dashboardData) return <PageLoading />;
    if (!overviewData && !dashboardData) return <PageError title="工作台暂时无法显示" message="概览和任务数据都没有读取成功，请检查网络后重试。" onRetry={() => void refresh()} />;
    if (feature) return <SectionErrorBoundary title="业务工作区" onRetry={() => void refresh()}><FeatureWorkspace feature={feature} initialJobId={selectedJobId || undefined} onBack={() => navigate("features")} onCompleted={() => void refresh()} /></SectionErrorBoundary>;
    if (!isNavigationAllowed(getNavigationItem(active), user.role)) return <PageError title="暂时没有访问权限" message="当前账号不能使用这个入口，请返回工作台继续处理业务。" onRetry={() => navigate("overview")} />;
    if (active === "overview") {
      return dashboardData ? <SectionErrorBoundary title="任务调度板" onRetry={() => retrySection("dashboard")}><DispatchBoard data={dashboardData} user={user} features={features} onRefresh={() => void refresh()} setActive={navigate} onOpenReviews={openReviews} onOpenTaskFilter={openTaskFilter} /></SectionErrorBoundary> : <PageError title="任务调度板暂时无法显示" onRetry={() => retrySection("dashboard")} />;
    }
    if (active === "workshop") return <SectionErrorBoundary title="现场问题" onRetry={() => void refresh()}><WorkshopIssuePage /></SectionErrorBoundary>;
    if (active === "features") return <SectionErrorBoundary title="业务模块" onRetry={() => retrySection("overview")}><FeaturesPage features={features} onOpen={openFeature} /></SectionErrorBoundary>;
    if (active === "library") return <SectionErrorBoundary title="数据库" onRetry={() => void refresh()}><FileLibraryPage /></SectionErrorBoundary>;
    if (active === "batch-track") return <SectionErrorBoundary title="批次跟踪" onRetry={() => void refresh()}><BatchTrackPage /></SectionErrorBoundary>;
    if (active === "reports") return <SectionErrorBoundary title="报表中心" onRetry={() => void refresh()}><ReportPage /></SectionErrorBoundary>;
    if (active === "daily-report" && user.role === "admin") return <SectionErrorBoundary title="日清数据看板" onRetry={() => void refresh()}><DailyReportPage /></SectionErrorBoundary>;
    if (active === "tasks") return <SectionErrorBoundary title="任务中心" onRetry={() => void refresh()}><TaskCenterPage onOpenFeature={openAction} initialFilter={taskFilter} /></SectionErrorBoundary>;
    if (active === "notifications") return <SectionErrorBoundary title="消息中心" onRetry={() => retrySection("notifications")}><NotificationCenterPage onChanged={handleNotificationChanged} /></SectionErrorBoundary>;
    if (active === "security") return <AccountSecurityPage onLoggedOut={onLogout} />;
    if (active === "users" && user.role === "admin") return <SectionErrorBoundary title="系统管理" onRetry={() => void refresh()}><AdminPage currentUserId={user.id} onChanged={() => void refresh()} /></SectionErrorBoundary>;
    return <PageError title="页面不存在" message="该入口暂时不可用，请返回工作台继续处理业务。" onRetry={() => navigate("overview")} />;
  }

  return <WebShell activeKey={active} title={title} user={user} theme={theme} online={online} pendingUsers={pendingUsers} pendingReviews={pendingReviews} unreadCount={unreadCount} moreOpen={moreOpen} onNavigate={(key: WebRouteKey) => navigate(key)} onToggleTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")} onOpenMore={() => setMoreOpen(true)} onCloseMore={() => setMoreOpen(false)} onLogout={onLogout}>
    {errors.overview && active !== "features" ? <div className="fyt-partial-notice" role="status">部分概览数据暂时无法读取，<button type="button" onClick={() => retrySection("overview")}>重新加载</button></div> : null}
    {errors.dashboard && active !== "overview" ? <div className="fyt-partial-notice" role="status">任务状态暂时无法读取，<button type="button" onClick={() => retrySection("dashboard")}>重新加载</button></div> : null}
    {errors.notifications ? <div className="fyt-partial-notice" role="status">消息暂时无法读取，<button type="button" onClick={() => retrySection("notifications")}>重新加载</button></div> : null}
    {refreshing ? <div className="fyt-refresh-line" role="status" aria-live="polite">正在更新工作台数据</div> : null}
    <GuidedTour open={tourOpen} onClose={closeTour} />
    {/* 路由、任务定位或筛选变化时重建舞台，使页面内部一次性状态不会串到另一工作流。 */}
    <div className="fyt-route-stage" key={`${active}:${selectedJobId}:${taskFilter}`}>{renderPage()}</div>
  </WebShell>;
}

/** 验证本地会话并在认证页与已登录工作台之间切换。 */
export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  // 令牌无效或网络请求失败都先回到登录页，避免在未知身份下渲染受保护内容。
  useEffect(() => { void me().then((result) => setUser(result.user)).catch(() => clearToken()).finally(() => setChecking(false)); }, []);  // 会话无效或请求失败都回登录页，避免未知身份渲染受保护内容

  /** 尽力撤销服务端会话；即使网络失败也清除本机令牌和用户状态。 */
  function onLogout() { void logout().catch(() => undefined).finally(() => { clearToken(); setUser(null); }); }  // 即使服务端撤销失败也清除本地会话
  if (checking) return <PageLoading text="正在验证登录状态..." />;
  return user ? <Dashboard initialUser={user} onLogout={onLogout} /> : <AuthScreen onAuthed={setUser} />;
}
