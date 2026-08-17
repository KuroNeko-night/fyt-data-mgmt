/**
 * 任务中心页面。
 *
 * 维护当前账号的持久化任务列表，轮询活动任务、筛选复核/异常记录、下载结果、
 * 创建限时分享，并支持从任务记录反向打开对应业务工作区。
 */
import { useEffect, useMemo, useState } from "react";
import { createShare, revokeShare, type ShareLink } from "./api";
import { cancelJob, downloadJobFile, getJob, listJobs, retryJob, searchAll, type SearchResponse, type WebJob } from "./api";
import { Icon } from "./icons";
import Button from "./ui/Button";
import Dialog from "./ui/Dialog";
import EmptyState from "./ui/EmptyState";
import IconButton from "./ui/IconButton";
import Notice from "./ui/Notice";
import PageHeader from "./ui/PageHeader";
import SegmentedControl from "./ui/SegmentedControl";
import StatusBadge from "./ui/StatusBadge";
import TaskRow from "./ui/TaskRow";
import type { StatusKey } from "./ui/status";
import "./workflows.css";

/** 页面入参：根据任务动作与编号打开对应业务工作区。 */
type Props = { onOpenFeature: (action: string, jobId: string) => void };
/** 任务筛选键；`active` 是排队与运行中的合成筛选，`failed` 包含异常、取消和中断。 */
export type TaskFilter = "all" | "active" | "review" | "completed" | "failed";

const labels: Record<string, string> = {
  queued: "排队", running: "处理中", completed: "已完成", failed: "异常", cancelled: "已取消", interrupted: "已中断",
};

const actionLabels: Record<string, string> = {
  "attendance.run": "考勤填报", "reconcile.run": "工时对账", "web.reconcile.review": "工时对账复核", "web.arrival": "到料明细", "pivot.run": "销售透视", "web.pivot.review": "销售透视复核", "purchase.run": "采购对账", "shipping_review.run": "发运评审对比", "delivery.run": "送货计划", "supplier_batch.run": "供应商批次表", "web.supplier_batch.review": "供应商批次表复核", "library.import": "数据资料归档", "web.invoice": "发票台账", "web.invoice.review": "发票复核", "rename.apply": "批量重命名", "text.transform": "文本处理", "pdf.run": "PDF 文件处理", "excel.run": "Excel 表格处理", "web.compare": "表格比对", "web.compare.review": "表格比对复核", "currency.convert": "金额大写转换",
};

const FILTER_OPTIONS: Array<{ value: TaskFilter; label: string }> = [
  { value: "all", label: "全部" }, { value: "active", label: "处理中" }, { value: "review", label: "待确认" }, { value: "completed", label: "已完成" }, { value: "failed", label: "异常" },
];

