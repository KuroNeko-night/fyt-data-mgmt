/**
 * 日清看板的维护性子页面集合。
 *
 * 为管理员提供人员考勤、班组编制、日清事项、到料/安全资料和生产发运资料
 * 的填写与上传入口；所有解析和聚合仍在服务端/核心层完成，这里只提交
 * 明确表单字段并回读服务端规范化后的结果。
 */
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {
  createDailyBriefItem,
  createDailyPerson,
  createDailyProductionGroup,
  deleteDailyBriefItem,
  deleteDailyPerson,
  deleteDailyProductionGroup,
  deleteDailyProductionPlan,
  deleteDailySource,
  downloadDailySource,
  downloadDailyProductionPlan,
  listDailyPeople,
  listDailyProductionGroups,
  saveDailyAttendance,
  updateDailyBriefItem,
  updateDailyPerson,
  updateDailyProductionGroup,
  uploadDailyProductionPlan,
  uploadDailySource,
  workshopImageUrl,
  type DailyAttendance,
  type DailyBriefCategory,
  type DailyBriefItem,
  type DailyBriefStatus,
  type DailyPerson,
  type DailyPersonType,
  type DailyProductionAttendance,
  type DailyProductionGroup,
  type DailyProductionGroupInput,
  type DailyProductionPlan,
  type DailyProductionLedger,
  type DailyReportData,
  type DailySourceUpload,
  type WorkshopIssueCategory,
  type WorkshopIssueSeverity,
} from "./api";
import { Icon } from "./icons";
import Button from "./ui/Button";
import Dialog from "./ui/Dialog";
import Drawer from "./ui/Drawer";
import EmptyState from "./ui/EmptyState";
import Notice from "./ui/Notice";
import SegmentedControl from "./ui/SegmentedControl";
import { ISSUE_CATEGORY_LABELS, workshopIssueOwnerLabel } from "./workshopIssueSchema";

export { ISSUE_CATEGORY_LABELS } from "./workshopIssueSchema";

export const ISSUE_SEVERITY_LABELS: Record<WorkshopIssueSeverity, string> = {
  normal: "一般", important: "重点", critical: "重大/升级",
};

export const BRIEF_CATEGORY_LABELS: Record<DailyBriefCategory, string> = {
  escalation: "重大/升级事项", notice: "通报", process: "过程指标",
  meeting_todo: "当日会议待办", past_todo: "往期会议待办",
};

const BRIEF_STATUS_LABELS: Record<DailyBriefStatus, string> = {
  open: "未开始", in_progress: "进行中", done: "已完成", cancelled: "已取消",
};

// 使用工厂函数而不是共享对象，确保每次重置参会人表单都获得独立引用，避免原地修改污染后续表单。
const EMPTY_PERSON = () => ({
  name: "", person_type: "participant" as DailyPersonType, unit: "", shift: "", sort_order: 0, active: true,
});
// 使用工厂函数而不是共享对象，确保每次重置表单都获得独立的 shifts 数组。
const EMPTY_PRODUCTION_GROUP = (): DailyProductionGroupInput => ({
  name: "", sort_order: 0, active: true,
  shifts: [{ name: "白班", staffing_count: 0, sort_order: 0, active: true }],
});

type AttendanceView = "today" | "master_data";
type PersonEditorDraft = ReturnType<typeof EMPTY_PERSON> & { id?: number };
type ProductionGroupEditorDraft = DailyProductionGroupInput & { id?: number };

const ATTENDANCE_VIEW_OPTIONS = [
  { value: "today", label: "今日考勤" },
  { value: "master_data", label: "人员与班组维护" },
] as const;

/** 将“编制减出勤”的数值转换成管理层容易理解的差异文案。 */
function differenceLabel(value: number) {
  return value > 0 ? `缺口 ${value}` : value < 0 ? `超编 ${Math.abs(value)}` : "持平";
}

