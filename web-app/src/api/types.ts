/**
 * Web 前端 `/api` 类型契约。
 *
 * 本文件从 `api.ts` 拆出，只包含接口响应、业务实体和上传下载参数类型，不包含任何
 * 运行时逻辑；`api.ts` 通过 `export *` 重新导出，保证现有导入路径不变。
 */
// 三种角色与服务端权限矩阵保持一致，前端可见性不能替代接口鉴权。
export type UserRole = "admin" | "team_leader" | "user";

/** 登录用户及账号审核状态；角色只用于界面可见性，服务端鉴权以会话为准。 */
export type User = {
  id: number;
  username: string;
  display_name: string;
  role: UserRole;
  status: "pending" | "approved" | "rejected" | "disabled";
  created_at: string;
  approved_at: string | null;
};

/** 业务模块入口描述，来自服务端功能白名单。 */
export type Feature = { key: string; title: string; group: string; description: string };
/** 工作台概览：当前用户、可用业务模块和管理员关注的待审/产出指标。 */
export type Overview = { user: User; features: Feature[]; metrics: { pending_users: number; approved_users: number; output_jobs: number } };
/** 任务调度板聚合数据：状态分布、趋势、功能用量、最近任务和消息。 */
export type DashboardData = {
  user: User;
  generated_at: string;
  metrics: {
    pending_users: number;
    approved_users: number;
    total_jobs: number;
    completed_jobs: number;
    running_jobs: number;
    failed_jobs: number;
  };
  status_breakdown: Record<string, number>;
  trend: Array<{ date: string; total: number; completed: number; failed: number }>;
  feature_usage: Array<{ key: string; title: string; count: number }>;
  recent_jobs: Array<Pick<WebJob, "id" | "action" | "title" | "status" | "progress" | "error" | "created_at" | "updated_at" | "review_pending">>;
  recent_files: Array<{ name: string; size: number; url: string; job_id: string; title: string; created_at: string }>;
  notifications: NotificationItem[];
};
/** 消息中心条目；公告与定向消息使用同一列表协议，`kind` 用于区分来源。 */
export type NotificationItem = { id: number; kind: "announcement" | "message"; title: string; content: string; created_at: string; expires_at: string | null; read_at: string | null };
export type NotificationResponse = { notifications: NotificationItem[]; unread_count: number };
export type PreviewData = { name: string; sheet: string; sheets: string[]; rows: string[][]; truncated: boolean };
/** 报表中心历史文件；下载地址由服务端按管理员权限和报表目录生成。 */
export type ReportFile = {
  name: string;
  url: string;
  size: number;
  generated_at: string;
  scope: "all" | "self";
  scope_label: string;
};
/** 管理员中心一次性返回的账号、任务与上传汇总快照。 */
export type AdminData = {
  summary: { users: number; approved_users: number; admins: number; team_leaders: number; pending_users: number; disabled_users: number; jobs: number; uploads: number; job_files: number; job_bytes: number; upload_bytes: number };
  users: Array<User & { job_count: number; session_count: number; is_primary_admin: boolean }>;
  jobs: Array<{ id: string; user_id: number; username: string; display_name: string; title: string; status: string; progress: number; error: string | null; assignee_id: number | null; assignee_display_name: string | null; file_count: number; file_size: number; created_at: string; updated_at: string }>;
  uploads: Array<{ handle: string; user_id: number; username: string; display_name: string; name: string; size: number; group_id: string; created_at: string }>;
};
export type Announcement = { id: number; title: string; content: string; created_at: string; expires_at: string | null; active: boolean };
export type AuditEntry = { id: number; action: string; target_user_id: number | null; created_at: string; actor_username: string | null; actor_display_name: string | null; target_username: string | null; target_display_name: string | null };
export type LoginSession = { id: string; created_at: string; last_seen_at: string; ip_address: string; user_agent: string; expires_at: number; current: boolean };
export type BackupItem = { id: string; created_at: string; version: string; file_count: number; size: number; status: "ready" | "damaged" };
export type TrashItem = { id: string; kind: "job" | "upload" | "library_file" | "workshop_issue" | "daily_production_plan" | "daily_source_upload"; label: string; size: number; deleted_at: string; deleted_by_username: string | null; deleted_by_name: string | null };
export type MasterDataImportStatus = "needs_review" | "ready_to_confirm" | "ready" | "merged" | "rejected" | "failed";
export type MasterDataImportSummary = {
  id: string;
  original_name: string;
  size: number;
  status: MasterDataImportStatus;
  status_label: string;
  created_at: string;
  uploader_id: number;
  uploader_name: string;
  candidate_count: number;
  conflict_count: number;
  unresolved_conflict_count: number;
  recognized_rows: number;
  recognized_sheet_count: number;
  unrecognized_sheet_count: number;
  confirmed_at: string;
  merged_at: string;
  merge_summary: { changed?: number; suppliers?: number; materials?: number };
};
export type MasterDataCandidateValue = {
  value: string;
  count: number;
  sources: Array<{ sheet: string; row: number; value: string }>;
};
export type MasterDataCandidate = {
  id: string;
  relation_type: string;
  relation_title: string;
  key: string;
  values: MasterDataCandidateValue[];
  current_value: string;
  expected_current_value: string;
  conflict: boolean;
  conflict_reasons: string[];
  selected_value: string;
  decision: null | { type: "keep_current" | "use_candidate" | "manual" | "ignore"; value: string; actor_name: string; decided_at: string };
};
/** 主数据学习批次详情：识别工作表、警告、候选关系与人工决定。 */
export type MasterDataImportDetail = MasterDataImportSummary & {
  recognized_sheets: Array<{ sheet: string; header_row: number; fields: string[]; recognized_rows: number }>;
  unrecognized_sheets: Array<{ sheet: string; reason: string }>;
  warnings: string[];
  candidates: MasterDataCandidate[];
  confirmed_by_name: string;
  merged_by_name: string;
  last_error: string;
};
export type MasterDataImportList = {
  items: MasterDataImportSummary[];
  summary: { total: number; needs_review: number; ready_to_confirm: number; ready: number; merged: number };
};
/** 任务输入文件上传后返回的隔离句柄，后续只通过句柄引用文件。 */
export type UploadedFile = { handle: string; group: string; name: string; size: number };
export type LibraryScope = "team" | "private";
/** 数据库文件及其分类、权限和服务端推导的可编辑边界。 */
export type LibraryFile = {
  id: string;
  name: string;
  size: number;
  content_type: string;
  description: string;
  scope: LibraryScope;
  category: string;
  category_title: string;
  categories: string[];
  confidence: number;
  signals: string[];
  sheet: string;
  category_sheets: Record<string, string>;
  created_at: string;
  updated_at: string;
  uploader: { id: number; username: string; display_name: string };
  updated_by: { id: number; username: string; display_name: string } | null;
  permissions: { can_download: boolean; can_edit: boolean; can_replace: boolean; can_delete: boolean };
};
/** 数据库文件分页查询结果，同时携带配额、分类计数和可用业务分类。 */
export type LibraryResponse = {
  files: LibraryFile[];
  pagination: { page: number; page_size: number; total: number; pages: number };
  summary: { visible_count: number; team_count: number; own_count: number; own_bytes: number; quota_bytes: number; category_counts: Record<string, number> };
  categories: Array<{ key: string; title: string }>;
};
export type WorkshopIssueImage = {
  id: string;
  name: string;
  size: number;
  content_type: string;
  width: number;
  height: number;
  url: string;
};
/** 现场问题完整记录，包含模板字段、状态、图片、上传者与服务端权限。 */
export type WorkshopIssue = {
  id: string;
  issue_date: string;
  cause: string;
  primary_owner: string;
  secondary_owner: string;
  notes: string;
  category: WorkshopIssueCategory;
  severity: WorkshopIssueSeverity;
  issue_source: string;
  model: string;
  country: string;
  batch_no: string;
  team: string;
  material_code: string;
  material_name: string;
  cause_analysis: string;
  corrective_action: string;
  responsibility_party: string;
  external_inspection_owner: string;
  discoverer: string;
  issue_level: string;
  quantity: string;
  issue_type: string;
  completion_date: string;
  recurring: string;
  record_count: string;
  happened_at: string;
  handling_time: string;
  responsible_person: string;
  updated_by_name: string;
  carrier: string;
  supplier: string;
  tracking_status: string;
  status: "draft" | "published";
  resolution_status: "open" | "resolved";
  resolution_note: string;
  resolved_at: string;
  resolved_by: { id: number | null; display_name: string };
  created_at: string;
  updated_at: string;
  uploader: { id: number; username: string; display_name: string };
  images: WorkshopIssueImage[];
  permissions: { can_edit: boolean; can_resolve: boolean; can_delete: boolean };
};
export type WorkshopIssueCategory = "main_material" | "auxiliary_material" | "packaging" | "overseas" | "error_proofing";
export type WorkshopIssueSeverity = "normal" | "important" | "critical";
export type WorkshopIssueResponse = {
  date: string;
  issues: WorkshopIssue[];
  summary: { issue_count: number; image_count: number; open_count: number; resolved_count: number };
};
export type BusinessResultMetric = {
  key: string;
  label: string;
  value: string;
  note: string;
  tone: "neutral" | "info" | "success" | "warning" | "danger";
};
export type BusinessResultSection = {
  key: string;
  title: string;
  description: string;
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, string>>;
  total: number;
  truncated: boolean;
};
/** 核心层注册的结构化业务结果投影，用于在线展示而非让前端重新分析输出文件。 */
export type BusinessResultPresentation = {
  kind: string;
  title: string;
  summary: string;
  metrics: BusinessResultMetric[];
  quality?: {
    score: number;
    level: string;
    tone: BusinessResultMetric["tone"];
    summary: string;
    checks: Array<{ tone: BusinessResultMetric["tone"]; title: string; message: string }>;
  };
  parameters?: Array<{ key: string; label: string; value: string }>;
  sections: BusinessResultSection[];
  notices: Array<{ tone: "info" | "success" | "warning" | "danger"; title: string; message: string }>;
};
export type DailyArrivalBatch = {
  id: string;
  job_id: string;
  job_title: string;
  uploader: string;
  completed_at: string;
  batch_no: string;
  missing_count: number;
  arrived_count: number;
  total_count: number;
  completion_rate: number;
  completion_label: string;
  data_valid: boolean;
  missing_materials: DailyArrivalMaterial[];
  supplier_distribution: DailyArrivalSupplier[];
};
export type DailyArrivalSupplier = {
  supplier: string;
  demand_quantity: string | number;
  received_quantity: string | number;
  shortage_quantity: string | number;
  material_count: number;
};
export type DailyArrivalMaterial = {
  material_code: string;
  material_name: string;
  supplier: string;
  demand_quantity: string | number;
  received_quantity: string | number;
  shortage_quantity: string | number;
};
export type DailyWorkshopIssue = {
  id: string;
  issue_date: string;
  cause: string;
  primary_owner: string;
  secondary_owner: string;
  notes: string;
  category: WorkshopIssueCategory;
  severity: WorkshopIssueSeverity;
  issue_source: string;
  model: string;
  country: string;
  batch_no: string;
  team: string;
  material_code: string;
  material_name: string;
  cause_analysis: string;
  corrective_action: string;
  responsibility_party: string;
  external_inspection_owner: string;
  discoverer: string;
  issue_level: string;
  quantity: string;
  issue_type: string;
  completion_date: string;
  recurring: string;
  record_count: string;
  happened_at: string;
  handling_time: string;
  responsible_person: string;
  updated_by_name: string;
  carrier: string;
  supplier: string;
  tracking_status: string;
  resolution_status: "open" | "resolved";
  resolution_note: string;
  resolved_at: string;
  resolved_by_name: string;
  created_at: string;
  updated_at: string;
  uploader: string;
  images: WorkshopIssueImage[];
  image_count: number;
};
export type DailyPersonType = "participant" | "production";
export type DailyPerson = {
  id: number;
  name: string;
  person_type: DailyPersonType;
  unit: string;
  shift: string;
  sort_order: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};
