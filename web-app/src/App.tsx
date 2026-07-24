import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { clearToken, dashboard, getToken, login, logout, me, overview, register, reviewUser, setToken, users, type DashboardData, type Feature, type Overview, type User } from "./api";
import { FeatureWorkspace } from "./FeatureWorkspace";
import { DashboardPage } from "./DashboardPage";
import { TaskCenterPage, type TaskFilter } from "./TaskCenterPage";
import { Icon } from "./icons";

type AuthMode = "login" | "register";

function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`brand ${compact ? "brand-compact" : ""}`}><img src="/logo.png" alt="峰运通" /><div><strong>峰运通</strong><span>数据管理系统</span></div></div>;
}

function AuthScreen({ onAuthed }: { onAuthed: (user: User) => void }) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ type: "error" | "success"; text: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setNotice(null);
    try {
      if (mode === "register") {
        const result = await register(username, displayName, password);
        setNotice({ type: "success", text: result.message });
        setMode("login"); setPassword("");
      } else {
        const result = await login(username, password);
        setToken(result.token); onAuthed(result.user);
      }
    } catch (error) { setNotice({ type: "error", text: error instanceof Error ? error.message : "请求失败" }); }
    finally { setBusy(false); }
  }

  return <main className="auth-shell">
    <section className="auth-story">
      <div className="story-glow" />
      <Brand />
      <div className="story-copy"><p className="eyebrow">LAN WORKSPACE</p><h1>让每一张业务表<br /><em>都流向正确的地方。</em></h1><p>从考勤填报到采购对账，峰运通把重复的数据工作放进同一个清晰、可靠的工作台。</p></div>
      <div className="story-foot"><span><i className="signal-dot" />局域网安全连接</span><span>v1.3.0</span></div>
    </section>
    <section className="auth-panel"><div className="auth-card">
      <div className="mobile-brand"><Brand compact /></div>
      <div className="auth-heading"><span className="auth-kicker">{mode === "login" ? "欢迎回来" : "加入工作台"}</span><h2>{mode === "login" ? "登录你的账号" : "申请一个账号"}</h2><p>{mode === "login" ? "使用已审核的账号继续处理业务" : "提交后由管理员审核，审核通过即可登录"}</p></div>
      <form onSubmit={submit} className="auth-form">
        <label>账号<input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="请输入账号" autoComplete="username" required /></label>
        {mode === "register" ? <label>姓名<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="例如：张三" required /></label> : null}
        <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === "login" ? "请输入密码" : "至少 8 位字符"} autoComplete={mode === "login" ? "current-password" : "new-password"} required /></label>
        {notice ? <div className={`auth-notice ${notice.type}`}>{notice.text}</div> : null}
        <button className="primary-button auth-submit" disabled={busy}>{busy ? "请稍候..." : mode === "login" ? "登录工作台" : "提交注册申请"}<Icon name="arrow" size={18} /></button>
      </form>
      <div className="auth-switch">{mode === "login" ? <>还没有账号？<button onClick={() => { setMode("register"); setNotice(null); }}>注册申请</button></> : <>已有账号？<button onClick={() => { setMode("login"); setNotice(null); }}>返回登录</button></>}</div>
    </div><p className="auth-legal">仅供峰运通内部使用 · 数据保存在本机服务端</p></section>
  </main>;
}

function Metric({ icon, label, value, tone }: { icon: string; label: string; value: string | number; tone?: string }) {
  return <div className="metric"><div className={`metric-icon ${tone || ""}`}><Icon name={icon} size={19} /></div><div><span>{label}</span><strong>{value}</strong></div></div>;
}

function Sidebar({ active, setActive, user, pendingUsers, pendingReviews, onLogout }: { active: string; setActive: (key: string) => void; user: User; pendingUsers: number; pendingReviews: number; onLogout: () => void }) {
  const links = [{ key: "overview", label: "工作台", icon: "grid" }, { key: "features", label: "业务模块", icon: "database" }, { key: "tasks", label: "任务中心", icon: "activity" }, ...(user.role === "admin" ? [{ key: "users", label: "账号审核", icon: "users" }] : [])];
  return <aside className="dashboard-sidebar"><div className="sidebar-top"><Brand compact /></div><nav>{links.map((link) => <button className={active === link.key || link.key === "features" && active.startsWith("feature:") ? "active" : ""} key={link.key} onClick={() => setActive(link.key)}><Icon name={link.icon} size={18} /><span>{link.label}</span>{link.key === "tasks" && pendingReviews > 0 ? <i className="nav-count review-count" aria-label={`${pendingReviews} 个任务待复核`}>{pendingReviews > 99 ? "99+" : pendingReviews}</i> : link.key === "users" && pendingUsers > 0 ? <i className="nav-count" aria-label={`${pendingUsers} 个账号待审核`}>{pendingUsers > 99 ? "99+" : pendingUsers}</i> : null}</button>)}</nav><div className="sidebar-bottom"><div className="profile"><div className="avatar">{user.display_name.slice(0, 1)}</div><div><strong>{user.display_name}</strong><span>{user.role === "admin" ? "系统管理员" : "业务成员"}</span></div></div><button className="logout-button" onClick={onLogout} aria-label="退出登录" title="退出登录"><Icon name="logout" size={18} /></button></div></aside>;
}

