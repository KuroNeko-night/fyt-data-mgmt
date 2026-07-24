import { useEffect, useMemo, useState } from "react";
import { bridgeRequest } from "../lib/bridge";
import { fileName } from "../lib/files";
import { FilePickerField, FieldRow, ResultSummary, TaskPanel } from "../components/FeatureUi";
import { useBridgeAction, useBridgeTask } from "../hooks/useBridgeTask";

const excelFilters = [{ name: "Excel 表格", extensions: ["xlsx", "xlsm", "xls", "csv"] }];

function useSheets(path: string) {
  const [sheets, setSheets] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    if (!path) {
      setSheets([]);
      return () => { active = false; };
    }
    bridgeRequest<{ sheets: string[] }>("system.sheets", { path })
      .then((response) => { if (active) setSheets(response.sheets || []); })
      .catch(() => { if (active) setSheets([]); });
    return () => { active = false; };
  }, [path]);
  return sheets;
}

function SheetSelect({ label, sheets, value, onChange }: { label: string; sheets: string[]; value: string; onChange: (value: string) => void }) {
  if (sheets.length <= 1) return null;
  return <FieldRow label={label} hint="留空时由 Python 自动识别"><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">自动识别</option>{sheets.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></FieldRow>;
}

interface AttendanceResult { out_files: string[]; out_dir: string; }

