/**
 * 管理层日清数据看板及各总览区块。
 *
 * 页面展示服务端已经聚合的到料、考勤、生产、安全、事项和现场问题数据；
 * 图表只做比例与分组呈现，不在浏览器重新分析上传表格。业务日期统一按上海时区计算。
 */
import { useEffect, useMemo, useState } from "react";
import { dailyReport, downloadDailyReport, workshopImageUrl, type DailyArrivalBatch, type DailyReportData } from "./api";
import type { DailyReportTabKey } from "./businessGuidance";
import { AttendanceTab, BriefTab, ISSUE_CATEGORY_LABELS, ProductionInsightsPanel, ProductionLedgerPanel, ProductionPlanTab, WorkshopCategoryTab } from "./DailyReportManagement";
import { Icon } from "./icons";
import Button from "./ui/Button";
import Dialog from "./ui/Dialog";
import EmptyState from "./ui/EmptyState";
import IconButton from "./ui/IconButton";
import Notice from "./ui/Notice";
import PageHeader from "./ui/PageHeader";
import { workshopIssueOwnerLabel } from "./workshopIssueSchema";

/** 日清看板的五个栏目：总览、考勤、现场问题、资料与生产、事项与待办。 */
type DailyTab = DailyReportTabKey;

/** 按业务时区生成本地日历日期，避免浏览器所在时区改变“今天”的含义。 */
function businessToday() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));  // 按上海时区取本地日历日期，避免浏览器时区改变“今天”
  return `${value.year}-${value.month}-${value.day}`;
}

/** 在纯日期上按天平移，使用 UTC 构造避免夏令时或本机时区造成跨日偏差。 */
function shiftDate(value: string, amount: number) {
  const [year, month, day] = value.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + amount));  // 纯日期按 UTC 平移，避免夏令时或本机时区造成跨日偏差
  return next.toISOString().slice(0, 10);
}

/** 将业务日期显示为“今天”或带星期的中文日期。 */
function dateTitle(value: string) {
  if (value === businessToday()) return "今天";
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "long", day: "numeric", weekday: "short" }).format(new Date(Date.UTC(year, month - 1, day, 4))); // 取 UTC 凌晨四点，确保转换到上海时区后仍是同一日期。
}