/** 用紧凑的本地化单位显示上传文件大小。 */
function sizeLabel(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * 渲染需要逐人确认的参会人员考勤。
 * 开关控制是否出勤；关闭后才开放迟到、请假、出差等细分状态和原因输入。
 */
function AttendanceRows({ records, showAbsentOnly, onChange, onMarkAllPresent, onToggleAbsentOnly }: {
  records: DailyAttendance[];
  showAbsentOnly: boolean;
  onChange: (personId: number, values: Partial<DailyAttendance>) => void;
  onMarkAllPresent: () => void;
  onToggleAbsentOnly: () => void;
}) {
  // 出勤率仅统计布尔 present；迟到等非正常状态按缺勤侧展示并保留具体原因。
  const present = records.filter((item) => item.present).length;  // 出勤率只统计布尔 present，非正常状态按缺勤展示
  const visibleRecords = showAbsentOnly ? records.filter((item) => !item.present) : records;
  return <section className="fyt-daily-attendance-group">
    <header className="fyt-daily-attendance-section-head"><div><h3>参会人员</h3><p>{present} / {records.length} 人出勤</p></div><div className="fyt-daily-attendance-section-actions"><button type="button" onClick={onMarkAllPresent} disabled={!records.length || present === records.length}>全部出勤</button><button type="button" aria-pressed={showAbsentOnly} onClick={onToggleAbsentOnly}>{showAbsentOnly ? "显示全部" : `只看缺勤${records.length - present ? ` ${records.length - present}` : ""}`}</button><strong>{records.length ? `${Math.round(present / records.length * 100)}%` : "--"}</strong></div></header>
    {visibleRecords.length ? <div className="fyt-daily-attendance-list">{visibleRecords.map((record) => <article key={record.person_id} data-present={record.present ? "true" : "false"}>
      <div className="fyt-daily-attendance-person"><strong>{record.name}</strong><span>{[record.unit, record.shift].filter(Boolean).join(" · ") || "未填写单位/班次"}</span></div>
      <label className="fyt-daily-switch"><input type="checkbox" checked={record.present} onChange={(event) => onChange(record.person_id, { present: event.target.checked, status: event.target.checked ? "present" : "absent", reason: event.target.checked ? "" : record.reason })} /><span aria-hidden="true" /><em>{record.present ? "出勤" : "缺勤"}</em></label>
      {record.present ? <div className="fyt-daily-attendance-normal"><Icon name="check" size={15} /><span>状态正常</span></div> : <div className="fyt-daily-attendance-exception"><select aria-label={`${record.name}考勤状态`} value={record.status || "absent"} onChange={(event) => onChange(record.person_id, { status: event.target.value })}><option value="absent">缺勤</option><option value="late">迟到</option><option value="leave">请假</option><option value="business_trip">出差</option></select><input aria-label={`${record.name}考勤原因`} value={record.reason} onChange={(event) => onChange(record.person_id, { reason: event.target.value })} placeholder="填写缺勤、请假或出差原因" /></div>}
    </article>)}</div> : <EmptyState title={showAbsentOnly && records.length ? "当前没有缺勤人员" : "还没有人员"} description={showAbsentOnly && records.length ? "所有参会人员均已标记为出勤。" : "请先到“人员与班组维护”添加需要每日核对的人员。"} />}
  </section>;
}

/** 按班组和班次填写生产人员出勤，并在前端即时计算各级编制差异。 */
function ProductionAttendanceRows({ records, onChange }: {
  records: DailyProductionAttendance[];
  onChange: (shiftId: number, values: Partial<DailyProductionAttendance>) => void;
}) {
  const [expandedNotes, setExpandedNotes] = useState<Set<number>>(() => new Set());
  // 汇总值以当前编辑状态计算，因此用户修改人数后无需等待保存即可看到总差异。
  const totals = records.reduce((result, item) => ({
    staffing: result.staffing + item.staffing_count,
    attendance: result.attendance + item.attendance_count,
  }), { staffing: 0, attendance: 0 });  // 汇总值基于当前编辑状态，改人数无需保存即可看到总差异
  const grouped = useMemo(() => {
    // Map 用于快速定位已有班组，result 数组同时保留服务端返回的稳定展示顺序。
    const result: Array<{ groupId: number; groupName: string; records: DailyProductionAttendance[] }> = [];
    const byId = new Map<number, { groupId: number; groupName: string; records: DailyProductionAttendance[] }>();
    records.forEach((record) => {
      let target = byId.get(record.group_id);
      if (!target) {
        target = { groupId: record.group_id, groupName: record.group_name, records: [] };
        byId.set(record.group_id, target);
        result.push(target);
      }
      // 同一班组的多个班次共享一张卡片，避免把班组名重复展示为扁平表格行。
      target.records.push(record);
    });
    return result;
  }, [records]);
  // 差异定义始终是编制减实际：正数表示缺口，负数表示超编。
  const totalDifference = totals.staffing - totals.attendance;  // 编制减实际：正数缺口，负数超编
  return <section className="fyt-daily-attendance-group fyt-daily-production-attendance">
    <header><div><h3>生产人员</h3><p>按班组和班次填写当天出勤，系统自动计算编制差异</p></div><strong>{totals.attendance} 人</strong></header>
    {records.length ? <div className="fyt-daily-production-attendance-list">{grouped.map((group) => {
      const staffing = group.records.reduce((sum, item) => sum + item.staffing_count, 0);
      const attendance = group.records.reduce((sum, item) => sum + item.attendance_count, 0);
      const difference = staffing - attendance;
      return <article key={group.groupId} className="fyt-daily-production-attendance-group-card">
        <header><div><strong>{group.groupName}</strong><span>编制 {staffing} · 出勤 {attendance}</span></div><em data-difference={difference === 0 ? "zero" : difference > 0 ? "shortage" : "over"}>{differenceLabel(difference)}</em></header>
        <div>{group.records.map((record) => {
          const currentDifference = record.staffing_count - record.attendance_count;
          const progress = record.staffing_count > 0 ? Math.min(100, record.attendance_count / record.staffing_count * 100) : record.attendance_count > 0 ? 100 : 0;
          const noteOpen = expandedNotes.has(record.shift_id) || Boolean(record.note);
          return <section key={record.shift_id} data-note-open={noteOpen ? "true" : "false"}>
            <div className="fyt-daily-production-shift-name"><strong>{record.shift_name}</strong><span>编制 {record.staffing_count}</span><em data-difference={currentDifference === 0 ? "zero" : currentDifference > 0 ? "shortage" : "over"}>{differenceLabel(currentDifference)}</em></div>
            <div className="fyt-daily-production-shift-progress"><div><span>出勤 {record.attendance_count} / {record.staffing_count}</span><strong>{record.staffing_count ? `${Math.round(record.attendance_count / record.staffing_count * 100)}%` : "--"}</strong></div><i><b style={{ width: `${progress}%` }} /></i></div>
            <label><span>出勤人数</span><input aria-label={`${record.group_name}${record.shift_name}出勤人数`} type="number" min="0" step="1" inputMode="numeric" value={record.attendance_count} onChange={(event) => onChange(record.shift_id, { attendance_count: Math.max(0, Number.parseInt(event.target.value || "0", 10) || 0) })} /></label>
            <button className="fyt-daily-note-toggle" type="button" aria-expanded={noteOpen} onClick={() => setExpandedNotes((current) => { const next = new Set(current); if (next.has(record.shift_id)) next.delete(record.shift_id); else next.add(record.shift_id); return next; })}>{noteOpen ? "收起备注" : "补充备注"}</button>
            {noteOpen ? <label className="fyt-daily-production-note"><span>备注</span><input aria-label={`${record.group_name}${record.shift_name}备注`} value={record.note} maxLength={500} onChange={(event) => onChange(record.shift_id, { note: event.target.value })} placeholder="例如：支援、请假或临时调整" /></label> : null}
          </section>;
        })}</div>
      </article>;
    })}<footer><span>总编制 {totals.staffing}</span><strong>总出勤 {totals.attendance}</strong><em data-difference={totalDifference === 0 ? "zero" : totalDifference > 0 ? "shortage" : "over"}>总差异：{differenceLabel(totalDifference)}</em></footer></div> : <EmptyState title="还没有生产班组" description="先在下方生产班组维护中添加班组、班次和人员编制。" />}
  </section>;
}

/** 日清考勤页：维护参会人员名册、生产班组编制，并保存指定日期的实际出勤。 */
export function AttendanceTab({ date, data, onRefresh }: { date: string; data: DailyReportData; onRefresh: () => Promise<void> }) {
  const [people, setPeople] = useState<DailyPerson[]>([]);
  const [records, setRecords] = useState<DailyAttendance[]>(data.attendance.people);
  const [productionGroups, setProductionGroups] = useState<DailyProductionGroup[]>([]);
  const [productionRecords, setProductionRecords] = useState<DailyProductionAttendance[]>(data.attendance.production_groups || []);
  const [view, setView] = useState<AttendanceView>("today");
  const [showAbsentOnly, setShowAbsentOnly] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [attendanceDirty, setAttendanceDirty] = useState(false);
  const [personDraft, setPersonDraft] = useState<PersonEditorDraft | null>(null);
  const [groupDraft, setGroupDraft] = useState<ProductionGroupEditorDraft | null>(null);
  // busy 保存操作类型或记录 id，用一个状态互斥所有会改变主数据和日报的请求。
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  // 父级刷新日清数据后覆盖本地日报副本，确保保存后的服务端规范化结果回到输入框。
  useEffect(() => {
    setRecords(data.attendance.people);
    setProductionRecords(data.attendance.production_groups || []);
    setAttendanceDirty(false);  // 服务端快照变化后，本地编辑基线随之更新。
  }, [data.attendance.people, data.attendance.production_groups]);
  // 人员名册和班组编制彼此独立，可并行读取以缩短页面首次可用时间。
  useEffect(() => { void Promise.all([listDailyPeople(), listDailyProductionGroups()]).then(([peopleResult, groupResult]) => { setPeople(peopleResult.people); setProductionGroups(groupResult.groups); }).catch((reason) => setError(reason instanceof Error ? reason.message : "考勤主数据读取失败")); }, []);

  const participantPresent = records.filter((item) => item.present).length;
  const participantAbsent = records.length - participantPresent;
  const productionTotals = productionRecords.reduce((result, item) => ({ staffing: result.staffing + item.staffing_count, attendance: result.attendance + item.attendance_count }), { staffing: 0, attendance: 0 });
  const productionDifference = productionTotals.staffing - productionTotals.attendance;
  const exceptionCount = participantAbsent + Math.max(0, productionDifference);
  // id 为空表示当天记录尚未正式落库，即使用户未改字段也需要允许第一次保存。
  const attendanceNeedsInitialSave = records.some((item) => item.id === null) || productionRecords.some((item) => item.id === null);
  const attendanceCanSave = attendanceDirty || attendanceNeedsInitialSave;
  const unitSummary = useMemo(() => {
    const result = new Map<string, { unit: string; shift: string; total: number; present: number; reasons: string[] }>();
    records.forEach((record) => {
      const unit = record.unit || "未填写单位"; const shift = record.shift || "未填写班次"; const key = `${unit}\u0000${shift}`;
      const current = result.get(key) || { unit, shift, total: 0, present: 0, reasons: [] };
      current.total += 1;
      if (record.present) current.present += 1;
      else if (record.reason.trim()) current.reasons.push(`${record.name}：${record.reason.trim()}`);
      result.set(key, current);
    });
    return [...result.values()];
  }, [records]);

  /** 只更新指定人员的本地日报副本，最终由“保存当天考勤”统一提交。 */
  function updateRecord(personId: number, values: Partial<DailyAttendance>) {
    setRecords((current) => current.map((item) => item.person_id === personId ? { ...item, ...values } : item));  // 只更新指定人员的本地日报副本，最终统一保存
    setAttendanceDirty(true);
  }

  /** 批量标记全部参会人员为出勤，并清理不再适用的异常状态与原因。 */
  function markAllPresent() {
    if (!records.some((item) => !item.present)) return;
    setRecords((current) => current.map((item) => ({ ...item, present: true, status: "present", reason: "" })));
    setAttendanceDirty(true);
  }

  /** 更新指定班次并同步重算差异字段，保持输入区与汇总展示一致。 */
  function updateProductionRecord(shiftId: number, values: Partial<DailyProductionAttendance>) {
    setProductionRecords((current) => current.map((item) => {
      if (item.shift_id !== shiftId) return item;
      const next = { ...item, ...values };
      // 服务端保存时会再次计算；这里的值仅用于编辑过程中的即时反馈。
      return { ...next, difference: next.staffing_count - next.attendance_count };  // 即时重算差异，服务端保存时会再次计算
    }));
    setAttendanceDirty(true);
  }

  /** 把参会人员和生产班次两组考勤作为同一天的一次保存操作提交。 */
  async function save() {
    setBusy("attendance"); setNotice(""); setError("");
    try {
      const result = await saveDailyAttendance(
        date,
        // 只发送接口允许的可编辑字段，不把姓名、单位等主数据展示字段混入日报记录。
        records.map(({ person_id, present, status, reason }) => ({ person_id, present, status, reason })),
        productionRecords.map(({ shift_id, attendance_count, note }) => ({ shift_id, attendance_count, note })),
      );
      setRecords(result.attendance); setProductionRecords(result.production_groups); setAttendanceDirty(false); setNotice(result.message); await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "考勤保存失败"); }
    finally { setBusy(""); }
  }

  /** 新增或更新参会人员；编辑过程留在弹窗草稿中，不直接污染列表快照。 */
  async function submitPerson(event: FormEvent) {
    event.preventDefault();
    if (!personDraft?.name.trim()) { setError("请填写人员姓名"); return; }
    const editingId = personDraft.id;
    setBusy(editingId ? `person-${editingId}` : "person-create"); setError(""); setNotice("");
    try {
      const values = { name: personDraft.name.trim(), person_type: "participant" as DailyPersonType, unit: personDraft.unit.trim(), shift: personDraft.shift.trim(), sort_order: personDraft.sort_order, active: personDraft.active };
      const result = editingId ? await updateDailyPerson(editingId, values) : await createDailyPerson(values);
      setPeople((current) => editingId ? current.map((item) => item.id === editingId ? result.person : item) : [...current, result.person]);
      setPersonDraft(null); setNotice(result.message); await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : editingId ? "人员更新失败" : "人员添加失败"); }
    finally { setBusy(""); }
  }

  /** 从当前名册移除人员；服务端保留历史考勤，避免旧日报失去姓名依据。 */
  async function removePerson(person: DailyPerson) {
    if (!window.confirm(`确定从日清人员名册中移除“${person.name}”吗？历史考勤会保留。`)) return;
    setBusy(`person-${person.id}`); setError(""); setNotice("");
    try {
      const result = await deleteDailyPerson(person.id); setNotice(result.message);
      const next = await listDailyPeople(); setPeople(next.people); setPersonDraft(null); await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "人员删除失败"); }
    finally { setBusy(""); }
  }

  /** 新增或更新班组及班次；弹窗确认前，所有修改都只存在于 groupDraft。 */
  async function submitProductionGroup(event: FormEvent) {
    event.preventDefault();
    if (!groupDraft?.name.trim()) { setError("请填写生产班组名称"); return; }
    const editingId = groupDraft.id;
    const values: DailyProductionGroupInput = {
      name: groupDraft.name.trim(), sort_order: groupDraft.sort_order, active: groupDraft.active,
      shifts: groupDraft.shifts.map((shift) => ({ ...(shift.id && shift.id > 0 ? { id: shift.id } : {}), name: shift.name.trim(), staffing_count: shift.staffing_count, sort_order: shift.sort_order, active: shift.active })),
    };
    if (!values.shifts.length || values.shifts.some((shift) => !shift.name)) { setError("每个班组至少需要一个已命名班次"); return; }
    setBusy(editingId ? `production-group-${editingId}` : "production-group-create"); setError(""); setNotice("");
    try {
      const result = editingId ? await updateDailyProductionGroup(editingId, values) : await createDailyProductionGroup(values);
      setProductionGroups((current) => editingId ? current.map((item) => item.id === editingId ? result.group : item) : [...current, result.group]);
      setGroupDraft(null); setNotice(result.message); await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : editingId ? "生产班组更新失败" : "生产班组添加失败"); }
    finally { setBusy(""); }
  }

  /** 删除班组主数据；历史日报引用由服务端保留，删除只影响后续日期的可选班组。 */
  async function removeProductionGroup(group: DailyProductionGroup) {
    if (!window.confirm(`确定移除生产班组“${group.name}”吗？历史出勤会保留。`)) return;
    setBusy(`production-group-${group.id}`); setError(""); setNotice("");
    try {
      const result = await deleteDailyProductionGroup(group.id); setNotice(result.message);
      const next = await listDailyProductionGroups(); setProductionGroups(next.groups); setGroupDraft(null); await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "生产班组删除失败"); }
    finally { setBusy(""); }
  }

  /** 修改班组弹窗中的指定班次；使用索引是因为新增班次尚未取得数据库 id。 */
  function updateGroupDraftShift(index: number, values: Partial<DailyProductionGroupInput["shifts"][number]>) {
    setGroupDraft((current) => current ? ({ ...current, shifts: current.shifts.map((shift, shiftIndex) => shiftIndex === index ? { ...shift, ...values } : shift) }) : current);
  }

  function addGroupDraftShift() {
    setGroupDraft((current) => current ? ({ ...current, shifts: [...current.shifts, { name: current.shifts.length ? "夜班" : "白班", staffing_count: 0, sort_order: current.shifts.length, active: true }] }) : current);
  }

  function removeGroupDraftShift(index: number) {
    setGroupDraft((current) => current && current.shifts.length > 1 ? ({ ...current, shifts: current.shifts.filter((_, shiftIndex) => shiftIndex !== index) }) : current);
  }

  return <div className="fyt-daily-tab-page">
    <div className="fyt-daily-tab-heading"><div><span>人工核对</span><h2>每日人员出勤</h2><p>日常只处理当天出勤；人员、班组和编制统一放到独立维护入口。</p></div></div>
    <div className="fyt-daily-attendance-toolbar"><SegmentedControl value={view} options={ATTENDANCE_VIEW_OPTIONS} onChange={setView} label="考勤页面" />{view === "today" ? <div className="fyt-daily-attendance-toolbar-actions"><Button type="button" variant="secondary" onClick={() => setSummaryOpen(true)}>查看汇总</Button><Button type="button" loading={busy === "attendance"} disabled={Boolean(busy) || !attendanceCanSave} onClick={() => void save()}><Icon name="check" size={16} />保存当天考勤</Button></div> : <p>低频主数据修改不会占用每天的填报空间。</p>}</div>
    {notice ? <Notice tone="success" title="操作已完成">{notice}</Notice> : null}
    {error ? <Notice tone="error" title="操作未完成">{error}</Notice> : null}
    {view === "today" ? <><section className="fyt-daily-attendance-summary-strip" aria-label="当天考勤摘要"><article><span>参会人员</span><strong>{participantPresent} / {records.length}</strong><small>{participantAbsent ? `${participantAbsent} 人需说明` : "全部正常出勤"}</small></article><article data-tone={productionDifference > 0 ? "warning" : "success"}><span>生产人员</span><strong>{productionTotals.attendance} / {productionTotals.staffing}</strong><small>{differenceLabel(productionDifference)}</small></article><article data-tone={exceptionCount ? "warning" : "success"}><span>异常数量</span><strong>{exceptionCount}</strong><small>缺勤人数与生产缺口合计</small></article><article data-tone={attendanceCanSave ? "warning" : "success"}><span>保存状态</span><strong>{attendanceCanSave ? "待保存" : "已同步"}</strong><small>{attendanceCanSave ? "完成核对后统一保存" : "当前数据已写入系统"}</small></article></section><div className="fyt-daily-attendance-layout"><AttendanceRows records={records} showAbsentOnly={showAbsentOnly} onChange={updateRecord} onMarkAllPresent={markAllPresent} onToggleAbsentOnly={() => setShowAbsentOnly((current) => !current)} /><ProductionAttendanceRows records={productionRecords} onChange={updateProductionRecord} /></div></> : <div className="fyt-daily-master-data-grid"><section className="fyt-daily-roster fyt-daily-master-card"><header><div><span>参会人员</span><h2>人员名册</h2><p>只维护需要逐人确认出勤状态的人员。</p></div><Button type="button" size="sm" onClick={() => setPersonDraft(EMPTY_PERSON())}>新增人员</Button></header>{people.length ? <div className="fyt-daily-master-list">{people.map((person) => <article key={person.id} data-active={person.active ? "true" : "false"}><div><strong>{person.name}</strong><span>{[person.unit, person.shift].filter(Boolean).join(" · ") || "未填写单位/班次"}</span></div><em>{person.active ? "启用" : "停用"}</em><Button type="button" size="sm" variant="secondary" onClick={() => setPersonDraft({ id: person.id, name: person.name, person_type: "participant", unit: person.unit, shift: person.shift, sort_order: person.sort_order, active: person.active })}>编辑</Button></article>)}</div> : <EmptyState title="还没有参会人员" description="新增后即可在每日考勤中逐人确认出勤。" />}</section><section className="fyt-daily-roster fyt-daily-master-card"><header><div><span>生产人员</span><h2>班组与编制</h2><p>按班组维护班次和固定编制，不记录个人姓名。</p></div><Button type="button" size="sm" onClick={() => setGroupDraft(EMPTY_PRODUCTION_GROUP())}>新增班组</Button></header>{productionGroups.length ? <div className="fyt-daily-master-list">{productionGroups.map((group) => <article key={group.id} data-active={group.active ? "true" : "false"}><div><strong>{group.name}</strong><span>{group.shifts.filter((shift) => shift.active).map((shift) => `${shift.name} ${shift.staffing_count} 人`).join(" · ") || "暂无启用班次"}</span></div><em>总编制 {group.shifts.filter((shift) => shift.active).reduce((sum, shift) => sum + shift.staffing_count, 0)}</em><Button type="button" size="sm" variant="secondary" onClick={() => setGroupDraft({ id: group.id, name: group.name, sort_order: group.sort_order, active: group.active, shifts: group.shifts.map((shift) => ({ id: shift.id, name: shift.name, staffing_count: shift.staffing_count, sort_order: shift.sort_order, active: shift.active })) })}>编辑</Button></article>)}</div> : <EmptyState title="还没有生产班组" description="新增班组、班次与编制后即可填写当天人数。" />}</section></div>}
    <Drawer open={summaryOpen} title="当天考勤汇总" description="汇总跟随当前编辑状态变化，保存后写入日清数据。" onClose={() => setSummaryOpen(false)}><div className="fyt-daily-attendance-drawer"><section><span>参会人员</span><strong>{participantPresent} / {records.length}</strong><small>{participantAbsent ? `${participantAbsent} 人未正常出勤` : "全部正常出勤"}</small></section><section><span>生产人员</span><strong>{productionTotals.attendance} / {productionTotals.staffing}</strong><small>{differenceLabel(productionDifference)}</small></section><div className="fyt-daily-attendance-drawer-list">{unitSummary.map((item) => <article key={`${item.unit}-${item.shift}`}><header><div><strong>{item.unit}</strong><span>{item.shift}</span></div><em>{item.present} / {item.total}</em></header>{item.reasons.length ? <p>{item.reasons.join("；")}</p> : <p>无异常原因</p>}</article>)}</div></div></Drawer>
    <Dialog open={Boolean(personDraft)} title={personDraft?.id ? "编辑参会人员" : "新增参会人员"} description="单位和班次用于汇总展示，可按实际情况留空。" onClose={() => setPersonDraft(null)}>{personDraft ? <form className="fyt-daily-editor-form" onSubmit={submitPerson}><label><span>姓名</span><input autoFocus value={personDraft.name} onChange={(event) => setPersonDraft((current) => current ? { ...current, name: event.target.value } : current)} /></label><div><label><span>单位</span><input value={personDraft.unit} onChange={(event) => setPersonDraft((current) => current ? { ...current, unit: event.target.value } : current)} /></label><label><span>班次</span><input value={personDraft.shift} onChange={(event) => setPersonDraft((current) => current ? { ...current, shift: event.target.value } : current)} /></label></div><div><label><span>排序</span><input type="number" value={personDraft.sort_order} onChange={(event) => setPersonDraft((current) => current ? { ...current, sort_order: Number.parseInt(event.target.value || "0", 10) || 0 } : current)} /></label><label className="fyt-daily-editor-check"><input type="checkbox" checked={personDraft.active} onChange={(event) => setPersonDraft((current) => current ? { ...current, active: event.target.checked } : current)} /><span>在名册中启用</span></label></div><footer>{personDraft.id ? <Button type="button" variant="danger" disabled={Boolean(busy)} onClick={() => { const person = people.find((item) => item.id === personDraft.id); if (person) void removePerson(person); }}>删除人员</Button> : <span />}<div><Button type="button" variant="ghost" onClick={() => setPersonDraft(null)}>取消</Button><Button type="submit" loading={busy === "person-create" || busy === `person-${personDraft.id}`} disabled={Boolean(busy)}>{personDraft.id ? "保存修改" : "添加人员"}</Button></div></footer></form> : null}</Dialog>
    <Dialog open={Boolean(groupDraft)} size="large" title={groupDraft?.id ? "编辑生产班组" : "新增生产班组"} description="维护班组、班次和固定编制；每日考勤只填写实际出勤。" onClose={() => setGroupDraft(null)}>{groupDraft ? <form className="fyt-daily-editor-form fyt-daily-group-editor" onSubmit={submitProductionGroup}><div className="fyt-daily-group-editor-main"><label><span>班组名称</span><input autoFocus value={groupDraft.name} onChange={(event) => setGroupDraft((current) => current ? { ...current, name: event.target.value } : current)} /></label><label><span>排序</span><input type="number" value={groupDraft.sort_order} onChange={(event) => setGroupDraft((current) => current ? { ...current, sort_order: Number.parseInt(event.target.value || "0", 10) || 0 } : current)} /></label><label className="fyt-daily-editor-check"><input type="checkbox" checked={groupDraft.active} onChange={(event) => setGroupDraft((current) => current ? { ...current, active: event.target.checked } : current)} /><span>启用班组</span></label></div><section className="fyt-daily-group-editor-shifts"><header><div><strong>班次与人员编制</strong><span>同一班组可以维护多个班次</span></div><Button type="button" size="sm" variant="secondary" onClick={addGroupDraftShift}>添加班次</Button></header>{groupDraft.shifts.map((shift, index) => <article key={shift.id || `new-${index}`} data-active={shift.active ? "true" : "false"}><label><span>班次名称</span><input value={shift.name} maxLength={40} onChange={(event) => updateGroupDraftShift(index, { name: event.target.value })} /></label><label><span>人员编制</span><input type="number" min="0" inputMode="numeric" value={shift.staffing_count} onChange={(event) => updateGroupDraftShift(index, { staffing_count: Math.max(0, Number.parseInt(event.target.value || "0", 10) || 0) })} /></label><label><span>排序</span><input type="number" value={shift.sort_order} onChange={(event) => updateGroupDraftShift(index, { sort_order: Number.parseInt(event.target.value || "0", 10) || 0 })} /></label><label className="fyt-daily-editor-check"><input type="checkbox" checked={shift.active} onChange={(event) => updateGroupDraftShift(index, { active: event.target.checked })} /><span>启用</span></label><Button type="button" size="sm" variant="ghost" disabled={groupDraft.shifts.length <= 1} onClick={() => removeGroupDraftShift(index)}>移除</Button></article>)}</section><footer>{groupDraft.id ? <Button type="button" variant="danger" disabled={Boolean(busy)} onClick={() => { const group = productionGroups.find((item) => item.id === groupDraft.id); if (group) void removeProductionGroup(group); }}>删除班组</Button> : <span />}<div><Button type="button" variant="ghost" onClick={() => setGroupDraft(null)}>取消</Button><Button type="submit" loading={busy === "production-group-create" || busy === `production-group-${groupDraft.id}`} disabled={Boolean(busy)}>{groupDraft.id ? "保存修改" : "添加班组"}</Button></div></footer></form> : null}</Dialog>
  </div>;
}

