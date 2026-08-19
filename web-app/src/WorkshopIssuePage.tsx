/**
 * 现场问题页面。
 *
 * 按业务日期维护标准问题模板的草稿与已发布记录：草稿先创建、图片逐张上传、
 * 最后确认发布；班组长与管理员可编辑、闭环和删除，普通成员只能维护自己的草稿。
 * 图片张数、类型、大小和字段白名单以 `workshopIssueSchema` 及服务端校验为准。
 */
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkshopIssue,
  deleteWorkshopIssueImage,
  deleteWorkshopIssue,
  downloadWorkshopIssues,
  listWorkshopIssues,
  publishWorkshopIssue,
  reopenWorkshopIssue,
  resolveWorkshopIssue,
  updateWorkshopIssue,
  uploadWorkshopIssueImage,
  workshopImageUrl,
  type WorkshopIssue,
  type WorkshopIssueInput,
  type WorkshopIssueResponse,
} from "./api";
import { Icon } from "./icons";
import EmptyState from "./ui/EmptyState";
import {
  EMPTY_WORKSHOP_TEMPLATE_FIELDS,
  WORKSHOP_CATEGORY_OPTIONS,
  WORKSHOP_FIELD_META,
  WORKSHOP_ISSUE_FORM_CONFIG,
  workshopCategoryLabel,
  workshopIssueOwnerLabel,
  type WorkshopTemplateFieldKey,
  type WorkshopTemplateFields,
} from "./workshopIssueSchema";

// 图片张数、单张体积和允许格式与 AGENTS.md 中的现场问题模板规则保持一致。
const MAX_IMAGES = 8;
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

// 浏览器对象地址只在当前页面进程内有效；保留原始 File 用于稍后的逐张上传。
type SelectedImage = { id: string; file: File; preview: string };

/**
 * 把服务端的问题记录转换成表单使用的完整字段对象。
 *
 * 服务端只保证返回该类别实际使用的值，而 React 表单需要每个受控输入始终拿到字符串。
 * 因此这里以空模板为字段清单，缺失值统一补为空串，避免输入框在受控与非受控状态间切换。
 */
function issueTemplateFields(issue: WorkshopIssue): WorkshopTemplateFields {
  return Object.fromEntries(
    // 以模板而不是问题对象枚举字段，防止把服务端附带的 id、权限等属性误传回更新接口。
    Object.keys(EMPTY_WORKSHOP_TEMPLATE_FIELDS).map((key) => [
      key,
      issue[key as WorkshopTemplateFieldKey] || "",
    ]),
  ) as WorkshopTemplateFields;
}

/**
 * 根据当前问题类别构造更新请求，并主动清空该类别不使用的模板字段。
 *
 * 用户编辑时可能先选择一种类别并填写字段，随后再切换类别。隐藏字段仍可能留在 React 状态中，
 * 如果原样提交就会把无关数据写入记录和导出表格，所以请求边界必须再次按配置白名单过滤。
 */
function workshopIssuePayload(
  issueDate: string,
  category: WorkshopIssue["category"],
  cause: string,
  notes: string,
  templateFields: WorkshopTemplateFields,
): WorkshopIssueInput {
  const config = WORKSHOP_ISSUE_FORM_CONFIG[category];
  // sections 是界面与业务模板共同认可的字段集合，也是提交时的字段白名单。
  const visibleFields = new Set(config.sections.flatMap((section) => section.fields));  // 界面与业务模板共同认可的提交白名单
  const visibleTemplatePayload = Object.fromEntries(
    Object.entries(templateFields).map(([key, value]) => [
      key,
      // 隐藏字段明确写为空串，使服务端能够清除旧类别遗留值，而不是继续保留脏数据。
      visibleFields.has(key as WorkshopTemplateFieldKey) ? value.trim() : "",  // 隐藏字段写空串，清除旧类别遗留值
    ]),
  ) as WorkshopTemplateFields;
  return {
    issue_date: issueDate,
    cause: cause.trim(),
    notes: config.allowsNotes ? notes.trim() : "",
    category,
    ...visibleTemplatePayload,
  };
}

/** 按类别配置校验原因、必填模板字段及现场图片要求，返回可直接展示的首条错误。 */
function validateWorkshopIssue(
  category: WorkshopIssue["category"],
  cause: string,
  templateFields: WorkshopTemplateFields,
  imageCount: number,
) {
  const config = WORKSHOP_ISSUE_FORM_CONFIG[category];
  if (!cause.trim()) return `请填写${config.causeLabel}`;
  // 按配置顺序定位第一个缺项，可让提示顺序与表单从上到下的填写顺序保持一致。
  const missingField = config.requiredFields.find((field) => !templateFields[field].trim());  // 按配置顺序定位首个缺项，提示顺序与表单一致
  if (missingField) return `请填写${config.fieldLabels?.[missingField] || WORKSHOP_FIELD_META[missingField].label}`;
  if (config.requiresImages && imageCount < 1) return "请至少保留一张现场图片";
  return "";
}

/** 生成适合 date 输入框的本地日期，避免 UTC 转换导致北京时间午夜附近日期偏移。 */
function localDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");  // 用本地年/月/日避免 UTC 转换造成日期偏移
  return `${year}-${month}-${day}`;
}

/** 在本地日历上移动日期；固定到正午可避开夏令时切换附近的午夜边界问题。 */
function moveDate(value: string, offset: number) {
  const date = new Date(`${value}T12:00:00`);  // 固定正午避开夏令时切换附近的午夜边界
  date.setDate(date.getDate() + offset);
  return localDate(date);
}

/** 把存储用的 YYYY-MM-DD 转成人员易读的中文月、日、星期标题。 */
function dateTitle(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long", day: "numeric", weekday: "short",
  }).format(new Date(`${value}T12:00:00`));
}