function Topbar({ title, user, onLogout }: { title: string; user: User; onLogout: () => void }) {
  return <header className="dashboard-topbar"><div><span className="topbar-path">峰运通 / 工作空间</span><h1>{title}</h1></div><div className="topbar-right"><span className="connection"><i />局域网已连接</span><div className="top-profile"><div className="avatar small">{user.display_name.slice(0, 1)}</div><span>{user.display_name}</span></div><button className="mobile-logout" onClick={onLogout}><Icon name="logout" size={18} /></button></div></header>;
}

function OverviewPage({ data, setActive }: { data: Overview; setActive: (key: string) => void }) {
  const grouped = useMemo(() => data.features.reduce<Record<string, Feature[]>>((all, item) => { (all[item.group] ||= []).push(item); return all; }, {}), [data.features]);
  return <div className="page-body"><section className="welcome-band"><div><span className="section-label">今天的工作台</span><h2>你好，{data.user.display_name}</h2><p>把注意力留给业务，重复的表格处理交给峰运通。</p></div><div className="welcome-mark"><span>FYT</span><i /></div></section><section className="metric-grid"><Metric icon="activity" label="可用业务模块" value={data.features.length} tone="blue" /><Metric icon="users" label="已审核成员" value={data.metrics.approved_users} tone="green" /><Metric icon="clock" label="待处理申请" value={data.metrics.pending_users} tone="orange" /><Metric icon="check" label="已完成任务" value={data.metrics.output_jobs} tone="purple" /></section><section className="section-head"><div><span className="section-label">快速开始</span><h3>选择一个业务模块</h3></div><button className="text-button" onClick={() => setActive("features")}>查看全部 <Icon name="arrow" size={16} /></button></section><div className="feature-groups">{Object.entries(grouped).slice(0, 3).map(([group, items]) => <div className="feature-group" key={group}><div className="group-title"><span>{group}</span><i /></div>{items.slice(0, 3).map((item, index) => <button className="feature-row" key={item.key} onClick={() => setActive(`feature:${item.key}`)}><span className="feature-index">0{index + 1}</span><span><strong>{item.title}</strong><small>{item.description}</small></span><Icon name="arrow" size={17} /></button>)}</div>)}</div></div>;
}

function FeaturesPage({ features, onOpen }: { features: Feature[]; onOpen: (key: string) => void }) {
  return <div className="page-body"><div className="page-intro"><span className="section-label">业务能力</span><h2>业务模块</h2><p>文件在服务端隔离工作区处理，完成后可直接下载结果。</p></div><div className="all-features">{features.map((feature, index) => <article className="feature-card" key={feature.key}><div className="feature-card-top"><span>{String(index + 1).padStart(2, "0")}</span><Icon name={index % 2 ? "activity" : "database"} size={20} /></div><h3>{feature.title}</h3><p>{feature.description}</p><button className="outline-button" onClick={() => onOpen(feature.key)}>打开功能 <Icon name="arrow" size={15} /></button></article>)}</div></div>;
}