/** 创建事项表单的空值；日期由当前日清页传入，避免切换日期后沿用旧日期。 */
const EMPTY_BRIEF = (date: string): Omit<DailyBriefItem, "id" | "created_by" | "created_at" | "updated_at"> => ({
  report_date: date, category: "escalation", unit: "", owner: "", title: "", description: "", due_date: "", progress: "", status: "open",
});

/** 维护重大事项、通报、过程指标和会议待办，并按类别显示各自需要的字段。 */
export function BriefTab({ date, data, onRefresh }: { date: string; data: DailyReportData; onRefresh: () => Promise<void> }) {
  const [draft, setDraft] = useState(EMPTY_BRIEF(date));
  const [editingId, setEditingId] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  // 切换日期时只重置新增表单；正在编辑的记录不被异步日期变化意外覆盖。
  useEffect(() => { if (!editingId) setDraft(EMPTY_BRIEF(date)); }, [date, editingId]);
  // 重大事项和通报只需要单位、责任人、事项三个字段；待办才展示日期、状态和进展。
  const simpleCategory = draft.category === "escalation" || draft.category === "notice";
  const todoCategory = draft.category === "meeting_todo" || draft.category === "past_todo";

  /** 切换类别并清除新类别不使用的字段，防止隐藏内容进入总览或导出。 */
  function changeCategory(category: DailyBriefCategory) {
    setDraft((current) => ({
      ...current,
      category,
      // 过程指标独有指标情况；离开该类别后显式清空旧说明。
      description: category === "process" ? current.description : "",
      due_date: category === "meeting_todo" || category === "past_todo" ? current.due_date : "",
      progress: category === "meeting_todo" || category === "past_todo" ? current.progress : "",
      status: category === "meeting_todo" || category === "past_todo" ? current.status : "open",
    }));
  }

  /** 根据 editingId 选择新增或更新接口，并刷新父级的日清聚合数据。 */
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) { setError("请填写事项标题"); return; }
    setBusy("brief"); setError(""); setNotice("");
    try {
      // 保存前统一去除文本首尾空白，避免列表排序、导出和空值判断受到无意义空格干扰。
      const values = { ...draft, report_date: date, title: draft.title.trim(), unit: draft.unit.trim(), owner: draft.owner.trim(), description: draft.description.trim(), progress: draft.progress.trim() };
      const result = editingId ? await updateDailyBriefItem(editingId, values) : await createDailyBriefItem(values);
      setNotice(result.message); setEditingId(""); setDraft(EMPTY_BRIEF(date)); await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "事项保存失败"); }
    finally { setBusy(""); }
  }

  /** 删除事项；若正在编辑同一记录，同时退出编辑状态以免继续提交已删除 id。 */
  async function remove(item: DailyBriefItem) {
    if (!window.confirm(`确定删除“${item.title}”吗？`)) return;
    setBusy(item.id); setError(""); setNotice("");
    try { const result = await deleteDailyBriefItem(item.id); setNotice(result.message); if (editingId === item.id) { setEditingId(""); setDraft(EMPTY_BRIEF(date)); } await onRefresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "事项删除失败"); }
    finally { setBusy(""); }
  }

  return <div className="fyt-daily-tab-page fyt-daily-brief-layout">
    <form className="fyt-daily-brief-form" onSubmit={submit}>
      <header><span>事项填写</span><h2>{editingId ? "编辑日清事项" : "新增日清事项"}</h2><p>按模板填写重大/升级事项、通报、过程指标和会议待办；安全检查由独立日报上传。</p></header>
      {notice ? <Notice tone="success" title="操作已完成">{notice}</Notice> : null}
      {error ? <Notice tone="error" title="操作未完成">{error}</Notice> : null}
      <label>事项类别<select value={draft.category} onChange={(event) => changeCategory(event.target.value as DailyBriefCategory)}>{Object.entries(BRIEF_CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="fyt-daily-form-grid"><label>单位<input value={draft.unit} onChange={(event) => setDraft((current) => ({ ...current, unit: event.target.value }))} /></label><label>责任人<input value={draft.owner} onChange={(event) => setDraft((current) => ({ ...current, owner: event.target.value }))} /></label></div>
      <label>{simpleCategory ? "事项" : todoCategory ? "待办事项" : "指标名称"}<textarea rows={simpleCategory ? 5 : 3} value={draft.title} maxLength={160} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder={simpleCategory ? "填写需要汇报的事项" : todoCategory ? "填写会议待办" : "填写需要关注的指标"} /></label>
      {draft.category === "process" ? <label>指标情况<textarea rows={4} value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="填写当日数值、目标或异常说明" /></label> : null}
      {todoCategory ? <><div className="fyt-daily-form-grid"><label>完成日期<input type="date" value={draft.due_date} onChange={(event) => setDraft((current) => ({ ...current, due_date: event.target.value }))} /></label><label>状态<select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value as DailyBriefStatus }))}>{Object.entries(BRIEF_STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><label>当前进展<textarea rows={3} value={draft.progress} onChange={(event) => setDraft((current) => ({ ...current, progress: event.target.value }))} /></label></> : null}
      <div className="fyt-daily-form-actions"><Button type="submit" loading={busy === "brief"} disabled={Boolean(busy)}>{editingId ? "保存修改" : "添加事项"}</Button>{editingId ? <Button type="button" variant="ghost" onClick={() => { setEditingId(""); setDraft(EMPTY_BRIEF(date)); }}>取消编辑</Button> : null}</div>
    </form>
    <section className="fyt-daily-brief-list"><header><div><span>当天汇报</span><h2>重点事项、通报与待办</h2></div><strong>{data.brief_items.length} 项</strong></header>
      {data.brief_items.length ? data.brief_items.map((item) => <article key={item.id} data-category={item.category} data-status={item.status}>
        <div className="fyt-daily-brief-meta"><span>{BRIEF_CATEGORY_LABELS[item.category]}</span>{item.category === "meeting_todo" || item.category === "past_todo" ? <em>{BRIEF_STATUS_LABELS[item.status]}</em> : null}</div>
        <h3>{item.title}</h3>{item.description ? <p>{item.description}</p> : null}
        <dl><div><dt>单位</dt><dd>{item.unit || "未填写"}</dd></div><div><dt>责任人</dt><dd>{item.owner || "未填写"}</dd></div>{item.category === "meeting_todo" || item.category === "past_todo" ? <div><dt>完成日期</dt><dd>{item.due_date || "未填写"}</dd></div> : null}</dl>
        {item.progress ? <blockquote>{item.progress}</blockquote> : null}
        <div className="fyt-daily-row-actions"><button type="button" onClick={() => { setEditingId(item.id); setDraft({ report_date: date, category: item.category, unit: item.unit, owner: item.owner, title: item.title, description: item.description, due_date: item.due_date, progress: item.progress, status: item.status }); }}>编辑</button><button type="button" className="danger" disabled={Boolean(busy)} onClick={() => void remove(item)}>删除</button></div>
      </article>) : <EmptyState title="当天没有重点事项" description="可从左侧添加重大/升级事项、通报、指标或会议待办。" />}
    </section>
  </div>;
}

