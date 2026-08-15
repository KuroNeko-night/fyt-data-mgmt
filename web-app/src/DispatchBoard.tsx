/**
 * 工作台任务调度板。
 *
 * 组合状态卡片、最近任务、待办事项、快速入口和近七日趋势；所有数量均来自
 * 服务端 `dashboard` 聚合结果，页面只负责按角色裁剪展示和跳转任务筛选。
 */
import { useEffect, useMemo, useState } from "react";
import { downloadJobFile, type DashboardData, type Feature, type JobFile, type User } from "./api";
import type { TaskFilter } from "./TaskCenterPage";
import { Icon } from "./icons";
import ArtAsset from "./ui/ArtAsset";

/** 调度板入参：服务端聚合数据、当前用户、可用业务功能以及页面跳转回调。 */
type Props = {
  data: DashboardData;
  user: User;
  features: Feature[];
  onRefresh: () => void;
  setActive: (key: string) => void;
  onOpenReviews: () => void;
  onOpenTaskFilter: (filter: TaskFilter) => void;
};

// 任务状态到界面文案、色调的本地映射；`review` 是复核阶段在前端合成的展示状态。
const STATUS_LABEL: Record<string, string> = {
  queued: "排队",
  running: "处理中",
  review: "待确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

const STATUS_TONE: Record<string, string> = {
  queued: "wait",
  running: "run",
  review: "wait",
  completed: "done",
  failed: "fail",
  cancelled: "off",
  interrupted: "fail",
};

/** 生成工作台紧凑时间戳，固定补零以避免列表列宽随日期变化。 */
function clockLabel(value: string) {
  const date = new Date(value);
  return String(date.getMonth() + 1).padStart(2, "0") + "/" + String(date.getDate()).padStart(2, "0") + " " + String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
}

/** 格式化最近输出文件大小。 */
function sizeLabel(value: number) {
  if (value < 1024) return value + " B";
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
  return (value / 1024 / 1024).toFixed(1) + " MB";
}

/**
 * 订阅媒体查询变化。
 * 除 change 事件外保留 resize 监听，兼容部分旧 WebView 对 MediaQueryList 事件更新不及时的情况。
 */
function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches); // 始终从媒体查询对象读取结果，不自行推断窗口宽度。
    update();
    media.addEventListener("change", update);
    window.addEventListener("resize", update);
    return () => {
      media.removeEventListener("change", update);
      window.removeEventListener("resize", update);
    };
  }, [query]);
  return matches;
}

/** 工作台顶部调度板：汇总需要确认、处理中、排队和异常任务，并提供直达筛选入口。 */
function Board({ data, user, onRefresh, onOpenReviews, onOpenTaskFilter }: Props) {
  const statusBreakdown = data.status_breakdown;
  // 失败与进程中断都需要人工处理，因此在首页合并为一个异常任务入口。
  const abnormal = (statusBreakdown.failed || 0) + (statusBreakdown.interrupted || 0);
  const todayRow = data.trend[data.trend.length - 1];
  const todayTotal = todayRow?.total || 0;
  const doneToday = todayRow?.completed || 0;
  // 卡片配置同时定义文案、色调和跳转筛选，避免显示与点击行为分散在 JSX 中。
  const statuses = [
    { key: "review", label: "待确认", note: "需要你的选择", tone: "warning", filter: "review" as TaskFilter, icon: "check" },
    { key: "running", label: "处理中", note: "正在执行的任务", tone: "info", filter: "active" as TaskFilter, icon: "activity" },
    { key: "queued", label: "排队", note: "等待执行的任务", tone: "neutral", filter: "active" as TaskFilter, icon: "clock" },
    { key: "abnormal", label: "异常任务", note: "失败或中断", tone: "danger", filter: "failed" as TaskFilter, icon: "x" },
  ] as const;

  return <section className="dsp-board" aria-label="任务调度板">
    <header className="dsp-board-head">
      <div className="dsp-board-art"><ArtAsset name="workbench-data-ribbon.webp" loading="eager" /></div>
      <div className="dsp-board-id"><span className="dsp-eyebrow">今日工作台</span><h2>{user.display_name}，{abnormal > 0 ? "有异常任务需要处理" : (statusBreakdown.review || 0) > 0 ? "有任务等你确认" : "当前没有紧急待办"}</h2></div>
      <div className="dsp-board-meta"><span className="dsp-stamp">更新于 <time className="dsp-num" dateTime={data.generated_at}>{clockLabel(data.generated_at)}</time></span><button className="dsp-icon-btn" type="button" onClick={onRefresh} title="刷新调度板" aria-label="刷新调度板"><Icon name="refresh" size={16} /></button></div>
    </header>
    <div className="dsp-board-body">
      <div className="dsp-status-grid" role="list" aria-label="当前任务状态">
        {statuses.map((status) => {
          const count = status.key === "abnormal" ? abnormal : statusBreakdown[status.key] || 0;
          return <button className="dsp-status-block" data-tone={status.tone} type="button" key={status.key} onClick={() => onOpenTaskFilter(status.filter)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpenTaskFilter(status.filter); } }} aria-label={status.label + count + "项，进入任务中心筛选"}><span className="dsp-status-icon"><Icon name={status.icon} size={17} /></span><span className="dsp-status-copy"><strong>{status.label}</strong><small>{status.note}</small></span><b className="dsp-num">{count}</b><Icon name="arrow" size={14} /></button>;
        })}
      </div>
    </div>
    <footer className="dsp-board-foot"><span>按任务创建日期统计</span><span className="dsp-today-summary"><b className="dsp-num">{todayTotal}</b> 今日创建 <i aria-hidden="true" /> <b className="dsp-num">{doneToday}</b> 其中已完成</span>{statusBreakdown.review > 0 ? <button className="dsp-foot-cta" type="button" onClick={onOpenReviews}>去确认 {statusBreakdown.review} 项 <Icon name="arrow" size={13} /></button> : null}</footer>
  </section>;
}

