import { useMemo, useState, type ReactNode } from "react";
import { Icon } from "./icons";

type ReviewKind = "reconcile" | "pivot" | "invoice" | "compare";
type ReviewPanelProps = {
  kind: ReviewKind;
  result: unknown;
  onConfirm: (choices: Record<string, unknown>) => void;
  busy?: boolean;
};

function unwrap(value: unknown): Record<string, any> {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  return record.result && typeof record.result === "object" ? record.result as Record<string, any> : record as Record<string, any>;
}

function ReviewShell({ title, description, onConfirm, busy, confirmDisabled, children, actionLabel }: ReviewPanelProps & { title: string; description: string; actionLabel: string; confirmDisabled?: boolean; children: ReactNode }) {
  return <section className="web-review-panel">
    <div className="web-review-head"><div><span className="section-label">人工复核</span><h3>{title}</h3><p>{description}</p></div><span className="web-review-mark"><Icon name="check" size={17} /></span></div>
    <div className="web-review-body">{children}</div>
    <div className="web-review-actions"><span>确认后将继续执行并生成结果文件</span><button className="primary-button" disabled={busy || confirmDisabled} onClick={() => onConfirm({})}>{busy ? "正在提交…" : actionLabel}<Icon name="arrow" size={16} /></button></div>
  </section>;
}

type ReconcilePlan = { target: { file: string; sheet: string; sheets?: string[]; name_col?: number; comp_col?: number; work_col?: number }; only_labor?: string[]; only_zong?: string[]; sources?: Array<Record<string, unknown>>; labor?: Array<Record<string, unknown>> };