/** 在浏览器中预览生产文件的多个工作表，显示服务端投影后的有限行列。 */
function PlanPreview({ plan }: { plan: DailyProductionPlan }) {
  const sheets = plan.summary.sheets || [];
  const [selectedSheetIndex, setSelectedSheetIndex] = useState(0);
  // 删除或刷新文件后工作表数可能缩短，索引钳制可避免短暂渲染 undefined 越界项。
  const activeSheet = sheets[Math.min(selectedSheetIndex, Math.max(sheets.length - 1, 0))];
  if (!activeSheet) return <p className="fyt-daily-plan-empty">文件已保存，但没有可以预览的工作表。</p>;
  return <div className="fyt-daily-plan-preview">
    {sheets.length > 1 ? <nav className="fyt-daily-plan-sheet-tabs" aria-label="生产计划工作表">{sheets.map((sheet, index) => <button type="button" key={`${sheet.sheet}-${index}`} className={index === selectedSheetIndex ? "selected" : ""} aria-pressed={index === selectedSheetIndex} onClick={() => setSelectedSheetIndex(index)}><strong>{sheet.sheet}</strong><span>{sheet.rows} 行 · {sheet.columns} 列</span></button>)}</nav> : null}
    {(activeSheet.table_rows?.length || activeSheet.preview?.length) ? <div className="fyt-daily-plan-sheet-table"><table><caption>{activeSheet.sheet} · {activeSheet.kind || "数据预览"}{activeSheet.table_truncated ? "（仅展示前 240 行）" : ""}</caption>{activeSheet.table_headers?.length ? <thead><tr>{activeSheet.table_headers.map((cell, cellIndex) => <th key={cellIndex}>{cell || ""}</th>)}</tr></thead> : null}<tbody>{(activeSheet.table_rows?.length ? activeSheet.table_rows : activeSheet.preview || []).map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell || ""}</td>)}</tr>)}</tbody></table></div> : <p className="fyt-daily-plan-empty">工作表“{activeSheet.sheet}”没有可以预览的单元格内容。</p>}
  </div>;
}