/** 将 UTC 时间戳转换为业务时区的月日和时分。 */
function timeLabel(value: string) {
  if (!value) return "暂无";
  return new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** 保留零值并只把真正缺失的数量显示为“未提供”。 */
function quantityLabel(value: string | number) {
  return value === "" || value === null || value === undefined ? "未提供" : String(value);
}

/** 将“编制减出勤”的差异转换为缺口、超编或持平文案。 */
function attendanceDifferenceLabel(value: number) {
  return value > 0 ? `缺口 ${value}` : value < 0 ? `超编 ${Math.abs(value)}` : "编制持平";
}

/** 汇总六项管理层核心指标，并根据阈值或异常数量选择状态色。 */
function MetricBand({ data }: { data: DailyReportData }) {
  const attendanceNote = data.attendance.production_group_count
    ? `生产编制 ${data.attendance.production_staffing_count} · ${attendanceDifferenceLabel(data.attendance.production_difference)}`
    : data.attendance.participant_total
      ? `参会 ${data.attendance.participant_present_count}/${data.attendance.participant_total}`
      : "当天尚未填报";
  const metrics = [
    { key: "completion", label: "到料完成率", value: `${data.arrival.completion_rate.toFixed(1)}%`, note: `${data.arrival.arrived_categories} / ${data.arrival.total_categories} 类`, tone: data.arrival.completion_rate >= 95 ? "success" : "warning" },
    { key: "missing", label: "未收料类数", value: data.arrival.missing_categories, note: `${data.arrival.batch_count} 个批次`, tone: data.arrival.missing_categories ? "danger" : "success" },
    { key: "issues", label: "现场问题", value: data.workshop.issue_count, note: `${data.workshop.image_count} 张现场图片`, tone: data.workshop.issue_count ? "warning" : "success" },
    { key: "attendance", label: "人员出勤", value: `${data.attendance.present_count} 人`, note: attendanceNote, tone: data.attendance.absent_count ? "warning" : "success" },
    { key: "brief", label: "重点事项", value: data.brief_items.filter((item) => item.status !== "done" && item.status !== "cancelled").length, note: `${data.brief_items.length} 项当天汇报`, tone: "info" },
    { key: "safety", label: "安全检查", value: data.safety_checks.unqualified_count, note: data.safety_checks.total_checks ? `${data.safety_checks.qualified_count}/${data.safety_checks.total_checks} 项合格` : "当天尚未上传", tone: data.safety_checks.unqualified_count ? "danger" : "success" },
  ];
  return <section className="fyt-daily-metrics" aria-label="当日核心指标">{metrics.map((metric) => <div key={metric.key} data-tone={metric.tone}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div>)}</section>;
}

/** 展示批次到料列表，并在大号对话框中查看单批次缺料与供应商影响。 */
function ArrivalPanel({ data }: { data: DailyReportData["arrival"] }) {
  const [selectedId, setSelectedId] = useState("");
  useEffect(() => { setSelectedId(""); }, [data.batches]); // 切换日期或刷新批次集合后关闭可能已经失效的详情。
  const selected = data.batches.find((item) => item.id === selectedId) || null;
  return <section className="fyt-daily-panel fyt-daily-arrival">
    <header className="fyt-daily-panel-head"><div><span>每日到料明细</span><h2>批次完成情况</h2><p>{data.job_count} 次当日处理，共 {data.batch_count} 个批次</p></div><div className="fyt-daily-ring" style={{ background: `conic-gradient(var(--fyt-primary) ${data.completion_rate * 3.6}deg, var(--fyt-surface-subtle) 0deg)` }} role="img" aria-label={`到料完成率 ${data.completion_rate.toFixed(1)}%`}><span><strong>{data.completion_rate.toFixed(1)}%</strong><small>完成率</small></span></div></header>
    {data.invalid_batch_count ? <Notice tone="warning" title="数量关系需要核对">{data.invalid_batch_count} 个批次的主料总类数与已到货、未收料合计不一致。</Notice> : null}
    {data.batches.length ? <div className="fyt-daily-batch-layout"><div className="fyt-daily-batch-list" role="list" aria-label="到料批次">
      {data.batches.map((batch) => <button key={batch.id} type="button" className={selected?.id === batch.id ? "selected" : ""} onClick={() => setSelectedId(batch.id)} aria-haspopup="dialog" aria-expanded={selected?.id === batch.id}>
        <span className="fyt-daily-batch-copy"><strong>{batch.batch_no}</strong><small>{batch.uploader} · 未收料 {batch.missing_count} 类</small></span><span className="fyt-daily-bar"><i style={{ width: `${batch.completion_rate ? Math.max(3, batch.completion_rate) : 0}%` }} /></span><b>{batch.completion_label}</b>
      </button>)}
    </div></div> : <EmptyState title="当天没有到料结果" description="可运行业务任务，也可在“资料与生产”中直接上传成品每日到料表。" icon={<Icon name="chart" size={19} />} />}
    <Dialog open={Boolean(selected)} size="large" title={selected ? `${selected.batch_no} 到料详情` : "批次到料详情"} description={selected ? `${selected.job_title} · ${selected.uploader} · 完成于 ${timeLabel(selected.completed_at)}` : undefined} onClose={() => setSelectedId("")}>{selected ? <div className="fyt-daily-batch-dialog"><BatchDetail batch={selected} /></div> : null}</Dialog>
  </section>;
}

/** 展示单批次汇总、具体未到物料和缺口供应商；历史任务缺少明细时明确说明。 */
function BatchDetail({ batch }: { batch: DailyArrivalBatch }) {
  const materials = Array.isArray(batch.missing_materials) ? batch.missing_materials : [];
  const suppliers = Array.isArray(batch.supplier_distribution) ? batch.supplier_distribution : [];
  return <section className="fyt-daily-batch-detail" aria-label={`${batch.batch_no} 批次详情`}>
    <div><span>当前批次</span><h3>{batch.batch_no}</h3></div>
    <dl><div><dt>主料总类数</dt><dd>{batch.total_count}</dd></div><div><dt>已到货</dt><dd>{batch.arrived_count}</dd></div><div><dt>未收料</dt><dd>{batch.missing_count}</dd></div><div><dt>完成率</dt><dd>{batch.completion_label}</dd></div></dl>
    <p><strong>{batch.uploader}</strong><span>{batch.job_title}</span><time dateTime={batch.completed_at}>完成于 {timeLabel(batch.completed_at)}</time></p>
    <section className="fyt-daily-materials" aria-label={`${batch.batch_no} 未到物料明细`}>
      <header><div><span>缺料明细</span><strong>具体未到物料</strong></div><b>{materials.length} 项</b></header>
      {materials.length ? <div className="fyt-daily-material-table"><table>
        <caption>{batch.batch_no} 未到物料及数量缺口</caption>
        <thead><tr><th>物料编码</th><th>物料名称</th><th>供应商</th><th>需求数</th><th>已收数</th><th>缺口数</th></tr></thead>
        <tbody>{materials.map((material, index) => <tr key={`${material.material_code}-${index}`}><td data-label="物料编码">{material.material_code || "未填写"}</td><td data-label="物料名称">{material.material_name || "未填写"}</td><td data-label="供应商">{material.supplier || "未填写"}</td><td data-label="需求数">{quantityLabel(material.demand_quantity)}</td><td data-label="已收数">{quantityLabel(material.received_quantity)}</td><td data-label="缺口数"><strong>{quantityLabel(material.shortage_quantity)}</strong></td></tr>)}</tbody>
      </table></div> : batch.missing_count ? <p className="fyt-daily-material-note">该历史任务只保存了数量汇总。重新处理源文件后，可在这里查看具体缺料与数量缺口。</p> : <p className="fyt-daily-material-note" data-clear="true">本批次物料已全部到齐。</p>}
      {suppliers.length ? <div className="fyt-daily-supplier-summary"><header><div><span>供应商影响</span><strong>缺料供应商汇总</strong></div><b>{suppliers.length} 家</b></header><div className="fyt-daily-supplier-grid">{suppliers.map((item) => <article key={item.supplier}><strong>{item.supplier}</strong><span>{item.material_count} 项物料</span><em>缺口 {quantityLabel(item.shortage_quantity)}</em></article>)}</div></div> : null}
    </section>
  </section>;
}

/**
 * 用同一进度条同时表达出勤、固定编制与正负差异。
 * 比例分母取出勤和编制的较大值，超编时仍能完整展示额外人数而不溢出轨道。
 */
function AttendanceProgressBar({ present, total, difference, compact = false }: { present: number; total: number; difference?: number; compact?: boolean }) {
  const safePresent = Math.max(0, Number(present) || 0);
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeDifference = typeof difference === "number" ? difference : safeTotal - safePresent;
  const scale = Math.max(safePresent, safeTotal, 1); // 至少为一，避免当天无编制无出勤时除零。
  const presentWidth = Math.min(safePresent, safeTotal) / scale * 100;
  const exceptionWidth = Math.abs(safeDifference) / scale * 100;
  const state = safeDifference > 0 ? "shortage" : safeDifference < 0 ? "over" : safeTotal ? "complete" : "empty";
  const statusLabel = safeDifference > 0 ? `缺口 ${safeDifference}` : safeDifference < 0 ? `超编 ${Math.abs(safeDifference)}` : safeTotal ? "编制持平" : "暂无编制";
  return <div className={`fyt-daily-attendance-progress${compact ? " is-compact" : ""}`} data-state={state}>
    <div className="fyt-daily-attendance-progress-track" aria-label={`出勤 ${safePresent} 人，编制 ${safeTotal} 人，${statusLabel}`}>
      <span className="fyt-daily-attendance-progress-segment is-present" style={{ width: `${presentWidth}%` }} />
      {safeDifference > 0 ? <span className="fyt-daily-attendance-progress-segment is-shortage" style={{ width: `${exceptionWidth}%` }} /> : null}
      {safeDifference < 0 ? <span className="fyt-daily-attendance-progress-segment is-over" style={{ width: `${exceptionWidth}%` }} /> : null}
      <strong>出勤 {safePresent} / {safeTotal}</strong>
    </div>
    <em>{statusLabel}</em>
  </div>;
}

/**
 * 汇总参会人员和生产班组出勤。
 * 总览默认只展示关键数字和异常班组，完整班组、单位和缺勤原因通过一次展开查看，避免长列表挤占管理层首屏。
 */
function AttendanceOverview({ data }: { data: DailyReportData["attendance"] }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const productionGroups = data.production_groups || [];
  const absences = data.people.filter((item) => !item.present);
  const totalStaffing = data.participant_total + data.production_staffing_count;
  const totalPresent = data.participant_present_count + data.production_present_count;
  const totalDifference = totalStaffing - totalPresent;
  const shortageGroups = productionGroups.filter((item) => item.difference > 0);
  const previewGroups = (shortageGroups.length ? shortageGroups : productionGroups).slice(0, 3);
  const totalStatus = totalDifference > 0 ? `缺口 ${totalDifference}` : totalDifference < 0 ? `超编 ${Math.abs(totalDifference)}` : totalStaffing ? "编制持平" : "暂无编制";
  const absentNames = absences.slice(0, 3).map((item) => item.name).filter(Boolean).join("、");

  function renderGroup(item: DailyReportData["attendance"]["production_groups"][number]) {
    return <article className="fyt-daily-attendance-group-row" key={item.shift_id}>
      <div><strong>{item.group_name} · {item.shift_name}</strong><small>编制 {item.staffing_count}{item.note ? ` · ${item.note}` : ""}</small></div>
      <AttendanceProgressBar compact present={item.attendance_count} total={item.staffing_count} difference={item.difference} />
    </article>;
  }

  return <section className="fyt-daily-panel fyt-daily-attendance-overview">
    <header className="fyt-daily-attendance-overview-head">
      <div><span>每日出勤</span><h2>到岗概览</h2><p>先看整体到岗和缺口，班组明细按需展开</p></div>
      <div className="fyt-daily-attendance-total" data-state={totalDifference > 0 ? "shortage" : totalDifference < 0 ? "over" : "complete"}>
        <strong>{totalPresent}<small> / {totalStaffing}</small></strong><span>总出勤</span><em>{totalStatus}</em>
      </div>
    </header>
    <div className="fyt-daily-attendance-quick-grid" aria-label="参会与生产人员出勤摘要">
      <article><div><span>参会人员</span><strong>{data.participant_present_count} / {data.participant_total}</strong><small>{data.participant_absent_count ? `缺勤 ${data.participant_absent_count} 人` : "全部到岗"}</small></div><AttendanceProgressBar compact present={data.participant_present_count} total={data.participant_total} /></article>
      <article><div><span>生产人员</span><strong>{data.production_present_count} / {data.production_staffing_count}</strong><small>{data.production_difference > 0 ? `缺口 ${data.production_difference} 人` : data.production_difference < 0 ? `超编 ${Math.abs(data.production_difference)} 人` : "编制持平"}</small></div><AttendanceProgressBar compact present={data.production_present_count} total={data.production_staffing_count} difference={data.production_difference} /></article>
    </div>
    {absences.length ? <div className="fyt-daily-attendance-alert"><span>参会缺勤</span><strong>{absences.length} 人</strong><small>{absentNames}{absences.length > 3 ? ` 等 ${absences.length} 人` : ""}</small></div> : <p className="fyt-daily-clear-note">参会人员已全部出勤。</p>}
    {productionGroups.length ? <section className="fyt-daily-attendance-details" aria-label="生产班组出勤明细">
      <header><div><span>生产编制</span><strong>班组到岗</strong><small>{productionGroups.length} 个班组 · {data.production_shift_count} 个班次</small></div><button type="button" onClick={() => setDetailsOpen(true)}>查看完整明细</button></header>
      <div className="fyt-daily-attendance-group-list">{previewGroups.map(renderGroup)}</div>
      {productionGroups.length > previewGroups.length ? <button className="fyt-daily-attendance-more" type="button" onClick={() => setDetailsOpen(true)}>还有 {productionGroups.length - previewGroups.length} 个班组，打开浮窗查看</button> : null}
    </section> : null}
    <Dialog open={detailsOpen} size="large" title="考勤完整明细" description={`生产班组 ${productionGroups.length} 个 · 参会单位 ${data.unit_summary?.length || 0} 个 · 缺勤 ${absences.length} 人`} onClose={() => setDetailsOpen(false)}>
      <div className="fyt-daily-attendance-dialog">
        <section><header><div><span>生产编制</span><strong>班组与班次</strong></div><b>{productionGroups.length} 个班组</b></header><div className="fyt-daily-attendance-dialog-grid">{productionGroups.map(renderGroup)}</div></section>
        {data.unit_summary?.length ? <section><header><div><span>参会人员</span><strong>单位与班次</strong></div><b>{data.unit_summary.length} 个单位</b></header><div className="fyt-daily-attendance-dialog-grid">{data.unit_summary.map((item) => <article className="fyt-daily-attendance-group-row" key={`${item.unit}-${item.shift}`}><div><strong>{item.unit}</strong><small>{item.shift || "未填写班次"} · 编制 {item.total}{item.reasons.length ? ` · ${item.reasons.join("；")}` : ""}</small></div><AttendanceProgressBar compact present={item.present} total={item.total} difference={item.difference} /></article>)}</div></section> : null}
        {absences.length ? <section><header><div><span>异常信息</span><strong>参会缺勤原因</strong></div><b>{absences.length} 人</b></header><div className="fyt-daily-attendance-reason-list">{absences.map((item) => <p key={item.person_id}><strong>{item.name}</strong><em>{item.reason || "未填写原因"}</em></p>)}</div></section> : null}
      </div>
    </Dialog>
  </section>;
}

/** 按服务端规定的五类事项组织管理层重点，每类最多在总览展示四条。 */
function BriefOverview({ data }: { data: DailyReportData }) {
  const columns = [
    ["escalation", "重大/升级事项"], ["notice", "通报"], ["process", "过程指标"],
    ["meeting_todo", "当日会议待办"], ["past_todo", "往期会议待办"],
  ].map(([key, title]) => ({ key, title, items: data.brief_items.filter((item) => item.category === key) }));
  return <section className="fyt-daily-brief-overview"><header><div><span>管理层重点</span><h2>事项、指标与会议待办</h2></div></header><div>{columns.map((column) => <section key={column.key} data-category={column.key}><h3>{column.title}<strong>{column.items.length}</strong></h3>{column.items.length ? column.items.slice(0, 4).map((item) => <article key={item.id}><span>{item.unit || "未填写单位"}</span><strong>{item.title}</strong>{item.description || item.progress ? <p>{item.description || item.progress}</p> : null}<footer><em>{item.owner || "未填写责任人"}</em>{item.category === "meeting_todo" || item.category === "past_todo" ? <small>{item.status === "done" ? "已完成" : item.status === "in_progress" ? "进行中" : item.status === "cancelled" ? "已取消" : "未开始"}</small> : null}</footer></article>) : <EmptyState title={`当天没有${column.title}`} description="可在“事项与待办”选项卡中添加。" />}</section>)}</div></section>;
}

/** 选择包含有效洞察的生产计划作为当天重点，并并列展示月度订单台账。 */
function ProductionOverview({ data }: { data: DailyReportData }) {
  const plan = data.production_plans.find((item) => Boolean(item.summary.insights?.daily?.length || item.summary.insights?.plan_total)) || data.production_plans[0];
  return <div className="fyt-daily-production-stack"><section className="fyt-daily-production-overview"><header><div><span>生产与发运</span><h2>当天生产重点</h2><p>{plan ? `${plan.original_name} · 上传于 ${new Date(plan.created_at).toLocaleString("zh-CN")}` : "上传生产计划后显示计划、实际、差异和班次重点"}</p></div><strong>{data.production_plans.length} 份当天文件</strong></header>{plan ? <ProductionInsightsPanel insights={plan.summary.insights} compact /> : <EmptyState title="当天还没有生产计划" description="月度订单台账仍会独立显示；当天计划可在“资料与生产”中上传。" icon={<Icon name="file" size={19} />} />}</section><ProductionLedgerPanel ledger={data.production_ledger} compact /></div>;
}

/** 展示安全检查合格概况和不合格整改项，现场图片通过统一预览对话框打开。 */
function SafetyOverview({ data, onPreview }: { data: DailyReportData["safety_checks"]; onPreview: (url: string, title: string) => void }) {
  const unqualified = data.records.filter((item) => item.result.includes("不合格"));  // 只挑不合格项展示整改重点
  return <section className="fyt-daily-panel fyt-daily-safety-overview"><header className="fyt-daily-panel-head"><div><span>安全检查日报</span><h2>当日检查与整改重点</h2><p>{data.total_checks ? `${data.total_checks} 项检查 · ${data.image_count} 张现场图片` : "在“资料与生产”中上传安全检查记录后自动展示"}</p></div><div className="fyt-daily-issue-count"><strong>{data.unqualified_count}</strong><span>项不合格</span></div></header>{data.total_checks ? <><div className="fyt-daily-safety-categories">{data.category_summary.map((item) => <article key={item.category}><strong>{item.category}</strong><span>{item.qualified}/{item.total} 合格</span><em>{item.unqualified ? `${item.unqualified} 项待整改` : "全部合格"}</em></article>)}</div>{unqualified.length ? <div className="fyt-daily-safety-issues">{unqualified.map((item) => <article key={`${item.row}-${item.check_item}`}><div><span>{item.category}</span><h3>{item.check_item}</h3><p>{item.problem_description || "未填写问题描述"}</p><small>整改：{item.corrective_action || "未填写"} · 责任人：{item.owner || "未填写"}</small></div>{item.images.length ? <button type="button" onClick={() => onPreview(workshopImageUrl(item.images[0].url), `${item.check_item} · 安全检查图片`)}><img src={workshopImageUrl(item.images[0].url)} alt={`${item.check_item}现场图片`} /></button> : null}</article>)}</div> : <p className="fyt-daily-clear-note">当日已检查项目全部合格。</p>}</> : <EmptyState title="当天没有安全检查日报" description="切换到“资料与生产”选项卡上传规范表格。" icon={<Icon name="check" size={19} />} />}</section>;
}

/** 按五种规范问题类别绘制相对数量条，最大类别占满可用宽度。 */
function CategoryOverview({ data }: { data: DailyReportData["workshop"] }) {
  const peak = Math.max(...data.category_distribution.map((item) => item.count), 1); // 空数组或全零时保留安全分母。
  return <section className="fyt-daily-panel fyt-daily-category-overview"><header className="fyt-daily-panel-head"><div><span>问题分类</span><h2>当日问题构成</h2><p>主料、辅料、包装、海外及防错异常</p></div></header>{data.category_distribution.length ? <ol>{data.category_distribution.map((item) => <li key={item.category}><span>{ISSUE_CATEGORY_LABELS[item.category]}</span><i><b style={{ width: `${item.count / peak * 100}%` }} /></i><strong>{item.count}</strong></li>)}</ol> : <EmptyState title="当天没有问题分类数据" description="发布现场问题后会自动生成分类汇总。" />}</section>;
}

/** 展示当天已发布现场问题明细，图片列表只显示前四张以控制总览高度。 */
function WorkshopLedger({ data, onPreview }: { data: DailyReportData["workshop"]; onPreview: (url: string, title: string) => void }) {
  return <section className="fyt-daily-ledger"><header><div><span>问题明细</span><h2>当天现场记录</h2></div></header>{data.issues.length ? <div className="fyt-daily-issue-list">{data.issues.map((issue, index) => <article key={issue.id}>
    <div className="fyt-daily-issue-index"><span>{String(index + 1).padStart(2, "0")}</span><time dateTime={issue.created_at}>{timeLabel(issue.created_at)}</time></div>
    <div className="fyt-daily-issue-body"><div className="fyt-daily-issue-tags"><span>{ISSUE_CATEGORY_LABELS[issue.category]}</span><em>{issue.issue_level || (issue.severity === "critical" ? "重大/升级" : issue.severity === "important" ? "重点" : "一般")}</em></div><h3>{issue.cause}</h3><dl>{(() => { const [label, value] = workshopIssueOwnerLabel(issue); return value ? <div><dt>{label}</dt><dd>{value}</dd></div> : null; })()}<div><dt>提交人</dt><dd>{issue.uploader}</dd></div>{issue.batch_no ? <div><dt>批次号</dt><dd>{issue.batch_no}</dd></div> : null}{issue.material_code || issue.material_name ? <div><dt>物料</dt><dd>{[issue.material_code, issue.material_name].filter(Boolean).join(" · ")}</dd></div> : null}{issue.supplier ? <div><dt>供应商</dt><dd>{issue.supplier}</dd></div> : null}</dl>{issue.cause_analysis ? <p><strong>原因分析：</strong>{issue.cause_analysis}</p> : null}{issue.corrective_action ? <p><strong>纠正措施：</strong>{issue.corrective_action}</p> : null}{issue.notes ? <p>{issue.notes}</p> : null}</div>
    <div className="fyt-daily-issue-images">{issue.images.length ? issue.images.slice(0, 4).map((image, imageIndex) => <button type="button" key={image.id} onClick={() => onPreview(workshopImageUrl(image.url), `${issue.cause} · 图片 ${imageIndex + 1}`)}><img src={workshopImageUrl(image.url)} alt={`${issue.cause}，现场图片 ${imageIndex + 1}`} loading="lazy" /></button>) : <span><Icon name="image" size={17} />无现场图片</span>}{issue.images.length > 4 ? <small>另有 {issue.images.length - 4} 张</small> : null}</div>
  </article>)}</div> : <EmptyState illustration="empty-workshop-note.webp" illustrationAlt="当天现场工作平稳的示意" title="当天没有已发布的问题记录" description="选择其他日期查看历史记录，或从现场问题页新增当天问题。" />}</section>;
}

/**
 * 管理日清业务日期、选项卡、刷新保留策略、报告导出和图片预览。
 * 普通换日期会清空旧数据并显示加载态；手动刷新保留上次成功结果，失败时仍可继续查看。
 */
export function DailyReportPage({ initialTab = "overview", onBackToWorkflow }: { initialTab?: DailyTab; onBackToWorkflow?: () => void }) {
  const today = useMemo(businessToday, []);
  const [date, setDate] = useState(today);
  const [data, setData] = useState<DailyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);
  const [tab, setTab] = useState<DailyTab>(initialTab);

  // 智能工作流可在进入看板时指定初始栏目；入口变化时同步切换，普通进入保持总览。
  useEffect(() => { setTab(initialTab); }, [initialTab]);

  /** 读取指定日期；`preserve` 为真时保留已有看板，避免刷新期间整页闪空。 */
  async function load(nextDate: string, preserve = false) {
    if (preserve) setRefreshing(true); else { setLoading(true); setData(null); }  // 手动刷新保留旧数据，普通换日期清空并显示加载态
    setError("");
    try { setData(await dailyReport(nextDate)); }  // 服务端聚合结果是唯一真值
    catch (reason) { setError(reason instanceof Error ? reason.message : "日清数据读取失败"); }
    finally { setLoading(false); setRefreshing(false); }
  }

  useEffect(() => { void load(date); }, [date]); // 日期是唯一查询键，切换后重新加载完整聚合数据。

  /** 导出当前日期报告，下载失败只更新页面提示，不清除看板数据。 */
  async function exportReport() {
    setExporting(true); setError("");
    try { await downloadDailyReport(date); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "日清报告导出失败"); }
    finally { setExporting(false); }
  }

  // 选项卡内容在数据存在时才创建，避免管理子页在空数据阶段发起无意义状态初始化。
  const tabContent = data ? (tab === "overview" ? <>
    <MetricBand data={data!} />
    <BriefOverview data={data!} />
    <ProductionOverview data={data!} />
    <ArrivalPanel data={data!.arrival} />
    <SafetyOverview data={data!.safety_checks} onPreview={(url, title) => setPreview({ url, title })} />
    <AttendanceOverview data={data!.attendance} />
    <CategoryOverview data={data!.workshop} />
    <WorkshopLedger data={data!.workshop} onPreview={(url, title) => setPreview({ url, title })} />
  </> : tab === "attendance" ? <AttendanceTab date={date} data={data} onRefresh={() => load(date, true)} /> : tab === "workshop" ? <WorkshopCategoryTab data={data.workshop} onPreview={(url, title) => setPreview({ url, title })} /> : tab === "production" ? <ProductionPlanTab date={date} data={data} onRefresh={() => load(date, true)} /> : <BriefTab date={date} data={data} onRefresh={() => load(date, true)} />) : null;

  return <div className="fyt-page fyt-content-container fyt-daily-page">
    <PageHeader eyebrow="管理日清" title="日清数据看板" actions={<>{onBackToWorkflow ? <Button variant="ghost" size="sm" type="button" onClick={onBackToWorkflow}><Icon name="left" size={15} />返回智能工作流</Button> : null}<Button variant="secondary" type="button" disabled={exporting || !data} loading={exporting} onClick={() => void exportReport()}><Icon name="download" size={16} />导出报告</Button><IconButton label="刷新日清数据" disabled={refreshing} onClick={() => void load(date, true)}><Icon name="refresh" size={17} /></IconButton></>} />
    <section className="fyt-daily-command"><div className="fyt-daily-date-nav"><IconButton label="前一天" onClick={() => setDate((current) => shiftDate(current, -1))}><Icon name="left" size={17} /></IconButton><label><Icon name="calendar" size={17} /><span><strong>{dateTitle(date)}</strong><small>{date}</small></span><input type="date" max={today} value={date} onChange={(event) => setDate(event.target.value || today)} aria-label="选择日清报告日期" /></label><IconButton label="后一天" disabled={date >= today} onClick={() => setDate((current) => shiftDate(current, 1))}><Icon name="right" size={17} /></IconButton>{date !== today ? <Button variant="ghost" size="sm" type="button" onClick={() => setDate(today)}>回到今天</Button> : null}</div><div className="fyt-daily-status"><span data-live={data ? "true" : undefined} /><div><strong>{refreshing ? "正在更新" : data ? "数据已更新" : "等待数据"}</strong><small>{data ? `更新于 ${timeLabel(data.generated_at)}` : "选择日期查看当天数据"}</small></div></div></section>
    <nav className="fyt-daily-tabs" aria-label="日清看板栏目">{[
      ["overview", "总览"], ["attendance", "每日考勤"], ["workshop", "现场问题"], ["production", "资料与生产"], ["brief", "事项与待办"],
    ].map(([key, label]) => <button key={key} type="button" className={tab === key ? "selected" : ""} onClick={() => setTab(key as DailyTab)}>{label}</button>)}</nav>
    {error ? <Notice tone={data ? "warning" : "error"} title={data ? "本次刷新未完成" : "日清数据暂时无法显示"}>{error}{data ? "，页面继续保留上一次成功结果。" : ""}</Notice> : null}
    {loading ? <div className="fyt-daily-loading" role="status"><span /><strong>正在汇总 {date} 的日清数据</strong></div> : data ? <div key={`${tab}-${date}`} className="fyt-daily-tab-view">{tabContent}</div> : <EmptyState title="没有可显示的日清数据" description="可以更换日期或刷新后重试。" icon={<Icon name="chart" size={20} />} />}
    <Dialog open={Boolean(preview)} title={preview?.title || "现场图片"} description="点击关闭后返回日清问题明细。" onClose={() => setPreview(null)}>{preview ? <img className="fyt-daily-preview-image" src={preview.url} alt={preview.title} /> : null}</Dialog>
  </div>;
}

export default DailyReportPage;