/** 返回所选日期所在月的有效导出范围；当月的结束日不能超过今天。 */
function monthRange(value: string, today: string): [string, string] {
  const selected = new Date(`${value}T12:00:00`);
  const first = localDate(new Date(selected.getFullYear(), selected.getMonth(), 1));
  const monthEnd = localDate(new Date(selected.getFullYear(), selected.getMonth() + 1, 0));
  return [first, monthEnd > today ? today : monthEnd];
}

/**
 * 计算包含首尾两天的自然日数量。
 * 使用 UTC 午夜做纯日期相减，避免浏览器所在时区和夏令时造成 23/25 小时日的误差。
 */
function rangeDayCount(startDate: string, endDate: string) {
  if (!startDate || !endDate || startDate > endDate) return 0;
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);  // UTC 午夜纯日期相减，避免时区和夏令时误差
  return Math.floor((end - start) / 86_400_000) + 1;
}

/** 选择现场问题报表的导出日期范围，并负责范围校验和下载状态反馈。 */
function WorkshopIssueExportDialog({ initialDate, today, onClose, onExported }: {
  initialDate: string;
  today: string;
  onClose: () => void;
  onExported: (startDate: string, endDate: string) => void;
}) {
  const [startDate, setStartDate] = useState(initialDate);
  const [endDate, setEndDate] = useState(initialDate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dayCount = rangeDayCount(startDate, endDate);
  const [monthStart, monthEnd] = monthRange(initialDate, today);
  const monthSelected = startDate === monthStart && endDate === monthEnd;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // 下载进行中禁止关闭弹窗，避免用户误以为下载已经取消而重复发起请求。
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  function chooseDay() {
    setStartDate(initialDate);
    setEndDate(initialDate);
    setError("");
  }

  function chooseMonth() {
    setStartDate(monthStart);
    setEndDate(monthEnd);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!startDate || !endDate) {
      setError("请选择完整的开始日期和结束日期");
      return;
    }
    if (startDate > endDate) {
      setError("开始日期不能晚于结束日期");
      return;
    }
    if (dayCount > 366) {
      // 限制单次范围，避免图片较多时生成超大工作簿并长时间占用服务端工作进程。
      setError("单次最多导出 366 天的问题报表");
      return;
    }
    setBusy(true);
    setError("");
    try {
      // 下载函数内部负责解析文件名、创建对象地址并触发浏览器保存。
      await downloadWorkshopIssues(startDate, endDate);
      onExported(startDate, endDate);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "现场问题报表导出失败");
    } finally {
      setBusy(false);
    }
  }

  return <div className="fyt-workshop-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="fyt-workshop-dialog fyt-workshop-export-dialog" role="dialog" aria-modal="true" aria-labelledby="workshop-export-title">
      <header><div><span>标准异常问题报告</span><h2 id="workshop-export-title">选择导出时间</h2><p>导出文件按标准问题表生成五类明细，并保留“问题一览表”工作表。</p></div><button type="button" className="fyt-action-icon" disabled={busy} onClick={onClose} aria-label="关闭导出窗口"><Icon name="x" size={19} /></button></header>
      <form onSubmit={(event) => void submit(event)}>
        <div className="fyt-workshop-export-presets" aria-label="快捷日期范围">
          <button type="button" className={startDate === initialDate && endDate === initialDate ? "selected" : ""} onClick={chooseDay}>当天</button>
          <button type="button" className={monthSelected ? "selected" : ""} onClick={chooseMonth}>本月</button>
        </div>
        <div className="fyt-workshop-export-range">
          <label>开始日期<input type="date" value={startDate} max={today} onChange={(event) => { setStartDate(event.target.value); setError(""); }} required /></label>
          <span aria-hidden="true">至</span>
          <label>结束日期<input type="date" value={endDate} min={startDate || undefined} max={today} onChange={(event) => { setEndDate(event.target.value); setError(""); }} required /></label>
        </div>
        <div className="fyt-workshop-export-summary"><Icon name="calendar" size={18} /><div><strong>{startDate === endDate ? startDate : `${startDate} 至 ${endDate}`}</strong><small>{dayCount ? `共 ${dayCount} 天，将导出范围内所有已发布问题` : "请检查日期范围"}</small></div></div>
        {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}
        <footer><button type="button" className="fyt-action-secondary" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="fyt-action-primary" disabled={busy}><Icon name="download" size={16} />{busy ? "正在生成报表..." : "导出标准报表"}</button></footer>
      </form>
    </section>
  </div>;
}

/**
 * 编辑已发布问题的完整弹窗。
 *
 * 图片增删会立即写入服务端，文本字段则在点击保存时一次提交。currentIssue 始终保存服务端
 * 最近一次返回的版本，这样后续更新可以携带最新 updated_at 做乐观并发检查。
 */