type ProductionInsights = NonNullable<DailyProductionPlan["summary"]["insights"]>;

/** 格式化图表数值；缺失数据使用破折号，不把“未填报”误显示为零。 */
function numberLabel(value: number | undefined) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 1 });
}

/**
 * 将服务端解析的结构化生产指标渲染成 KPI、趋势、班次差异、排行和发运进度。
 * 前端只负责比例换算与展示，不重新读取或推断原始工作簿业务含义。
 */
export function ProductionInsightsPanel({ insights, compact = false }: { insights?: ProductionInsights; compact?: boolean }) {
  const daily = insights?.daily || [];
  const shifts = insights?.shift_summary || [];
  const teams = insights?.team_summary || [];
  const batches = insights?.batch_summary || [];
  const shipping = insights?.shipping_summary || [];
  // 分母至少为 1，空数据或全零数据下仍能生成合法的 CSS 百分比。
  const maxShift = Math.max(...shifts.map((item) => Math.max(item.plan, item.actual)), 1);
  const maxTeam = Math.max(...teams.map((item) => item.quantity), 1);
  const maxBatch = Math.max(...batches.map((item) => item.quantity), 1);
  if (!insights || (!daily.length && !shifts.length && !teams.length && !batches.length && !shipping.length)) {
    return <section className="fyt-production-insights is-empty"><header><div><span>生产重点</span><h3>暂未解析出可视化指标</h3></div><p>可以继续核对下方原始工作表，系统会在识别到计划、实际和差异字段后生成图表。</p></header></section>;
  }
  const difference = insights.difference_total || 0;
  // 兼容较早的服务端投影：没有汇总计数字段时，从班次明细回退计算。
  const unreportedShiftCount = insights.unreported_shift_count ?? shifts.filter((item) => item.actual_reported === false).length;
  const reportedShiftCount = insights.reported_shift_count ?? Math.max(0, shifts.length - unreportedShiftCount);
  const hasUnreported = unreportedShiftCount > 0;
  return <section className={`fyt-production-insights${compact ? " is-compact" : ""}`}>
    <header className="fyt-production-insights-head"><div><span>生产重点</span><h3>当天生产一眼看懂</h3><p>聚焦 {insights.focus_date || "当前日期"} · {insights.focus_date_source || "上传文件"}{insights.has_focus_date === false ? "（文件中没有完全匹配的日期，已取最近日期）" : ""}</p></div><strong data-tone={hasUnreported || difference < 0 ? "warning" : "success"}>{hasUnreported ? `${unreportedShiftCount} 个班次待填报` : difference < 0 ? "需要关注" : "按计划或超额"}</strong></header>
    <div className="fyt-production-kpis"><article><span>计划数量</span><strong>{numberLabel(insights.plan_total)}</strong><small>当天计划总量</small></article><article><span>实际数量</span><strong>{numberLabel(insights.actual_total)}</strong><small>{hasUnreported ? `已填报 ${reportedShiftCount} 个班次` : "已填报实际产量"}</small></article><article data-tone={hasUnreported || difference < 0 ? "warning" : "success"}><span>已确认差异</span><strong>{difference > 0 ? "+" : ""}{numberLabel(difference)}</strong><small>{hasUnreported ? "不含未填报班次" : "实际 − 计划"}</small></article><article><span>已填报完成率</span><strong>{numberLabel(insights.completion_rate)}%</strong><small>{hasUnreported ? "按已填报计划计算" : "计划 / 实际"}</small></article></div>
    {insights.highlights?.length ? <div className="fyt-production-highlights"><span>管理层重点</span>{insights.highlights.map((item) => <p key={item}>{item}</p>)}</div> : null}
    {daily.length > 1 ? <section className="fyt-production-chart-block"><header><div><span>趋势</span><h4>每日计划与实际</h4></div><small>柱顶直接标注数量</small></header><div className="fyt-production-daily-chart">{daily.map((item) => { const max = Math.max(item.plan, item.actual, 1); const pending = (item.unreported_shift_count || 0) > 0; return <article key={item.date} data-focus={item.date === insights.focus_date ? "true" : undefined}><div className="fyt-production-bars"><i className="plan" style={{ height: `${Math.max(item.plan ? 8 : 0, item.plan / max * 100)}%` }}><b>{numberLabel(item.plan)}</b></i><i className={`actual${pending ? " is-pending" : ""}`} style={{ height: `${Math.max(item.actual ? 8 : 0, item.actual / max * 100)}%` }}><b>{numberLabel(item.actual)}</b></i></div><strong>{item.date.slice(5)}</strong><small className={`${item.difference < 0 ? "is-negative " : ""}${pending ? "is-pending" : ""}`}>{pending ? `待填 ${(item.unreported_shift_count || 0)} 班` : `${item.difference > 0 ? "+" : ""}${numberLabel(item.difference)}`}</small></article>; })}</div><div className="fyt-production-legend"><span><i className="plan" />计划</span><span><i className="actual" />实际</span><span><i className="pending" />部分未填报</span></div></section> : null}
    {shifts.length ? <section className="fyt-production-chart-block"><header><div><span>班次</span><h4>计划与实际差异</h4></div><small>虚线表示尚未填报实际产量</small></header><div className="fyt-production-shift-chart">{shifts.map((item) => { const pending = item.actual_reported === false; return <article key={`${item.date}-${item.shift}`} data-pending={pending ? "true" : undefined}><div><strong>{item.shift}</strong><small>计划 {numberLabel(item.plan)} · 实际 {pending ? "尚未填报" : numberLabel(item.actual)}</small></div><div className={`fyt-production-shift-track${pending ? " is-pending" : ""}`}><i style={{ width: `${pending ? 0 : Math.max(item.actual ? 4 : 0, item.actual / maxShift * 100)}%` }} /><b style={{ left: `${Math.min(100, Math.max(0, item.plan / maxShift * 100))}%` }} /></div><em className={`${item.difference < 0 ? "is-negative " : ""}${pending ? "is-pending" : ""}`}>{pending ? "尚未填报" : `${item.difference > 0 ? "+" : ""}${numberLabel(item.difference)}`}</em></article>; })}</div></section> : null}
    {(teams.length || batches.length) ? <div className="fyt-production-split-charts"><section className="fyt-production-chart-block"><header><div><span>班组</span><h4>实际产量排行</h4></div></header>{teams.length ? <ol className="fyt-production-ranking">{teams.slice(0, compact ? 4 : 8).map((item, index) => <li key={item.team}><span>{index + 1}</span><strong>{item.team}</strong><i><b style={{ width: `${Math.max(7, item.quantity / maxTeam * 100)}%` }} /></i><em>{numberLabel(item.quantity)}</em></li>)}</ol> : <p className="fyt-production-muted">暂无班组明细</p>}</section><section className="fyt-production-chart-block"><header><div><span>批次</span><h4>批次产量分布</h4></div></header>{batches.length ? <ol className="fyt-production-ranking fyt-production-batch-ranking">{batches.slice(0, compact ? 4 : 8).map((item) => <li key={item.batch}><strong title={item.batch}>{item.batch}</strong><i><b style={{ width: `${Math.max(7, item.quantity / maxBatch * 100)}%` }} /></i><em>{numberLabel(item.quantity)}</em></li>)}</ol> : <p className="fyt-production-muted">暂无批次明细</p>}</section></div> : null}
    {shipping.length ? <section className="fyt-production-chart-block"><header><div><span>发运</span><h4>订单完成状态</h4></div></header><div className="fyt-production-shipping-grid">{shipping.map((item) => <article key={item.type}><strong>{item.type}</strong><span>{item.completed} / {item.total} 单已完成</span><i><b style={{ width: `${item.total ? item.completed / item.total * 100 : 0}%` }} /></i><small>待处理 {item.pending} 单</small></article>)}</div></section> : null}
  </section>;
}