/** 最近任务台账：按任务归并输出文件，并在移动端限制首屏记录数量。 */
function Ledger({ data, setActive }: { data: DashboardData; setActive: (key: string) => void }) {
  const [error, setError] = useState("");
  const mobile = useMediaQuery("(max-width: 767px)");
  const filesByJob = useMemo(() => {
    // recent_files 是扁平列表，先按 job_id 建索引可避免每渲染一项任务都遍历全部文件。
    const map = new Map<string, DashboardData["recent_files"]>();
    for (const file of data.recent_files) map.set(file.job_id, (map.get(file.job_id) || []).concat(file));
    return map;
  }, [data.recent_files]);

  /** 把工作台精简文件信息转换成下载接口需要的 JobFile。 */
  async function downloadFile(file: DashboardData["recent_files"][number]) {
    setError("");
    const jobFile: JobFile = { name: file.name, size: file.size, url: file.url };
    try {
      await downloadJobFile(jobFile);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "下载失败");
    }
  }

  // 移动端减少首屏条目，保留触控滚动空间；完整记录始终可从任务中心查看。
  const jobs = data.recent_jobs.slice(0, mobile ? 4 : 8);
  return <section className="dsp-cell dsp-ledger"><header className="dsp-cell-head"><div><span className="dsp-kicker">最近处理</span><h2>最近任务</h2></div><button className="dsp-link" type="button" onClick={() => setActive("tasks")}>全部任务 <Icon name="arrow" size={13} /></button></header>{error ? <p className="dsp-err" role="alert">{error}</p> : null}{data.recent_jobs.length === 0 ? <p className="dsp-empty">还没有任务。可以从快速开始选择一个业务模块，先处理第一张表。</p> : <ol className="dsp-rows">{jobs.map((job) => { const status = job.review_pending ? "review" : job.status; const files = filesByJob.get(job.id) || []; return <li className="dsp-row" key={job.id}><div className="dsp-row-main"><i className={"dsp-tick tone-" + (STATUS_TONE[status] || "off")} aria-hidden="true" /><div className="dsp-row-id"><strong>{job.title}</strong><time className="dsp-num" dateTime={job.created_at}>{clockLabel(job.created_at)}</time></div><span className={"dsp-tag tone-" + (STATUS_TONE[status] || "off")}>{STATUS_LABEL[status] || status}</span></div>{job.error ? <p className="dsp-row-err">{job.error}</p> : null}{files.length > 0 ? <ul className="dsp-files">{files.map((file) => <li key={file.job_id + "-" + file.name}><button type="button" onClick={() => void downloadFile(file)} title={"下载 " + file.name}><Icon name="download" size={13} /><span className="dsp-file-name">{file.name}</span><span className="dsp-num dsp-file-size">{sizeLabel(file.size)}</span></button></li>)}</ul> : null}</li>; })}</ol>}</section>;
}

/** 以轻量 CSS 柱状图展示近七日任务创建量、失败占比和日均线。 */
function Trend({ trend }: { trend: DashboardData["trend"] }) {
  // 峰值至少为 1，额外留出 15% 顶部空间用于显示柱顶数值。
  const peak = Math.max(...trend.map((item) => item.total), 1);
  const scale = peak * 1.15;
  const avg = trend.reduce((sum, item) => sum + item.total, 0) / (trend.length || 1); // 空数组分母回退为 1。
  const today = trend[trend.length - 1]?.total || 0;
  const delta = today - avg;
  return <section className="dsp-cell dsp-trend"><header className="dsp-cell-head"><div><span className="dsp-kicker">工作负载</span><h2>近七日任务创建量</h2></div><span className="dsp-cell-note">日均 <b className="dsp-num">{avg.toFixed(1)}</b>{Math.abs(delta) >= 0.05 ? <em className={delta > 0 ? "up" : "down"}>{delta > 0 ? "↑" : "↓"}{Math.abs(delta).toFixed(1)}</em> : null}</span></header><div className="dsp-chart" role="img" aria-label={"近七日任务创建量：" + trend.map((item) => item.date.slice(5) + " " + item.total + " 件" + (item.failed ? "（失败 " + item.failed + " 件）" : "")).join("，") + "；日均 " + avg.toFixed(1) + " 件"}><i className="dsp-avg-line" style={{ bottom: "calc(var(--dsp-axis, 0px) + (100% - var(--dsp-axis, 0px)) * " + (avg / scale).toFixed(4) + ")" }} aria-hidden="true" />{trend.map((item, index) => { const isToday = index === trend.length - 1; const failPercent = item.total > 0 ? item.failed / item.total * 100 : 0; return <div className="dsp-chart-col" key={item.date}><div className="dsp-chart-track"><div className={"dsp-chart-bar" + (isToday ? " is-today" : "")} style={{ height: item.total ? Math.max(3, item.total / scale * 100) + "%" : "2px" }}>{item.total > 0 ? <span className="dsp-num">{item.total}</span> : null}{item.failed > 0 ? <i className="dsp-chart-fail" style={{ height: failPercent + "%" }} aria-hidden="true" /> : null}</div></div><div className="dsp-chart-foot"><small className="dsp-num">{item.date.slice(5).replace("-", "/")}</small>{item.failed > 0 ? <em>失败 {item.failed}</em> : null}</div></div>; })}</div></section>;
}