export type DailyAttendance = {
  id: number | null;
  report_date: string;
  person_id: number;
  name: string;
  person_type: DailyPersonType;
  unit: string;
  shift: string;
  present: boolean;
  status: string;
  reason: string;
  updated_by: number | null;
  updated_at: string;
};
export type DailyProductionShift = {
  id: number;
  group_id: number;
  name: string;
  staffing_count: number;
  sort_order: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};
export type DailyProductionGroup = {
  id: number;
  name: string;
  sort_order: number;
  active: boolean;
  staffing_count: number;
  shifts: DailyProductionShift[];
  created_at: string;
  updated_at: string;
};
export type DailyProductionShiftInput = Pick<DailyProductionShift, "name" | "staffing_count" | "sort_order" | "active"> & { id?: number };
export type DailyProductionGroupInput = Pick<DailyProductionGroup, "name" | "sort_order" | "active"> & { shifts: DailyProductionShiftInput[] };
export type DailyProductionAttendance = {
  id: number | null;
  report_date: string;
  group_id: number;
  group_name: string;
  shift_id: number;
  shift_name: string;
  staffing_count: number;
  attendance_count: number;
  difference: number;
  note: string;
  updated_by: number | null;
  updated_at: string;
};
export type DailyBriefCategory = "escalation" | "notice" | "meeting_todo" | "past_todo" | "process";
export type DailyBriefStatus = "open" | "in_progress" | "done" | "cancelled";
export type DailyBriefItem = {
  id: string;
  report_date: string;
  category: DailyBriefCategory;
  unit: string;
  owner: string;
  title: string;
  description: string;
  due_date: string;
  progress: string;
  status: DailyBriefStatus;
  created_by: number | null;
  created_at: string;
  updated_at: string;
};
export type DailyProductionPlanSummary = {
  file_name?: string;
  sheet_count?: number;
  row_count?: number;
  insights?: {
    focus_date?: string;
    focus_date_source?: string;
    has_focus_date?: boolean;
    plan_total?: number;
    actual_total?: number;
    difference_total?: number;
    reported_plan_total?: number;
    unreported_plan_total?: number;
    reported_shift_count?: number;
    unreported_shift_count?: number;
    completion_rate?: number;
    actual_quantity_from_result?: number;
    daily?: Array<{ date: string; plan: number; actual: number; difference: number; reported_plan?: number; unreported_plan?: number; reported_shift_count?: number; unreported_shift_count?: number; completion_rate: number; shifts?: Array<{ date: string; shift: string; plan: number; actual: number; difference: number; actual_reported?: boolean }> }>;
    shift_summary?: Array<{ date: string; shift: string; plan: number; actual: number; difference: number; actual_reported?: boolean }>;
    team_summary?: Array<{ team: string; quantity: number }>;
    batch_summary?: Array<{ batch: string; quantity: number }>;
    shipping_summary?: Array<{ type: string; total: number; completed: number; pending: number; quantity: number }>;
    order_ledger?: DailyOrderLedgerSource;
    highlights?: string[];
  };
  sheets?: Array<{ sheet: string; rows: number; columns: number; preview: string[][]; kind?: string; table_headers?: string[]; table_rows?: string[][]; table_truncated?: boolean }>;
};
export type DailyProductionPlan = {
  id: string;
  report_date: string;
  data_month: string;
  original_name: string;
  size: number;
  content_type: string;
  summary: DailyProductionPlanSummary;
  uploaded_by: number | null;
  uploaded_by_name: string;
  created_at: string;
  updated_at: string;
  download_url: string;
};
export type DailyFormalOrder = { month: string; order_no: string; country: string; order_type: string; quantity: number; shipment_date: string; status: string; completed: boolean; note: string; outstanding_missing_count: number; outstanding_hazardous_count: number; missing_parts: DailyOrderPart[]; hazardous_packages: DailyOrderPart[] };
export type DailyOrderPart = { order_no?: string; material_code: string; material_name: string; quantity: number; shipment_order_no: string; shipment_date: string; completed: boolean };
export type DailySporadicOrder = { month: string; order_no: string; transport_mode: string; country: string; order_type: string; pallet_count: number; volume_cbm: number; shipment_date: string; shipment_dates: string[]; driver_plate: string; driver_name: string; driver_phone: string; status: string; completed: boolean; note: string; pallets: Array<{ pallet_count: number; length_mm: number; width_mm: number; height_mm: number; volume_cbm: number }> };
export type DailyOrderLedgerSource = { formal_orders: DailyFormalOrder[]; sporadic_orders: DailySporadicOrder[]; missing_parts: DailyOrderPart[]; hazardous_packages: DailyOrderPart[]; monthly_summary: Array<Record<string, string | number>> };
/** 月度生产订单台账：正式/零星订单、缺件、危包与今日发运的服务端聚合结果。 */
export type DailyProductionLedger = { month: string; source_file_count: number; source_files: Array<{ id: string; original_name: string; updated_at: string; uploaded_by_name: string }>; formal_total: number; formal_completed: number; formal_pending: number; formal_quantity: number; sporadic_total: number; sporadic_completed: number; sporadic_pending: number; sporadic_pallets: number; sporadic_volume_cbm: number; missing_part_count: number; outstanding_missing_part_count: number; hazardous_package_count: number; outstanding_hazardous_package_count: number; today_shipments: Array<Record<string, unknown>>; formal_orders: DailyFormalOrder[]; sporadic_orders: DailySporadicOrder[]; missing_parts: DailyOrderPart[]; hazardous_packages: DailyOrderPart[] };
export type DailySafetyImage = { id: string; file_name: string; row: number; category: string; check_item: string; width: number; height: number; url: string };
export type DailySafetyRecord = { row: number; category: string; sequence: string; check_item: string; standard: string; result: string; problem_description: string; corrective_action: string; owner: string; images: DailySafetyImage[] };
/** 管理员上传的到料或安全检查资料，服务端解析后直接进入日清看板。 */
export type DailySourceUpload = { id: string; kind: "arrival" | "safety"; report_date: string; data_month: string; original_name: string; size: number; content_type: string; summary: Record<string, unknown>; uploaded_by: number | null; uploaded_by_name: string; created_at: string; updated_at: string; download_url: string };
/** 指定业务日期的日清聚合数据，按到料、安全、现场、考勤、事项和生产分块。 */
export type DailyReportData = {
  date: string;
  generated_at: string;
  timezone: string;
  scope: "all";
  definitions: { arrival: string; workshop: string; safety: string; production: string };
  arrival: {
    job_count: number;
    upload_count: number;
    task_count: number;
    batch_count: number;
    total_categories: number;
    arrived_categories: number;
    missing_categories: number;
    missing_material_detail_count: number;
    completion_rate: number;
    invalid_batch_count: number;
    supplier_distribution: DailyArrivalSupplier[];
    batches: DailyArrivalBatch[];
  };
  safety_checks: { upload_count: number; latest_upload: DailySourceUpload | null; total_checks: number; qualified_count: number; unqualified_count: number; pending_count: number; qualification_rate: number; image_count: number; category_summary: Array<{ category: string; total: number; qualified: number; unqualified: number }>; records: DailySafetyRecord[]; uploads: DailySourceUpload[] };
  workshop: {
    issue_count: number;
    open_count: number;
    resolved_count: number;
    image_count: number;
    owner_count: number;
    owner_distribution: Array<{ owner: string; count: number }>;
    category_distribution: Array<{ category: WorkshopIssueCategory; count: number }>;
    issues: DailyWorkshopIssue[];
  };
  attendance: {
    people: DailyAttendance[];
    production_groups: DailyProductionAttendance[];
    present_count: number;
    absent_count: number;
    participant_absent_count: number;
    participant_present_count: number;
    participant_total: number;
    production_present_count: number;
    production_total: number;
    production_staffing_count: number;
    production_difference: number;
    production_shortage_count: number;
    production_group_count: number;
    production_shift_count: number;
    unit_summary: Array<{ person_type: DailyPersonType; unit: string; shift: string; total: number; present: number; absent: number; difference: number; reasons: string[] }>;
  };
  brief_items: DailyBriefItem[];
  production_plans: DailyProductionPlan[];
  production_ledger: DailyProductionLedger;
  source_uploads: DailySourceUpload[];
};
export type JobFile = { name: string; size: number; url: string };
/** 持久化业务任务的完整快照，包含进度、日志、结构化展示、文件和版本。 */
export type WebJob = {
  id: string;
  action: string;
  title: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  progress: number;
  logs: string[];
  result: unknown;
  presentation: BusinessResultPresentation | null;
  error: string | null;
  files: JobFile[];
  review_pending?: boolean;
  created_at: string;
  updated_at: string;
  retry_of?: string | null;
  versions?: Array<{ version: number; status: string; created_at: string; files: JobFile[] }>;
};
/** 用户保存的参数模板，仅绑定正式动作不参与分析动作。 */
export type JobTemplate = { id: string; name: string; action: string; payload: Record<string, unknown>; created_at: string; updated_at: string };
/** 任务中心的跨任务、文件与消息搜索结果。 */
export type SearchResponse = { jobs: Array<{ id: string; title: string; action: string; status: string; created_at: string; updated_at: string }>; files: Array<{ name: string; size: number; url: string; job_id: string; title: string }>; messages: Array<{ id: number; title: string; content: string; created_at: string; read_at: string | null }> };

// 会话鉴权统一由服务端 HttpOnly + SameSite=Strict Cookie 承载；前端不再把令牌写入