/**
 * 统一管理每日到料成品表、安全检查日报，以及生产、订单和发运资料。
 * 上传接口负责解析文件并生成结构化看板数据，本组件只呈现结果、原表预览和文件维护操作。
 */
export function ProductionPlanTab({ date, data, onRefresh }: { date: string; data: DailyReportData; onRefresh: () => Promise<void> }) {
  const [selected, setSelected] = useState(data.production_plans[0]?.id || "");
  const [busy, setBusy] = useState("");
  const [progress, setProgress] = useState(0);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  // 文件被删除或父级刷新后，若原选中项已不存在则自动回到第一份文件。
  useEffect(() => { if (!data.production_plans.some((item) => item.id === selected)) setSelected(data.production_plans[0]?.id || ""); }, [data.production_plans, selected]);
  const selectedPlan = data.production_plans.find((item) => item.id === selected) || data.production_plans[0] || null;

  /** 上传生产、订单或发运工作簿，并将新文件设为当前预览项。 */
  async function uploadProduction(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = ""; // 允许用户修正后再次选择同名文件。
    if (!file) return;
    setBusy("production"); setProgress(0); setNotice(""); setError("");
    try { const result = await uploadDailyProductionPlan(file, date, setProgress); setSelected(result.plan.id); setNotice(result.message); await onRefresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "生产计划上传失败"); }
    finally { setBusy(""); }
  }

  /** 上传已经制作完成的到料或安全日报；不要求人工重复填写表内已有日期和批次。 */
  async function uploadSource(kind: "arrival" | "safety", event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = ""; // 清空原生选择器以支持同名文件重传。
    if (!file) return;
    setBusy(kind); setProgress(0); setNotice(""); setError("");
    try { const result = await uploadDailySource(file, { kind, date }, setProgress); setNotice(result.message); await onRefresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "日清资料上传失败"); }
    finally { setBusy(""); }
  }

  /** 将生产资料移入回收站；结构化看板由刷新后的服务端聚合结果同步移除。 */
  async function removePlan(plan: DailyProductionPlan) {
    if (!window.confirm(`确定将生产计划“${plan.original_name}”移入回收站吗？`)) return;
    setBusy(plan.id); setError(""); setNotice("");
    try { const result = await deleteDailyProductionPlan(plan.id); setNotice(result.message); await onRefresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "生产计划移入回收站失败"); }
    finally { setBusy(""); }
  }

  /** 将到料或安全资料移入回收站，并重新聚合当前日期的日清数据。 */
  async function removeSource(upload: DailySourceUpload) {
    if (!window.confirm(`确定将“${upload.original_name}”移入回收站吗？`)) return;
    setBusy(upload.id); setError(""); setNotice("");
    try { const result = await deleteDailySource(upload.id); setNotice(result.message); await onRefresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "日清资料移入回收站失败"); }
    finally { setBusy(""); }
  }

  return <div className="fyt-daily-tab-page fyt-daily-source-tab">
    {notice ? <Notice tone="success" title="资料已更新">{notice}</Notice> : null}{error ? <Notice tone="error" title="操作未完成">{error}</Notice> : null}
    <div className="fyt-daily-source-grid fyt-daily-upload-hub">
      <section><header><span>每日到料成品表</span><h2>上传后直接进入看板</h2><p>请选择已经制作完成的《每日主料到料明细》。系统自动读取批次号、主料总类数、到货数量和逐项缺料，不重新生成报表。</p></header><label className="fyt-daily-upload-button"><input type="file" accept=".xlsx,.xlsm" disabled={Boolean(busy)} onChange={(event) => void uploadSource("arrival", event)} /><Icon name="upload" size={17} />{busy === "arrival" ? `解析中 ${progress}%` : "选择成品到料表"}</label></section>
      <section><header><span>安全检查日报</span><h2>上传检查记录与现场图片</h2><p>系统读取表内日期、检查类别、不合格项、整改措施、责任人和现场图片，并同步到当天总览。</p></header><label className="fyt-daily-upload-button"><input type="file" accept=".xlsx,.xlsm" disabled={Boolean(busy)} onChange={(event) => void uploadSource("safety", event)} /><Icon name="upload" size={17} />{busy === "safety" ? `解析中 ${progress}%` : "选择安全检查表"}</label></section>
      <section><header><span>生产与发运</span><h2>上传生产、订单和发运表</h2><p>系统识别生产计划、正式订单、零星订单、缺件和危包记录，并生成当天重点与月度订单台账。</p></header><label className="fyt-daily-upload-button"><input type="file" accept=".xlsx,.xlsm" disabled={Boolean(busy)} onChange={(event) => void uploadProduction(event)} /><Icon name="upload" size={17} />{busy === "production" ? `解析中 ${progress}%` : "选择生产与发运表"}</label></section>
    </div>
    <section className="fyt-daily-source-list"><header><span>到料与安全资料</span><h2>{date} 已上传文件</h2></header>{data.source_uploads.length ? data.source_uploads.map((upload) => <article key={upload.id}><div><strong>{upload.original_name}</strong><small>{upload.kind === "arrival" ? "每日到料成品表" : "安全检查日报"} · {upload.uploaded_by_name || "管理员"} · {sizeLabel(upload.size)}</small></div><div><Button variant="secondary" size="sm" type="button" onClick={() => void downloadDailySource(upload).catch((reason) => setError(reason instanceof Error ? reason.message : "下载失败"))}>下载</Button><Button variant="ghost" size="sm" type="button" disabled={Boolean(busy)} onClick={() => void removeSource(upload)}>移入回收站</Button></div></article>) : <EmptyState title="当天还没有到料或安全资料" description="可从上方直接上传已经制作完成的日报文件。" />}</section>
    <ProductionLedgerPanel ledger={data.production_ledger} />
    {data.production_plans.length ? <div className="fyt-daily-plan-layout"><nav aria-label="生产与发运文件">{data.production_plans.map((plan) => <button type="button" key={plan.id} className={selectedPlan?.id === plan.id ? "selected" : ""} onClick={() => setSelected(plan.id)}><strong>{plan.original_name}</strong><span>{plan.uploaded_by_name || "管理员"} · {sizeLabel(plan.size)}</span><small>{plan.summary.sheet_count || 0} 个工作表 · {plan.summary.row_count || 0} 行</small></button>)}</nav>{selectedPlan ? <section className="fyt-daily-plan-detail"><header><div><span>文件预览</span><h2>{selectedPlan.original_name}</h2><p>上传于 {new Date(selectedPlan.created_at).toLocaleString("zh-CN")}</p></div><div><Button type="button" variant="secondary" onClick={() => void downloadDailyProductionPlan(selectedPlan).catch((reason) => setError(reason instanceof Error ? reason.message : "下载失败"))}><Icon name="download" size={16} />下载原文件</Button><Button type="button" variant="ghost" disabled={Boolean(busy)} onClick={() => void removePlan(selectedPlan)}>移入回收站</Button></div></header><ProductionInsightsPanel insights={selectedPlan.summary.insights} /><PlanPreview key={selectedPlan.id} plan={selectedPlan} /></section> : null}</div> : <section className="fyt-daily-production-empty"><EmptyState title="当天还没有生产与发运数据" description="上传生产计划或订单发运统计后，管理层可直接查看工作表内容。" icon={<Icon name="file" size={20} />} /></section>}
  </div>;
}

