/**
 * Web 业务模块的通用文件处理工作区。
 *
 * `SPECS` 是 Web 表单与动作映射的单一事实来源；组件负责上传用户文件、任务预检、
 * 创建持久化任务、轮询状态、呈现结构化结果和承接人工复核。所有表格算法仍在
 * `core/`，上传句柄、任务和结果文件的用户隔离由服务端执行。
 */
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { cancelJob, createJob, createTemplate, downloadJobFile, getJob, listTemplates, listJobs, preflightJob, previewJobFile, scanArrival, scanReconcile, submitJobReview, uploadFile, type ArrivalScanRow, type Feature, type JobTemplate, type PreviewData, type ReconcileScanFile, type WebJob } from "./api";
import { Icon } from "./icons";
import { ReviewPanel } from "./ReviewPanel";
import BusinessResultView from "./BusinessResultView";
import Button from "./ui/Button";
import FormField from "./ui/FormField";
import IconButton from "./ui/IconButton";
import PageHeader from "./ui/PageHeader";
import StatusBadge from "./ui/StatusBadge";
import Notice from "./ui/Notice";
import type { StatusKey } from "./ui/status";
import TemplateGuide from "./TemplateGuide";
import "./workflows.css";

/** 业务参数支持的原生表单控件种类。 */
type FieldKind = "text" | "select" | "checkbox" | "textarea" | "month";
/** 单个可调参数：键名与界面标签一致，`choices` 使用“值、文案”二元组。 */
type OptionField = { key: string; label: string; kind: FieldKind; value: string | boolean; choices?: Array<[string, string]>; placeholder?: string; optional?: boolean };
/** 一个文件上传组：描述界面文案，`accept` 限定文件类型，`directory` 表示选择整个文件夹。 */
type FileGroup = { key: string; label: string; description: string; multiple?: boolean; directory?: boolean; optional?: boolean; accept: string };
/** 单个业务模块的前端规格：执行动作、可选的复核动作、文件组和参数定义。 */
type FeatureSpec = { action: string; reviewAction?: string; reviewOnly?: boolean; files: FileGroup[]; options: OptionField[]; runLabel: string; reviewLabel?: string };

const WORKFLOW_STEPS = ["准备文件", "检查设置", "运行并查看结果"];
/** 与服务端 `MAX_UPLOAD_BYTES` 保持一致的单个业务文件上限。 */
const MAX_FILE_BYTES = 200 * 1024 * 1024;

/** 上传前给出明确的大小/空文件提示，避免服务端提前断开时前端只显示笼统的网络错误。 */
function uploadableError(file: File) {
  if (!file.size) return `文件「${file.name}」为空，无法上传，请检查文件夹内容。`;
  if (file.size > MAX_FILE_BYTES) return `文件「${file.name}」超过单文件 200 MB 限制，请移出或压缩后重试。`;
  return "";
}

/** 根据输入、运行和完成边界展示固定三步流程，不参与任务状态计算。 */
function WorkflowSteps({ step, done }: { step: number; done: number }) {
  return <div className="fyt-flow-steps" role="list" aria-label="处理流程">
    {WORKFLOW_STEPS.map((label, index) => {
      const number = index + 1;
      return <div key={label} className="fyt-flow-step" data-active={number <= step ? "true" : undefined} data-done={number <= done ? "true" : undefined} role="listitem" aria-current={number === step ? "step" : undefined}>
        <span className="fyt-flow-step-dot">{number <= done ? <Icon name="check" size={14} /> : number}</span>
        <strong>{label}</strong>
      </div>;
    })}
  </div>;
}