/** 格式化任务列表使用的月日和分钟时间。 */
function dateLabel(value: string) {
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** 将内部动作键转换为业务模块名称，未知动作使用安全的通用文案。 */
function actionLabel(action: string) { return actionLabels[action] || "业务处理"; }

/**
 * 计算任务卡片的展示状态。
 * 人工复核是覆盖在运行状态之上的业务阶段，因此 review_pending 的优先级高于 job.status。
 */
function statusKey(job: WebJob): StatusKey {
  if (job.review_pending) return "review";  // 人工复核优先于底层运行状态展示
  if (job.status === "queued" || job.status === "running" || job.status === "completed" || job.status === "failed" || job.status === "cancelled" || job.status === "interrupted") return job.status;
  return "interrupted"; // 未知状态按中断展示，提醒用户检查，而不是误标为成功。
}

/** 判断任务是否属于当前筛选；复核中的任务不重复计入处理中或已完成。 */
function statusMatch(job: WebJob, filter: TaskFilter) {
  if (filter === "all") return true;
  if (filter === "active") return !job.review_pending && (job.status === "queued" || job.status === "running");  // 复核中的任务不重复计入处理中
  if (filter === "review") return Boolean(job.review_pending);
  if (filter === "completed") return job.status === "completed" && !job.review_pending;
  return job.status === "failed" || job.status === "cancelled" || job.status === "interrupted";
}

/** 把筛选名称与实时数量组合成分段控件标签。 */
function filterLabel(filter: TaskFilter, summary: { total: number; active: number; review: number; completed: number; failed: number }) {
  const count = filter === "all" ? summary.total : filter === "active" ? summary.active : filter === "review" ? summary.review : filter === "completed" ? summary.completed : summary.failed;
  return `${FILTER_OPTIONS.find((item) => item.value === filter)?.label || "全部"} ${count}`;
}

/** 任务中心：负责任务列表、活动任务轮询、全局搜索、输出下载和临时分享。 */
export function TaskCenterPage({ onOpenFeature, initialFilter = "all" }: Props & { initialFilter?: TaskFilter }) {
  const [jobs, setJobs] = useState<WebJob[]>([]);
  const [filter, setFilter] = useState<TaskFilter>(initialFilter);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(""); // 取消或重试操作对应的任务 id。
  const [shareBusy, setShareBusy] = useState(""); // 创建分享使用任务与文件索引，撤销分享使用令牌。
  const [sharePanel, setSharePanel] = useState<(ShareLink & { fileIndex: number }) | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);

  /** 为某个结果文件创建七天有效的匿名下载链接。 */
  async function shareFile(jobId: string, fileIndex: number) {
    setShareBusy(`${jobId}-${fileIndex}`); setError("");
    try { const link = await createShare(jobId, fileIndex); setSharePanel({ ...link, fileIndex }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "创建分享失败"); }
    finally { setShareBusy(""); }
  }

  /** 撤销当前弹窗展示的分享令牌，成功后关闭弹窗。 */
  async function revokeCurrentShare() {
    if (!sharePanel) return;
    setShareBusy(`revoke-${sharePanel.token}`);
    try { await revokeShare(sharePanel.token); setSharePanel(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "撤销分享失败"); }
    finally { setShareBusy(""); }
  }

  /** 读取完整任务列表；首次加载与手动刷新使用不同状态，避免页面反复变成骨架屏。 */
  async function refresh(manual = false) {
    if (manual) setRefreshing(true); else setLoading(true);
    try { setJobs((await listJobs()).jobs); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "加载任务失败"); }
    finally { setLoading(false); setRefreshing(false); }
  }

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    // 没有活动任务时不创建定时器，减少空闲页面的网络请求和服务端压力。
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return undefined;  // 无活动任务时不创建定时器，减少空闲请求
    const timer = window.setInterval(() => {
      // 只轮询排队和运行中的任务，并行获取后按 id 合并，已完成任务保持原快照。
      void Promise.all(jobs.filter((job) => job.status === "queued" || job.status === "running").map((job) => getJob(job.id)))
        .then((updates) => setJobs((current) => current.map((job) => updates.find((item) => item.job.id === job.id)?.job || job)))  // 按 id 合并轮询结果，未更新任务保持原快照
        // 单次轮询失败不覆盖已有任务和全局错误，下一秒仍会自动重试。
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const visible = useMemo(() => jobs.filter((job) => statusMatch(job, filter)), [jobs, filter]);
  // 摘要与筛选使用同一复核优先规则，防止卡片数量与实际列表不一致。
  const summary = useMemo(() => ({
    total: jobs.length,
    active: jobs.filter((job) => !job.review_pending && (job.status === "queued" || job.status === "running")).length,
    review: jobs.filter((job) => job.review_pending).length,
    completed: jobs.filter((job) => job.status === "completed" && !job.review_pending).length,
    failed: jobs.filter((job) => ["failed", "cancelled", "interrupted"].includes(job.status)).length,
  }), [jobs]);

  /** 请求取消排队或运行中的任务，随后完整刷新状态。 */
  async function stop(job: WebJob) {
    setBusyId(job.id); setError("");
    try { await cancelJob(job.id); await refresh(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "取消任务失败"); }
    finally { setBusyId(""); }
  }

  /** 下载任务结果文件，下载工具负责文件名和对象地址生命周期。 */
  async function download(file: WebJob["files"][number]) {
    try { await downloadJobFile(file); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "下载失败"); }
  }

  /** 基于失败任务的原输入创建一条新任务，原任务记录保持不变。 */
  async function retry(job: WebJob) {
    setBusyId(job.id); setError("");
    try { await retryJob(job.id); await refresh(true); setError("已创建重新处理任务"); }  // 原任务记录保持不变，只创建新任务
    catch (reason) { setError(reason instanceof Error ? reason.message : "创建重新处理任务失败"); }
    finally { setBusyId(""); }
  }

  /** 跨任务标题、结果文件和消息执行服务端搜索。 */
  async function search() {
    if (!query.trim()) { setSearchResult(null); return; }
    setSearching(true); setError("");
    try { setSearchResult(await searchAll(query.trim())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "搜索失败"); }
    finally { setSearching(false); }
  }

  // 分段控件需要稳定的 value 与实时的数量标签，每次摘要变化时重新生成轻量数组。
  const segments = FILTER_OPTIONS.map((item) => ({ value: item.value, label: filterLabel(item.value, summary) }));
  return <div className="fyt-tasks-page">
    <div className="fyt-tasks-header"><PageHeader eyebrow="运行记录" title="任务中心" description="查看当前账号提交的任务进度、结果文件和异常信息。" actions={<IconButton label="刷新任务" disabled={refreshing} onClick={() => void refresh(true)}><Icon name="refresh" size={17} /></IconButton>} /></div>
    <section className="fyt-tasks-summary" aria-label="任务摘要"><div><span>全部任务</span><strong>{summary.total}</strong></div><div><span>处理中</span><strong>{summary.active}</strong></div><div data-tone={summary.review ? "warning" : undefined}><span>待确认</span><strong>{summary.review}</strong></div><div><span>已完成</span><strong>{summary.completed}</strong></div><div><span>异常</span><strong>{summary.failed}</strong></div></section>
    <form className="fyt-tasks-search" onSubmit={(event) => { event.preventDefault(); void search(); }}><Icon name="search" size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务、结果文件或消息" aria-label="搜索任务、结果文件或消息" /><Button variant="primary" size="sm" type="submit" disabled={searching} loading={searching}>{searching ? "搜索中" : "搜索"}</Button></form>
    {searchResult ? <section className="fyt-tasks-results"><div className="fyt-tasks-result-head"><div><h2>搜索结果</h2><p>任务 {searchResult.jobs.length} 条 · 文件 {searchResult.files.length} 个 · 消息 {searchResult.messages.length} 条</p></div><IconButton label="关闭搜索结果" onClick={() => setSearchResult(null)}><Icon name="x" size={15} /></IconButton></div>{searchResult.jobs.map((item) => <button className="fyt-tasks-result-row" type="button" key={`job-${item.id}`} onClick={() => onOpenFeature(item.action, item.id)}><Icon name="activity" size={15} /><span><strong>{item.title}</strong><small>{dateLabel(item.created_at)} · {labels[item.status] || "未知状态"}</small></span><Icon name="arrow" size={15} /></button>)}{searchResult.files.map((item) => <button className="fyt-tasks-result-row" type="button" key={`file-${item.url}`} onClick={() => void download({ name: item.name, size: item.size, url: item.url })}><Icon name="file" size={15} /><span><strong>{item.name}</strong><small>{item.title}</small></span><Icon name="download" size={15} /></button>)}{searchResult.messages.map((item) => <div className="fyt-tasks-result-row" key={`message-${item.id}`}><Icon name="bell" size={15} /><span><strong>{item.title}</strong><small>{item.content}</small></span><span className="fyt-search-message-state" data-unread={!item.read_at ? "true" : undefined}><span aria-hidden="true">{item.read_at ? "已" : "新"}</span>{item.read_at ? "已读" : "未读"}</span></div>)}{!searchResult.jobs.length && !searchResult.files.length && !searchResult.messages.length ? <EmptyState title="没有找到匹配内容" description="可以换一个任务名称、文件名称或消息关键词。" icon={<Icon name="search" size={18} />} /> : null}</section> : null}
    <div className="fyt-tasks-filter"><SegmentedControl value={filter} options={segments} onChange={setFilter} label="任务筛选" /></div>
    {error ? <Notice tone="error">{error}</Notice> : null}
    <section className="fyt-tasks-list" aria-label="任务列表">{loading ? <div className="fyt-empty-state" role="status"><h3>正在加载任务</h3></div> : visible.length ? visible.map((job) => <article className="fyt-task-card" key={job.id}><TaskRow title={job.title} status={statusKey(job)} time={dateLabel(job.created_at)} meta={<><span>{actionLabel(job.action)}</span>{job.versions?.length ? <span>{job.versions.length} 个结果版本</span> : null}</>} error={job.error || undefined} onOpen={() => onOpenFeature(job.action, job.id)} actions={<div className="fyt-task-card-actions">{job.files.map((file, fileIndex) => <span className="fyt-task-file-actions" key={file.url}><IconButton size="sm" label={`下载 ${file.name}`} onClick={() => void download(file)}><Icon name="download" size={16} /></IconButton><IconButton size="sm" label={`分享 ${file.name}`} disabled={shareBusy === `${job.id}-${fileIndex}`} onClick={() => void shareFile(job.id, fileIndex)}><Icon name="link" size={15} /></IconButton></span>)}{["failed", "cancelled", "interrupted"].includes(job.status) ? <IconButton size="sm" label="重新处理" disabled={busyId === job.id} onClick={() => void retry(job)}><Icon name="refresh" size={16} /></IconButton> : null}{job.status === "queued" || job.status === "running" ? <IconButton size="sm" label="取消任务" disabled={busyId === job.id} onClick={() => void stop(job)}><Icon name="x" size={16} /></IconButton> : null}</div>} />{job.status === "queued" || job.status === "running" ? <div className="fyt-task-card-progress" aria-label={`任务进度 ${job.progress}%`}><i style={{ width: `${Math.max(3, job.progress)}%` }} /></div> : null}</article>) : <EmptyState illustration={filter === "review" ? "empty-review-check.webp" : "empty-task-archive.webp"} illustrationAlt={filter === "review" ? "当前没有待人工确认事项" : "尚未开始的任务记录示意"} title={filter === "review" ? "当前没有待确认事项" : "当前筛选下没有任务"} description={filter === "review" ? "新的人工确认事项会在任务进入复核阶段后显示。" : "可以切换筛选条件，或从业务模块开始新的处理。"} />}</section>
    <Dialog open={Boolean(sharePanel)} title={sharePanel ? `分享「${sharePanel.name}」` : "分享文件"} description="链接有效期为 7 天，对方无需登录即可下载。" onClose={() => setSharePanel(null)} footer={sharePanel ? <div className="fyt-tasks-share-actions"><Button variant="danger" size="sm" type="button" disabled={shareBusy === `revoke-${sharePanel.token}`} loading={shareBusy === `revoke-${sharePanel.token}`} onClick={() => void revokeCurrentShare()}>撤销分享</Button><span>到期时间：{new Date(sharePanel.expires_at).toLocaleString("zh-CN")}</span></div> : null}>{sharePanel ? <div className="fyt-tasks-share"><div className="fyt-tasks-share-link"><input readOnly value={`${window.location.origin}${sharePanel.url}`} onFocus={(event) => event.currentTarget.select()} aria-label="分享链接" /><Button variant="secondary" type="button" onClick={() => void navigator.clipboard.writeText(`${window.location.origin}${sharePanel.url}`).then(() => setError("链接已复制"))}>复制</Button></div></div> : null}</Dialog>
  </div>;
}

export default TaskCenterPage;