/** 展示当前月份的正式订单、零星订单、缺件和危包汇总及可展开明细。 */
export function ProductionLedgerPanel({ ledger, compact = false }: { ledger: DailyProductionLedger; compact?: boolean }) {
  // 两类未闭环异常合并成管理层关注的“缺件与危包未完成”指标。
  const pendingParts = ledger.outstanding_missing_part_count + ledger.outstanding_hazardous_package_count;
  if (!ledger.source_file_count) return <section className="fyt-order-ledger is-empty"><EmptyState title={`${ledger.month} 暂无订单台账`} description="上传订单号发运统计后，系统会按订单号汇总正式订单、缺件、危包和零星订单。" icon={<Icon name="file" size={19} />} /></section>;
  return <section className={`fyt-order-ledger${compact ? " is-compact" : ""}`}>
    <header><div><span>月度生产订单台账</span><h2>{ledger.month} 发运与订单状态</h2><p>{ledger.source_file_count} 份台账文件，按订单号去重汇总</p></div><strong>{ledger.today_shipments.length} 单今日发运</strong></header>
    <div className="fyt-order-ledger-kpis"><article><span>正式订单</span><strong>{ledger.formal_completed}/{ledger.formal_total}</strong><small>待关闭 {ledger.formal_pending} 单 · {ledger.formal_quantity} 件</small></article><article><span>零星订单</span><strong>{ledger.sporadic_completed}/{ledger.sporadic_total}</strong><small>{ledger.sporadic_pallets} 托 · {ledger.sporadic_volume_cbm} CBM</small></article><article data-tone={pendingParts ? "warning" : "success"}><span>缺件与危包未完成</span><strong>{pendingParts}</strong><small>缺件 {ledger.outstanding_missing_part_count} · 危包 {ledger.outstanding_hazardous_package_count}</small></article></div>
    {!compact ? <div className="fyt-order-ledger-columns"><section><h3>正式订单明细</h3>{ledger.formal_orders.slice(0, 30).map((order) => <details key={order.order_no}><summary><span><strong>{order.order_no}</strong><small>{order.country || "未填写国家"} · {order.order_type || "未填写类型"} · {order.quantity} 件</small></span><em data-status={order.completed ? "done" : "pending"}>{order.status}</em></summary><div><p>发运完成：{order.shipment_date || "尚未填写"}</p><p>缺件 {order.missing_parts.length} 项（未完成 {order.outstanding_missing_count}） · 危包 {order.hazardous_packages.length} 项（未完成 {order.outstanding_hazardous_count}）</p>{order.note ? <p>{order.note}</p> : null}</div></details>)}</section><section><h3>零星订单详细数据</h3>{ledger.sporadic_orders.slice(0, 30).map((order) => <article key={order.order_no}><div><strong>{order.order_no}</strong><small>{order.transport_mode || "未填写运输方式"} · {order.country || "未填写国家"}</small></div><em>{order.pallet_count} 托 · {order.volume_cbm} CBM</em><p>{order.shipment_dates.length ? `发运 ${order.shipment_dates.join("、")}` : "尚未填写发运时间"}{order.driver_name ? ` · 司机 ${order.driver_name}` : ""}</p></article>)}</section></div> : null}
  </section>;
}

