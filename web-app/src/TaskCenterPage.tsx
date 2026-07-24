import { useEffect, useMemo, useState } from "react";
import { cancelJob, downloadJobFile, getJob, listJobs, type WebJob } from "./api";
import { Icon } from "./icons";

type Props = { onOpenFeature: (action: string, jobId: string) => void };
export type TaskFilter = "all" | "active" | "review" | "completed" | "failed";

const labels: Record<WebJob["status"], string> = {
  queued: "排队中", running: "处理中", completed: "已完成", failed: "失败", cancelled: "已取消", interrupted: "已中断",
};

function dateLabel(value: string) {
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function statusMatch(job: WebJob, filter: TaskFilter) {
  if (filter === "all") return true;
  if (filter === "active") return !job.review_pending && (job.status === "queued" || job.status === "running");
  if (filter === "review") return Boolean(job.review_pending);
  if (filter === "completed") return job.status === "completed" && !job.review_pending;
  return job.status === "failed" || job.status === "cancelled" || job.status === "interrupted";
}

export function TaskCenterPage({ onOpenFeature, initialFilter = "all" }: Props & { initialFilter?: TaskFilter }) {
  const [jobs, setJobs] = useState<WebJob[]>([]);
  const [filter, setFilter] = useState<TaskFilter>(initialFilter);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  async function refresh() {
    try { setJobs((await listJobs()).jobs); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "加载任务失败"); }
    finally { setLoading(false); }
  }

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return;
    const timer = window.setInterval(() => {
      void Promise.all(jobs.filter((job) => job.status === "queued" || job.status === "running").map((job) => getJob(job.id)))
        .then((updates) => setJobs((current) => current.map((job) => updates.find((item) => item.job.id === job.id)?.job || job)))
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const visible = useMemo(() => jobs.filter((job) => statusMatch(job, filter)), [jobs, filter]);
  const summary = useMemo(() => ({
    total: jobs.length,
    active: jobs.filter((job) => !job.review_pending && (job.status === "queued" || job.status === "running")).length,
    review: jobs.filter((job) => job.review_pending).length,
    completed: jobs.filter((job) => job.status === "completed" && !job.review_pending).length,
    failed: jobs.filter((job) => ["failed", "cancelled", "interrupted"].includes(job.status)).length,
  }), [jobs]);

  async function stop(job: WebJob) {
    setBusyId(job.id); setError("");
    try { await cancelJob(job.id); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "取消任务失败"); }
    finally { setBusyId(""); }
  }

  async function download(file: WebJob["files"][number]) {
    try { await downloadJobFile(file); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "下载失败"); }
  }

  return <div className="page-body task-center-page">
    <section className="page-intro task-center-intro"><div><span className="section-label">运行记录</span><h2>任务中心</h2><p>查看当前账号提交的任务进度、结果文件和异常信息。</p></div><button className="icon-button" onClick={() => void refresh()} title="刷新任务" aria-label="刷新任务"><Icon name="refresh" size={17} /></button></section>
    <section className="task-summary-grid"><div><span>全部任务</span><strong>{summary.total}</strong></div><div><span>处理中</span><strong>{summary.active}</strong></div><div className={summary.review ? "has-review" : ""}><span>待复核</span><strong>{summary.review}</strong></div><div><span>已完成</span><strong>{summary.completed}</strong></div><div><span>异常</span><strong>{summary.failed}</strong></div></section>
    <div className="task-filter-bar" role="tablist">{([['all', `全部 ${summary.total}`], ['active', `处理中 ${summary.active}`], ['review', `待复核 ${summary.review}`], ['completed', `已完成 ${summary.completed}`], ['failed', `异常 ${summary.failed}`]] as Array<[TaskFilter, string]>).map(([key, label]) => <button key={key} className={filter === key ? "selected" : ""} aria-selected={filter === key} onClick={() => setFilter(key)}>{label}</button>)}</div>
    {error ? <div className="auth-notice error">{error}</div> : null}
    <section className="task-list-panel">{loading ? <div className="empty-row">正在加载任务...</div> : visible.length ? visible.map((job) => <article className="task-card" key={job.id}><div className={`task-card-icon ${job.review_pending ? "review" : job.status}`}><Icon name={job.review_pending ? "check" : job.status === "completed" ? "check" : job.status === "failed" ? "x" : job.status === "running" || job.status === "queued" ? "activity" : "clock"} size={17} /></div><div className="task-card-main"><div className="task-card-title"><strong>{job.title}</strong><span className={`task-card-status ${job.review_pending ? "review" : job.status}`}><i />{job.review_pending ? "待人工复核" : labels[job.status]}</span></div><small>{dateLabel(job.created_at)} · {job.action}</small>{job.status === "queued" || job.status === "running" ? <div className="task-card-progress"><i style={{ width: `${Math.max(3, job.progress)}%` }} /></div> : null}{job.error ? <p>{job.error}</p> : null}</div><div className="task-card-actions">{job.files.map((file) => <button key={file.url} onClick={() => void download(file)} title={`下载 ${file.name}`} aria-label={`下载 ${file.name}`}><Icon name="download" size={16} /></button>)}{job.status === "queued" || job.status === "running" ? <button className="task-stop" disabled={busyId === job.id} onClick={() => void stop(job)} title="取消任务" aria-label="取消任务"><Icon name="x" size={16} /></button> : null}<button className="task-open" onClick={() => onOpenFeature(job.action, job.id)} title="打开对应功能" aria-label="打开对应功能"><Icon name="arrow" size={16} /></button></div></article>) : <div className="empty-row">当前筛选下没有任务</div>}</section>
  </div>;
}