function ReconcileReview({ plan, onConfirm, busy }: { plan: ReconcilePlan; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const target = plan.target || { file: "", sheet: "" };
  const [sheet, setSheet] = useState(target.sheet || "");
  const [roles, setRoles] = useState<Record<string, number>>({ name: target.name_col || 0, comp: target.comp_col || 0, work: target.work_col || 0 });
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const candidates = plan.only_zong || [];
  const upper = Math.max(20, Math.min(60, Math.max(target.name_col || 0, target.comp_col || 0, target.work_col || 0) + 10));
  const choices = () => ({
    target_sheet: sheet && sheet !== target.sheet ? sheet : null,
    target_roles: Object.fromEntries(Object.entries(roles).filter(([key, value]) => value && value !== (target as Record<string, any>)[`${key}_col`])),
    aliases: Object.fromEntries(Object.entries(aliases).filter(([, value]) => value.trim())),
    save_mapping: true,
  });
  return <ReviewShell kind="reconcile" result={plan} onConfirm={() => onConfirm(choices())} busy={busy} title="工时对账确认" description="确认目标表结构和姓名配对后，再生成对账结果。" actionLabel="按此对账">
    <div className="review-block"><div className="review-block-title">目标表结构</div><div className="review-form-grid"><label>文件<strong>{target.file}</strong></label><label>工作表<select value={sheet} onChange={(event) => setSheet(event.target.value)}>{(target.sheets || [target.sheet]).map((item) => <option value={item} key={item}>{item}</option>)}</select></label>{[["name", "姓名列"], ["comp", "所属公司列"], ["work", "出勤工时列"]].map(([key, label]) => <label key={key}>{label}<select value={String(roles[key])} onChange={(event) => setRoles((current) => ({ ...current, [key]: Number(event.target.value) }))}><option value="0">自动识别</option>{Array.from({ length: upper }, (_, index) => index + 1).map((column) => <option value={column} key={column}>第 {column} 列</option>)}</select></label>)}</div></div>
    <div className="review-block"><div className="review-block-title">姓名匹配 <span>{(plan.only_labor || []).length} 项待确认</span></div>{plan.only_labor?.length ? <div className="review-edit-list">{plan.only_labor.map((name) => <label key={name}><span>{name}</span><select value={aliases[name] || ""} onChange={(event) => setAliases((current) => ({ ...current, [name]: event.target.value }))}><option value="">不配对</option>{candidates.map((candidate) => <option value={candidate} key={candidate}>{candidate}</option>)}</select></label>)}</div> : <p className="review-empty">两侧姓名已全部匹配，无需手动配对。</p>}</div>
    <div className="review-block review-readonly"><div className="review-block-title">识别概况</div><p>数据来源 {plan.sources?.length || 0} 份，对账单 {plan.labor?.length || 0} 份；仅我司有 {plan.only_zong?.length || 0} 人。</p></div>
  </ReviewShell>;
}

type PivotPlan = { sheets?: Array<{ id: number | string; file: string; sheet: string; use: boolean; kind: string; confidence: number; reason?: string }>; held_index?: Array<{ sid: number | string; ridx: number; file?: string; sheet?: string; rec?: unknown }>; unit_conflicts?: Array<{ gk: unknown; default?: string; dist?: Record<string, number>; name?: string; code?: string; spec?: string }>; spec_merges?: Array<{ gk: unknown; default?: string; variants?: Record<string, number>; name?: string; code?: string }> };

function PivotReview({ plan, onConfirm, busy }: { plan: PivotPlan; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const sheets = plan.sheets || [];
  const held = plan.held_index || [];
  const units = plan.unit_conflicts || [];
  const specs = plan.spec_merges || [];
  const [sheetUse, setSheetUse] = useState<Record<string, boolean>>(() => Object.fromEntries(sheets.map((item) => [String(item.id), item.use])));
  const [heldKeep, setHeldKeep] = useState<Record<string, boolean>>({});
  const [unitValues, setUnitValues] = useState<Record<string, string>>(() => Object.fromEntries(units.map((item, index) => [`${index}`, item.default || ""])));
  const [specValues, setSpecValues] = useState<Record<string, string>>(() => Object.fromEntries(specs.map((item, index) => [`${index}`, item.default || ""])));
  function options(item: { default?: string; dist?: Record<string, number>; variants?: Record<string, number> }) { return Array.from(new Set([item.default || "", ...Object.keys(item.dist || item.variants || {})])); }
  function choices() {
    return {
      sheets: sheetUse,
      held: held.map((item) => ({ sid: item.sid, ridx: item.ridx, keep: Boolean(heldKeep[`${item.sid}:${item.ridx}`]) })),
      unit_overrides: units.map((item, index) => ({ gk: item.gk, value: unitValues[String(index)] || "" })).filter((item, index) => item.value !== (units[index].default || "")),
      spec_overrides: specs.map((item, index) => ({ gk: item.gk, value: specValues[String(index)] || "" })).filter((item, index) => item.value !== (specs[index].default || "")),
    };
  }
  return <ReviewShell kind="pivot" result={plan} onConfirm={() => onConfirm(choices())} busy={busy} title="销售透视确认" description="确认工作表、疑似误删行和单位/规格归并后再生成透视表。" actionLabel="按此生成">
    <div className="review-block"><div className="review-block-title">工作表纳入 <span>{sheets.length} 张</span></div><div className="review-table-wrap"><table className="review-table"><thead><tr><th>纳入</th><th>文件</th><th>工作表</th><th>识别类型</th><th>可信度</th></tr></thead><tbody>{sheets.map((item) => <tr key={`${item.id}`}><td><input type="checkbox" checked={Boolean(sheetUse[String(item.id)])} onChange={(event) => setSheetUse((current) => ({ ...current, [String(item.id)]: event.target.checked }))} /></td><td>{item.file}</td><td title={item.reason}>{item.sheet}</td><td>{item.kind}</td><td>{item.confidence}</td></tr>)}</tbody></table></div></div>
    <div className="review-block"><div className="review-block-title">疑似误删行 <span>{held.length} 行</span></div>{held.length ? <div className="review-edit-list">{held.map((item) => { const key = `${item.sid}:${item.ridx}`; return <label key={key}><input type="checkbox" checked={Boolean(heldKeep[key])} onChange={(event) => setHeldKeep((current) => ({ ...current, [key]: event.target.checked }))} /><span>{item.file || item.sheet || item.sid} · {typeof item.rec === "string" ? item.rec : JSON.stringify(item.rec)}</span></label>; })}</div> : <p className="review-empty">没有疑似误删行。</p>}</div>
    <div className="review-block"><div className="review-block-title">单位/规格归并 <span>{units.length + specs.length} 项</span></div>{units.concat(specs).length ? <div className="review-edit-list">{units.map((item, index) => <label key={`unit-${index}`}><span>单位 · {item.name || item.code || "未命名物料"}</span><select value={unitValues[String(index)] || ""} onChange={(event) => setUnitValues((current) => ({ ...current, [String(index)]: event.target.value }))}>{options(item).map((value) => <option value={value} key={value}>{value || "（空）"}</option>)}</select></label>)}{specs.map((item, index) => <label key={`spec-${index}`}><span>规格 · {item.name || item.code || "未命名物料"}</span><select value={specValues[String(index)] || ""} onChange={(event) => setSpecValues((current) => ({ ...current, [String(index)]: event.target.value }))}>{options(item).map((value) => <option value={value} key={value}>{value || "（空）"}</option>)}</select></label>)}</div> : <p className="review-empty">没有单位冲突或规格归并提示。</p>}</div>
  </ReviewShell>;
}

type InvoiceItem = { num?: string; date?: string; seller?: string; item_seed?: string; amount?: number; tax?: number; total?: number; rate?: number | string; note_seed?: string; special?: boolean };
type InvoiceRow = { selected: boolean; num: string; date: string; seller: string; item: string; amount?: number; tax?: number; total?: number; rate?: number | string; note: string; special: boolean };

function InvoiceReview({ plan, onConfirm, busy }: { plan: { invoices?: InvoiceItem[]; suggested_month?: string }; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const [month, setMonth] = useState(plan.suggested_month || "");
  const [includeNormal, setIncludeNormal] = useState(false);
  const [rows, setRows] = useState<InvoiceRow[]>(() => (plan.invoices || []).map((item) => ({ selected: Boolean(item.special), num: item.num || "", date: item.date || "", seller: item.seller || "", item: item.item_seed || "", amount: item.amount, tax: item.tax, total: item.total, rate: item.rate, note: item.note_seed || "", special: Boolean(item.special) })));
  const visible = useMemo(() => rows.filter((row) => (includeNormal || row.special) && (!month || row.date.startsWith(month))), [rows, includeNormal, month]);
  function patch(index: number, value: Partial<InvoiceRow>) { setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...value } : row)); }
  function choices() { return { month, include_normal: includeNormal, rows: visible.filter((row) => row.selected).map(({ selected: _selected, special: _special, ...row }) => row) }; }
  return <ReviewShell kind="invoice" result={plan} onConfirm={() => onConfirm(choices())} busy={busy} title="发票逐张复核" description="号码、日期和金额保持识别原值；销售方、费用项目、税率和备注可调整。" actionLabel="生成发票台账">
    <div className="review-toolbar"><label>统计月份<input type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label><label className="review-check"><input type="checkbox" checked={includeNormal} onChange={(event) => setIncludeNormal(event.target.checked)} />同时包含普通发票</label><span>当前显示 {visible.length} 张</span></div>
    <div className="review-table-wrap"><table className="review-table invoice-review-table"><thead><tr><th>保留</th><th>发票号码</th><th>日期</th><th>销售方</th><th>费用项目</th><th>不含税</th><th>税额</th><th>合计</th><th>税率</th><th>备注</th></tr></thead><tbody>{visible.map((row) => { const index = rows.indexOf(row); return <tr key={`${row.num}-${row.date}`}><td><input type="checkbox" checked={row.selected} onChange={(event) => patch(index, { selected: event.target.checked })} /></td><td>{row.num}</td><td>{row.date}</td><td><input value={row.seller} onChange={(event) => patch(index, { seller: event.target.value })} /></td><td><input value={row.item} onChange={(event) => patch(index, { item: event.target.value })} /></td><td>{row.amount ?? ""}</td><td>{row.tax ?? ""}</td><td>{row.total ?? ""}</td><td><input value={String(row.rate ?? "")} onChange={(event) => patch(index, { rate: event.target.value })} /></td><td><input value={row.note} onChange={(event) => patch(index, { note: event.target.value })} /></td></tr>; })}</tbody></table></div>
    {!visible.length ? <p className="review-empty">当前月份或发票类型筛选后没有记录。</p> : null}
  </ReviewShell>;
}

