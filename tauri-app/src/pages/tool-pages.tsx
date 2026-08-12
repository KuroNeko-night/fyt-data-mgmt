/**
 * 桌面端通用文件工具页面。
 *
 * 本文件只组织参数、预览和桥接动作；重命名、文本处理、PDF、Excel 与表格比对
 * 的实际算法均由 Python `core/` 提供，前端不会重复解析或改写业务文件。
 */
import { useEffect, useState } from "react";
import { bridgeRequest } from "../lib/bridge";
import { fileName } from "../lib/files";
import { FilePickerField, FieldRow, ResultSummary, TaskPanel } from "../components/FeatureUi";
import { useBridgeAction, useBridgeTask } from "../hooks/useBridgeTask";
import BusinessResultView from "../ui/BusinessResultView";

const excelFilters = [{ name: "Excel 表格", extensions: ["xlsx", "xlsm", "xls", "csv"] }];
const pdfFilters = [{ name: "PDF 文件", extensions: ["pdf"] }];

interface RenameRule {
  find: string; replace: string; use_regex: boolean; prefix: string; suffix: string;
  base_name: string; seq_enabled: boolean; seq_start: number; seq_digits: number;
  seq_sep: string; ext_lower: boolean;
}
interface RenamePlan { items: Array<{ old_path: string; old_name: string; new_name: string; status: string; note: string }>; summary: { ok: number; blocked: number; same: number; total: number }; }
interface RenameResult { count: number; failed: Array<[string, string]>; undo_map: Array<[string, string]>; paths: string[]; }

/** 将重命名预览状态转换为操作含义，未知状态统一视为不可处理。 */
function renameStatusLabel(status: string) {
  if (status === "ok") return "可处理";
  if (status === "same") return "无需修改";
  if (status === "blocked") return "存在冲突";
  return "无法处理";
}

/**
 * 提供“预览后执行”的批量重命名工作流，并保留最近一次成功操作的撤销映射。
 * 规则或文件顺序变化都会使旧预览失效；只有服务端判定存在可处理项时才允许执行。
 */