function IssueEditDialog({ issue, onClose, onSaved }: {
  issue: WorkshopIssue;
  onClose: () => void;
  onSaved: (issue: WorkshopIssue, message: string) => Promise<void>;
}) {
  const [currentIssue, setCurrentIssue] = useState(issue);
  const [issueDate, setIssueDate] = useState(issue.issue_date);
  const [category, setCategory] = useState(issue.category);
  const [cause, setCause] = useState(issue.cause);
  const [notes, setNotes] = useState(issue.notes);
  const [templateFields, setTemplateFields] = useState<WorkshopTemplateFields>(() => issueTemplateFields(issue));
  // busy 保存具体操作名或图片 id，同一状态既能锁定弹窗，也能区分正在上传、保存或删除哪一项。
  const [busy, setBusy] = useState("");
  const [progress, setProgress] = useState(0);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const cameraInput = useRef<HTMLInputElement>(null);
  const galleryInput = useRef<HTMLInputElement>(null);
  const config = WORKSHOP_ISSUE_FORM_CONFIG[category];
  // Set 让动态字段渲染时的必填判断保持常数时间，并避免在每个字段上重复遍历数组。
  const requiredFields = useMemo(() => new Set(config.requiredFields), [config.requiredFields]);  // 必填判断保持常数时间，避免逐字段遍历数组

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // 有写操作时不响应 Esc，防止关闭后失去进度和错误反馈。
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  function setTemplateField<K extends keyof WorkshopTemplateFields>(key: K, value: WorkshopTemplateFields[K]) {
    // 函数式更新保证连续输入时总是在最新字段对象上修改单个键。
    setTemplateFields((current) => ({ ...current, [key]: value }));  // 函数式更新保证连续输入时总是基于最新字段对象
  }

  /** 按字段语义选择合适的原生控件，具体显示字段由问题类别配置决定。 */
  function templateField(key: WorkshopTemplateFieldKey) {
    const meta = WORKSHOP_FIELD_META[key];
    const label = config.fieldLabels?.[key] || meta.label;
    const required = requiredFields.has(key);
    if (key === "cause_analysis" || key === "corrective_action") {
      // 原因分析和纠正措施通常是多句说明，使用多行输入避免重要内容被截断。
      return <label key={key}>{label}<textarea value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} rows={3} placeholder={meta.placeholder} required={required} /></label>;
    }
    if (key === "completion_date") {
      return <label key={key}>{label}<input type="date" value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required} /></label>;
    }
    if (key === "happened_at" || key === "handling_time") {
      // datetime-local 不附带时区；服务端按业务时区解释现场人员填写的本地时间。
      return <label key={key}>{label}<input type="datetime-local" value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required} /></label>;
    }
    if (key === "recurring") {
      return <label key={key}>{label}<select value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required}><option value="">未填写</option><option value="否">否</option><option value="是">是</option></select></label>;
    }
    if (key === "tracking_status") {
      return <label key={key}>{label}<select value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required}><option value="">未填写</option><option value="待处理">待处理</option><option value="处理中">处理中</option><option value="校验完成">校验完成</option><option value="已完成">已完成</option></select></label>;
    }
    return <label key={key}>{label}<input value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} placeholder={meta.placeholder} inputMode={key === "quantity" ? "decimal" : key === "record_count" ? "numeric" : undefined} required={required} /></label>;
  }

  function changeCategory(nextCategory: WorkshopIssue["category"]) {
    setCategory(nextCategory);
    setError("");
    setNotice("");
    // 不支持备注的类别切换后立即清空旧值；其余隐藏模板字段会在请求构造阶段统一清空。
    if (!WORKSHOP_ISSUE_FORM_CONFIG[nextCategory].allowsNotes) setNotes("");
  }

  /** 校验新增图片并逐张上传；逐张处理便于服务端分别校验、压缩和保存图片。 */
  async function addImages(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    // 清空原生 file input，用户删除或上传失败后仍可再次选择同名文件。
    event.target.value = "";
    setError("");
    setNotice("");
    if (!files.length) return;
    if (currentIssue.images.length + files.length > MAX_IMAGES) {
      setError(`每条问题最多保留 ${MAX_IMAGES} 张图片`);
      return;
    }
    const invalidType = files.find((file) => !IMAGE_TYPES.has(file.type));
    if (invalidType) {
      setError(`“${invalidType.name}”不是支持的 JPG、PNG 或 WebP 图片`);
      return;
    }
    const oversized = files.find((file) => file.size > MAX_IMAGE_BYTES);
    if (oversized) {
      setError(`“${oversized.name}”超过 15 MB`);
      return;
    }
    setBusy("images");
    setProgress(0);
    try {
      let nextIssue = currentIssue;
      for (let index = 0; index < files.length; index += 1) {
        const result = await uploadWorkshopIssueImage(currentIssue.id, files[index], (value) => {
          // 单图进度折算到整个文件组，避免每换一张图片进度条重新从零开始。
          setProgress(Math.round((index * 100 + value) / files.length));
        });
        // 每次响应都含最新图片列表和 updated_at，最后一次响应即为当前问题的权威快照。
        nextIssue = result.issue;
      }
      setCurrentIssue(nextIssue);
      setProgress(100);
      setNotice("现场图片已保存");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "图片上传失败");
    } finally {
      setBusy("");
    }
  }

  /** 删除已保存图片并用服务端返回的问题快照替换本地状态。 */
  async function removeImage(imageId: string) {
    if (!window.confirm("确定删除这张现场图片吗？")) return;
    setBusy(imageId);
    setError("");
    setNotice("");
    try {
      const result = await deleteWorkshopIssueImage(currentIssue.id, imageId);
      setCurrentIssue(result.issue);
      setNotice(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "图片删除失败");
    } finally {
      setBusy("");
    }
  }

  /** 校验编辑表单并携带版本时间提交，防止覆盖其他用户刚刚保存的修改。 */
  async function save(event: FormEvent) {
    event.preventDefault();
    const validationError = validateWorkshopIssue(category, cause, templateFields, currentIssue.images.length);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const result = await updateWorkshopIssue(
        currentIssue.id,
        workshopIssuePayload(issueDate, category, cause, notes, templateFields),
        // 服务端比较 updated_at；若版本已变化会拒绝旧页面的覆盖请求并提示重新加载。
        currentIssue.updated_at,
      );
      await onSaved(result.issue, result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "问题更新失败");
    } finally {
      setBusy("");
    }
  }

  return <div className="fyt-workshop-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="fyt-workshop-dialog fyt-workshop-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="workshop-edit-title">
      <header><div><span>修正已发布内容</span><h2 id="workshop-edit-title">编辑现场问题</h2><p>保存后会立即同步到当天记录、日清看板和导出表格。</p></div><button type="button" className="fyt-action-icon" disabled={Boolean(busy)} onClick={onClose} aria-label="关闭编辑窗口"><Icon name="x" size={19} /></button></header>
      <form onSubmit={save}>
        {notice ? <div className="fyt-notice fyt-notice-success">{notice}</div> : null}
        {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}
        <div className="fyt-workshop-edit-topline"><label>问题日期<input type="date" value={issueDate} max={localDate()} onChange={(event) => setIssueDate(event.target.value)} required /></label><label>问题类型<select value={category} onChange={(event) => changeCategory(event.target.value as WorkshopIssue["category"])}>{WORKSHOP_CATEGORY_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
        <p className="fyt-workshop-category-help"><strong>{workshopCategoryLabel(category)}</strong>{config.description}</p>
        <section className="fyt-workshop-edit-images"><div className="fyt-workshop-edit-section-head"><div><strong>现场图片</strong><span>{currentIssue.images.length} / {MAX_IMAGES} 张</span></div><div><input ref={cameraInput} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(event) => void addImages(event)} /><input ref={galleryInput} type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => void addImages(event)} /><button type="button" disabled={Boolean(busy) || currentIssue.images.length >= MAX_IMAGES} onClick={() => cameraInput.current?.click()}><Icon name="camera" size={16} />拍照补充</button><button type="button" disabled={Boolean(busy) || currentIssue.images.length >= MAX_IMAGES} onClick={() => galleryInput.current?.click()}><Icon name="image" size={16} />选择图片</button></div></div>{currentIssue.images.length ? <div className="fyt-workshop-edit-image-grid">{currentIssue.images.map((image, index) => <div key={image.id}><img src={workshopImageUrl(image.url)} alt={`现场图片 ${index + 1}`} /><span>{index + 1}</span><button type="button" disabled={Boolean(busy)} onClick={() => void removeImage(image.id)} aria-label={`删除第 ${index + 1} 张图片`}><Icon name="trash" size={15} /></button></div>)}</div> : <div className="fyt-workshop-photo-empty">当前没有现场图片</div>}{busy === "images" ? <div className="fyt-workshop-upload-progress"><div><span>正在保存图片</span><strong>{progress}%</strong></div><i><b style={{ width: `${progress}%` }} /></i></div> : null}</section>
        {config.sections.map((section, index) => <fieldset className="fyt-workshop-template-section" key={section.legend}><legend>{section.legend}</legend><div className={`fyt-workshop-template-grid${section.fields.some((field) => field === "cause_analysis" || field === "corrective_action") ? " fyt-workshop-template-grid-wide" : ""}`}>{section.fields.map(templateField)}</div>{index === 0 ? <label className="fyt-workshop-edit-cause">{config.causeLabel}<textarea value={cause} onChange={(event) => setCause(event.target.value)} maxLength={1000} rows={4} required placeholder={config.causePlaceholder} /></label> : null}</fieldset>)}
        {config.allowsNotes ? <label className="fyt-workshop-edit-note">备注<textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} rows={3} placeholder="填写防错异常的补充信息（选填）" /></label> : null}
        <footer><button type="button" className="fyt-action-secondary" disabled={Boolean(busy)} onClick={onClose}>取消</button><button type="submit" className="fyt-action-primary" disabled={Boolean(busy)}>{busy === "save" ? "正在保存..." : "保存修改"}</button></footer>
      </form>
    </section>
  </div>;
}