/** 根据最近使用频率生成快速入口；无使用历史时回退到可用业务模块顺序。 */
function Launcher({ usage, features, setActive }: { usage: DashboardData["feature_usage"]; features: Feature[]; setActive: (key: string) => void }) {
  const items = usage.length > 0 ? usage.slice(0, 5).map((item) => ({ key: item.key, title: item.title, countLabel: item.count + " 次" })) : features.slice(0, 5).map((feature) => ({ key: feature.key, title: feature.title, countLabel: "开始处理" }));
  return <section className="dsp-cell dsp-launch"><header className="dsp-cell-head"><div><span className="dsp-kicker">常用入口</span><h2>快速开始</h2></div><button className="dsp-link" type="button" onClick={() => setActive("features")}>全部模块 <Icon name="arrow" size={13} /></button></header>{items.length === 0 ? <p className="dsp-empty">暂无可用业务模块。</p> : <ul className="dsp-launch-list">{items.map((item) => <li key={item.key}><button type="button" onClick={() => setActive("feature:" + item.key)}><span className="dsp-launch-name">{item.title}</span><span className="dsp-launch-count dsp-num">{item.countLabel}</span><Icon name="arrow" size={13} /></button></li>)}</ul>}</section>;
}

/** 汇总人工复核、异常任务、账号审核和普通通知，按移动端容量裁剪普通通知。 */
function Alerts({ data, user, setActive, onOpenReviews, onOpenTaskFilter }: Props) {
  const notes = data.notifications || [];
  const mobile = useMediaQuery("(max-width: 767px)");
  const reviews = data.status_breakdown.review || 0;
  const abnormal = (data.status_breakdown.failed || 0) + (data.status_breakdown.interrupted || 0);
  // 非管理员不应看到账号审核数量，即使旧缓存数据中意外带有该指标也不展示。
  const pendingUsers = user.role === "admin" ? data.metrics.pending_users : 0;
  const nothing = notes.length === 0 && reviews === 0 && pendingUsers === 0 && abnormal === 0;
  return <section className="dsp-cell dsp-alerts"><header className="dsp-cell-head"><div><span className="dsp-kicker">优先处理</span><h2>需要处理</h2></div></header>{nothing ? <p className="dsp-empty">没有待办。</p> : <ul className="dsp-alert-list">{reviews > 0 ? <li><button type="button" onClick={onOpenReviews}><span className="dsp-alert-dot tone-wait" aria-hidden="true" /><span><strong>{reviews} 项等你确认</strong><small>确认业务选择后才会继续生成</small></span><Icon name="arrow" size={14} /></button></li> : null}{abnormal > 0 ? <li><button type="button" onClick={() => onOpenTaskFilter("failed")}><span className="dsp-alert-dot tone-fail" aria-hidden="true" /><span><strong>{abnormal} 项异常任务</strong><small>检查失败原因或重新执行</small></span><Icon name="arrow" size={14} /></button></li> : null}{pendingUsers > 0 ? <li><button type="button" onClick={() => setActive("users")}><span className="dsp-alert-dot tone-wait" aria-hidden="true" /><span><strong>{pendingUsers} 个账号待审核</strong><small>审核通过后才能进入工作台</small></span><Icon name="arrow" size={14} /></button></li> : null}{notes.slice(0, mobile ? 3 : 12).map((note) => <li key={note.kind + "-" + note.id}><div className="dsp-alert-static"><span className="dsp-alert-dot" aria-hidden="true" /><span><strong>{note.title}</strong><small>{note.content}</small></span></div></li>)}</ul>}</section>;
}

/** 组合调度板、最近任务、待办、快速入口和趋势图的工作台布局。 */
export function DispatchBoard(props: Props) {
  return <div className="dsp fyt-content-container"><Board {...props} /><div className="dsp-paper"><div className="dsp-grid"><Ledger data={props.data} setActive={props.setActive} /><div className="dsp-rail"><Alerts {...props} /><Launcher usage={props.data.feature_usage} features={props.features} setActive={props.setActive} /><Trend trend={props.data.trend} /></div></div></div></div>;
}

export default DispatchBoard;