export function AttendancePage() {
  const [sources, setSources] = useState<string[]>([]);
  const [targets, setTargets] = useState<string[]>([]);
  const [options, setOptions] = useState({ workday_hours: 9, overtime: true, night_shift: true, night_start_hour: 17, night_workday_hours: 11, night_max_hours: 16 });
  const task = useBridgeTask<AttendanceResult>();
  const setNumber = (key: keyof typeof options, value: string) => {
    setOptions((current) => ({ ...current, [key]: Number(value) }));
    task.reset();
  };
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="系统数据（打卡来源）" description="考勤机或系统导出的原始打卡表，可多选。" value={sources} onChange={(next) => { setSources(next); task.reset(); }} multiple filters={excelFilters} />
    <FilePickerField label="待填考勤表（目标）" description="需要填写的考勤模板，可多选，原文件不会被覆盖。" value={targets} onChange={(next) => { setTargets(next); task.reset(); }} multiple filters={excelFilters} />
    <section className="option-card"><h3>计算口径</h3><div className="form-grid">
      <FieldRow label="白班标准工时"><input type="number" min="1" max="24" step="0.5" value={options.workday_hours} onChange={(event) => setNumber("workday_hours", event.target.value)} /></FieldRow>
      <FieldRow label="夜班判定钟点"><input type="number" min="0" max="23.5" step="0.5" value={options.night_start_hour} onChange={(event) => setNumber("night_start_hour", event.target.value)} /></FieldRow>
      <FieldRow label="夜班标准工时"><input type="number" min="1" max="24" step="0.5" value={options.night_workday_hours} onChange={(event) => setNumber("night_workday_hours", event.target.value)} /></FieldRow>
      <FieldRow label="夜班合理上限"><input type="number" min="1" max="24" step="0.5" value={options.night_max_hours} onChange={(event) => setNumber("night_max_hours", event.target.value)} /></FieldRow>
    </div><label className="check-row"><input type="checkbox" checked={options.night_shift} onChange={(event) => { setOptions({ ...options, night_shift: event.target.checked }); task.reset(); }} />启用跨零点夜班识别</label><label className="check-row"><input type="checkbox" checked={options.overtime} onChange={(event) => { setOptions({ ...options, overtime: event.target.checked }); task.reset(); }} />计算加班列</label></section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={sources.length > 0 && targets.length > 0} runLabel="开始填报" onRun={() => void task.run("attendance.run", { sources, targets, options })} outDir={task.outDir}>
      {task.result ? <ResultSummary><strong>已生成 {task.result.out_files.length} 个已填写考勤表</strong><span>{task.result.out_dir}</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface ReconcilePlan {
  target: { sheet: string; sheets: string[]; name_col: number; comp_col: number; work_col: number; names: string[] };
  only_labor: string[];
  only_zong: string[];
}
interface ReconcileResult { filled_path: string; summary_path: string; credibility: { level: string; score: number }; anomalies: unknown[]; }

export function ReconcilePage() {
  const [target, setTarget] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [labor, setLabor] = useState<string[]>([]);
  const [sheet, setSheet] = useState("");
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const [roles, setRoles] = useState({ name: "", comp: "", work: "" });
  const sheets = useSheets(target[0] || "");
  const analysis = useBridgeAction<ReconcilePlan>();
  const task = useBridgeTask<ReconcileResult>();
  const options = target[0] && sheet ? { columns: { [fileName(target[0])]: { sheet } } } : {};
  const choices = analysis.result ? {
    target_sheet: sheet || null,
    target_roles: Object.fromEntries(Object.entries(roles).filter(([, value]) => value).map(([key, value]) => [key, Number(value)])),
    aliases,
  } : null;
  const ready = Boolean(target.length && sources.length && labor.length);
  function resetReview() {
    setAliases({});
    setRoles({ name: "", comp: "", work: "" });
    analysis.reset();
    task.reset();
  }
  async function analyze() {
    const plan = await analysis.run("reconcile.analyze", { target, sources, labor, options });
    if (plan) setSheet((current) => current || plan.target.sheet || "");
  }
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="待对表（目标）" description="需要被核对填写的总表，选择一个。" value={target} onChange={(next) => { setTarget(next); setSheet(""); resetReview(); }} filters={excelFilters} />
    <SheetSelect label="待对表工作表" sheets={sheets} value={sheet} onChange={(next) => { setSheet(next); resetReview(); }} />
    <FilePickerField label="数据来源" description="已填好的考勤或工时数据，可多选。" value={sources} onChange={(next) => { setSources(next); resetReview(); }} multiple filters={excelFilters} />
    <FilePickerField label="对账单 / 工时单" description="需要与来源核对的劳务对账单，可多选。" value={labor} onChange={(next) => { setLabor(next); resetReview(); }} multiple filters={excelFilters} />
    <section className="option-card"><div className="section-heading compact"><div><h3>人工复核</h3><p>先分析结构和姓名差异，再按需纠正。</p></div><button className="secondary-button" disabled={!ready || analysis.busy} onClick={() => void analyze()}>{analysis.busy ? "分析中…" : "分析并复核"}</button></div>
      {analysis.error ? <div className="notice error">{analysis.error}</div> : null}
      {analysis.result ? <><div className="form-grid"><FieldRow label="姓名列（1 起）" hint={`自动：${analysis.result.target.name_col}`}><input value={roles.name} placeholder={String(analysis.result.target.name_col || "")} onChange={(event) => setRoles({ ...roles, name: event.target.value })} /></FieldRow><FieldRow label="公司列（1 起）" hint={`自动：${analysis.result.target.comp_col || "无"}`}><input value={roles.comp} placeholder={String(analysis.result.target.comp_col || "")} onChange={(event) => setRoles({ ...roles, comp: event.target.value })} /></FieldRow><FieldRow label="工时列（1 起）" hint={`自动：${analysis.result.target.work_col || "无"}`}><input value={roles.work} placeholder={String(analysis.result.target.work_col || "")} onChange={(event) => setRoles({ ...roles, work: event.target.value })} /></FieldRow></div>
        {analysis.result.only_labor.length ? <div className="review-list"><strong>待配对姓名 · {analysis.result.only_labor.length}</strong>{analysis.result.only_labor.map((name) => <label key={name}><span>{name}</span><select value={aliases[name] || ""} onChange={(event) => setAliases({ ...aliases, [name]: event.target.value })}><option value="">不配对</option>{analysis.result?.only_zong.map((candidate) => <option key={candidate}>{candidate}</option>)}</select></label>)}</div> : <div className="notice success">姓名已全部匹配。</div>}</> : <p className="empty-message">人工复核可选；不分析时按 Python 自动识别直接运行。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={ready} runLabel="开始对账" onRun={() => void task.run("reconcile.run", { target, sources, labor, options, choices })} outDir={task.outDir} outputPath={task.result?.summary_path}>
      {task.result ? <ResultSummary><strong>可信度 {task.result.credibility.level} · {task.result.credibility.score}/100</strong><span>异常 {task.result.anomalies.length} 条</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface ArrivalRow { path: string; batch_no: string; total: number; remark: string; include: boolean; }
interface ArrivalResult { out_file: string; out_dir: string; results: Array<[string, number, number, number]>; }

export function ArrivalPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [rows, setRows] = useState<ArrivalRow[]>([]);
  const [topLabel, setTopLabel] = useState("截止16点的数据");
  const prepare = useBridgeAction<{ rows: ArrivalRow[]; top_label: string }>();
  const task = useBridgeTask<ArrivalResult>();
  async function changePaths(next: string[]) {
    setPaths(next);
    task.reset();
    if (!next.length) { setRows([]); return; }
    const result = await prepare.run("arrival.prepare", { paths: next });
    if (result) { setRows(result.rows); setTopLabel(result.top_label); }
  }
  function updateRow(index: number, patch: Partial<ArrivalRow>) {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  }
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="送货计划表" description="含未收料数据的送货计划，可多选。" value={paths} onChange={(next) => void changePaths(next)} multiple filters={excelFilters} />
    <section className="option-card"><FieldRow label="表头标签"><input value={topLabel} onChange={(event) => setTopLabel(event.target.value)} /></FieldRow>{prepare.error ? <div className="notice error">{prepare.error}</div> : null}
      {rows.length ? <div className="editable-table"><table><thead><tr><th>纳入</th><th>文件</th><th>批次号</th><th>主料总类数</th><th>备注</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.path}><td><input type="checkbox" checked={row.include} onChange={(event) => updateRow(index, { include: event.target.checked })} /></td><td title={row.path}>{fileName(row.path)}</td><td><input value={row.batch_no} onChange={(event) => updateRow(index, { batch_no: event.target.value })} /></td><td><input type="number" min="0" value={row.total} onChange={(event) => updateRow(index, { total: Number(event.target.value) })} /></td><td><input value={row.remark} onChange={(event) => updateRow(index, { remark: event.target.value })} /></td></tr>)}</tbody></table></div> : <p className="empty-message">选择文件后自动识别批次。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={rows.some((row) => row.include)} runLabel="生成到料明细" onRun={() => void task.run("arrival.run", { rows, top_label: topLabel })} outDir={task.outDir} outputPath={task.result?.out_file}>
      {task.result ? <ResultSummary><strong>已写入 {task.result.results.length} 个批次</strong><span>{task.result.out_file}</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface PivotSheet { id: string; file: string; sheet: string; use: boolean; kind: string; confidence: number; reason: string; }
interface PivotHeld { sid: string; ridx: number; sheet?: string; summary?: string; rec?: unknown; }
interface PivotConflict { gk: unknown; default: string; dist?: Record<string, number>; variants?: Record<string, number>; name?: string; code?: string; spec?: string; }
interface PivotPlan { sheets: PivotSheet[]; held_index: PivotHeld[]; unit_conflicts: PivotConflict[]; spec_merges: PivotConflict[]; }
interface PivotResult { out: string; out_dir: string; report: string; groups: number; total: number; level: string; score: number; }

export function PivotPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [plan, setPlan] = useState<PivotPlan | null>(null);
  const [sheetUse, setSheetUse] = useState<Record<string, boolean>>({});
  const [held, setHeld] = useState<Record<string, boolean>>({});
  const [unitValues, setUnitValues] = useState<Record<string, string>>({});
  const [specValues, setSpecValues] = useState<Record<string, string>>({});
  const analysis = useBridgeTask<PivotPlan>();
  const task = useBridgeTask<PivotResult>();
  async function analyze() {
    const result = await analysis.run("pivot.analyze", { paths });
    if (!result) return;
    setPlan(result);
    setSheetUse(Object.fromEntries(result.sheets.map((sheet) => [sheet.id, sheet.use])));
    setHeld({});
    setUnitValues(Object.fromEntries(result.unit_conflicts.map((item, index) => [`u-${index}`, item.default || ""])));
    setSpecValues(Object.fromEntries(result.spec_merges.map((item, index) => [`s-${index}`, item.default || ""])));
  }
  const choices = plan ? {
    sheets: sheetUse,
    held: plan.held_index.map((item) => ({ sid: item.sid, ridx: item.ridx, keep: Boolean(held[`${item.sid}:${item.ridx}`]) })),
    unit_overrides: plan.unit_conflicts.map((item, index) => ({ gk: item.gk, value: unitValues[`u-${index}`] })).filter((item, index) => item.value !== (plan.unit_conflicts[index].default || "")),
    spec_overrides: plan.spec_merges.map((item, index) => ({ gk: item.gk, value: specValues[`s-${index}`] })).filter((item, index) => item.value !== (plan.spec_merges[index].default || "")),
  } : null;
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="采购数据表" description="包装方案、采购量核算表或组托辅材，可多选。" value={paths} onChange={(next) => { setPaths(next); setPlan(null); analysis.reset(); task.reset(); }} multiple filters={excelFilters} />
    <section className="option-card"><div className="section-heading compact"><div><h3>人工复核</h3><p>确认工作表、疑似误删行及单位规格归并。</p></div><button className="secondary-button" disabled={!paths.length || analysis.busy} onClick={() => void analyze()}>{analysis.busy ? "分析中…" : "分析数据"}</button></div>{analysis.error ? <div className="notice error">{analysis.error}</div> : null}
      {plan ? <div className="review-stack"><div className="editable-table"><table><thead><tr><th>纳入</th><th>文件</th><th>工作表</th><th>类型</th><th>可信度</th></tr></thead><tbody>{plan.sheets.map((sheet) => <tr key={sheet.id}><td><input type="checkbox" checked={sheetUse[sheet.id] ?? sheet.use} onChange={(event) => setSheetUse({ ...sheetUse, [sheet.id]: event.target.checked })} /></td><td>{sheet.file}</td><td title={sheet.reason}>{sheet.sheet}</td><td>{sheet.kind}</td><td>{sheet.confidence}</td></tr>)}</tbody></table></div>
        {plan.held_index.length ? <div className="review-list"><strong>疑似误删行 · {plan.held_index.length}</strong>{plan.held_index.map((item) => { const key = `${item.sid}:${item.ridx}`; return <label key={key}><input type="checkbox" checked={Boolean(held[key])} onChange={(event) => setHeld({ ...held, [key]: event.target.checked })} /><span>{item.sheet || item.sid} · {item.summary || JSON.stringify(item.rec)}</span></label>; })}</div> : null}
        {[{ title: "单位冲突", items: plan.unit_conflicts, prefix: "u", values: unitValues, setValues: setUnitValues }, { title: "规格归并", items: plan.spec_merges, prefix: "s", values: specValues, setValues: setSpecValues }].map((group) => group.items.length ? <div className="review-list" key={group.title}><strong>{group.title} · {group.items.length}</strong>{group.items.map((item, index) => { const key = `${group.prefix}-${index}`; const candidates = Object.keys(item.dist || item.variants || {}); return <label key={key}><span>{item.name || item.code || "未命名物料"}</span><select value={group.values[key] || ""} onChange={(event) => group.setValues({ ...group.values, [key]: event.target.value })}>{Array.from(new Set([item.default || "", ...candidates])).map((value) => <option key={value} value={value}>{value || "（空）"}</option>)}</select></label>; })}</div> : null)}</div> : <p className="empty-message">可先分析后复核，也可直接按默认规则生成。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={paths.length > 0} runLabel="生成透视表" onRun={() => void task.run("pivot.run", { paths, choices })} outDir={task.outDir} outputPath={task.result?.out}>
      {task.result ? <ResultSummary><strong>分组 {task.result.groups} 项 · 合计 {task.result.total}</strong><span>可信度 {task.result.level} · {task.result.score}/100</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface PurchaseResult { out_dir: string; report: string; pairs: unknown[]; matched1: boolean[]; matched2: boolean[]; qty_conflicts: unknown[]; }

export function PurchasePage() {
  const [file1, setFile1] = useState<string[]>([]);
  const [file2, setFile2] = useState<string[]>([]);
  const [sheet1, setSheet1] = useState("");
  const [sheet2, setSheet2] = useState("");
  const [name1, setName1] = useState("我方");
  const [name2, setName2] = useState("供方");
  const sheets1 = useSheets(file1[0] || "");
  const sheets2 = useSheets(file2[0] || "");
  const task = useBridgeTask<PurchaseResult>();
  const unmatched1 = task.result ? task.result.matched1.length - task.result.matched1.filter(Boolean).length : 0;
  const unmatched2 = task.result ? task.result.matched2.length - task.result.matched2.filter(Boolean).length : 0;
  const changeFile1 = (next: string[]) => { setFile1(next); setSheet1(""); task.reset(); };
  const changeFile2 = (next: string[]) => { setFile2(next); setSheet2(""); task.reset(); };
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="我方对账单" description="我方导出的采购或对账明细。" value={file1} onChange={changeFile1} filters={excelFilters} /><SheetSelect label="我方工作表" sheets={sheets1} value={sheet1} onChange={(next) => { setSheet1(next); task.reset(); }} />
    <FilePickerField label="供应商对单明细" description="供应商发来的对单明细。" value={file2} onChange={changeFile2} filters={excelFilters} /><SheetSelect label="供方工作表" sheets={sheets2} value={sheet2} onChange={(next) => { setSheet2(next); task.reset(); }} />
    <section className="option-card"><h3>双方显示名称</h3><div className="form-grid"><FieldRow label="我方"><input value={name1} onChange={(event) => setName1(event.target.value)} /></FieldRow><FieldRow label="供方"><input value={name2} onChange={(event) => setName2(event.target.value)} /></FieldRow></div></section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(file1.length && file2.length)} runLabel="开始对账" onRun={() => void task.run("purchase.run", { file1, file2, sheet1, sheet2, name1, name2 })} outDir={task.outDir} outputPath={task.result?.report}>
      {task.result ? <ResultSummary><strong>配对 {task.result.pairs.length} 对 · 数量疑点 {task.result.qty_conflicts.length}</strong><span>未对上：{name1} {unmatched1} 条 / {name2} {unmatched2} 条</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface DeliveryResult { plan_path: string; out_dir: string; rows: number; matched: number; missing: unknown[]; order_type: string; case_hit: number; case_used: boolean; supplier_used: boolean; }

export function DeliveryPage() {
  const [file1, setFile1] = useState<string[]>([]);
  const [file2, setFile2] = useState<string[]>([]);
  const [refPlan, setRefPlan] = useState<string[]>([]);
  const [sheet1, setSheet1] = useState("");
  const [sheet2, setSheet2] = useState("");
  const [orderType, setOrderType] = useState("SUB");
  const sheets1 = useSheets(file1[0] || "");
  const sheets2 = useSheets(file2[0] || "");
  const analysis = useBridgeAction<{ ok: boolean; header_row?: number; n_rows?: number; source?: string; error?: string }>();
  const task = useBridgeTask<DeliveryResult>();
  const changePrimary = (next: string[]) => { setFile1(next); setSheet1(""); analysis.reset(); task.reset(); };
  const changeSupplier = (next: string[]) => { setFile2(next); setSheet2(""); analysis.reset(); task.reset(); };
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="物料清单" description="含物料号与需求数量的主表。" value={file1} onChange={changePrimary} filters={excelFilters} /><SheetSelect label="物料清单工作表" sheets={sheets1} value={sheet1} onChange={(next) => { setSheet1(next); analysis.reset(); task.reset(); }} />
    <FilePickerField label="供应商明细" description="按物料号带出供应商代码与名称；不选则留空。" value={file2} onChange={changeSupplier} optional filters={excelFilters} /><SheetSelect label="供应商工作表" sheets={sheets2} value={sheet2} onChange={(next) => { setSheet2(next); task.reset(); }} />
    <FilePickerField label="参考送货计划" description="可按物料编码带出 CASE、托数和班组。" value={refPlan} onChange={(next) => { setRefPlan(next); task.reset(); }} optional filters={excelFilters} />
    <section className="option-card"><div className="segmented compact"><button className={orderType === "SUB" ? "active" : ""} onClick={() => setOrderType("SUB")}>SUB 订单</button><button className={orderType === "KD" ? "active" : ""} onClick={() => setOrderType("KD")}>KD 订单</button></div><button className="text-button" disabled={!file1.length || analysis.busy} onClick={() => void analysis.run("delivery.analyze", { path: file1, sheet: sheet1 })}>{analysis.busy ? "预检中…" : "预检物料清单"}</button>{analysis.result ? <div className={`notice ${analysis.result.ok ? "success" : "error"}`}>{analysis.result.ok ? `识别成功：表头第 ${analysis.result.header_row} 行，约 ${analysis.result.n_rows} 行数据。` : analysis.result.error}</div> : null}{analysis.error ? <div className="notice error">{analysis.error}</div> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={file1.length > 0} runLabel="生成送货计划" onRun={() => void task.run("delivery.run", { file1, file2, ref_plan: refPlan, sheet1, sheet2, order_type: orderType })} outDir={task.outDir} outputPath={task.result?.plan_path}>
      {task.result ? <ResultSummary><strong>{task.result.order_type} · {task.result.rows} 行 · 供应商匹配 {task.result.matched}</strong><span>未匹配 {task.result.missing.length} · CASE/班组 {task.result.case_used ? `${task.result.case_hit} 行` : "未使用"}</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface InvoiceItem { path: string; num: string; date: string; seller: string; amount: number | null; tax: number | null; total: number | null; rate: string; item_seed: string; note_seed: string; special: boolean; }
interface InvoiceScan { invoices: InvoiceItem[]; suspects: Array<[string, string]>; suggested_month: string; }
interface InvoiceResult { xlsx: string; review_dir: string; out_dir: string; count: number; suspects: number; }

export function InvoicePage() {
  const [root, setRoot] = useState<string[]>([]);
  const [month, setMonth] = useState("");
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [edits, setEdits] = useState<Record<string, { item: string; note: string }>>({});
  const scanTask = useBridgeTask<InvoiceScan>();
  const generateTask = useBridgeTask<InvoiceResult>();
  const specials = useMemo(() => (scanTask.result?.invoices || []).filter((item) => item.special), [scanTask.result]);
  async function scan() {
    generateTask.reset();
    const result = await scanTask.run("invoice.scan", { root: root[0] });
    if (!result) return;
    setMonth(result.suggested_month || "");
    setSelected(Object.fromEntries(result.invoices.filter((item) => item.special).map((item) => [item.num, true])));
    setEdits(Object.fromEntries(result.invoices.map((item) => [item.num, { item: item.item_seed || "", note: item.note_seed || "" }])));
  }
  const rows = specials.filter((invoice) => selected[invoice.num]).map((invoice) => ({ num: invoice.num, date: invoice.date, seller: invoice.seller, item: edits[invoice.num]?.item || "", amount: invoice.amount, tax: invoice.tax, total: invoice.total, rate: invoice.rate, note: edits[invoice.num]?.note || "" }));
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="资料文件夹" description="递归扫描其中全部 PDF，自动识别增值税专用发票。" value={root} onChange={(next) => { setRoot(next); setMonth(""); setSelected({}); setEdits({}); scanTask.reset(); generateTask.reset(); }} directory />
    <section className="option-card"><div className="section-heading compact"><div><h3>扫描与复核</h3><p>扫描后逐张勾选，并可修正费用项目与备注。</p></div><div className="toolbar-controls">{scanTask.busy ? <button className="secondary-button danger-button" onClick={() => void scanTask.cancel()}>取消扫描</button> : null}<button className="secondary-button" disabled={!root.length || scanTask.busy} onClick={() => void scan()}>{scanTask.busy ? "扫描中…" : "扫描识别发票"}</button></div></div>{scanTask.busy ? <div className="task-progress"><i style={{ width: `${Math.max(2, scanTask.progress ?? 4)}%` }} /></div> : null}{scanTask.error ? <div className="notice error">{scanTask.error}</div> : null}{scanTask.logs.length ? <details className="task-log"><summary>扫描日志 · {scanTask.logs.length} 条</summary><pre>{scanTask.logs.join("\n")}</pre></details> : null}
      {specials.length ? <><FieldRow label="统计月份"><input type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></FieldRow><div className="editable-table"><table><thead><tr><th>纳入</th><th>发票号码</th><th>日期</th><th>销售方</th><th>金额</th><th>费用项目</th><th>备注</th></tr></thead><tbody>{specials.map((invoice) => <tr key={invoice.num}><td><input type="checkbox" checked={Boolean(selected[invoice.num])} onChange={(event) => setSelected({ ...selected, [invoice.num]: event.target.checked })} /></td><td>{invoice.num}</td><td>{invoice.date}</td><td>{invoice.seller}</td><td>{invoice.total ?? "—"}</td><td><input value={edits[invoice.num]?.item || ""} onChange={(event) => setEdits({ ...edits, [invoice.num]: { ...edits[invoice.num], item: event.target.value } })} /></td><td><input value={edits[invoice.num]?.note || ""} onChange={(event) => setEdits({ ...edits, [invoice.num]: { ...edits[invoice.num], note: event.target.value } })} /></td></tr>)}</tbody></table></div>{scanTask.result?.suspects.length ? <div className="notice warning">另有 {scanTask.result.suspects.length} 项存疑，将写入复核清单。</div> : null}</> : scanTask.result ? <div className="notice error">未识别到增值税专用发票。</div> : null}
    </section>
    <TaskPanel busy={generateTask.busy} error={generateTask.error} logs={generateTask.logs} progress={generateTask.progress} onCancel={() => void generateTask.cancel()} canRun={Boolean(scanTask.result && rows.length && month)} runLabel="生成月度台账" onRun={() => void generateTask.run("invoice.generate", { scan: scanTask.result, rows, month })} outDir={generateTask.outDir} outputPath={generateTask.result?.xlsx}>
      {generateTask.result ? <ResultSummary><strong>已归档 {generateTask.result.count} 张专用发票</strong><span>存疑 {generateTask.result.suspects} 项</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}