function UsersPage({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<User[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [busyId, setBusyId] = useState(0);
  async function load() { try { setLoading(true); setItems((await users()).users); setError(""); } catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  async function decide(id: number, decision: "approve" | "reject") { setBusyId(id); setError(""); try { await reviewUser(id, decision); await load(); onChanged(); } catch (reason) { setError(reason instanceof Error ? reason.message : "审核失败"); } finally { setBusyId(0); } }
  return <div className="page-body"><div className="page-intro admin-intro"><div><span className="section-label">管理员中心</span><h2>账号审核</h2><p>审核新成员申请，管理局域网工作台的访问权限。</p></div><div className="admin-stat"><span>待处理</span><strong>{items.filter((item) => item.status === "pending").length}</strong></div></div>{error ? <div className="auth-notice error">{error}</div> : null}<div className="user-table"><div className="table-head"><span>成员</span><span>状态</span><span>申请时间</span><span>操作</span></div>{loading ? <div className="empty-row">正在加载成员...</div> : items.map((item) => <div className="table-row" key={item.id}><div className="member-cell"><div className="avatar table-avatar">{item.display_name.slice(0, 1)}</div><div><strong>{item.display_name}</strong><small>@{item.username}</small></div></div><span className={`status status-${item.status}`}>{item.status === "pending" ? "待审核" : item.status === "approved" ? "已通过" : "已拒绝"}</span><span className="muted-cell">{new Date(item.created_at).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" })}</span><div className="row-actions">{item.status === "pending" ? <><button className="approve" disabled={busyId === item.id} onClick={() => void decide(item.id, "approve")}><Icon name="check" size={15} />{busyId === item.id ? "处理中" : "通过"}</button><button className="reject" disabled={busyId === item.id} onClick={() => void decide(item.id, "reject")}><Icon name="x" size={15} />拒绝</button></> : <span className="muted-cell">无需操作</span>}</div></div>)}</div></div>;
}

function Dashboard({ initialUser, onLogout }: { initialUser: User; onLogout: () => void }) {
  const [user, setUser] = useState(initialUser); const [data, setData] = useState<Overview | null>(null); const [dashboardData, setDashboardData] = useState<DashboardData | null>(null); const [active, setActive] = useState("overview"); const [selectedJobId, setSelectedJobId] = useState(""); const [taskFilter, setTaskFilter] = useState<TaskFilter>("all"); const [error, setError] = useState("");
  const load = useCallback(async () => { try { const [next, board] = await Promise.all([overview(), dashboard()]); setData(next); setDashboardData(board); setUser(next.user); setError(""); } catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); } }, []);
  useEffect(() => { void load(); }, [load]);
  const feature = active.startsWith("feature:") ? data?.features.find((item) => item.key === active.slice(8)) : undefined;
  const title = feature?.title || (active === "overview" ? "工作台" : active === "features" ? "业务模块" : active === "tasks" ? "任务中心" : "账号审核");
  function openAction(action: string, jobId: string) {
    const reviewFeatures: Record<string, string> = {
      "web.reconcile.review": "reconcile",
      "web.pivot.review": "pivot",
      "web.invoice.review": "invoice",
      "web.compare.review": "compare",
    };
    const key = reviewFeatures[action] || (action.startsWith("web.") ? action.slice(4) : action.split(".")[0]);
    setSelectedJobId(jobId);
    setActive(`feature:${key}`);
  }
  return <div className="dashboard-shell"><Sidebar active={active} setActive={(key) => { setSelectedJobId(""); setTaskFilter("all"); setActive(key); }} user={user} pendingUsers={data?.metrics.pending_users || 0} pendingReviews={dashboardData?.status_breakdown.review || 0} onLogout={onLogout} /><main className="dashboard-main"><Topbar title={title} user={user} onLogout={onLogout} />{error ? <div className="global-error">{error}</div> : null}<div className="route-stage" key={`${active}:${selectedJobId}:${taskFilter}`}>{data ? feature ? <FeatureWorkspace feature={feature} initialJobId={selectedJobId || undefined} onBack={() => { setSelectedJobId(""); setActive("features"); }} onCompleted={load} /> : active === "overview" && dashboardData ? <DashboardPage data={dashboardData} user={user} onRefresh={() => void load()} setActive={(key) => { setSelectedJobId(""); setTaskFilter("all"); setActive(key); }} onOpenReviews={() => { setSelectedJobId(""); setTaskFilter("review"); setActive("tasks"); }} /> : active === "features" ? <FeaturesPage features={data.features} onOpen={(key) => { setSelectedJobId(""); setActive(`feature:${key}`); }} /> : active === "tasks" ? <TaskCenterPage onOpenFeature={openAction} initialFilter={taskFilter} /> : <UsersPage onChanged={load} /> : <div className="loading-state">正在连接服务端...</div>}</div></main></div>;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null); const [checking, setChecking] = useState(Boolean(getToken()));
  useEffect(() => { if (!getToken()) return; me().then((result) => setUser(result.user)).catch(() => clearToken()).finally(() => setChecking(false)); }, []);
  function onLogout() { void logout().catch(() => undefined).finally(() => { clearToken(); setUser(null); }); }
  if (checking) return <div className="loading-state full">正在验证登录状态...</div>;
  return user ? <Dashboard initialUser={user} onLogout={onLogout} /> : <AuthScreen onAuthed={setUser} />;
}
