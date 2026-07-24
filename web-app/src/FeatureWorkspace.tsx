import { useEffect, useMemo, useRef, useState } from "react";
import { cancelJob, createJob, downloadJobFile, getJob, listJobs, submitJobReview, uploadFile, type Feature, type WebJob } from "./api";
import { Icon } from "./icons";
import { ReviewPanel } from "./ReviewPanel";

type FieldKind = "text" | "select" | "checkbox" | "textarea" | "month";
type OptionField = { key: string; label: string; kind: FieldKind; value: string | boolean; choices?: Array<[string, string]>; placeholder?: string };
type FileGroup = { key: string; label: string; description: string; multiple?: boolean; optional?: boolean; accept: string };
type FeatureSpec = { action: string; reviewAction?: string; files: FileGroup[]; options: OptionField[]; runLabel: string; reviewLabel?: string };

const SPECS: Record<string, FeatureSpec> = {
  attendance: { action: "attendance.run", runLabel: "开始填报", files: [
    { key: "sources", label: "打卡来源表", description: "可上传多份原始考勤数据。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
    { key: "targets", label: "工时模板", description: "上传需要写入的填报模板。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [
    { key: "workday_hours", label: "白班标准工时", kind: "text", value: "8" },
    { key: "overtime", label: "计算加班列", kind: "checkbox", value: true },
    { key: "night_shift", label: "计算夜班", kind: "checkbox", value: false },
    { key: "night_start_hour", label: "夜班起始时刻", kind: "text", value: "18" },
    { key: "night_workday_hours", label: "夜班标准工时", kind: "text", value: "8" },
    { key: "night_max_hours", label: "夜班合理上限", kind: "text", value: "12" },
  ] },
  reconcile: { action: "reconcile.run", reviewAction: "web.reconcile.review", reviewLabel: "人工确认后对账", runLabel: "开始对账", files: [
    { key: "target", label: "目标工时表", description: "作为对账基准的目标表。", accept: ".xlsx,.xlsm,.xls" },
    { key: "sources", label: "来源工时表", description: "可上传多份来源表。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
    { key: "labor", label: "劳务工时表", description: "上传参与核对的劳务表。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [] },
  arrival: { action: "web.arrival", runLabel: "生成到料明细", files: [
    { key: "paths", label: "送货计划", description: "上传一个或多个批次计划表。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [{ key: "top_label", label: "表头说明", kind: "text", value: "", placeholder: "例如：截止 16 点" }] },
  pivot: { action: "pivot.run", reviewAction: "web.pivot.review", reviewLabel: "人工复核后生成", runLabel: "生成透视表", files: [
    { key: "paths", label: "销售数据源", description: "可合并处理多份采购或销售明细。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [] },
  purchase: { action: "purchase.run", runLabel: "开始采购对账", files: [
    { key: "file1", label: "我方采购表", description: "上传内部采购数据。", accept: ".xlsx,.xlsm,.xls" },
    { key: "file2", label: "供应商采购表", description: "上传供应商提供的数据。", accept: ".xlsx,.xlsm,.xls" },
  ], options: [
    { key: "name1", label: "我方名称", kind: "text", value: "我方" },
    { key: "name2", label: "对方名称", kind: "text", value: "供方" },
  ] },
  delivery: { action: "delivery.run", runLabel: "生成送货计划", files: [
    { key: "file1", label: "物料清单", description: "送货计划的主要物料来源。", accept: ".xlsx,.xlsm,.xls" },
    { key: "file2", label: "供应商清单", description: "用于匹配供应商，可不上传。", optional: true, accept: ".xlsx,.xlsm,.xls" },
    { key: "ref_plan", label: "参考计划", description: "用于继承 CASE 或班组信息，可不上传。", optional: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [{ key: "order_type", label: "订单类型", kind: "select", value: "SUB", choices: [["SUB", "SUB"], ["KD", "KD"], ["SKD", "SKD"]] }] },
  library: { action: "library.import", runLabel: "导入数据库", files: [
    { key: "paths", label: "业务文件", description: "文件会自动识别分类并归档。", multiple: true, accept: ".xlsx,.xlsm,.xls,.csv,.pdf" },
  ], options: [] },
  invoice: { action: "web.invoice", reviewAction: "web.invoice.review", reviewLabel: "逐张复核后生成", runLabel: "生成发票台账", files: [
    { key: "paths", label: "PDF 发票", description: "可一次上传同一月份的多张 PDF 发票。", multiple: true, accept: ".pdf" },
  ], options: [{ key: "month", label: "统计月份", kind: "month", value: "" }] },
  rename: { action: "rename.apply", runLabel: "执行重命名", files: [
    { key: "paths", label: "待处理文件", description: "服务端处理上传副本，不改动客户端原文件。", multiple: true, accept: "*" },
  ], options: [
    { key: "find", label: "查找内容", kind: "text", value: "" },
    { key: "replace", label: "替换为", kind: "text", value: "" },
    { key: "prefix", label: "名称前缀", kind: "text", value: "" },
    { key: "suffix", label: "名称后缀", kind: "text", value: "" },
    { key: "ext_lower", label: "扩展名转小写", kind: "checkbox", value: false },
  ] },
  text: { action: "text.transform", runLabel: "处理文本", files: [], options: [
    { key: "text", label: "文本内容", kind: "textarea", value: "", placeholder: "在此粘贴需要处理的文本" },
    { key: "operation", label: "处理方式", kind: "select", value: "dedup", choices: [["dedup", "去重"], ["sort", "排序"], ["reverse", "倒序"], ["remove_empty", "删除空行"], ["trim", "清理首尾空白"], ["collapse", "合并连续空格"], ["upper", "转大写"], ["lower", "转小写"], ["email", "提取邮箱"], ["phone", "提取手机号"], ["url", "提取网址"]] },
  ] },
  pdf: { action: "pdf.run", runLabel: "开始处理 PDF", files: [
    { key: "paths", label: "PDF 文件", description: "合并时可多选，其余模式使用第一份文件。", multiple: true, accept: ".pdf" },
  ], options: [
    { key: "mode", label: "处理方式", kind: "select", value: "merge", choices: [["merge", "合并"], ["split", "拆分"], ["extract", "提取页"], ["delete", "删除页"]] },
    { key: "spec", label: "页码范围", kind: "text", value: "", placeholder: "例如：1-3,5" },
    { key: "split_mode", label: "拆分方式", kind: "select", value: "each", choices: [["each", "每页一个文件"], ["range", "按页码范围"]] },
  ] },
  excel: { action: "excel.run", runLabel: "开始处理表格", files: [
    { key: "paths", label: "表格文件", description: "支持 xlsx、xlsm、xls 和 csv。", multiple: true, accept: ".xlsx,.xlsm,.xls,.csv" },
  ], options: [
    { key: "mode", label: "处理方式", kind: "select", value: "merge", choices: [["merge", "多簿合并"], ["split", "按 Sheet 拆分"], ["convert", "格式转换"], ["stack", "纵向合并"]] },
    { key: "target", label: "转换格式", kind: "select", value: "xlsx", choices: [["xlsx", "xlsx"], ["csv", "CSV"]] },
    { key: "has_header", label: "首行是表头", kind: "checkbox", value: true },
    { key: "keep_formula", label: "保留公式", kind: "checkbox", value: false },
  ] },
  compare: { action: "web.compare", reviewAction: "web.compare.review", reviewLabel: "确认关键列后比对", runLabel: "开始比对", files: [
    { key: "file1", label: "A 表", description: "通常放程序输出或新版。", accept: ".xlsx,.xlsm,.xls,.csv" },
    { key: "file2", label: "B 表", description: "通常放手工结果或旧版。", accept: ".xlsx,.xlsm,.xls,.csv" },
  ], options: [{ key: "key", label: "关键列", kind: "text", value: "", placeholder: "留空时自动使用首个公共列" }] },
  currency: { action: "currency.convert", runLabel: "转换金额", files: [], options: [
    { key: "amount", label: "人民币金额", kind: "text", value: "", placeholder: "例如：12345.67" },
  ] },
};

function initialOptions(spec: FeatureSpec) {
  return Object.fromEntries(spec.options.map((field) => [field.key, field.value]));
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function jobStatusLabel(job: WebJob) {
  if (job.review_pending) return "待复核";
  if (job.status === "completed") return "已完成";
  if (job.status === "failed") return "失败";
  if (job.status === "running") return "处理中";
  if (job.status === "queued") return "排队中";
  if (job.status === "cancelled") return "已取消";
  return "已中断";
}

function FileField({ config, files, onChange }: { config: FileGroup; files: File[]; onChange: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  function accept(next: File[]) { onChange(config.multiple ? Array.from(new Map([...files, ...next].map((file) => [`${file.name}-${file.size}`, file])).values()) : next.slice(0, 1)); }
  return <section className={`web-file-field ${dragging ? "dragging" : ""} ${files.length ? "has-files" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); accept(Array.from(event.dataTransfer.files)); }}>
    <div className="web-file-heading"><div><strong>{config.label}</strong>{config.optional ? <span>可选</span> : null}<p>{config.description}</p></div><button type="button" className="outline-button" onClick={() => inputRef.current?.click()}><Icon name="plus" size={15} />选择文件</button></div>
    <input ref={inputRef} className="hidden-file-input" type="file" accept={config.accept === "*" ? undefined : config.accept} multiple={config.multiple} onChange={(event) => { accept(Array.from(event.target.files || [])); event.currentTarget.value = ""; }} />
    {files.length ? <div className="web-selected-files">{files.map((file, index) => <div key={`${file.name}-${file.size}-${index}`}><span><strong>{file.name}</strong><small>{formatSize(file.size)}</small></span><button type="button" aria-label={`移除 ${file.name}`} onClick={() => onChange(files.filter((_, itemIndex) => itemIndex !== index))}><Icon name="x" size={14} /></button></div>)}</div> : <div className="web-file-empty"><Icon name="plus" size={17} /><span>拖放到此处，或选择本机文件</span></div>}
  </section>;
}

function ResultValue({ job }: { job: WebJob }) {
  if (!job.result) return null;
  const value = job.result as Record<string, unknown>;
  const envelope = value.result && typeof value.result === "object" ? value.result as Record<string, unknown> : value;
  const text = typeof envelope.text === "string" ? envelope.text : "";
  if (text) return <pre className="result-text">{text}</pre>;
  return <details className="result-detail"><summary>查看处理摘要</summary><pre>{JSON.stringify(job.result, null, 2)}</pre></details>;
}

export function FeatureWorkspace({ feature, onBack, onCompleted, initialJobId }: { feature: Feature; onBack: () => void; onCompleted: () => void; initialJobId?: string }) {
  const spec = SPECS[feature.key];
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [options, setOptions] = useState<Record<string, string | boolean>>(() => initialOptions(spec));
  const [uploading, setUploading] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [job, setJob] = useState<WebJob | null>(null);
  const [history, setHistory] = useState<WebJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const totalFiles = useMemo(() => Object.values(files).reduce((count, items) => count + items.length, 0), [files]);
  const canRun = spec.files.every((group) => group.optional || (files[group.key]?.length || 0) > 0)
    && spec.options.filter((field) => ["textarea"].includes(field.kind) || field.key === "amount").every((field) => String(options[field.key] || "").trim());

  useEffect(() => {
    const actions = new Set([spec.action, spec.reviewAction].filter(Boolean));
    setHistoryLoading(true);
    void listJobs().then((result) => setHistory(result.jobs.filter((item) => actions.has(item.action)).slice(0, 5))).catch(() => undefined).finally(() => setHistoryLoading(false));
  }, [spec.action, spec.reviewAction]);

  useEffect(() => {
    if (!initialJobId) return;
    let active = true;
    setRestoring(true); setError("");
    void getJob(initialJobId).then(({ job: next }) => { if (active) setJob(next); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "读取任务失败"); }).finally(() => { if (active) setRestoring(false); });
    return () => { active = false; };
  }, [initialJobId]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void getJob(job.id).then(({ job: next }) => {
        if (!active) return;
        setJob(next);
        if (!["queued", "running"].includes(next.status)) {
          window.clearInterval(timer);
          setHistory((current) => [next, ...current.filter((item) => item.id !== next.id)].slice(0, 5));
          if (next.status === "completed") onCompleted();
        }
      }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "读取任务失败"); });
    }, 700);
    return () => { active = false; window.clearInterval(timer); };
  }, [job?.id, job?.status, onCompleted]);

  function buildPayload(handles: Record<string, string[]>) {
    const payload: Record<string, unknown> = { ...handles, ...options };
    if (feature.key === "attendance") {
      payload.options = {
        workday_hours: Number(options.workday_hours) || 8,
        overtime: Boolean(options.overtime),
        night_shift: Boolean(options.night_shift),
        night_start_hour: Number(options.night_start_hour) || 18,
        night_workday_hours: Number(options.night_workday_hours) || 8,
        night_max_hours: Number(options.night_max_hours) || 12,
      };
      for (const key of ["workday_hours", "overtime", "night_shift", "night_start_hour", "night_workday_hours", "night_max_hours"]) delete payload[key];
    }
    if (feature.key === "reconcile") payload.options = {};
    if (feature.key === "rename") {
      payload.rule = { find: options.find, replace: options.replace, prefix: options.prefix, suffix: options.suffix, ext_lower: options.ext_lower };
      for (const key of ["find", "replace", "prefix", "suffix", "ext_lower"]) delete payload[key];
    }
    if (feature.key === "text") payload.options = {};
    return payload;
  }

  async function submit(action: string, extra: Record<string, unknown> = {}) {
    setError(""); setDownloadError(""); setUploading(true); setUploadedCount(0); setJob(null);
    try {
      const group = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`;
      const handles: Record<string, string[]> = {};
      for (const config of spec.files) {
        handles[config.key] = [];
        for (const file of files[config.key] || []) {
          const uploaded = await uploadFile(file, group);
          handles[config.key].push(uploaded.handle);
          setUploadedCount((count) => count + 1);
        }
      }
      const created = await createJob(action, feature.title, { ...buildPayload(handles), ...extra });
      const next = await getJob(created.job_id);
      setJob(next.job);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务提交失败");
    } finally { setUploading(false); }
  }

  async function run() { await submit(spec.action); }
  async function startReview() {
    if (spec.reviewAction) await submit(spec.reviewAction);
  }

  async function confirmReview(choices: Record<string, unknown>) {
    if (!job) return;
    setReviewBusy(true); setError("");
    try {
      await submitJobReview(job.id, choices);
      const next = await getJob(job.id);
      setJob(next.job);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提交复核失败");
    } finally { setReviewBusy(false); }
  }

  async function download(file: WebJob["files"][number]) {
    setDownloadError("");
    try { await downloadJobFile(file); } catch (reason) { setDownloadError(reason instanceof Error ? reason.message : "下载失败"); }
  }

  async function restoreJob(id: string) {
    setRestoring(true); setError(""); setDownloadError("");
    try { setJob((await getJob(id)).job); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "读取任务失败"); }
    finally { setRestoring(false); }
  }

  return <div className="page-body workspace-page">
    <button className="back-button" onClick={onBack}><span>←</span>返回业务模块</button>
    <div className="workspace-heading"><div><span className="section-label">在线业务处理</span><h2>{feature.title}</h2><p>{feature.description}</p></div><div className="workspace-number">{feature.group}</div></div>
    <div className="workspace-layout"><section className="workspace-form">
      {spec.files.map((group) => <FileField key={group.key} config={group} files={files[group.key] || []} onChange={(next) => setFiles((current) => ({ ...current, [group.key]: next }))} />)}
      {spec.options.length ? <section className="web-options"><div className="web-options-title"><span>处理参数</span><i /></div><div className="web-option-grid">{spec.options.map((field) => <label key={field.key} className={field.kind === "textarea" ? "wide" : ""}><span>{field.label}</span>{field.kind === "select" ? <select value={String(options[field.key])} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.value }))}>{field.choices?.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select> : field.kind === "checkbox" ? <input type="checkbox" checked={Boolean(options[field.key])} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.checked }))} /> : field.kind === "textarea" ? <textarea value={String(options[field.key])} placeholder={field.placeholder} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.value }))} /> : <input type={field.kind === "month" ? "month" : "text"} value={String(options[field.key])} placeholder={field.placeholder} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.value }))} />}</label>)}</div></section> : null}
    </section><aside className="web-task-panel"><div className="task-panel-head"><div><span className={`task-state ${job?.review_pending ? "review" : job?.status || "idle"}`} /><strong>{restoring ? "正在恢复任务" : uploading ? "正在上传" : job?.review_pending ? "等待人工复核" : job?.status === "running" || job?.status === "queued" ? "正在处理" : job?.status === "completed" ? "处理完成" : job?.status === "failed" ? "处理失败" : job?.status === "cancelled" ? "任务已取消" : "等待输入"}</strong></div><span>{restoring ? "同步中" : job?.review_pending ? "需要确认" : job ? `${job.progress}%` : totalFiles ? `${totalFiles} 个文件` : "尚未提交"}</span></div>
      {(uploading || job && ["queued", "running"].includes(job.status)) ? <div className="web-progress"><i style={{ width: `${uploading ? totalFiles ? uploadedCount / totalFiles * 100 : 4 : Math.max(3, job?.progress || 3)}%` }} /></div> : null}
      {error || job?.error ? <div className="auth-notice error">{error || job?.error}</div> : null}
      {job?.files.length ? <div className="download-list"><span>结果文件</span>{job.files.map((file) => <button key={file.url} onClick={() => void download(file)}><Icon name="arrow" size={15} /><span><strong>{file.name}</strong><small>{formatSize(file.size)}</small></span></button>)}</div> : null}
      {downloadError ? <div className="auth-notice error">{downloadError}</div> : null}
      {job?.logs.length ? <details className="web-log"><summary>处理日志 · {job.logs.length} 条</summary><pre>{job.logs.join("\n")}</pre></details> : null}
      {job?.review_pending && job.result ? <ReviewPanel kind={feature.key as "reconcile" | "pivot" | "invoice" | "compare"} result={job.result} onConfirm={(choices) => void confirmReview(choices)} busy={reviewBusy} /> : null}
      {job?.status === "completed" && !job.review_pending ? <ResultValue job={job} /> : null}
      <div className="web-task-actions">{job && ["queued", "running"].includes(job.status) ? <button className="cancel-button" onClick={() => void cancelJob(job.id)}>取消任务</button> : null}{spec.reviewAction && !job?.review_pending ? <button className="review-button" disabled={!canRun || uploading || Boolean(job && ["queued", "running"].includes(job.status))} onClick={() => void startReview()}><Icon name="check" size={15} />{uploading ? `上传中 ${uploadedCount}/${totalFiles}` : spec.reviewLabel}</button> : null}<button className="primary-button" disabled={!canRun || uploading || Boolean(job && ["queued", "running"].includes(job.status)) || Boolean(job?.review_pending)} onClick={() => void run()}>{uploading ? `上传中 ${uploadedCount}/${totalFiles}` : spec.runLabel}<Icon name="arrow" size={16} /></button></div>
    </aside></div>
    <section className="recent-jobs"><div className="section-head"><div><span className="section-label">最近处理</span><h3>本功能任务记录</h3></div></div>{historyLoading ? <div className="recent-jobs-empty">正在加载任务记录...</div> : history.length ? history.map((item) => <button key={item.id} disabled={restoring} onClick={() => void restoreJob(item.id)}><span className={`history-dot ${item.review_pending ? "review" : item.status}`} /><span><strong>{item.title}</strong><small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></span><em>{jobStatusLabel(item)}</em></button>) : <div className="recent-jobs-empty">当前功能还没有任务记录</div>}</section>
  </div>;
}