// 每个业务键只在此声明上传组、可调参数、执行动作和是否需要两阶段人工复核。
const SPECS: Record<string, FeatureSpec> = {
  attendance: { action: "attendance.run", runLabel: "开始填报", files: [
    { key: "sources", label: "打卡来源表", description: "上传打卡记录（可多份，自动合并处理）。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
    { key: "targets", label: "工时模板", description: "选择要填写的考勤表模板。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [
    { key: "workday_hours", label: "白班标准工时（小时）", kind: "text", value: "9" },
    { key: "overtime", label: "计算加班列", kind: "checkbox", value: true },
    { key: "auto_actual", label: "自动按半小时计算实际上/下班时间", kind: "checkbox", value: true },
    { key: "conflict", label: "重复打卡记录", kind: "select", value: "last", choices: [["last", "后者覆盖"], ["first", "先者优先"], ["warn", "不覆盖，仅提示"]] },
    { key: "day_max_hours", label: "白班合理工时上限", kind: "text", value: "16" },
    { key: "night_shift", label: "启用跨零点夜班识别", kind: "checkbox", value: true },
    { key: "night_start_hour", label: "夜班开始时间（时）", kind: "text", value: "17" },
    { key: "night_workday_hours", label: "夜班标准工时", kind: "text", value: "11" },
    { key: "night_max_hours", label: "夜班合理工时上限", kind: "text", value: "16" },
    { key: "skip_extra", label: "额外假休标记（可选）", kind: "textarea", value: "", optional: true, placeholder: "用逗号或换行分隔，例如：培训、外勤" },
  ] },
  attendance_archive: { action: "attendance_archive.run", runLabel: "生成月度汇总", files: [
    { key: "paths", label: "考勤填报表", description: "可多选本月已填写的考勤表，自动按姓名汇总出勤天数、工时、加班与异常。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [
    { key: "tolerance", label: "工时差异容差（小时）", kind: "text", value: "0.1", placeholder: "例如：0.1" },
  ] },
  reconcile: { action: "reconcile.run", reviewAction: "web.reconcile.review", reviewLabel: "确认后开始对账", runLabel: "开始对账", files: [
    { key: "target", label: "目标工时表", description: "作为对账基准的目标表。", accept: ".xlsx,.xlsm,.xls" },
    { key: "sources", label: "来源工时表", description: "可上传多份来源表。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
    { key: "labor", label: "劳务工时表", description: "上传参与核对的劳务表。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [] },
  arrival: { action: "web.arrival", runLabel: "生成到料明细", files: [
    { key: "paths", label: "送货计划", description: "上传一个或多个批次计划表。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [{ key: "top_label", label: "报表抬头（可选）", kind: "text", value: "", placeholder: "例如：截止 16 点" }] },
  pivot: { action: "pivot.run", reviewAction: "web.pivot.review", reviewLabel: "确认后生成采购汇总", runLabel: "生成采购汇总", files: [
    { key: "paths", label: "采购数据源", description: "可合并处理多份采购明细，直接清洗并按物料号汇总。", multiple: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [] },
  purchase: { action: "purchase.run", runLabel: "开始采购对账", files: [
    { key: "file1", label: "我方采购表", description: "上传本公司自己的采购表。", accept: ".xlsx,.xlsm,.xls" },
    { key: "file2", label: "供应商采购表", description: "上传供应商提供的采购表。", accept: ".xlsx,.xlsm,.xls" },
  ], options: [
    { key: "name1", label: "我方名称", kind: "text", value: "我方" },
    { key: "name2", label: "对方名称", kind: "text", value: "供方" },
  ] },
  shipping_review: { action: "shipping_review.run", runLabel: "生成对比报告", files: [
    { key: "package_plan", label: "包装日计划", description: "系统会自动排除 BOX 状态为“已作废”的记录，并按物料号、物料描述汇总实际包装数量。", accept: ".xlsx,.xlsm" },
    { key: "review_workbook", label: "发运评审表", description: "默认读取文件保存时的活动工作表，并按 Part No 汇总 Chinese Name 与总数。", accept: ".xlsx,.xlsm" },
  ], options: [
    { key: "review_sheet", label: "评审工作表（可选）", kind: "text", value: "", placeholder: "留空使用文件保存时的活动工作表" },
  ] },
  delivery: { action: "delivery.run", runLabel: "生成送货计划", files: [
    { key: "file1", label: "物料清单", description: "送货计划的主要物料来源。", accept: ".xlsx,.xlsm,.xls" },
    { key: "file2", label: "供应商清单", description: "用于匹配供应商（可选）。", optional: true, accept: ".xlsx,.xlsm,.xls" },
    { key: "ref_plan", label: "参考计划", description: "可选：参考上一期计划，自动带出班组信息。", optional: true, accept: ".xlsx,.xlsm,.xls" },
  ], options: [{ key: "order_type", label: "订单类型", kind: "select", value: "SUB", choices: [["SUB", "SUB"], ["KD", "KD"], ["SKD", "SKD"]] }] },
  supplier_batch: { action: "supplier_batch.run", reviewAction: "web.supplier_batch.review", reviewOnly: true, reviewLabel: "扫描并填写交付日期", runLabel: "生成供应商批次表", files: [
    { key: "batch_paths", label: "当前批次清单", description: "可选择多个辅料清单总表，系统会自动识别批次和供应商。", multiple: true, accept: ".xlsx,.xlsm" },
    { key: "history_paths", label: "历史供应商明细", description: "可选，用于补充当前清单中缺失的供应商归属。", multiple: true, optional: true, accept: ".xlsx,.xlsm" },
  ], options: [] },
  purchase_plan: { action: "purchase_plan.run", runLabel: "生成采购计划", files: [
    { key: "template_paths", label: "采购计划模板", description: "含供应商代码子表的模板文件；模板中已填写的仓库编号、采购员编号与预计到货日期会原样保留。", accept: ".xlsx,.xlsm" },
    { key: "batch_paths", label: "辅料清单总表", description: "可多选，每个文件按批次号（如 26036-02）生成一个采购计划。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [] },
  purchase_diff: { action: "purchase_plan.diff", runLabel: "生成差异清单", files: [
    { key: "batch_paths", label: "辅料清单总表", description: "可多选，提取清单中实收与计划数量不一致的记录。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [] },
  reconcile_statement: { action: "reconcile_statement.build", runLabel: "生成对账单", files: [
    { key: "paths", label: "采购清单文件", description: "上传各供应商的采购清单明细（可多选），扫描后勾选批次生成对账单。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [] },
  invoice: { action: "web.invoice", reviewAction: "web.invoice.review", reviewLabel: "逐张确认后生成", runLabel: "生成发票台账", files: [
    { key: "paths", label: "发票资料文件夹", description: "选择包含同一月份 PDF 发票的文件夹，系统会递归扫描其中全部 PDF 并识别增值税专用发票。", directory: true, accept: ".pdf" },
  ], options: [{ key: "month", label: "统计月份", kind: "month", value: "" }] },
  invoice_match: { action: "invoice_match.run", runLabel: "开始票货匹配", files: [
    { key: "invoice_paths", label: "发票台账", description: "发票统计生成的月度台账，读取销售方与价税合计。", multiple: true, accept: ".xlsx,.xlsm" },
    { key: "purchase_paths", label: "采购明细", description: "供应商批次表或采购计划导入输出，读取供应商列。", multiple: true, accept: ".xlsx,.xlsm" },
  ], options: [] },
  rename: { action: "rename.apply", runLabel: "执行重命名", files: [
    { key: "paths", label: "待处理文件", description: "系统只处理上传文件的副本，不会改动你电脑上的原文件。", multiple: true, accept: "*" },
  ], options: [
    { key: "find", label: "查找内容", kind: "text", value: "", placeholder: "要查找的文字，可留空" },
    { key: "replace", label: "替换为", kind: "text", value: "", placeholder: "替换成的文字，可留空" },
    { key: "prefix", label: "名称前缀", kind: "text", value: "", placeholder: "加在名称前面，例如：新-" },
    { key: "suffix", label: "名称后缀", kind: "text", value: "", placeholder: "加在名称后面，例如：-副本" },
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
    { key: "mode", label: "处理方式", kind: "select", value: "merge", choices: [["merge", "合并多个文件"], ["split", "按工作表拆分"], ["convert", "格式转换"], ["stack", "纵向合并"]] },
    { key: "target", label: "转换格式", kind: "select", value: "xlsx", choices: [["xlsx", "xlsx"], ["csv", "CSV"]] },
    { key: "has_header", label: "首行是表头", kind: "checkbox", value: true },
    { key: "keep_formula", label: "保留公式", kind: "checkbox", value: false },
  ] },
  compare: { action: "web.compare", reviewAction: "web.compare.review", reviewLabel: "确认关键列后比对", runLabel: "开始比对", files: [
    { key: "file1", label: "A 表", description: "第一份表（如新版或系统输出）。", accept: ".xlsx,.xlsm,.xls,.csv" },
    { key: "file2", label: "B 表", description: "第二份表（如旧版或手工结果）。", accept: ".xlsx,.xlsm,.xls,.csv" },
  ], options: [{ key: "key", label: "关键列", kind: "text", value: "", placeholder: "留空时自动使用首个公共列" }] },
  currency: { action: "currency.convert", runLabel: "转换金额", files: [], options: [
    { key: "amount", label: "人民币金额", kind: "text", value: "", placeholder: "例如：12345.67" },
  ] },
};

/** 从静态功能规格生成新的参数对象，防止不同工作区共享可变引用。 */
function initialOptions(spec: FeatureSpec) {
  return Object.fromEntries(spec.options.map((field) => [field.key, field.value]));  // 生成新对象，防止不同工作区共享可变引用
}

/** 将上传和结果文件大小转换为紧凑单位。 */
function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/** 任务待复核状态优先于底层运行状态，向用户显示当前真正需要的动作。 */
function jobStatusLabel(job: WebJob) {
  if (job.review_pending) return "待复核";
  if (job.status === "completed") return "已完成";
  if (job.status === "failed") return "失败";
  if (job.status === "running") return "处理中";
  if (job.status === "queued") return "排队中";
  if (job.status === "cancelled") return "已取消";
  return "已中断";
}

/** 将服务端任务状态规范为设计系统支持的状态键。 */
function jobStatusKey(job: WebJob): StatusKey {
  if (job.review_pending) return "review";
  if (job.status === "queued" || job.status === "running" || job.status === "completed" || job.status === "failed" || job.status === "cancelled" || job.status === "interrupted") return job.status;
  return "interrupted";
}

/** 浏览器目录选择给出的 File 额外带相对路径，用于显示和去重。 */
type DirectoryFile = File & { webkitRelativePath?: string };

/** 拖放文件夹时 WebKit 目录条目；浏览器标准类型不完整，这里只声明读取所需的最小接口。 */
type WebkitFileEntry = {
  isFile: true;
  isDirectory: false;
  name: string;
  fullPath: string;
  file: (success: (file: File) => void, error?: (error: DOMException) => void) => void;
};

type WebkitDirectoryEntry = {
  isFile: false;
  isDirectory: true;
  name: string;
  fullPath: string;
  createReader: () => { readEntries: (success: (entries: WebkitEntry[]) => void, error?: (error: DOMException) => void) => void };
};

type WebkitEntry = WebkitFileEntry | WebkitDirectoryEntry;

function readFileEntry(entry: WebkitFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

function readEntryBatch(entry: WebkitDirectoryEntry): Promise<WebkitEntry[]> {
  return new Promise((resolve, reject) => entry.createReader().readEntries(resolve, reject));
}

/** 拖放目录得到的 File 不一定带相对路径，这里按 entry.fullPath 补齐，保证同名文件不互相覆盖。 */
function withRelativePath(file: File, fullPath: string): DirectoryFile {
  try {
    Object.defineProperty(file, "webkitRelativePath", { value: fullPath, configurable: true });
  } catch {
    // File 对象不可扩展时保留浏览器原始行为，仍可用名称和大小去重。
  }
  return file as DirectoryFile;
}

/** 递归展开拖入的目录条目，得到真实文件对象；拖放目录时 DataTransfer.files 可能只给一个 0 字节占位项。 */
async function filesFromEntry(entry: WebkitEntry | null | undefined): Promise<File[]> {
  if (!entry) return [];
  if (entry.isFile) {
    const file = await readFileEntry(entry);
    return file.size > 0 ? [withRelativePath(file, entry.fullPath)] : [];  // 目录占位项为 0 字节，不能进入上传列表。
  }
  if (entry.isDirectory) {
    const files: File[] = [];
    let batch = await readEntryBatch(entry);
    while (batch.length) {
      for (const child of batch) files.push(...await filesFromEntry(child));
      batch = await readEntryBatch(entry);
    }
    return files;
  }
  return [];
}

/** 从拖放事件读取文件；目录模式优先通过 WebKit entry 递归读取真实文件。 */
async function filesFromDataTransfer(dataTransfer: DataTransfer, directory: boolean): Promise<File[]> {
  const items = Array.from(dataTransfer.items || []);
  if (!directory) return Array.from(dataTransfer.files || []);
  const entries = items.map((item) => (item as DataTransferItem & { webkitGetAsEntry?: () => unknown }).webkitGetAsEntry?.());
  if (entries.some(Boolean)) {
    const groups = await Promise.all(entries.map((entry) => filesFromEntry(entry as WebkitEntry | null | undefined)));
    return groups.flat();
  }
  return Array.from(dataTransfer.files || []).filter((file) => file.size > 0);  // 不支持 entry API 时退回普通文件列表并过滤目录占位项
}

/**
 * 受控文件输入组件，支持文件/文件夹选择器和浏览器拖放。
 * 多选文件按稳定键去重，保留当前文件在前、新文件在后的顺序。
 */
function FileField({ config, files, onChange }: { config: FileGroup; files: File[]; onChange: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [readingDrop, setReadingDrop] = useState(false);
  const [dropError, setDropError] = useState("");

  useEffect(() => {
    // React 类型没有 webkitdirectory，目录选择属性需要直接写到原生节点。
    const input = inputRef.current;
    if (!input) return;
    if (config.directory) {
      input.setAttribute("webkitdirectory", "");
      input.setAttribute("directory", "");
    } else {
      input.removeAttribute("webkitdirectory");
      input.removeAttribute("directory");
    }
  }, [config.directory]);

  function fileKey(file: File) {
    const relative = (file as DirectoryFile).webkitRelativePath;
    return relative ? `${relative}-${file.size}` : `${file.name}-${file.size}`;  // 文件夹内同名文件用相对路径区分
  }

  function relativePath(file: File) {
    return (file as DirectoryFile).webkitRelativePath || file.name;
  }

  /** 合并新文件：文件夹模式保留全部内容，普通模式遵守单选或多选约束。 */
  function accept(next: File[]) {
    setDropError("");
    const merged = config.directory ? next : config.multiple ? [...files, ...next] : next.slice(0, 1);
    onChange(Array.from(new Map(merged.map((file) => [fileKey(file), file])).values()));
  }

  /** 处理浏览器拖放；目录模式需要递归读取 entry，不能直接使用只有占位项的 FileList。 */
  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    setDropError("");
    if (!config.directory) {
      accept(Array.from(event.dataTransfer.files));
      return;
    }
    setReadingDrop(true);
    void filesFromDataTransfer(event.dataTransfer, true).then((next) => {
      if (next.length) accept(next);
      else setDropError("没有从拖放的文件夹中读取到文件，请改用“选择文件夹”。");
    }).catch(() => setDropError("读取拖放文件夹失败，请改用“选择文件夹”。")).finally(() => setReadingDrop(false));
  }

  return <section className="fyt-flow-file-field" data-dragging={dragging ? "true" : undefined} data-has-files={files.length ? "true" : undefined} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={handleDrop}>
    <div className="fyt-flow-file-heading"><div><strong className="fyt-flow-file-title">{config.label}{config.optional ? <span className="fyt-flow-optional">可选</span> : null}</strong><p>{config.description}</p></div><Button variant="secondary" size="sm" type="button" onClick={() => inputRef.current?.click()}><Icon name="plus" size={15} />选择{config.directory ? "文件夹" : "文件"}</Button></div>
    <input ref={inputRef} className="fyt-flow-file-input" type="file" accept={config.accept === "*" ? undefined : config.accept} multiple={config.directory ? undefined : config.multiple} onChange={(event) => { accept(Array.from(event.target.files || [])); event.currentTarget.value = ""; }} />
    {files.length ? <div className="fyt-flow-file-list">{files.map((file, index) => <div className="fyt-flow-file-row" key={`${fileKey(file)}-${index}`}><Icon name="file" size={16} /><span><strong title={relativePath(file)}>{file.name}</strong><small>{config.directory && (file as DirectoryFile).webkitRelativePath ? `${relativePath(file)} · ${formatSize(file.size)}` : formatSize(file.size)}</small></span><IconButton className="fyt-flow-file-remove" size="sm" label={`移除 ${file.name}`} onClick={() => onChange(files.filter((_, itemIndex) => itemIndex !== index))}><Icon name="x" size={15} /></IconButton></div>)}</div> : <div className="fyt-flow-dropzone"><Icon name="plus" size={17} /><span>{readingDrop ? "正在读取文件夹内容…" : config.directory ? "拖放文件夹到此处，或选择本机文件夹" : "拖放到此处，或选择本机文件"}</span></div>}
    {dropError ? <p className="fyt-flow-drop-error" role="alert">{dropError}</p> : null}
  </section>;
}

/** 优先展示核心层结构化投影，未注册投影时仅提供安全的文本或下载提示。 */
function ResultValue({ job }: { job: WebJob }) {
  if (!job.result) return null;
  if (job.presentation) return <BusinessResultView presentation={job.presentation} />;
  const value = job.result as Record<string, unknown>;
  const envelope = value.result && typeof value.result === "object" ? value.result as Record<string, unknown> : value; // 兼容历史桥接结果外层多包一层 `result`。
  const text = typeof envelope.text === "string" ? envelope.text : "";
  if (text) return <div className="fyt-flow-result"><pre>{text}</pre></div>;
  return <div className="fyt-flow-result"><strong>处理结果已生成</strong><span>请下载结果文件查看完整内容。</span></div>;
}

/** 异步读取单个结果文件的结构化预览，并在切换文件或关闭后忽略旧响应。 */
function PreviewPanel({ file, onClose }: { file: WebJob["files"][number]; onClose: () => void }) {
  const [data, setData] = useState<PreviewData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; void previewJobFile(file).then((result) => { if (active) setData(result); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "预览失败"); }); return () => { active = false; }; }, [file]);  // active 守卫在切换文件后忽略旧预览响应
  return <div className="fyt-flow-preview"><div className="fyt-flow-preview-head"><div><span>在线预览</span><strong title={file.name}>{file.name}</strong></div><IconButton label="关闭预览" onClick={onClose}><Icon name="x" size={16} /></IconButton></div>{error ? <Notice tone="error">{error}</Notice> : data ? <div className="fyt-flow-preview-table"><table><tbody>{data.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => rowIndex === 0 ? <th key={cellIndex}>{cell}</th> : <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div> : <div className="fyt-empty-state"><h3>正在读取文件内容</h3></div>}{data?.truncated ? <small className="fyt-flow-preview-note">仅显示前 30 行，完整内容请下载文件查看</small> : null}</div>;
}

/**
 * 组织一个业务模块从输入到结果的完整生命周期。
 * `initialJobId` 用于从任务中心恢复历史任务；恢复任务不会重新上传或执行文件。
 */
export function FeatureWorkspace({ feature, onBack, onCompleted, initialJobId, backLabel = "返回业务模块" }: { feature: Feature; onBack: () => void; onCompleted: () => void; initialJobId?: string; backLabel?: string }) {
  const spec = SPECS[feature.key];
  if (!spec) {
    return <div className="fyt-feature-missing"><div><span className="fyt-eyebrow">提示</span><h3>「{feature.title}」使用独立页面</h3><p>该功能需要专用交互界面，请从左侧菜单进入「{feature.title}」。<button className="fyt-action-secondary" onClick={onBack} style={{ marginTop: 14 }}>{backLabel}</button></p></div></div>;
  }
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [options, setOptions] = useState<Record<string, string | boolean>>(() => initialOptions(spec));
  const [uploading, setUploading] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [job, setJob] = useState<WebJob | null>(null);
  const [history, setHistory] = useState<WebJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [previewFile, setPreviewFile] = useState<WebJob["files"][number] | null>(null);
  const [templates, setTemplates] = useState<JobTemplate[]>([]);
  const [templateName, setTemplateName] = useState("");
  const [preflight, setPreflight] = useState<{ warnings: string[]; missing: string[] } | null>(null);
  const isReconcile = feature.key === "reconcile_statement";
  const isArrival = feature.key === "arrival";
  const [scanResult, setScanResult] = useState<ReconcileScanFile[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [month, setMonth] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [reconcileHandles, setReconcileHandles] = useState<string[]>([]);
  const [arrivalRows, setArrivalRows] = useState<ArrivalScanRow[]>([]);
  const [arrivalScanning, setArrivalScanning] = useState(false);
  const [arrivalScanError, setArrivalScanError] = useState("");
  // 上传总进度需要跨文件组累计，因此先派生本次选择的文件总数。
  const totalFiles = useMemo(() => Object.values(files).reduce((count, items) => count + items.length, 0), [files]);  // 跨文件组累计总数，用于上传进度与可运行判断
  const canRun = isReconcile ? Boolean(reconcileHandles.length && selected.size && month.trim())
    : isArrival ? arrivalRows.some((row) => row.include && row.total > 0 && row.batch_no.trim())
    : spec.files.every((group) => group.optional || (files[group.key]?.length || 0) > 0)
    // 仅“明确必填”的输入项参与可用性判断：金额，以及未标记 optional 的文本域；可选文本域
    // （如考勤的“额外假休标记”）留空不应阻止启动，否则会把可选字段误判成必填导致按钮永远禁用。
    && spec.options
      .filter((field) => !field.optional && (field.kind === "textarea" || field.key === "amount"))
      .every((field) => String(options[field.key] || "").trim());  // 仅必填文本参数参与可用性判断，可选字段留空不阻止启动

  useEffect(() => {
    // 历史同时匹配正式动作与分析动作，使待复核任务也能在当前功能下恢复。
    const actions = new Set([spec.action, spec.reviewAction].filter(Boolean));  // 同时匹配正式动作与分析动作，待复核任务也能恢复
    setHistoryLoading(true);
    void listJobs().then((result) => setHistory(result.jobs.filter((item) => actions.has(item.action)).slice(0, 5))).catch(() => undefined).finally(() => setHistoryLoading(false));
  }, [spec.action, spec.reviewAction]);
  useEffect(() => { void listTemplates().then((result) => setTemplates(result.templates.filter((item) => item.action === spec.action))).catch(() => undefined); }, [spec.action]); // 模板只绑定正式动作，不与分析动作混用。

  useEffect(() => {
    if (!initialJobId) return;
    let active = true;
    setRestoring(true); setError("");
    void getJob(initialJobId).then(({ job: next }) => { if (active) setJob(next); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "读取任务失败"); }).finally(() => { if (active) setRestoring(false); });  // 恢复历史任务不重新上传或执行
    return () => { active = false; }; // 快速切换任务时不让旧详情覆盖当前工作区。
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
          setHistory((current) => [next, ...current.filter((item) => item.id !== next.id)].slice(0, 5)); // 完成任务移到首位并按编号去重。
          if (next.status === "completed") onCompleted();
        }
      }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "读取任务失败"); });
    }, 700);
    return () => { active = false; window.clearInterval(timer); };
  }, [job?.id, job?.status, onCompleted]);

  /**
   * 把通用表单状态转换为各核心动作要求的嵌套协议。
   * 转换只改变请求载荷，不修改页面参数；删除顶层字段可避免同一设置重复出现两处。
   */
  function buildPayload(handles: Record<string, string[]>) {
    const payload: Record<string, unknown> = { ...handles, ...options };
    if (feature.key === "attendance") {
      payload.options = {
        workday_hours: Number(options.workday_hours) || 9,
        overtime: Boolean(options.overtime),
        auto_actual: Boolean(options.auto_actual),
        conflict: String(options.conflict || "last"),
        day_max_hours: Number(options.day_max_hours) || 16,
        night_shift: Boolean(options.night_shift),
        night_start_hour: Number(options.night_start_hour) || 17,
        night_workday_hours: Number(options.night_workday_hours) || 11,
        night_max_hours: Number(options.night_max_hours) || 16,
        skip_extra: String(options.skip_extra || "").split(/[，,、\n\r]+/).map((item) => item.trim()).filter(Boolean), // 接受中文与英文分隔符，核心层收到规范字符串数组。
      };
      for (const key of ["workday_hours", "overtime", "auto_actual", "conflict", "day_max_hours", "night_shift", "night_start_hour", "night_workday_hours", "night_max_hours", "skip_extra"]) delete payload[key];
    }
    if (feature.key === "reconcile") {
      payload.options = { tolerance: Math.max(0, Number(options.tolerance) || 0) };
      delete payload.tolerance;
    }
    if (feature.key === "rename") {
      payload.rule = { find: options.find, replace: options.replace, prefix: options.prefix, suffix: options.suffix, ext_lower: options.ext_lower };
      for (const key of ["find", "replace", "prefix", "suffix", "ext_lower"]) delete payload[key];
    }
    if (feature.key === "text") payload.options = {};
    return payload;
  }

  /**
   * 顺序上传全部输入文件，执行服务端预检后创建任务并读取首个状态快照。
   * 同一次提交使用随机分组号，服务端可据此隔离和清理本批临时文件。
   */
  async function submit(action: string, extra: Record<string, unknown> = {}) {
    setError(""); setDownloadError(""); setUploading(true); setUploadedCount(0); setUploadProgress(0); setJob(null); setPreviewFile(null);
    try {
      const group = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`;  // 随机分组号隔离本批上传，服务端据此清理临时文件
      const handles: Record<string, string[]> = {};
      let completedFiles = 0;
      for (const config of spec.files) {
        handles[config.key] = [];
        // 当前采用顺序上传，整体进度可稳定按“已完成文件＋当前文件比例”累计。
        for (const file of files[config.key] || []) {
          const invalid = uploadableError(file);
          if (invalid) throw new Error(invalid);
          const uploaded = await uploadFile(file, group, (progress) => setUploadProgress(Math.max(0, Math.min(100, Math.round(((completedFiles + progress / 100) / Math.max(totalFiles, 1)) * 100)))));
          handles[config.key].push(uploaded.handle);
          completedFiles += 1;
          setUploadedCount(completedFiles); setUploadProgress(Math.round((completedFiles / Math.max(totalFiles, 1)) * 100));
        }
      }
      const check = await preflightJob(action, { ...buildPayload(handles), ...extra }); // 创建持久任务前确认上传句柄仍存在且归属当前用户。
      setPreflight({ warnings: check.warnings, missing: check.missing });
      if (!check.ok) throw new Error([...check.missing.map((item) => `文件不存在：${item}`), ...check.warnings].join("；"));
      const created = await createJob(action, feature.title, { ...buildPayload(handles), ...extra });  // 任务创建成功后才读取首个状态快照
      const next = await getJob(created.job_id);
      setJob(next.job);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务提交失败");
    } finally { setUploading(false); }
  }

  /** 应用同一正式动作保存的参数模板，文件选择不会从模板恢复。 */
  function applyTemplate(template: JobTemplate) { setOptions((current) => ({ ...current, ...(template.payload.options && typeof template.payload.options === "object" ? template.payload.options as Record<string, string | boolean> : {}) })); }

  /** 保存当前参数快照并重新读取模板列表，避免本地猜测服务端生成的编号。 */
  async function saveTemplate() {
    if (!templateName.trim()) return;
    setError("");
    try { await createTemplate(templateName.trim(), spec.action, { options }); setTemplateName(""); setTemplates((await listTemplates()).templates.filter((item) => item.action === spec.action)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "保存模板失败"); }
  }

  /**
   * 对账单专用扫描：先上传文件副本，再让服务端识别供应商和批次。
   * 新扫描会清除旧句柄与选择，防止把不同上传批次混入同一生成任务。
   */
  async function scanReconcileBatches() {
    if (!(files.paths?.length || 0)) return;
    setScanning(true); setScanError(""); setScanResult(null); setSelected(new Set()); setReconcileHandles([]);
    try {
      const group = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`;
      const handles: string[] = [];
      for (const file of files.paths || []) {
        const invalid = uploadableError(file);
        if (invalid) throw new Error(invalid);
        handles.push((await uploadFile(file, group)).handle);
      }
      const data = await scanReconcile(handles);
      setReconcileHandles(handles);
      setScanResult(data.files);
    } catch (reason) { setScanError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setScanning(false); }
  }

  /** 上传到料计划副本并读取每个文件的批次、完整主料类数和非零未到料数。 */
  async function scanArrivalPlans() {
    if (!(files.paths?.length || 0)) return;
    setArrivalScanning(true); setArrivalScanError(""); setArrivalRows([]); setJob(null);
    try {
      const group = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`;
      const handles: string[] = [];
      for (const file of files.paths || []) {
        const invalid = uploadableError(file);
        if (invalid) throw new Error(invalid);
        handles.push((await uploadFile(file, group)).handle);
      }
      setArrivalRows((await scanArrival(handles)).rows);
    } catch (reason) {
      setArrivalScanError(reason instanceof Error ? reason.message : "到料计划识别失败");
    } finally { setArrivalScanning(false); }
  }

  /** 更新单个到料批次的人工复核值，保留服务端返回的上传句柄和自动识别依据。 */
  function updateArrivalRow(index: number, patch: Partial<ArrivalScanRow>) {
    setArrivalRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));  // 只更新指定批次行，保留其他行引用不变
  }

  /** 以不可变 Set 切换扫描批次选择。 */
  function toggleBatch(key: string) {
    setSelected((prev) => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; });  // 复制 Set 再切换，确保 React 检测到新引用
  }

  /** 执行普通业务，或把对账单扫描选择转换为正式任务载荷。 */
  async function run() {
    if (isArrival) {
      setError(""); setDownloadError(""); setJob(null); setUploading(true);
      try {
        const rows = arrivalRows.map((row) => ({ path: row.path, batch_no: row.batch_no, total: row.total, remark: row.remark, include: row.include }));  // 只发送任务需要的字段，上传句柄保留在服务端
        const payload = { rows, top_label: String(options.top_label || "") };
        const check = await preflightJob(spec.action, payload);
        setPreflight({ warnings: check.warnings, missing: check.missing });
        if (!check.ok) throw new Error([...check.missing.map((item) => `文件不存在：${item}`), ...check.warnings].join("；"));
        const created = await createJob(spec.action, feature.title, payload);
        setJob((await getJob(created.job_id)).job);
      } catch (reason) { setError(reason instanceof Error ? reason.message : "任务提交失败"); }
      finally { setUploading(false); }
      return;
    }
    if (!isReconcile) { await submit(spec.action); return; }
    if (!reconcileHandles.length) { setScanError("请先点击「扫描批次」再生成对账单"); return; }
    setError(""); setDownloadError(""); setJob(null); setUploading(true);
    try {
      const supplierMap: Record<string, string> = {};
      scanResult?.forEach((_, index) => {
        const value = (overrides[String(index)] || "").trim();
        if (value) supplierMap[String(index + 1)] = value; // 扫描协议按一起始文件序号关联人工补填供应商。
      });
      const payload = { paths: reconcileHandles, selected: [...selected], month: month.trim(), supplier_map: supplierMap };
      const check = await preflightJob(spec.action, payload);
      setPreflight({ warnings: check.warnings, missing: check.missing });
      if (!check.ok) throw new Error([...check.missing.map((item) => `文件不存在：${item}`), ...check.warnings].join("；"));
      const created = await createJob(spec.action, feature.title, payload);
      setJob((await getJob(created.job_id)).job);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "任务提交失败"); }
    finally { setUploading(false); }
  }

  /** 启动只读分析动作，结果完成后由 `ReviewPanel` 收集人工选择。 */
  async function startReview() {
    if (spec.reviewAction) await submit(spec.reviewAction);
  }

  /** 提交分析任务的人工选择，并读取同一任务转入执行阶段后的最新状态。 */
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

  /** 下载当前任务结果，并把失败限制在下载提示而不改变业务任务状态。 */
  async function download(file: WebJob["files"][number]) {
    setDownloadError("");
    try { await downloadJobFile(file); } catch (reason) { setDownloadError(reason instanceof Error ? reason.message : "下载失败"); }
  }

  /** 下载历史结果版本中的文件。 */
  async function downloadVersion(file: { name: string; size: number; url: string }) {
    setDownloadError("");
    try { await downloadJobFile(file); } catch (reason) { setDownloadError(reason instanceof Error ? reason.message : "版本下载失败"); }
  }

  /** 从最近任务列表恢复任务详情，不重新执行任务。 */
  async function restoreJob(id: string) {
    setRestoring(true); setError(""); setDownloadError("");
    try { setJob((await getJob(id)).job); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "读取任务失败"); }
    finally { setRestoring(false); }
  }

  /** 请求取消当前排队或运行任务，并从服务端读取取消后的最终状态。 */
  async function cancelCurrentJob() {
    if (!job) return;
    setError("");
    try { await cancelJob(job.id); setJob((await getJob(job.id)).job); }  // 取消后读取服务端最终状态，不本地猜测
    catch (reason) { setError(reason instanceof Error ? reason.message : "取消任务失败"); }
  }

  const ready = totalFiles > 0;
  const running = uploading || Boolean(job && ["queued", "running"].includes(job.status));
  const finished = Boolean(job?.status === "completed") || Boolean(job?.review_pending);
  // 上传和后台处理都属于第三步；完成边界单独决定哪些步骤显示勾选。
  const workflowStep = finished ? 3 : running ? 3 : ready ? 2 : 1;  // 上传与后台处理都归入第三步，完成边界单独计算
  const workflowDone = finished ? 3 : running ? 2 : ready ? 1 : 0;

  return <div className="fyt-flow-page">
    <div className="fyt-flow-back"><Button variant="ghost" size="sm" type="button" onClick={onBack}><Icon name="left" size={16} />{backLabel}</Button></div>
    <div className="fyt-flow-header"><PageHeader eyebrow="在线业务处理" title={feature.title} description={feature.description} actions={<div className="fyt-flow-header-tools"><TemplateGuide featureKey={feature.key} title={feature.title} /><span className="fyt-flow-group">{feature.group}</span></div>} /></div>
    <WorkflowSteps step={workflowStep} done={workflowDone} />
    <div className="fyt-flow-layout"><section className="fyt-flow-form">
      {spec.files.map((group) => <FileField key={group.key} config={group} files={files[group.key] || []} onChange={(next) => { setFiles((current) => ({ ...current, [group.key]: next })); if (isReconcile) { setScanResult(null); setSelected(new Set()); setReconcileHandles([]); setScanError(""); } if (isArrival) { setArrivalRows([]); setArrivalScanError(""); } }} />)}
      {isArrival ? <section className="fyt-flow-section fyt-flow-scan"><header className="fyt-flow-section-head"><div><h2>批次与主料类数</h2><p>系统扫描完整源表，筛选隐藏行也会参与统计；剩余未收数非零的物料自动列为未到料。</p></div></header>
        <div className="fyt-flow-scan-actions"><Button variant="secondary" type="button" disabled={!totalFiles || arrivalScanning} loading={arrivalScanning} onClick={() => void scanArrivalPlans()}>识别批次与主料类数</Button><span className="fyt-flow-scan-hint">自动结果会预填到表格中，主料总类数仍可逐批修改。</span></div>
        {arrivalScanError ? <Notice tone="error">{arrivalScanError}</Notice> : null}
        {arrivalRows.length ? <div className="fyt-review-table-wrap"><table className="fyt-review-table fyt-arrival-review-table"><thead><tr><th>纳入</th><th>文件</th><th>批次号</th><th>主料总类数</th><th>未到料</th><th>备注</th></tr></thead><tbody>{arrivalRows.map((row, index) => <tr key={row.path}><td><input type="checkbox" checked={row.include} onChange={(event) => updateArrivalRow(index, { include: event.target.checked })} /></td><td><strong title={row.name}>{row.name}</strong></td><td><input value={row.batch_no} placeholder="请填写批次号" onChange={(event) => updateArrivalRow(index, { batch_no: event.target.value })} /></td><td><input type="number" min="0" step="1" value={row.total} onChange={(event) => updateArrivalRow(index, { total: Math.max(0, Number(event.target.value) || 0) })} /><small>自动识别 {row.auto_total} 类</small></td><td><strong>{row.missing_count} 类</strong><small>按非零剩余未收数识别</small></td><td><input value={row.remark} placeholder="可选" onChange={(event) => updateArrivalRow(index, { remark: event.target.value })} /></td></tr>)}</tbody></table></div> : null}
      </section> : null}
      {isReconcile ? <section className="fyt-flow-section fyt-flow-scan"><header className="fyt-flow-section-head"><div><h2>批次选择</h2><p>先扫描文件中的批次，再勾选要生成对账单的批次。</p></div></header>
        <div className="fyt-flow-scan-actions"><Button variant="secondary" type="button" disabled={!totalFiles || scanning} loading={scanning} onClick={() => void scanReconcileBatches()}>扫描批次</Button><span className="fyt-flow-scan-hint">扫描只读取已上传的文件副本。</span></div>
        {scanError ? <Notice tone="error">{scanError}</Notice> : null}
        {scanResult ? <div className="fyt-flow-scan">{scanResult.map((file, index) => <div className="fyt-flow-scan-file" key={file.name}>
          <div className="fyt-flow-scan-file-head"><strong title={file.name}>{file.name}</strong>{file.supplier ? <span className="fyt-flow-scan-supplier">供应商：<b>{file.supplier}</b></span> : <label className="fyt-flow-scan-supplier">供应商：<input placeholder="未识别，请填写" value={overrides[String(index)] || ""} onChange={(event) => setOverrides({ ...overrides, [String(index)]: event.target.value })} /></label>}</div>
          <div className="fyt-flow-batch-list">{file.batches.map((batch) => { const key = `${index + 1}:${batch.batch}`; return <label className="fyt-flow-batch" data-selected={selected.has(key) ? "true" : undefined} key={key}><input type="checkbox" checked={selected.has(key)} onChange={() => toggleBatch(key)} /><span><strong>{batch.batch}</strong><small>{batch.sheet} · {batch.rows} 行{batch.excluded_rows ? ` · 排除标黄 ${batch.excluded_rows} 行` : ""}</small></span></label>; })}</div>
        </div>)}<div className="fyt-flow-scan-actions"><label className="fyt-flow-month">月份（如 202607）<input value={month} onChange={(event) => setMonth(event.target.value)} placeholder="202607" /></label><span className="fyt-flow-scan-count">{selected.size} 个批次已选</span></div></div> : null}
      </section> : null}
      {spec.options.length ? <section className="fyt-flow-section"><header className="fyt-flow-section-head"><div><h2>处理参数</h2><p>只填写与本次处理有关的设置，未填写的可选项会使用默认值。</p></div></header>{templates.length ? <div className="fyt-flow-template-strip"><span>常用配置</span>{templates.map((template) => <Button variant="secondary" size="sm" type="button" key={template.id} onClick={() => applyTemplate(template)}>{template.name}</Button>)}</div> : null}<div className="fyt-flow-option-grid">{spec.options.map((field) => field.kind === "checkbox" ? <label className="fyt-flow-checkbox" key={field.key} htmlFor={`${feature.key}-${field.key}`}><input id={`${feature.key}-${field.key}`} type="checkbox" checked={Boolean(options[field.key])} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.checked }))} /><span>{field.label}</span></label> : <FormField key={field.key} label={field.label} htmlFor={`${feature.key}-${field.key}`} className={field.kind === "textarea" ? "fyt-flow-wide-field" : ""}><>{field.kind === "select" ? <select id={`${feature.key}-${field.key}`} value={String(options[field.key])} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.value }))}>{field.choices?.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select> : field.kind === "textarea" ? <textarea id={`${feature.key}-${field.key}`} value={String(options[field.key])} placeholder={field.placeholder} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.value }))} /> : <input id={`${feature.key}-${field.key}`} type={field.kind === "month" ? "month" : "text"} value={String(options[field.key])} placeholder={field.placeholder} onChange={(event) => setOptions((current) => ({ ...current, [field.key]: event.target.value }))} />}</></FormField>)}</div><div className="fyt-flow-template-save"><input value={templateName} onChange={(event) => setTemplateName(event.target.value)} placeholder="模板名称" /><Button variant="secondary" size="sm" type="button" disabled={!templateName.trim()} onClick={() => void saveTemplate()}>保存当前配置</Button></div></section> : null}
    </section><aside className="fyt-flow-task-panel"><div className="fyt-flow-task-head"><div>{job ? <StatusBadge status={jobStatusKey(job)} /> : <strong>{restoring ? "正在读取任务记录" : uploading ? "正在上传" : "等待输入"}</strong>}</div><span>{restoring ? "读取中" : job?.review_pending ? "需要确认" : job ? `${job.progress}%` : totalFiles ? `${totalFiles} 个文件` : "尚未提交"}</span></div>
      {(uploading || job && ["queued", "running"].includes(job.status)) ? <div className="fyt-flow-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={uploading ? uploadProgress : job?.progress || 0}><i style={{ width: `${uploading ? Math.max(4, uploadProgress) : Math.max(3, job?.progress || 3)}%` }} /></div> : null}
      {error || job?.error ? <Notice tone="error">{error || job?.error}</Notice> : null}
      {(() => {
        if (!job?.result) return null;
        const result = job.result as Record<string, unknown>;
        const newMaterials = Array.isArray(result.new_materials) ? result.new_materials as string[] : [];
        const newSuppliers = Array.isArray(result.new_suppliers) ? result.new_suppliers as string[] : [];
        if (!newMaterials.length && !newSuppliers.length) return null;
        return <Notice tone="info" className="fyt-flow-catalog"><span><strong>主数据档案提示：</strong>{newSuppliers.length ? `发现 ${newSuppliers.length} 个新供应商（${newSuppliers.slice(0, 5).join("、")}${newSuppliers.length > 5 ? " 等" : ""}）；` : ""}{newMaterials.length ? `发现 ${newMaterials.length} 个新材料` : ""}，已自动记录，可在系统管理的主数据中查看。</span></Notice>;
      })()}
      {job?.files.length ? <div className="fyt-flow-result-files"><strong>结果文件</strong>{job.files.map((file) => <div className="fyt-flow-result-file" key={file.url}><Button variant="ghost" size="sm" type="button" onClick={() => void download(file)}><Icon name="download" size={15} /><span><strong title={file.name}>{file.name}</strong><small>{formatSize(file.size)}</small></span></Button>{/\.(csv|xlsx?|xlsm|txt|json)$/i.test(file.name) ? <IconButton className="fyt-flow-preview-button" label={`在线预览 ${file.name}`} onClick={() => setPreviewFile(file)}><Icon name="search" size={15} /></IconButton> : null}</div>)}</div> : null}
      {downloadError ? <Notice tone="error">{downloadError}</Notice> : null}
      {job?.logs.length && job.status === "failed" ? <details className="fyt-flow-log"><summary>查看处理提示</summary><pre>{job.logs.join("\n")}</pre></details> : null}
      {job?.status === "completed" && !job.review_pending && !job.presentation ? <ResultValue job={job} /> : null}
      {job?.versions?.length ? <section className="fyt-flow-versions"><div className="fyt-flow-versions-head"><strong>结果版本</strong><span>每次成功处理都会保留历史结果</span></div>{job.versions.map((version) => <div className="fyt-flow-version" key={version.version}><div><strong>第 {version.version} 版</strong><small>{new Date(version.created_at).toLocaleString("zh-CN")}</small></div><div>{version.files.map((file) => <Button variant="ghost" size="sm" type="button" key={file.url} onClick={() => void downloadVersion(file)} title={`下载第 ${version.version} 版 ${file.name}`}><Icon name="download" size={14} />{file.name}</Button>)}</div></div>)}</section> : null}
      {previewFile ? <PreviewPanel file={previewFile} onClose={() => setPreviewFile(null)} /> : null}
      <div className="fyt-flow-actions">{job && ["queued", "running"].includes(job.status) ? <Button variant="danger" type="button" onClick={() => void cancelCurrentJob()}>取消任务</Button> : null}{spec.reviewAction && !job?.review_pending ? <Button variant={spec.reviewOnly ? "primary" : "secondary"} type="button" disabled={!canRun || uploading || Boolean(job && ["queued", "running"].includes(job.status))} loading={uploading} onClick={() => void startReview()}><Icon name="check" size={15} />{uploading ? `上传中 ${uploadedCount}/${totalFiles}` : spec.reviewLabel}</Button> : null}{!spec.reviewOnly ? <Button variant="primary" type="button" disabled={!canRun || uploading || Boolean(job && ["queued", "running"].includes(job.status)) || Boolean(job?.review_pending)} loading={uploading} onClick={() => void run()}>{uploading ? (isArrival ? "正在提交" : `上传中 ${uploadedCount}/${totalFiles}`) : spec.runLabel}<Icon name="arrow" size={16} /></Button> : null}</div>
    </aside></div>
    {job?.review_pending && job.result ? <div className="fyt-flow-result-stage fyt-flow-review-stage"><ReviewPanel key={job.id} kind={feature.key as "reconcile" | "pivot" | "invoice" | "compare" | "supplier_batch"} result={job.result} onConfirm={(choices) => void confirmReview(choices)} busy={reviewBusy} /></div> : null}
    {job?.status === "completed" && !job.review_pending && job.presentation ? <div className="fyt-flow-result-stage"><BusinessResultView presentation={job.presentation} /></div> : null}
    <section className="fyt-flow-history"><div className="fyt-flow-section-head"><div><span className="fyt-eyebrow">最近处理</span><h2>本功能任务记录</h2></div></div>{historyLoading ? <div className="fyt-empty-state"><h3>正在加载任务记录</h3></div> : history.length ? <div className="fyt-flow-history-list">{history.map((item) => <Button variant="ghost" className="fyt-flow-history-item" type="button" key={item.id} disabled={restoring} onClick={() => void restoreJob(item.id)}><StatusBadge status={jobStatusKey(item)} /><span><strong title={item.title}>{item.title}</strong><small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></span><Icon name="arrow" size={15} /></Button>)}</div> : <div className="fyt-empty-state"><h3>当前功能还没有任务记录</h3><p>提交一次处理后，历史任务会显示在这里。</p></div>}</section>
  </div>;
}
