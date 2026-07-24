import { useMemo, useState } from "react";
import { downloadJobFile, type DashboardData, type JobFile, type User } from "./api";
import { Icon } from "./icons";

type Props = {
  data: DashboardData;
  user: User;
  onRefresh: () => void;
  setActive: (key: string) => void;
  onOpenReviews: () => void;
};

const statusLabels: Record<string, string> = {
  queued: "排队中",
  running: "处理中",
  completed: "已完成",
  review: "待复核",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

function dateLabel(value: string, withTime = false) {
  return new Date(value).toLocaleString("zh-CN", withTime
    ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }
    : { month: "2-digit", day: "2-digit" });
}

function sizeLabel(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function MiniMetric({ icon, label, value, note, tone }: { icon: string; label: string; value: number; note: string; tone: string }) {
  return <article className={`board-metric ${tone}`}>
    <div className="board-metric-top"><span>{label}</span><i><Icon name={icon} size={17} /></i></div>
    <strong>{value.toLocaleString("zh-CN")}</strong>
    <small>{note}</small>
  </article>;
}

function TrendChart({ data }: { data: DashboardData["trend"] }) {
  const max = Math.max(...data.map((item) => item.total), 1);
  return <div className="trend-chart" aria-label="近七日任务趋势">
    {data.map((item) => <div className="trend-column" key={item.date}>
      <div className="trend-bar-wrap"><div className="trend-bar" style={{ height: `${Math.max(8, item.total / max * 100)}%` }}><span>{item.total || ""}</span></div></div>
      <small>{item.date.slice(5).replace("-", "/")}</small>
    </div>)}
  </div>;
}

function StatusBars({ data }: { data: DashboardData }) {
  const entries = Object.entries(data.status_breakdown).filter(([, count]) => count > 0);
  const total = entries.reduce((sum, [, count]) => sum + count, 0) || 1;
  return <div className="status-bars">
    {entries.length ? entries.map(([status, count]) => <div className="status-bar-row" key={status}>
      <div><span className={`status-dot dot-${status}`} />{statusLabels[status] || status}<strong>{count}</strong></div>
      <div className="status-track"><i className={`status-fill fill-${status}`} style={{ width: `${count / total * 100}%` }} /></div>
    </div>) : <p className="board-empty">还没有任务记录</p>}
  </div>;
}

function JobStatus({ status }: { status: string }) {
  return <span className={`board-status board-status-${status}`}><i />{statusLabels[status] || status}</span>;
}

export function DashboardPage({ data, user, onRefresh, setActive, onOpenReviews }: Props) {
  const [range, setRange] = useState<"7d" | "all">("7d");
  const [downloadError, setDownloadError] = useState("");
  const maxUsage = Math.max(...data.feature_usage.map((item) => item.count), 1);
  const sevenDayMetrics = useMemo(() => data.trend.reduce((total, item) => ({
    total_jobs: total.total_jobs + item.total,
    completed_jobs: total.completed_jobs + item.completed,
    failed_jobs: total.failed_jobs + item.failed,
  }), { total_jobs: 0, completed_jobs: 0, failed_jobs: 0 }), [data.trend]);
  const displayMetrics = range === "7d" ? sevenDayMetrics : data.metrics;
  const reviewPending = data.status_breakdown.review || 0;
  const completedToday = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return data.trend.find((item) => item.date === today)?.completed || 0;
  }, [data.trend]);

  async function download(file: DashboardData["recent_files"][number]) {
    setDownloadError("");
    const jobFile: JobFile = { name: file.name, size: file.size, url: file.url };
    try { await downloadJobFile(jobFile); } catch (error) { setDownloadError(error instanceof Error ? error.message : "下载失败"); }
  }

  return <div className="page-body dashboard-page">
    <section className="board-hero">
      <div><span className="section-label">数据看板 / {dateLabel(data.generated_at)}</span><h2>掌握每一项业务进度</h2><p>你好，{user.display_name}。这里汇总了当前账号的任务、产出与工作台使用情况。</p></div>
      <div className="board-hero-actions"><div className="range-switch" role="tablist"><button className={range === "7d" ? "selected" : ""} onClick={() => setRange("7d")}>近 7 日</button><button className={range === "all" ? "selected" : ""} onClick={() => setRange("all")}>全部任务</button></div><button className="icon-button" onClick={onRefresh} title="刷新看板" aria-label="刷新看板"><Icon name="refresh" size={17} /></button></div>
    </section>

    <section className="board-metric-grid">
      <MiniMetric icon="activity" label="任务总量" value={displayMetrics.total_jobs} note={range === "7d" ? "近 7 日累计" : "当前账号累计"} tone="blue" />
      <MiniMetric icon="check" label="已完成任务" value={displayMetrics.completed_jobs} note={`今日完成 ${completedToday} 项`} tone="green" />
      <MiniMetric icon="clock" label="进行中" value={data.metrics.running_jobs} note="排队、处理与待复核" tone="orange" />
      <MiniMetric icon="x" label="异常任务" value={displayMetrics.failed_jobs} note="需要关注的失败项" tone="red" />
    </section>

    <section className="board-grid board-grid-main">
      <article className="board-panel trend-panel"><div className="board-panel-head"><div><span className="section-label">任务趋势</span><h3>最近七天</h3></div><span className="panel-caption">总任务数</span></div><TrendChart data={data.trend} /></article>
      <article className="board-panel status-panel"><div className="board-panel-head"><div><span className="section-label">任务状态</span><h3>当前分布</h3></div><Icon name="pie" size={19} /></div><StatusBars data={data} /></article>
    </section>

    <section className="board-grid board-grid-secondary">
      <article className="board-panel usage-panel"><div className="board-panel-head"><div><span className="section-label">使用情况</span><h3>功能使用排行</h3></div><button className="text-button" onClick={() => setActive("features")}>全部功能 <Icon name="arrow" size={15} /></button></div><div className="usage-list">{data.feature_usage.length ? data.feature_usage.map((item, index) => <div className="usage-row" key={item.key}><span className="usage-rank">0{index + 1}</span><div className="usage-name"><strong>{item.title}</strong><div className="usage-track"><i style={{ width: `${item.count / maxUsage * 100}%` }} /></div></div><b>{item.count}</b></div>) : <p className="board-empty">完成任务后会显示使用排行</p>}</div></article>
      <article className="board-panel attention-panel"><div className="board-panel-head"><div><span className="section-label">协作提醒</span><h3>需要关注</h3></div><Icon name="bell" size={19} /></div>{reviewPending > 0 ? <button className="attention-item" onClick={onOpenReviews}><span className="attention-icon blue"><Icon name="check" size={17} /></span><span><strong>{reviewPending} 个任务等待人工复核</strong><small>确认业务选择后继续生成结果</small></span><Icon name="arrow" size={16} /></button> : null}{user.role === "admin" && data.metrics.pending_users > 0 ? <button className="attention-item" onClick={() => setActive("users")}><span className="attention-icon orange"><Icon name="users" size={17} /></span><span><strong>{data.metrics.pending_users} 个账号等待审核</strong><small>审核通过后才能进入工作台</small></span><Icon name="arrow" size={16} /></button> : null}{reviewPending === 0 && (user.role !== "admin" || data.metrics.pending_users === 0) ? <div className="attention-clear"><span className="attention-icon green"><Icon name="check" size={17} /></span><div><strong>当前没有待处理提醒</strong><small>工作台状态良好，可以继续处理业务</small></div></div> : null}</article>
    </section>

    <section className="board-grid board-grid-bottom">
      <article className="board-panel recent-panel"><div className="board-panel-head"><div><span className="section-label">任务记录</span><h3>最近任务</h3></div><button className="text-button" onClick={() => setActive("features")}>新建任务 <Icon name="plus" size={15} /></button></div><div className="recent-job-list">{data.recent_jobs.length ? data.recent_jobs.map((job) => { const status = job.review_pending ? "review" : job.status; return <div className="recent-job-row" key={job.id}><span className={`job-icon job-icon-${status}`}><Icon name={status === "completed" ? "check" : status === "failed" ? "x" : "activity"} size={15} /></span><div><strong>{job.title}</strong><small>{dateLabel(job.created_at, true)}</small></div><JobStatus status={status} /></div>; }) : <p className="board-empty">还没有任务记录</p>}</div></article>
      <article className="board-panel files-panel"><div className="board-panel-head"><div><span className="section-label">文件产出</span><h3>最近输出</h3></div><Icon name="file" size={19} /></div>{downloadError ? <p className="download-error">{downloadError}</p> : null}<div className="recent-file-list">{data.recent_files.length ? data.recent_files.map((file) => <button className="recent-file-row" key={`${file.job_id}-${file.name}`} onClick={() => void download(file)}><span className="file-icon"><Icon name="file" size={15} /></span><span><strong>{file.name}</strong><small>{sizeLabel(file.size)} · {dateLabel(file.created_at)}</small></span><Icon name="download" size={16} /></button>) : <p className="board-empty">完成任务后会显示输出文件</p>}</div></article>
    </section>
  </div>;
}