/** 收集问题闭环说明，实际状态更新由页面级处理函数统一完成并刷新列表。 */
function ResolveIssueDialog({ issue, onClose, onResolve }: {
  issue: WorkshopIssue;
  onClose: () => void;
  onResolve: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState(issue.resolution_note || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) {
      setError("请填写问题的解决情况");
      return;
    }
    setBusy(true);
    setError("");
    try { await onResolve(note.trim()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "状态更新失败"); }
    finally { setBusy(false); }
  }

  return <div className="fyt-workshop-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="fyt-workshop-dialog fyt-workshop-resolve-dialog" role="dialog" aria-modal="true" aria-labelledby="workshop-resolve-title">
      <header><div><span>完成问题闭环</span><h2 id="workshop-resolve-title">标记问题已解决</h2><p>{issue.cause}</p></div><button type="button" className="fyt-action-icon" disabled={busy} onClick={onClose} aria-label="关闭解决窗口"><Icon name="x" size={19} /></button></header>
      <form onSubmit={submit}>{error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}<label>解决情况<textarea autoFocus value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} rows={6} required placeholder="例如：缺少物料已于 14:30 补齐，现场复核无误；或填写采用的处理办法和后续注意事项。" /><small>{note.length} / 2000 字</small></label><footer><button type="button" className="fyt-action-secondary" disabled={busy} onClick={onClose}>暂不处理</button><button type="submit" className="fyt-action-primary" disabled={busy}><Icon name="check" size={16} />{busy ? "正在保存..." : "确认已解决"}</button></footer></form>
    </section>
  </div>;
}

/**
 * 展示一条已发布问题及当前用户可执行的操作。
 * 权限按钮只依据服务端返回的 permissions 渲染；前端隐藏只是体验优化，最终权限仍由接口校验。
 */