/** 按标准问题模板的五类汇总现场问题，并提供带权限校验地址的图片预览入口。 */
export function WorkshopCategoryTab({ data, onPreview }: { data: DailyReportData["workshop"]; onPreview: (url: string, title: string) => void }) {
  // 即使某一类别当天为零，也从固定标签表生成卡片，保证五类顺序和导出模板一致。
  const categories = useMemo(() => Object.entries(ISSUE_CATEGORY_LABELS).map(([category, label]) => ({ category: category as WorkshopIssueCategory, label, count: data.category_distribution.find((item) => item.category === category)?.count || 0 })), [data.category_distribution]);
  return <div className="fyt-daily-tab-page"><section className="fyt-daily-category-summary"><header><div><span>分类汇报</span><h2>当天现场问题构成</h2><p>严格按问题报告模板的五类工作表归集；导出时会保留对应字段和现场图片。</p></div><div className="fyt-daily-workshop-summary"><strong>{data.issue_count} 条</strong><small><i>{data.open_count} 条处理中</i><i>{data.resolved_count} 条已解决</i></small></div></header><div>{categories.map((item) => <article key={item.category} data-category={item.category}><span>{item.label}</span><strong>{item.count}</strong><small>{data.issue_count ? `${(item.count / data.issue_count * 100).toFixed(0)}%` : "0%"}</small></article>)}</div></section>
    {data.issues.length ? <section className="fyt-daily-classified-issues">{data.issues.map((issue, index) => <article key={issue.id} data-severity={issue.severity} data-resolution={issue.resolution_status}><header><div><span>{ISSUE_CATEGORY_LABELS[issue.category]}</span><em>{issue.issue_level || ISSUE_SEVERITY_LABELS[issue.severity]}</em><em className="fyt-daily-resolution-chip" data-status={issue.resolution_status}>{issue.resolution_status === "resolved" ? "已解决" : "处理中"}</em></div><b>{String(index + 1).padStart(2, "0")}</b></header><h3>{issue.cause}</h3><dl>{(() => { const [label, value] = workshopIssueOwnerLabel(issue); return value ? <div><dt>{label}</dt><dd>{value}</dd></div> : null; })()}<div><dt>提交人</dt><dd>{issue.uploader}</dd></div>{issue.batch_no ? <div><dt>批次号</dt><dd>{issue.batch_no}</dd></div> : null}{issue.material_code || issue.material_name ? <div><dt>物料</dt><dd>{[issue.material_code, issue.material_name].filter(Boolean).join(" · ")}</dd></div> : null}{issue.supplier ? <div><dt>供应商</dt><dd>{issue.supplier}</dd></div> : null}{issue.completion_date ? <div><dt>完成时间</dt><dd>{issue.completion_date}</dd></div> : null}</dl>{issue.cause_analysis ? <p><strong>原因分析：</strong>{issue.cause_analysis}</p> : null}{issue.corrective_action ? <p><strong>纠正措施：</strong>{issue.corrective_action}</p> : null}{issue.notes ? <p>{issue.notes}</p> : null}{issue.resolution_note ? <p className="fyt-daily-resolution-note"><strong>{issue.resolution_status === "resolved" ? "解决情况：" : "上次解决记录："}</strong>{issue.resolution_note}</p> : null}<div className="fyt-daily-classified-images">{issue.images.map((image, imageIndex) => <button type="button" key={image.id} onClick={() => onPreview(workshopImageUrl(image.url), `${issue.cause} · 图片 ${imageIndex + 1}`)}><img src={workshopImageUrl(image.url)} alt={`${issue.cause}，现场图片 ${imageIndex + 1}`} loading="lazy" /></button>)}</div></article>)}</section> : <EmptyState title="当天没有现场问题" description="现场问题页发布的记录会自动按分类显示在这里。" />}
  </div>;
}