function CompareReview({ plan, onConfirm, busy }: { plan: { headers1?: string[]; headers2?: string[]; common?: string[] }; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const common = plan.common || [];
  const [key, setKey] = useState(common[0] || "");
  return <ReviewShell kind="compare" result={plan} onConfirm={() => onConfirm({ key })} busy={busy} confirmDisabled={!key} title="表格比对确认" description="选择用于配对两张表的关键列，再生成差异报告。" actionLabel="开始比对">
    <div className="review-block"><div className="review-block-title">公共列</div>{common.length ? <label className="review-select-wide">关键列<select value={key} onChange={(event) => setKey(event.target.value)}>{common.map((item) => <option value={item} key={item}>{item}</option>)}</select></label> : <p className="review-empty">两张表没有公共列，无法进行配对。</p>}<p className="review-muted">A 表 {plan.headers1?.length || 0} 列 · B 表 {plan.headers2?.length || 0} 列 · 可用关键列 {common.length} 个</p></div>
  </ReviewShell>;
}

export function ReviewPanel({ kind, result, onConfirm, busy }: ReviewPanelProps) {
  const plan = unwrap(result);
  if (kind === "reconcile") return <ReconcileReview plan={plan as ReconcilePlan} onConfirm={onConfirm} busy={busy} />;
  if (kind === "pivot") return <PivotReview plan={plan as PivotPlan} onConfirm={onConfirm} busy={busy} />;
  if (kind === "invoice") return <InvoiceReview plan={plan as { invoices?: InvoiceItem[]; suggested_month?: string }} onConfirm={onConfirm} busy={busy} />;
  return <CompareReview plan={plan as { headers1?: string[]; headers2?: string[]; common?: string[] }} onConfirm={onConfirm} busy={busy} />;
}