function IssueCard({ issue, onEdit, onResolve, onReopen, onDelete, busy }: {
  issue: WorkshopIssue;
  onEdit: (issue: WorkshopIssue) => void;
  onResolve: (issue: WorkshopIssue) => void;
  onReopen: (issue: WorkshopIssue) => void;
  onDelete: (issue: WorkshopIssue) => void;
  busy: boolean;
}) {
  const [lightbox, setLightbox] = useState("");
  const config = WORKSHOP_ISSUE_FORM_CONFIG[issue.category];
  // 不同问题类型的责任人字段不同，由统一模式函数返回最适合展示的标签和值。
  const [ownerLabel, ownerValue] = workshopIssueOwnerLabel(issue);
  return <article className="fyt-workshop-issue-card">
    <div className="fyt-workshop-issue-head">
      <div className="fyt-workshop-person"><span>{issue.uploader.display_name.slice(0, 1)}</span><div><strong>{issue.uploader.display_name}</strong><time dateTime={issue.created_at}>{new Date(issue.created_at).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</time></div></div>
      <div className="fyt-workshop-card-actions">
        <span className="fyt-workshop-resolution-badge" data-status={issue.resolution_status}>{issue.resolution_status === "resolved" ? "已解决" : "处理中"}</span>
        {issue.permissions.can_edit ? <button type="button" disabled={busy} onClick={() => onEdit(issue)}><Icon name="edit" size={16} />编辑</button> : null}
        {issue.permissions.can_resolve ? issue.resolution_status === "resolved" ? <button type="button" disabled={busy} onClick={() => onReopen(issue)}><Icon name="refresh" size={16} />重新打开</button> : <button type="button" className="is-resolve" disabled={busy} onClick={() => onResolve(issue)}><Icon name="check" size={16} />标记已解决</button> : null}
        {issue.permissions.can_delete ? <button className="fyt-workshop-delete" type="button" disabled={busy} onClick={() => onDelete(issue)} title="删除问题" aria-label="删除问题"><Icon name="trash" size={17} /></button> : null}
      </div>
    </div>
    {issue.images.length ? <div className="fyt-workshop-image-rail">
      {issue.images.map((image, index) => <button type="button" key={image.id} onClick={() => setLightbox(workshopImageUrl(image.url))} aria-label={`查看第 ${index + 1} 张现场图片`}>
        {/* 列表图片延迟加载，避免某天问题较多时一次下载全部现场图片。 */}
        <img src={workshopImageUrl(image.url)} alt={`${issue.cause}，现场图片 ${index + 1}`} loading="lazy" />
      </button>)}
    </div> : null}
    <div className="fyt-workshop-issue-content">
      <div className="fyt-workshop-issue-tags"><span data-category={issue.category}>{workshopCategoryLabel(issue.category)}</span>{issue.issue_level ? <span>{issue.issue_level}</span> : null}</div>
      <div><span>{config.causeLabel}</span><p>{issue.cause}</p></div>
      {issue.cause_analysis ? <div><span>原因分析</span><p>{issue.cause_analysis}</p></div> : null}
      {issue.corrective_action ? <div><span>纠正措施</span><p>{issue.corrective_action}</p></div> : null}
      <dl>
        {ownerValue ? <div><dt>{ownerLabel}</dt><dd>{ownerValue}</dd></div> : null}
        {issue.batch_no ? <div><dt>批次号</dt><dd>{issue.batch_no}</dd></div> : null}
        {issue.country ? <div><dt>国家</dt><dd>{issue.country}</dd></div> : null}
        {issue.material_code || issue.material_name ? <div><dt>物料</dt><dd>{[issue.material_code, issue.material_name].filter(Boolean).join(" · ")}</dd></div> : null}
        {issue.supplier ? <div><dt>供应商</dt><dd>{issue.supplier}</dd></div> : null}
        {issue.external_inspection_owner ? <div><dt>外检责任人</dt><dd>{issue.external_inspection_owner}</dd></div> : null}
        {issue.completion_date ? <div><dt>完成时间</dt><dd>{issue.completion_date}</dd></div> : null}
        {issue.tracking_status ? <div><dt>状态</dt><dd>{issue.tracking_status}</dd></div> : null}
      </dl>
      {issue.notes ? <div className="fyt-workshop-note"><span>备注</span><p>{issue.notes}</p></div> : null}
      {issue.resolution_note ? <div className="fyt-workshop-resolution-note" data-status={issue.resolution_status}><span>{issue.resolution_status === "resolved" ? "解决情况" : "上次解决记录"}</span><p>{issue.resolution_note}</p><small>{issue.resolved_by.display_name ? `${issue.resolved_by.display_name} · ` : ""}{issue.resolved_at ? new Date(issue.resolved_at).toLocaleString("zh-CN") : ""}</small></div> : null}
    </div>
    {lightbox ? <div className="fyt-workshop-lightbox" role="dialog" aria-modal="true" aria-label="现场图片预览" onClick={() => setLightbox("")}>
      <button type="button" onClick={() => setLightbox("")} aria-label="关闭图片预览"><Icon name="x" size={20} /></button>
      {/* 阻止图片点击冒泡，只有点击遮罩或关闭按钮才退出大图。 */}
      <img src={lightbox} alt="现场图片大图" onClick={(event) => event.stopPropagation()} />
    </div> : null}
  </article>;
}

/** 现场问题主页面：负责按日读取、草稿发布、编辑、闭环、删除及报表导出。 */
export function WorkshopIssuePage({ onBackToWorkflow }: { onBackToWorkflow?: () => void }) {
  const today = localDate();
  const [date, setDate] = useState(today);
  const [data, setData] = useState<WorkshopIssueResponse | null>(null);
  const [cause, setCause] = useState("");
  const [notes, setNotes] = useState("");
  const [category, setCategory] = useState<WorkshopIssue["category"]>("main_material");
  const [templateFields, setTemplateFields] = useState<WorkshopTemplateFields>(EMPTY_WORKSHOP_TEMPLATE_FIELDS);
  const [photos, setPhotos] = useState<SelectedImage[]>([]);
  // busy 为空表示空闲；发布时为 publish，维护已有问题时为对应问题 id。
  const [busy, setBusy] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [publishStatus, setPublishStatus] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [editingIssue, setEditingIssue] = useState<WorkshopIssue | null>(null);
  const [resolvingIssue, setResolvingIssue] = useState<WorkshopIssue | null>(null);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  // ref 为组件卸载清理函数保存最新对象地址，避免空依赖 effect 捕获首次渲染的空数组。
  const previewsRef = useRef<string[]>([]);
  const cameraInput = useRef<HTMLInputElement>(null);
  const galleryInput = useRef<HTMLInputElement>(null);
  const issueFormConfig = WORKSHOP_ISSUE_FORM_CONFIG[category];
  // 可见集合用于提交白名单；必填集合用于动态控件的 required 属性与提交前校验。
  const visibleTemplateFields = useMemo(
    () => new Set(issueFormConfig.sections.flatMap((section) => section.fields)),
    [issueFormConfig.sections],
  );  // 可见集合用作提交白名单
  const requiredTemplateFields = useMemo(
    () => new Set(issueFormConfig.requiredFields),
    [issueFormConfig.requiredFields],
  );  // 必填集合驱动 required 属性与提交前校验

  function setTemplateField<K extends keyof WorkshopTemplateFields>(key: K, value: WorkshopTemplateFields[K]) {
    // 仅替换当前输入对应的键，保留同一模板中尚未提交的其他字段。
    setTemplateFields((current) => ({ ...current, [key]: value }));  // 函数式更新保证连续输入时总是基于最新字段对象
  }

  /** 根据模板字段类型生成输入控件；调用方只需按配置顺序映射字段名。 */
  function templateField(key: WorkshopTemplateFieldKey) {
    const meta = WORKSHOP_FIELD_META[key];
    const label = issueFormConfig.fieldLabels?.[key] || meta.label;
    const required = requiredTemplateFields.has(key);
    if (key === "cause_analysis" || key === "corrective_action") {
      // 长文本字段跨整行展示，其布局由外层 wide 类控制。
      return <label key={key}>{label}<textarea value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} rows={3} placeholder={meta.placeholder} required={required} /></label>;
    }
    if (key === "completion_date") {
      return <label key={key}>{label}<input type="date" value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required} /></label>;
    }
    if (key === "happened_at" || key === "handling_time") {
      return <label key={key}>{label}<input type="datetime-local" value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required} /></label>;
    }
    if (key === "recurring") {
      return <label key={key}>{label}<select value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required}><option value="">未填写</option><option value="否">否</option><option value="是">是</option></select></label>;
    }
    if (key === "tracking_status") {
      return <label key={key}>{label}<select value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} required={required}><option value="">未填写</option><option value="待处理">待处理</option><option value="处理中">处理中</option><option value="校验完成">校验完成</option><option value="已完成">已完成</option></select></label>;
    }
    return <label key={key}>{label}<input value={templateFields[key]} onChange={(event) => setTemplateField(key, event.target.value)} placeholder={meta.placeholder} inputMode={key === "quantity" ? "decimal" : key === "record_count" ? "numeric" : undefined} required={required} /></label>;
  }

  /** 读取当前业务日期的问题、汇总和服务端计算后的操作权限。 */
  const load = useCallback(async () => {
    try {
      const next = await listWorkshopIssues(date);
      setData(next);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "当天问题加载失败");
    }
  }, [date]);

  // 日期改变时重新加载；useCallback 保证 effect 只在查询日期真正改变时执行。
  useEffect(() => { void load(); }, [load]);
  // photos 每次改变都把最新对象地址同步到 ref，供仅在卸载时运行的清理函数读取。
  useEffect(() => { previewsRef.current = photos.map((item) => item.preview); }, [photos]);
  // 页面离开时释放仍存活的 blob 地址，防止多次进入现场问题页面后持续占用浏览器内存。
  useEffect(() => () => previewsRef.current.forEach((url) => URL.revokeObjectURL(url)), []);  // 页面离开时释放所有预览地址，避免浏览器内存持续占用

  /** 校验本次选择的图片，并创建只用于本地预览的对象地址。 */
  function addPhotos(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files || []);
    // 立即重置原生输入，使用户能连续选择同一张照片进行纠正操作。
    event.target.value = "";
    setNotice("");
    if (!incoming.length) return;
    const available = MAX_IMAGES - photos.length;
    if (available <= 0 || incoming.length > available) {
      setError(`每条问题最多选择 ${MAX_IMAGES} 张图片`);
      return;
    }
    const invalidType = incoming.find((file) => !IMAGE_TYPES.has(file.type));
    if (invalidType) {
      setError(`“${invalidType.name}”不是支持的 JPG、PNG 或 WebP 图片`);
      return;
    }
    const oversized = incoming.find((file) => file.size > MAX_IMAGE_BYTES);
    if (oversized) {
      setError(`“${oversized.name}”超过 15 MB`);
      return;
    }
    setError("");
    setPhotos((current) => [...current, ...incoming.map((file) => ({
      // File 没有稳定的业务 id，这个组合值只用于当前 React 列表的键和移除操作。
      id: `${file.name}-${file.lastModified}-${Math.random()}`,
      file,
      // 对象地址避免把大图片编码成 base64 放入 React 状态；使用完必须主动释放。
      preview: URL.createObjectURL(file),  // 对象地址避免把大图片编码成 base64 放入状态
    }))]);
  }

  /** 移除待上传图片，并立即释放其浏览器对象地址。 */
  function removePhoto(id: string) {
    setPhotos((current) => {
      const target = current.find((item) => item.id === id);
      // revoke 只释放预览 URL，不会改变用户设备上的原始照片。
      if (target) URL.revokeObjectURL(target.preview);  // revoke 只释放预览地址，不影响用户设备上的原图
      return current.filter((item) => item.id !== id);
    });
  }

  /** 切换问题类型，同时清理新类型明确不允许保留的图片和备注。 */
  function changeCategory(value: WorkshopIssue["category"]) {
    const nextConfig = WORKSHOP_ISSUE_FORM_CONFIG[value];
    setCategory(value);
    setError("");
    setNotice("");
    if (!nextConfig.requiresImages && photos.length) {
      // 防错异常不接收图片；切换后释放预览资源，避免隐藏文件被意外上传。
      photos.forEach((item) => URL.revokeObjectURL(item.preview));
      setPhotos([]);
    }
    if (!nextConfig.allowsNotes) setNotes("");
  }

  /**
   * 按“创建草稿 -> 上传图片 -> 确认发布”三阶段提交现场问题。
   *
   * 先创建草稿可让每张图片都绑定稳定的问题 id；只有全部图片成功后才发布，因此列表和看板
   * 不会看到缺图的半成品记录。任一步失败都会尝试补偿删除草稿。
   */
  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice("");
    setError("");
    if (!cause.trim()) {
      setError(`请填写${issueFormConfig.causeLabel}`);
      return;
    }
    const missingField = issueFormConfig.requiredFields.find((field) => !templateFields[field].trim());
    if (missingField) {
      setError(`请填写${issueFormConfig.fieldLabels?.[missingField] || WORKSHOP_FIELD_META[missingField].label}`);
      return;
    }
    if (issueFormConfig.requiresImages && !photos.length) {
      setError("请至少选择一张现场图片");
      return;
    }
    setBusy("publish");
    setUploadProgress(0);
    setPublishStatus("正在创建问题记录");
    let draftId = "";
    let published = false;
    try {
      // 即使隐藏字段仍留在组件状态，也只允许当前类别配置声明的字段进入请求。
      const visibleTemplatePayload = Object.fromEntries(
        Object.entries(templateFields).map(([key, value]) => [key, visibleTemplateFields.has(key as WorkshopTemplateFieldKey) ? value.trim() : ""]),
      ) as WorkshopTemplateFields;
      const created = await createWorkshopIssue({
        issue_date: date,
        cause: cause.trim(),
        notes: issueFormConfig.allowsNotes ? notes.trim() : "",
        category,
        ...visibleTemplatePayload,
      });  // 先创建草稿让每张图片绑定稳定问题 id
      // 从此处开始失败时需要删除草稿；在创建成功前 draftId 为空，不执行补偿请求。
      draftId = created.issue.id;  // 创建成功后才允许后续失败时补偿删除草稿
      const selectedPhotos = issueFormConfig.requiresImages ? photos : [];
      for (let index = 0; index < selectedPhotos.length; index += 1) {
        setPublishStatus(`正在上传第 ${index + 1} / ${selectedPhotos.length} 张图片`);
        await uploadWorkshopIssueImage(created.issue.id, selectedPhotos[index].file, (progress) => {
          // 把当前单图百分比折算成全部图片的总体百分比，进度条在多图上传时持续向前。
          setUploadProgress(Math.round((index * 100 + progress) / selectedPhotos.length));
        }, () => {
          // 网络上传结束后服务端仍可能在校验或落盘，单独提示可避免界面看似卡在 100%。
          setPublishStatus(`服务器正在处理第 ${index + 1} / ${selectedPhotos.length} 张图片`);
        });
      }
      setUploadProgress(100);
      setPublishStatus("正在确认发布");
      await publishWorkshopIssue(created.issue.id);
      // 标记发布完成后即使后续列表刷新失败，也不能再把已发布的问题当作草稿删除。
      published = true;  // 发布完成后即使列表刷新失败也不再删除已发布问题
      // 服务端已经持久化图片，本地预览地址不再需要，必须在清空状态前释放。
      photos.forEach((item) => URL.revokeObjectURL(item.preview));  // 服务端已持久化图片，释放本地预览地址
      setPhotos([]);
      setCause("");
      setNotes("");
      setCategory("main_material");
      setTemplateFields(EMPTY_WORKSHOP_TEMPLATE_FIELDS);
      setUploadProgress(100);
      setNotice("问题已加入当天记录");
      await load();
    } catch (reason) {
      if (draftId && !published) {
        // 这是前端的补偿清理：尽量撤销已创建但未完成发布的草稿，避免占用图片和索引空间。
        try { await deleteWorkshopIssue(draftId); }
        // 补偿请求也可能因网络中断失败；服务端的定期草稿清理是最终兜底，原发布错误仍应优先反馈。
        catch { /* 草稿会由服务端定期清理。 */ }
      }
      setError(reason instanceof Error ? reason.message : "问题发布失败");
    } finally {
      setBusy("");
      setPublishStatus("");
    }
  }

  /** 将问题移入服务端回收站，并在成功后重新读取当天列表。 */
  async function removeIssue(issue: WorkshopIssue) {
    if (!window.confirm(`确定删除“${issue.cause}”吗？删除后管理员可以从回收站恢复。`)) return;
    setBusy(issue.id);
    setError("");
    try {
      const result = await deleteWorkshopIssue(issue.id);
      setNotice(result.message);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setBusy("");
    }
  }

  /** 编辑弹窗保存成功后的统一收尾；服务端结果由随后一次完整刷新覆盖。 */
  async function saveEditedIssue(nextIssue: WorkshopIssue, message: string) {
    setEditingIssue(null);
    setNotice(message);
    await load();
  }

  /** 使用弹窗打开时的版本时间闭环问题，防止覆盖其他用户同时作出的修改。 */
  async function resolveIssue(note: string) {
    if (!resolvingIssue) return;
    setBusy(resolvingIssue.id);
    setError("");
    try {
      const result = await resolveWorkshopIssue(resolvingIssue.id, note, resolvingIssue.updated_at);
      setResolvingIssue(null);
      setNotice(result.message);
      await load();
    } catch (reason) {
      // 错误交回弹窗显示，主页面不能吞掉错误后关闭用户正在填写的解决说明。
      throw reason;
    } finally {
      setBusy("");
    }
  }

  /** 把已解决问题重新置为处理中，并通过 updated_at 执行乐观并发校验。 */
  async function reopenIssue(issue: WorkshopIssue) {
    if (!window.confirm("确定重新打开这个问题吗？打开后它会重新计入处理中问题。")) return;
    setBusy(issue.id);
    setError("");
    try {
      const result = await reopenWorkshopIssue(issue.id, issue.updated_at);
      setNotice(result.message);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "问题重新打开失败");
    } finally {
      setBusy("");
    }
  }

  return <div className="fyt-page fyt-ops-page fyt-workshop-page">
    <header className="fyt-workshop-toolbar">
      <div className="fyt-workshop-date-nav">
        <button type="button" onClick={() => setDate(moveDate(date, -1))} aria-label="前一天" title="前一天"><Icon name="left" size={18} /></button>
        <label><Icon name="calendar" size={17} /><span>{dateTitle(date)}</span><input type="date" value={date} max={today} onChange={(event) => setDate(event.target.value || today)} /></label>
        <button type="button" disabled={date >= today} onClick={() => setDate(moveDate(date, 1))} aria-label="后一天" title="后一天"><Icon name="right" size={18} /></button>
      </div>
      <div className="fyt-workshop-day-actions">
         <span><strong>{data?.summary.issue_count || 0}</strong> 项问题</span>
         <span><strong>{data?.summary.open_count ?? data?.summary.issue_count ?? 0}</strong> 项处理中</span>
         <span><strong>{data?.summary.resolved_count || 0}</strong> 项已解决</span>
         <span><strong>{data?.summary.image_count || 0}</strong> 张图片</span>
        {onBackToWorkflow ? <button type="button" className="fyt-action-secondary" onClick={onBackToWorkflow}><Icon name="left" size={16} />返回智能工作流</button> : null}
        <button type="button" className="fyt-action-secondary" disabled={Boolean(busy)} onClick={() => { setError(""); setExportDialogOpen(true); }}><Icon name="download" size={16} />导出问题报表</button>
      </div>
    </header>

    {notice ? <div className="fyt-notice fyt-notice-success">{notice}</div> : null}
    {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}

    <div className="fyt-workshop-layout">
      <form className="fyt-workshop-form" onSubmit={submit}>
        <div className="fyt-workshop-form-head"><div className="fyt-workshop-form-icon"><Icon name="camera" size={20} /></div><div><h2>记录现场问题</h2><time dateTime={date}>{date}</time></div></div>
        {issueFormConfig.requiresImages ? <><div className="fyt-workshop-photo-picker">
          <input ref={cameraInput} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={addPhotos} />
          <input ref={galleryInput} type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={addPhotos} />
          <button type="button" onClick={() => cameraInput.current?.click()}><Icon name="camera" size={20} /><span>拍照</span></button>
          <button type="button" onClick={() => galleryInput.current?.click()}><Icon name="image" size={20} /><span>从相册选择</span></button>
        </div>
        {photos.length ? <div className="fyt-workshop-photo-grid">{photos.map((photo, index) => <div key={photo.id}>
          <img src={photo.preview} alt={`待上传现场图片 ${index + 1}`} />
          <span>{index + 1}</span>
          <button type="button" onClick={() => removePhoto(photo.id)} aria-label={`移除第 ${index + 1} 张图片`}><Icon name="x" size={15} /></button>
        </div>)}</div> : <div className="fyt-workshop-photo-empty">还未选择现场图片</div>}
        <small className="fyt-workshop-photo-count">{photos.length} / {MAX_IMAGES} 张</small></> : null}

        <div className="fyt-workshop-classify-grid">
          <label>问题类型<select value={category} onChange={(event) => changeCategory(event.target.value as WorkshopIssue["category"])}>{WORKSHOP_CATEGORY_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        <p className="fyt-workshop-category-help"><strong>{workshopCategoryLabel(category)}</strong>{issueFormConfig.description}</p>
        <fieldset className="fyt-workshop-template-section">
          <legend>{issueFormConfig.sections[0].legend}</legend>
          <div className="fyt-workshop-template-grid">
            {issueFormConfig.sections[0].fields.map(templateField)}
          </div>
        </fieldset>
        <label>{issueFormConfig.causeLabel}<textarea value={cause} onChange={(event) => setCause(event.target.value)} maxLength={1000} rows={4} required placeholder={issueFormConfig.causePlaceholder} /></label>
        {issueFormConfig.sections.slice(1).map((section) => <fieldset className="fyt-workshop-template-section" key={section.legend}>
          <legend>{section.legend}</legend>
          <div className={`fyt-workshop-template-grid${section.fields.some((field) => field === "cause_analysis" || field === "corrective_action") ? " fyt-workshop-template-grid-wide" : ""}`}>
            {section.fields.map(templateField)}
          </div>
        </fieldset>)}
        {issueFormConfig.allowsNotes ? <label>备注<textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} rows={3} placeholder="填写防错异常的补充信息（选填）" /></label> : null}
        {busy === "publish" ? <div className="fyt-workshop-upload-progress"><div><span>{publishStatus || "正在准备发布"}</span><strong>{uploadProgress}%</strong></div><i><b style={{ width: `${uploadProgress}%` }} /></i></div> : null}
        <button className="fyt-action-primary fyt-workshop-submit" disabled={Boolean(busy)}>{busy === "publish" ? "正在发布..." : "发布当天问题"}<Icon name="arrow" size={17} /></button>
      </form>

      <section className="fyt-workshop-feed" aria-live="polite">
        <div className="fyt-workshop-feed-head"><div><h2>{dateTitle(date)}</h2><p>{date}</p></div><button type="button" className="fyt-action-icon" disabled={Boolean(busy)} onClick={() => void load()} title="刷新当天问题" aria-label="刷新当天问题"><Icon name="refresh" size={17} /></button></div>
        {!data ? <div className="fyt-loading-state">正在读取当天问题...</div> : data.issues.length ? <div className="fyt-workshop-issue-list">{data.issues.map((issue) => <IssueCard key={issue.id} issue={issue} busy={Boolean(busy)} onEdit={(item) => { setError(""); setEditingIssue(item); }} onResolve={(item) => { setError(""); setResolvingIssue(item); }} onReopen={(item) => void reopenIssue(item)} onDelete={(item) => void removeIssue(item)} />)}</div> : <EmptyState className="fyt-workshop-empty" illustration="empty-workshop-note.webp" illustrationAlt="可以开始记录现场问题的示意" title="当天还没有问题记录" description="可以从左侧拍照或选择现场图片，开始记录当天问题。" />}
      </section>
    </div>
    {exportDialogOpen ? <WorkshopIssueExportDialog initialDate={date} today={today} onClose={() => setExportDialogOpen(false)} onExported={(startDate, endDate) => { setExportDialogOpen(false); setNotice(startDate === endDate ? `${startDate} 的问题报表已导出` : `${startDate} 至 ${endDate} 的问题报表已导出`); }} /> : null}
    {editingIssue ? <IssueEditDialog key={`${editingIssue.id}-${editingIssue.updated_at}`} issue={editingIssue} onClose={() => setEditingIssue(null)} onSaved={saveEditedIssue} /> : null}
    {resolvingIssue ? <ResolveIssueDialog issue={resolvingIssue} onClose={() => setResolvingIssue(null)} onResolve={resolveIssue} /> : null}
  </div>;
}