export function RenamePage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [rule, setRule] = useState<RenameRule>({ find: "", replace: "", use_regex: false, prefix: "", suffix: "", base_name: "", seq_enabled: false, seq_start: 1, seq_digits: 3, seq_sep: "_", ext_lower: false });
  const preview = useBridgeAction<RenamePlan>();
  const task = useBridgeTask<RenameResult>();
  const undo = useBridgeAction<{ count: number; failed: Array<[string, string]> }>();
  // 任一规则变化都会改变目标文件名，必须同时清除预览、执行结果和旧撤销状态。
  const setText = (key: keyof RenameRule, value: string | number | boolean) => {
    setRule((current) => ({ ...current, [key]: value }));
    preview.reset();
    task.reset();
    undo.reset();
  };

  /** 执行当前已预览规则，并立即用服务端返回的新路径刷新下一轮预览。 */
  async function apply() {
    const result = await task.run("rename.apply", { paths, rule });
    // 文件已在磁盘原地改名，受控路径必须切换为真实新路径，不能继续引用旧名称。
    if (result) { setPaths(result.paths); await preview.run("rename.preview", { paths: result.paths, rule }); }
  }

  /** 使用执行结果附带的反向路径映射撤销最近一次成功改名，再同步刷新页面状态。 */
  async function undoLast() {
    if (!task.result?.undo_map.length) return;
    const result = await undo.run("rename.undo", { undo_map: task.result.undo_map });
    if (result) {
      // 映射元组的第二项是原始路径；撤销成功后它重新成为当前文件选择。
      const restored = task.result.undo_map.map(([, origin]) => origin);
      setPaths(restored);
      await preview.run("rename.preview", { paths: restored, rule });
    }
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="待重命名文件" description="按选择顺序生成序号；可用箭头调整顺序，原地重命名，先预览再应用。" value={paths} onChange={(next) => { setPaths(next); preview.reset(); task.reset(); undo.reset(); }} multiple reorderable />
    <section className="fyt-option-card"><h3>重命名规则</h3><div className="fyt-form-grid"><FieldRow label="查找"><input value={rule.find} onChange={(event) => setText("find", event.target.value)} /></FieldRow><FieldRow label="替换为"><input value={rule.replace} onChange={(event) => setText("replace", event.target.value)} /></FieldRow><FieldRow label="前缀"><input value={rule.prefix} onChange={(event) => setText("prefix", event.target.value)} /></FieldRow><FieldRow label="后缀"><input value={rule.suffix} onChange={(event) => setText("suffix", event.target.value)} /></FieldRow><FieldRow label="统一基名"><input value={rule.base_name} onChange={(event) => setText("base_name", event.target.value)} /></FieldRow><FieldRow label="序号起始 / 位数"><div className="fyt-inline-fields"><input type="number" min="0" value={rule.seq_start} onChange={(event) => setText("seq_start", Number(event.target.value))} /><input type="number" min="1" max="8" value={rule.seq_digits} onChange={(event) => setText("seq_digits", Number(event.target.value))} /><input value={rule.seq_sep} onChange={(event) => setText("seq_sep", event.target.value)} /></div></FieldRow></div><div className="fyt-check-grid"><label className="fyt-check-row"><input type="checkbox" checked={rule.use_regex} onChange={(event) => setText("use_regex", event.target.checked)} />按正则表达式</label><label className="fyt-check-row"><input type="checkbox" checked={rule.seq_enabled} onChange={(event) => setText("seq_enabled", event.target.checked)} />追加序号</label><label className="fyt-check-row"><input type="checkbox" checked={rule.ext_lower} onChange={(event) => setText("ext_lower", event.target.checked)} />扩展名转小写</label></div><button className="fyt-secondary-button" disabled={!paths.length || preview.busy} onClick={() => void preview.run("rename.preview", { paths, rule })}>{preview.busy ? "预览中…" : "刷新预览"}</button>{preview.error ? <div className="fyt-page-notice error">{preview.error}</div> : null}</section>
    {preview.result ? <section className="fyt-table-card"><div className="fyt-table-toolbar"><strong>可重命名 {preview.result.summary.ok} 个</strong><span>冲突 {preview.result.summary.blocked} · 无变化 {preview.result.summary.same}</span></div><div className="fyt-table-scroll"><table><thead><tr><th>原文件名</th><th>新文件名</th><th>状态</th></tr></thead><tbody>{preview.result.items.map((item) => <tr key={item.old_path}><td>{item.old_name}</td><td>{item.new_name || "—"}</td><td><span className={`fyt-task-status ${item.status === "ok" ? "ok" : "failed"}`}>{renameStatusLabel(item.status)}{item.note ? ` · ${item.note}` : ""}</span></td></tr>)}</tbody></table></div></section> : null}
    <TaskPanel busy={task.busy} error={task.error || undo.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(preview.result?.summary.ok)} runLabel="应用重命名" onRun={() => void apply()}>
      {task.result ? <ResultSummary><strong>已重命名 {task.result.count} 个文件</strong><span>失败 {task.result.failed.length} 个</span><button className="fyt-secondary-button" disabled={undo.busy || !task.result.undo_map.length} onClick={() => void undoLast()}>{undo.busy ? "撤销中…" : "撤销上次"}</button></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

const textOperations = [
  ["dedup", "行去重"], ["sort", "排序"], ["reverse", "倒序"],
  ["remove_empty", "去空行"], ["trim", "去首尾空格"], ["collapse", "压缩空格"],
  ["upper", "转大写"], ["lower", "转小写"], ["line_numbers", "加行号"],
  ["email", "提取邮箱"], ["phone", "提取手机号"], ["url", "提取网址"],
];

/** 将小型文本转换统一交给桥接动作，并允许用户把结果回填后串联多步处理。 */
export function TextPage() {
  const [source, setSource] = useState("");
  const [result, setResult] = useState("");
  const [options, setOptions] = useState({ ignore_case: false, numeric: false, reverse: false, pad: false });
  const action = useBridgeAction<{ text: string; stats: { lines: number; chars: number } }>();

  /** 运行单个文本动作；先清空旧结果，避免请求期间把上一次内容误认为本次输出。 */
  async function transform(operation: string) {
    setResult("");
    const response = await action.run("text.transform", { text: source, operation, options });
    if (response) setResult(response.text);
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-text-workbench"><div className="fyt-editor-panel"><div><strong>原文本</strong><span>{source.length} 字符</span></div><textarea value={source} onChange={(event) => setSource(event.target.value)} placeholder="在这里粘贴或输入文本" /><button className="fyt-text-button" onClick={() => setSource("")}>清空</button></div><div className="fyt-editor-panel"><div><strong>结果</strong><span>{result.length} 字符</span></div><textarea value={result} readOnly placeholder="处理结果显示在这里" /><div><button className="fyt-text-button" disabled={!result} onClick={() => setSource(result)}>回填到原文本</button><button className="fyt-text-button" disabled={!result} onClick={() => void navigator.clipboard.writeText(result)}>复制结果</button></div></div></section>
    <section className="fyt-option-card"><div className="fyt-check-grid"><label className="fyt-check-row"><input type="checkbox" checked={options.ignore_case} onChange={(event) => setOptions({ ...options, ignore_case: event.target.checked })} />忽略大小写</label><label className="fyt-check-row"><input type="checkbox" checked={options.numeric} onChange={(event) => setOptions({ ...options, numeric: event.target.checked })} />按数字排序</label><label className="fyt-check-row"><input type="checkbox" checked={options.reverse} onChange={(event) => setOptions({ ...options, reverse: event.target.checked })} />降序</label><label className="fyt-check-row"><input type="checkbox" checked={options.pad} onChange={(event) => setOptions({ ...options, pad: event.target.checked })} />行号补零</label></div><div className="fyt-operation-grid">{textOperations.map(([key, label]) => <button key={key} className="fyt-secondary-button" disabled={action.busy} onClick={() => void transform(key)}>{label}</button>)}</div>{action.error ? <div className="fyt-page-notice error">{action.error}</div> : null}</section>
  </div>;
}

interface FileToolResult { out_dir: string; out_files: string[]; }

/**
 * 汇总 PDF 合并、拆分、提取和删页入口。
 * 合并依赖文件选择顺序；其余模式只处理首个文件，并按模式决定是否要求页码表达式。
 */
export function PdfPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [mode, setMode] = useState("merge");
  const [splitMode, setSplitMode] = useState("each");
  const [spec, setSpec] = useState("");
  const [pages, setPages] = useState<number | null>(null);
  const task = useBridgeTask<FileToolResult>();
  // 切换模式时旧页码范围不再具有相同语义，因此一并清空任务结果和范围输入。
  const changeMode = (next: string) => { setMode(next); setSpec(""); task.reset(); };
  useEffect(() => {
    let active = true;
    if (!paths[0] || mode === "merge") { setPages(null); return () => { active = false; }; }
    // 页数只用于辅助填写，不阻断主任务；读取失败时退回未知页数而非制造页面错误。
    bridgeRequest<{ pages: number }>("pdf.info", { path: paths[0] }).then((response) => { if (active) setPages(response.pages); }).catch(() => { if (active) setPages(null); });
    // 文件或模式快速切换时忽略旧请求结果，避免旧 PDF 页数覆盖当前选择。
    return () => { active = false; };
  }, [paths, mode]);
  const needsSpec = mode === "extract" || mode === "delete" || (mode === "split" && splitMode === "ranges");
  const canRun = mode === "merge" ? paths.length >= 2 : Boolean(paths.length && (!needsSpec || spec.trim()));
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form"><section className="fyt-option-card"><div className="fyt-segmented fyt-four">{[["merge", "合并"], ["split", "拆分"], ["extract", "提取页"], ["delete", "删除页"]].map(([key, label]) => <button key={key} className={mode === key ? "active" : ""} onClick={() => changeMode(key)}>{label}</button>)}</div></section><FilePickerField label="PDF 文件" description="合并时按选择顺序；其他操作仅处理第一个文件。" value={paths} onChange={(next) => { setPaths(next); task.reset(); }} multiple filters={pdfFilters} />
    <section className="fyt-option-card">{mode === "split" ? <FieldRow label="拆分方式"><select value={splitMode} onChange={(event) => { setSplitMode(event.target.value); setSpec(""); task.reset(); }}><option value="each">每页一个文件</option><option value="ranges">按范围分段</option></select></FieldRow> : null}{needsSpec ? <FieldRow label="页码范围" hint="例如 1,3,5-8,12-"><input value={spec} onChange={(event) => { setSpec(event.target.value); task.reset(); }} /></FieldRow> : null}{pages !== null ? <p className="fyt-field-help">{fileName(paths[0])} 共 {pages} 页</p> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={canRun} runLabel="开始处理" onRun={() => void task.run("pdf.run", { paths, mode, split_mode: splitMode, spec })} outDir={task.outDir}>{task.result ? <ResultSummary><strong>已生成 {task.result.out_files.length} 个 PDF</strong></ResultSummary> : null}</TaskPanel></section></div>;
}

/** 根据选定模式组织 Excel 文件工具参数，具体格式保真与输出拆分由核心层完成。 */
export function ExcelToolsPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [mode, setMode] = useState("merge");
  const [target, setTarget] = useState("xlsx");
  const [hasHeader, setHasHeader] = useState(true);
  const [keepFormula, setKeepFormula] = useState(false);
  const task = useBridgeTask<FileToolResult>();
  const changeMode = (next: string) => { setMode(next); task.reset(); };
  const canRun = mode === "merge" || mode === "stack" ? paths.length >= 2 : paths.length >= 1;
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form"><section className="fyt-option-card"><div className="fyt-segmented fyt-four">{[["merge", "多簿合并"], ["split", "按 Sheet 拆分"], ["convert", "格式转换"], ["stack", "纵向合并"]].map(([key, label]) => <button key={key} className={mode === key ? "active" : ""} onClick={() => changeMode(key)}>{label}</button>)}</div></section><FilePickerField label="表格文件" description="支持 xlsx、xlsm、xls、csv，可多选。" value={paths} onChange={(next) => { setPaths(next); task.reset(); }} multiple filters={excelFilters} />
    <section className="fyt-option-card">{mode === "convert" ? <FieldRow label="转换目标"><select value={target} onChange={(event) => setTarget(event.target.value)}><option value="xlsx">xlsx</option><option value="csv">CSV（每个 Sheet 一个文件）</option></select></FieldRow> : null}{mode === "merge" ? <label className="fyt-check-row"><input type="checkbox" checked={keepFormula} onChange={(event) => setKeepFormula(event.target.checked)} />保留公式</label> : null}{mode === "stack" ? <label className="fyt-check-row"><input type="checkbox" checked={hasHeader} onChange={(event) => setHasHeader(event.target.checked)} />首行是表头，仅保留一次并添加来源文件列</label> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={canRun} runLabel="开始处理" onRun={() => void task.run("excel.run", { paths, mode, target, has_header: hasHeader, keep_formula: keepFormula })} outDir={task.outDir}>{task.result ? <ResultSummary><strong>已生成 {task.result.out_files.length} 个文件</strong></ResultSummary> : null}</TaskPanel></section></div>;
}

interface ComparePrepare { common: string[]; headers1: string[]; headers2: string[]; }
interface CompareResult { out_dir: string; report_path: string; counts: { diffs: number; only_a: number; only_b: number; same: number }; diffs: Array<{ key: string; column: string; a: unknown; b: unknown }>; only_a: Array<{ key: string; row: Record<string, unknown> }>; only_b: Array<{ key: string; row: Record<string, unknown> }>; }

/** 为表格比对页读取工作表列表，路径变化后忽略仍在返回途中的旧请求。 */
function useSheets(path: string) {
  const [sheets, setSheets] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    if (!path) { setSheets([]); return () => { active = false; }; }
    // 工作表读取是辅助请求；快速换文件后通过 active 标记丢弃已经过期的响应。
    bridgeRequest<{ sheets: string[] }>("system.sheets", { path }).then((response) => { if (active) setSheets(response.sheets || []); }).catch(() => { if (active) setSheets([]); });
    return () => { active = false; };
  }, [path]);
  return sheets;
}

/**
 * 先读取两份表格的公共列，再让用户明确关键列和比较列，最后生成结构化差异及报告。
 * 表头准备结果与正式比对结果分开保存，避免参数变化后误用旧差异。
 */
export function ComparePage() {
  const [file1, setFile1] = useState<string[]>([]);
  const [file2, setFile2] = useState<string[]>([]);
  const [sheet1, setSheet1] = useState("");
  const [sheet2, setSheet2] = useState("");
  const [keyColumn, setKeyColumn] = useState("");
  const [compareColumns, setCompareColumns] = useState<string[]>([]);
  const sheets1 = useSheets(file1[0] || "");
  const sheets2 = useSheets(file2[0] || "");
  const prepare = useBridgeAction<ComparePrepare>();
  const task = useBridgeTask<CompareResult>();
  const resetComparison = () => { setKeyColumn(""); setCompareColumns([]); prepare.reset(); task.reset(); };

  /** 读取公共列，并尽量保留当前仍合法的关键列与比较列选择。 */
  async function loadColumns() {
    const result = await prepare.run("compare.prepare", { file1, file2, sheet1, sheet2 });
    if (!result) return;
    const nextKey = result.common.includes(keyColumn) ? keyColumn : result.common[0] || "";
    const selectable = result.common.filter((column) => column !== nextKey);
    setKeyColumn(nextKey);
    setCompareColumns((current) => {
      // 用户原选择仍存在时优先保留；全部失效或首次读取时默认比较其余所有公共列。
      const retained = current.filter((column) => selectable.includes(column));
      return retained.length ? retained : selectable;
    });
  }
  const selectableColumns = (prepare.result?.common || []).filter((column) => column !== keyColumn);

  /** 更换配对关键列，并从比较列中移除新关键列，防止同一列承担两种角色。 */
  function changeKeyColumn(nextKey: string) {
    const selectable = (prepare.result?.common || []).filter((column) => column !== nextKey);
    setKeyColumn(nextKey);
    setCompareColumns((current) => {
      const retained = current.filter((column) => selectable.includes(column));
      return retained.length ? retained : selectable;
    });
    task.reset();
  }

  /** 切换单个比较列；选择变化会使已有差异结果失效。 */
  function toggleCompareColumn(column: string) {
    setCompareColumns((current) => current.includes(column)
      ? current.filter((item) => item !== column)
      : [...current, column]);
    task.reset();
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form"><FilePickerField label="A 表" description="通常放程序输出或新版。" value={file1} onChange={(next) => { setFile1(next); setSheet1(""); resetComparison(); }} filters={excelFilters} />{sheets1.length > 1 ? <FieldRow label="A 表工作表"><select value={sheet1} onChange={(event) => { setSheet1(event.target.value); resetComparison(); }}><option value="">自动识别</option>{sheets1.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></FieldRow> : null}<FilePickerField label="B 表" description="通常放手工结果或旧版。" value={file2} onChange={(next) => { setFile2(next); setSheet2(""); resetComparison(); }} filters={excelFilters} />{sheets2.length > 1 ? <FieldRow label="B 表工作表"><select value={sheet2} onChange={(event) => { setSheet2(event.target.value); resetComparison(); }}><option value="">自动识别</option>{sheets2.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></FieldRow> : null}
    <section className="fyt-option-card"><div className="fyt-section-heading fyt-compact"><div><h3>比对范围</h3><p>先读取两表公共列，再选择配对依据与需要核对的字段。</p></div><button className="fyt-secondary-button" disabled={!file1.length || !file2.length || prepare.busy} onClick={() => void loadColumns()}>{prepare.busy ? "读取中…" : "读取公共列"}</button></div>{prepare.error ? <div className="fyt-page-notice error">{prepare.error}</div> : null}{prepare.result ? <><FieldRow label="按此列配对"><select value={keyColumn} onChange={(event) => changeKeyColumn(event.target.value)}>{prepare.result.common.map((column) => <option key={column}>{column}</option>)}</select></FieldRow><div className="fyt-review-toolbar"><strong>比较列</strong><span>已选 {compareColumns.length} 列</span><div><button className="fyt-text-button" type="button" onClick={() => { setCompareColumns(selectableColumns); task.reset(); }}>全选</button><button className="fyt-text-button" type="button" onClick={() => { setCompareColumns([]); task.reset(); }}>清空</button></div></div>{selectableColumns.length ? <div className="fyt-review-list">{selectableColumns.map((column) => <label key={column}><input type="checkbox" checked={compareColumns.includes(column)} onChange={() => toggleCompareColumn(column)} /><span>{column}</span></label>)}</div> : <p className="fyt-empty-message">除关键列外没有其他公共列可比较。</p>}</> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(keyColumn && compareColumns.length)} runLabel="开始比对" onRun={() => void task.run("compare.run", { file1, file2, sheet1, sheet2, key: keyColumn, columns: compareColumns })} outDir={task.outDir} outputPath={task.result?.report_path}>{task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <><ResultSummary><strong>差异 {task.result.counts.diffs} 处</strong><span>只在 A {task.result.counts.only_a} · 只在 B {task.result.counts.only_b}</span></ResultSummary><div className="fyt-editable-table"><table><thead><tr><th>关键值</th><th>列</th><th>A</th><th>B</th></tr></thead><tbody>{/* 页面只展示前一百条便于快速复核，完整差异仍保存在输出报告中。 */}{task.result.diffs.slice(0, 100).map((item, index) => <tr key={`${item.key}-${item.column}-${index}`}><td>{item.key}</td><td>{item.column}</td><td>{String(item.a ?? "")}</td><td>{String(item.b ?? "")}</td></tr>)}</tbody></table></div></> : null}</TaskPanel></section></div>;
}
