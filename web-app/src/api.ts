/**
 * Web 前端与同源 `/api` 服务端之间的类型契约和请求适配层。
 *
 * 页面组件只调用本模块导出的业务函数，不自行拼接鉴权头、解析错误或实现上传下载。
 * 普通 JSON 请求统一走 `request`；需要上传进度的文件使用 `XMLHttpRequest`；文件下载
 * 使用带会话头的 `fetch` 转为临时对象地址。这里不包含任何业务算法或权限判断，
 * 最终权限、文件归属、并发版本和数据校验仍以服务端为准。
 */
import { normalizeDailyReportData } from "./dailyReportCompat";

export * from "./api/types";
import type { AdminData, Announcement, AuditEntry, BackupItem, BusinessResultMetric, BusinessResultPresentation, BusinessResultSection, DailyArrivalBatch, DailyArrivalMaterial, DailyArrivalSupplier, DailyAttendance, DailyBriefCategory, DailyBriefItem, DailyBriefStatus, DailyFormalOrder, DailyOrderLedgerSource, DailyOrderPart, DailyPerson, DailyPersonType, DailyProductionAttendance, DailyProductionGroup, DailyProductionGroupInput, DailyProductionLedger, DailyProductionPlan, DailyProductionPlanSummary, DailyProductionShift, DailyProductionShiftInput, DailyReportData, DailySafetyImage, DailySafetyRecord, DailySourceUpload, DailySporadicOrder, DailyWorkshopIssue, DashboardData, Feature, JobFile, JobTemplate, LibraryFile, LibraryResponse, LibraryScope, LoginSession, MasterDataCandidate, MasterDataCandidateValue, MasterDataImportDetail, MasterDataImportList, MasterDataImportStatus, MasterDataImportSummary, NotificationItem, NotificationResponse, Overview, PreviewData, SearchResponse, TrashItem, UploadedFile, User, UserRole, WebJob, WorkshopIssue, WorkshopIssueCategory, WorkshopIssueImage, WorkshopIssueResponse, WorkshopIssueSeverity } from "./api/types";
import { getToken, setToken, clearToken } from "./api/client";
export { getToken, setToken, clearToken };

const API_BASE = import.meta.env.VITE_API_BASE || "";
type ApiRequestOptions = RequestInit & {
  timeoutMs?: number;
  timeoutMessage?: string;
  retryNetwork?: boolean;
  retryAttempts?: number;
};

class ApiResponseError extends Error {}

// localStorage 或通过 X-Session-Token 头回传，避免 XSS 通过读取 localStorage 窃取会话。
// 以下三个函数保留为兼容旧调用方的空实现，登录/登出实际由 Set-Cookie 生效。

/**
 * 发送 JSON API 请求并统一处理会话、超时、网络重试和错误消息。
 *
 * 默认只重试 GET 等幂等请求；调用方显式启用 `retryNetwork` 时，非幂等接口必须由
 * 服务端保证重复请求安全。HTTP 业务错误不会重试，避免把权限或校验失败重复提交。
 * 外部已经传入 `signal` 时不再创建内部超时控制器，以免两个取消来源互相覆盖。
 */
async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const {
    timeoutMs = 0,
    timeoutMessage = "请求超时，请检查网络连接后重试",
    retryNetwork = false,
    retryAttempts,
    ...fetchOptions
  } = options;
  const headers = new Headers(fetchOptions.headers);  // 复制调用方头信息，后续统一叠加会话与内容类型
  if (fetchOptions.body && typeof fetchOptions.body === "string") headers.set("Content-Type", "application/json"); // 文件与 FormData 不应被误标为 JSON。
  const token = getToken();  // 兼容未来需要显式 X-Session-Token 的部署场景
  if (token) headers.set("X-Session-Token", token);  // 仅在存在令牌时附加，避免发送空请求头
  const retryable = retryNetwork || !fetchOptions.method || fetchOptions.method.toUpperCase() === "GET";  // 默认只重试幂等 GET，非幂等接口须服务端保证安全
  const attempts = retryable ? Math.max(1, retryAttempts ?? (retryNetwork ? 2 : 3)) : 1;  // 计算尝试次数，普通 GET 最多三次
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = timeoutMs > 0 && !fetchOptions.signal ? new AbortController() : null; // 调用方信号优先，内部只补充缺失的超时能力。
    const timeoutId = controller
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : 0;
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...fetchOptions,
        headers,
        cache: fetchOptions.cache || "no-store",
        credentials: "same-origin",
        signal: fetchOptions.signal || controller?.signal,
      });
      const data = await response.json().catch(() => ({})); // 兼容空响应或反向代理生成的非 JSON 错误页。
      if (!response.ok) throw new ApiResponseError(data.error || "请求失败");  // 业务错误不重试，避免把权限或校验失败重复提交
      return data as T;
    } catch (error) {
      const timedOut = Boolean(controller?.signal.aborted);  // 内部超时控制器中断视为超时，外部取消原样抛出
      lastError = timedOut ? new Error(timeoutMessage) : error;
      const canRetry = !(error instanceof ApiResponseError) && attempt + 1 < attempts; // 服务端明确返回的业务错误不属于瞬时网络故障。
      if (canRetry) await new Promise((resolve) => window.setTimeout(resolve, 450 * (attempt + 1)));  // 指数退避避免瞬时故障期间密集重试
      else break;
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("请求失败");  // 统一抛出 Error，调用方无需处理未知类型
}

// 认证、会话与工作台基础数据接口。
export function login(username: string, password: string) { return request<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }); }
export function register(username: string, display_name: string, password: string) { return request<{ message: string }>("/api/auth/register", { method: "POST", body: JSON.stringify({ username, display_name, password }) }); }
export function me() { return request<{ user: User }>("/api/auth/me"); }
export function loginSessions() { return request<{ sessions: LoginSession[] }>("/api/auth/sessions"); }
export function changePassword(values: { current_password: string; new_password: string }) { return request<{ message: string }>("/api/auth/password", { method: "POST", body: JSON.stringify(values) }); }
export function deleteLoginSession(id: string) { return request<{ message: string }>(`/api/auth/sessions/${id}`, { method: "DELETE" }); }
export function overview() { return request<Overview>("/api/overview"); }
export function dashboard() { return request<DashboardData>("/api/dashboard"); }

/** 读取指定业务日期的日清数据，并补齐旧版本或空日期缺失的数组与统计字段。 */
export async function dailyReport(date: string) {
  const data = await request<Partial<DailyReportData>>(`/api/daily-report?date=${encodeURIComponent(date)}`);
  return normalizeDailyReportData(data, date);  // 旧版本或空日期缺失数组字段时在此补齐
}

// 日清基础资料、考勤、班组、事项和生产计划管理接口，仅管理员页面调用。
export function listDailyPeople() { return request<{ people: DailyPerson[] }>("/api/admin/daily-people"); }
export function createDailyPerson(values: Omit<DailyPerson, "id" | "created_at" | "updated_at">) { return request<{ message: string; person: DailyPerson }>("/api/admin/daily-people", { method: "POST", body: JSON.stringify(values) }); }
export function updateDailyPerson(id: number, values: Omit<DailyPerson, "id" | "created_at" | "updated_at">) { return request<{ message: string; person: DailyPerson }>(`/api/admin/daily-people/${id}`, { method: "PATCH", body: JSON.stringify(values) }); }
export function deleteDailyPerson(id: number) { return request<{ message: string }>(`/api/admin/daily-people/${id}`, { method: "DELETE" }); }
export function listDailyProductionGroups() { return request<{ groups: DailyProductionGroup[] }>("/api/admin/daily-production-groups"); }
export function createDailyProductionGroup(values: DailyProductionGroupInput) { return request<{ message: string; group: DailyProductionGroup }>("/api/admin/daily-production-groups", { method: "POST", body: JSON.stringify(values) }); }
export function updateDailyProductionGroup(id: number, values: DailyProductionGroupInput) { return request<{ message: string; group: DailyProductionGroup }>(`/api/admin/daily-production-groups/${id}`, { method: "PATCH", body: JSON.stringify(values) }); }
export function deleteDailyProductionGroup(id: number) { return request<{ message: string }>(`/api/admin/daily-production-groups/${id}`, { method: "DELETE" }); }
export function listDailyAttendance(date: string) { return request<{ date: string; attendance: DailyAttendance[]; production_groups: DailyProductionAttendance[] }>(`/api/admin/daily-attendance?date=${encodeURIComponent(date)}`); }
export function saveDailyAttendance(date: string, records: Array<Pick<DailyAttendance, "person_id" | "present" | "status" | "reason">>, productionGroups: Array<Pick<DailyProductionAttendance, "shift_id" | "attendance_count" | "note">>) { return request<{ message: string; date: string; attendance: DailyAttendance[]; production_groups: DailyProductionAttendance[] }>("/api/admin/daily-attendance", { method: "POST", body: JSON.stringify({ date, records, production_groups: productionGroups }) }); }
export function listDailyBriefItems(date: string) { return request<{ date: string; items: DailyBriefItem[] }>(`/api/admin/daily-brief-items?date=${encodeURIComponent(date)}`); }
export function createDailyBriefItem(values: Omit<DailyBriefItem, "id" | "created_by" | "created_at" | "updated_at">) { return request<{ message: string; item: DailyBriefItem }>("/api/admin/daily-brief-items", { method: "POST", body: JSON.stringify(values) }); }
export function updateDailyBriefItem(id: string, values: Omit<DailyBriefItem, "id" | "created_by" | "created_at" | "updated_at">) { return request<{ message: string; item: DailyBriefItem }>(`/api/admin/daily-brief-items/${id}`, { method: "PATCH", body: JSON.stringify(values) }); }
export function deleteDailyBriefItem(id: string) { return request<{ message: string }>(`/api/admin/daily-brief-items/${id}`, { method: "DELETE" }); }
export function listDailyProductionPlans(date: string) { return request<{ date: string; plans: DailyProductionPlan[] }>(`/api/admin/daily-production-plans?date=${encodeURIComponent(date)}`); }

// 系统管理接口：账号审核、角色与访问控制、任务和上传数据维护。
export function users() { return request<{ users: User[] }>("/api/admin/users"); }
export function reviewUser(id: number, decision: "approve" | "reject") { return request<{ message: string }>(`/api/admin/users/${id}/${decision === "approve" ? "approve" : "reject"}`, { method: "POST", body: "{}" }); }
export function adminData() { return request<AdminData>("/api/admin/data"); }
export function updateUser(id: number, values: { display_name: string; status: User["status"] }) { return request<{ message: string }>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(values) }); }
export function updateUserRole(id: number, role: User["role"]) { return request<{ message: string }>(`/api/admin/users/${id}/role`, { method: "POST", body: JSON.stringify({ role }) }); }
export function updateUserAccess(id: number, enabled: boolean) { return request<{ message: string }>(`/api/admin/users/${id}/access`, { method: "POST", body: JSON.stringify({ enabled }) }); }
export function revokeUserSessions(id: number) { return request<{ message: string }>(`/api/admin/users/${id}/sessions/revoke`, { method: "POST", body: "{}" }); }
export function resetUserPassword(id: number, password: string) { return request<{ message: string }>(`/api/admin/users/${id}/password`, { method: "POST", body: JSON.stringify({ password }) }); }
export function deleteUser(id: number) { return request<{ message: string }>(`/api/admin/users/${id}`, { method: "DELETE" }); }
export function deleteAdminJob(id: string) { return request<{ message: string }>(`/api/admin/jobs/${id}`, { method: "DELETE" }); }
export function assignJob(jobId: string, assigneeId: number | null) { return request<{ message: string }>(`/api/jobs/${jobId}/assign`, { method: "POST", body: JSON.stringify({ assignee_id: assigneeId }) }); }
export function deleteAdminUpload(handle: string) { return request<{ message: string }>(`/api/admin/uploads/${encodeURIComponent(handle)}`, { method: "DELETE" }); }

// 公告、定向消息和用户通知接口。
export function adminAnnouncements() { return request<{ announcements: Announcement[] }>("/api/admin/announcements"); }
export function adminAudit() { return request<{ audit: AuditEntry[] }>("/api/admin/audit"); }
export function publishAnnouncement(values: { title: string; content: string; expires_at?: string }) { return request<{ message: string }>("/api/admin/announcements", { method: "POST", body: JSON.stringify(values) }); }
export function updateAnnouncement(id: number, values: { title: string; content: string; active: boolean }) { return request<{ message: string }>(`/api/admin/announcements/${id}`, { method: "PATCH", body: JSON.stringify(values) }); }
export function deleteAnnouncement(id: number) { return request<{ message: string }>(`/api/admin/announcements/${id}`, { method: "DELETE" }); }
export function publishMessage(values: { user_id: number; title: string; content: string }) { return request<{ message: string }>("/api/admin/messages", { method: "POST", body: JSON.stringify(values) }); }
export function notifications() { return request<NotificationResponse>("/api/notifications"); }
export function markNotificationRead(kind: NotificationItem["kind"], id: number) { return request<{ message: string; read_at: string }>(`/api/notifications/${kind}/${id}/read`, { method: "POST", body: "{}" }); }
export function markAllNotificationsRead() { return request<{ message: string }>("/api/notifications/read-all", { method: "POST", body: "{}" }); }
export function logout() { return request<{ message: string }>("/api/auth/logout", { method: "POST", body: "{}" }); }

// 备份与回收站接口；恢复和永久删除的安全确认由相应管理页面收集。
export function adminBackups() { return request<{ backups: BackupItem[] }>("/api/admin/backups"); }
export function createAdminBackup() { return request<{ message: string; backup: BackupItem }>("/api/admin/backups", { method: "POST", body: "{}" }); }
export function restoreAdminBackup(id: string, confirmation: string) { return request<{ message: string; safety_backup_id: string }>(`/api/admin/backups/${id}/restore`, { method: "POST", body: JSON.stringify({ confirmation }) }); }
export function deleteAdminBackup(id: string) { return request<{ message: string }>(`/api/admin/backups/${id}`, { method: "DELETE" }); }
export function adminTrash() { return request<{ trash: TrashItem[] }>("/api/admin/trash"); }
export function restoreAdminTrash(id: string) { return request<{ message: string }>(`/api/admin/trash/${id}/restore`, { method: "POST", body: "{}" }); }
export function deleteAdminTrash(id: string) { return request<{ message: string }>(`/api/admin/trash/${id}`, { method: "DELETE" }); }
/** 正式主数据库快照：供应商名称到编码、材料编号到基本属性的映射。 */
export type CatalogData = { suppliers: Record<string, string>; materials: Record<string, { name?: string; spec?: string; unit?: string; supplier?: string }>; updated_at: string };

// 正式主数据维护与表格学习批次接口；冲突决定按候选项单独保存。
export function catalogList() { return request<CatalogData>("/api/admin/catalog"); }
export function catalogMutate(op: "upsert_supplier" | "delete_supplier" | "upsert_material" | "delete_material", params: Record<string, string>) { return request<CatalogData>("/api/admin/catalog", { method: "POST", body: JSON.stringify({ op, ...params }) }); }
export function masterDataImports() { return request<MasterDataImportList>("/api/admin/master-data/imports"); }
export function masterDataImport(id: string) { return request<{ batch: MasterDataImportDetail }>(`/api/admin/master-data/imports/${id}`); }

/** 保存单个主数据候选冲突的人工决定，并返回更新后的整批详情。 */
export function resolveMasterDataConflict(id: string, candidateId: string, decision: "keep_current" | "use_candidate" | "manual" | "ignore", value = "") {
  return request<{ message: string; batch: MasterDataImportDetail }>(`/api/admin/master-data/imports/${id}/resolve`, {
    method: "POST", body: JSON.stringify({ candidate_id: candidateId, decision, value }),
  });
}
export function confirmMasterDataImport(id: string) { return request<{ message: string; batch: MasterDataImportDetail }>(`/api/admin/master-data/imports/${id}/confirm`, { method: "POST", body: "{}" }); }
export function mergeMasterDataImport(id: string) { return request<{ message: string; batch: MasterDataImportDetail }>(`/api/admin/master-data/imports/${id}/merge`, { method: "POST", body: "{}" }); }
export function rejectMasterDataImport(id: string) { return request<{ message: string; batch: MasterDataImportDetail }>(`/api/admin/master-data/imports/${id}/reject`, { method: "POST", body: "{}" }); }

/**
 * 上传管理员提供的主数据表，并分别报告网络传输进度与服务端分析阶段。
 * XHR 用于获得上传进度；三分钟超时覆盖大表解析，但最终大小限制仍由服务端执行。
 */
export function uploadMasterDataImport(file: File, onProgress?: (progress: number) => void, onProcessing?: () => void): Promise<{ message: string; batch: MasterDataImportDetail }> {
  return new Promise((resolve, reject) => {
    const query = new URLSearchParams({ name: file.name });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/admin/master-data/imports?${query}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("X-Session-Token", token);
    xhr.withCredentials = true;  // 上传请求同样携带同源会话，归属由服务端校验
    xhr.timeout = 180_000;  // 大表解析需要较长时间，超时兜底防止 Promise 永不落定
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100)); };
    xhr.upload.onload = () => onProcessing?.(); // 请求体发送完毕不代表解析完成，界面由此切换为“正在分析”。
    xhr.onerror = () => reject(new Error(`上传 ${file.name} 失败，请检查网络连接`));
    xhr.ontimeout = () => reject(new Error(`分析 ${file.name} 超时，请缩小表格后重试`));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try { data = JSON.parse(xhr.responseText || "{}"); }
      catch { reject(new Error(`分析 ${file.name} 失败`)); return; }
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(String(data.error || `分析 ${file.name} 失败`))); return; }
      onProgress?.(100);
      resolve(data as { message: string; batch: MasterDataImportDetail });
    };
    xhr.send(file);
  });
}

/** 下载当前正式主数据库快照，并在浏览器完成点击后立即释放临时对象地址。 */
export async function downloadMasterDataCatalog(): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}/api/admin/master-data/export`, { headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "主数据库导出失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob); // 对象地址只用于本次下载，不长期占用浏览器内存。
  const link = document.createElement("a");
  link.href = url;
  link.download = "主数据库.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);  // 点击后立即释放对象地址，避免浏览器长期占用
}
export type BatchTrackItem = { job_id: string; action: string; title: string; status: string; created_at: string; files: string[] };
export function batchTrack(q: string) { return request<{ keyword: string; items: BatchTrackItem[] }>(`/api/batch-track?q=${encodeURIComponent(q)}`); }
export type ReconcileScanBatch = { batch: string; sheet: string; rows: number; excluded_rows: number };
export type ReconcileScanFile = { name: string; path: string; supplier: string | null; batches: ReconcileScanBatch[] };
export type ArrivalScanRow = { path: string; name: string; batch_no: string; total: number; auto_total: number; missing_count: number; remark: string; include: boolean };
// 批次跟踪、到料/对账单扫描、报表导出与任务结果分享接口。
export function scanReconcile(paths: string[]) { return request<{ files: ReconcileScanFile[] }>("/api/reconcile/scan", { method: "POST", body: JSON.stringify({ paths }) }); }
export function scanArrival(paths: string[]) { return request<{ rows: ArrivalScanRow[] }>("/api/arrival/scan", { method: "POST", body: JSON.stringify({ paths }) }); }
export function buildReport(range: "7d" | "30d" | "month" | "all", scopeAll: boolean) { return request<{ url: string; name: string }>(`/api/reports?range=${range}&scope=${scopeAll ? "all" : "self"}`); }
export type ShareLink = { token: string; url: string; name: string; expires_at: string };
export function createShare(jobId: string, fileIndex: number, expiresInDays = 7) { return request<ShareLink>("/api/shares", { method: "POST", body: JSON.stringify({ job_id: jobId, file_index: fileIndex, expires_in_days: expiresInDays }) }); }
export function revokeShare(token: string) { return request<{ message: string }>(`/api/shares/${token}`, { method: "DELETE" }); }

/** 按分页、可见范围、分类和关键字查询数据库文件；空筛选不写入查询串。 */
export function listLibraryFiles(values: { page?: number; page_size?: number; q?: string; scope?: "all" | "team" | "private" | "mine"; category?: string } = {}) {
  const query = new URLSearchParams();
  if (values.page) query.set("page", String(values.page));
  if (values.page_size) query.set("page_size", String(values.page_size));
  if (values.q) query.set("q", values.q);
  if (values.scope && values.scope !== "all") query.set("scope", values.scope);  // 默认 all 不写入查询串，由服务端按角色解析可见范围
  if (values.category) query.set("category", values.category);
  return request<LibraryResponse>(`/api/library/files${query.size ? `?${query}` : ""}`);
}

/** 复用数据库新建和替换内容的二进制上传协议，并统一进度与错误解析。 */
function uploadLibraryContent(path: string, file: File, queryValues: Record<string, string>, onProgress?: (progress: number) => void): Promise<{ message: string; file: LibraryFile }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const query = new URLSearchParams({ name: file.name, ...queryValues });
    xhr.open("POST", `${API_BASE}${path}?${query}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("X-Session-Token", token);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100)); };
    xhr.onerror = () => reject(new Error(`上传 ${file.name} 失败，请检查网络连接`));
    xhr.onabort = () => reject(new Error(`上传 ${file.name} 已取消`));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch { reject(new Error(`上传 ${file.name} 失败`)); return; }
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(String(data.error || `上传 ${file.name} 失败`))); return; }
      onProgress?.(100); resolve(data as { message: string; file: LibraryFile });
    };
    xhr.send(file);
  });
}

/** 上传新的数据库文件，并由服务端完成归属、分类和权限记录。 */
export function uploadLibraryFile(file: File, scope: LibraryScope, description: string, onProgress?: (progress: number) => void) {
  return uploadLibraryContent("/api/library/files", file, { scope, description }, onProgress);
}

/** 替换已有数据库文件内容；是否有权替换由服务端按文件权限判断。 */
export function replaceLibraryFile(id: string, file: File, onProgress?: (progress: number) => void) {
  return uploadLibraryContent(`/api/library/files/${id}/content`, file, {}, onProgress);
}

/** 更新数据库文件的展示元数据和可见范围，不修改其二进制内容。 */
export function updateLibraryFile(id: string, values: { name: string; description: string; scope: LibraryScope; category: string }) {
  return request<{ message: string; file: LibraryFile }>(`/api/library/files/${id}`, { method: "PATCH", body: JSON.stringify(values) });
}

/** 将数据库文件移入服务端回收站；前端不直接删除归档路径。 */
export function deleteLibraryFile(id: string) {
  return request<{ message: string }>(`/api/library/files/${id}`, { method: "DELETE" });
}

/** 带会话头下载数据库文件，并使用服务端记录的原始文件名触发浏览器保存。 */
export async function downloadLibraryFile(file: LibraryFile): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}/api/library/files/${file.id}/download`, { headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "数据库文件下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** 按单个业务日期读取用户可见的现场问题。 */
export function listWorkshopIssues(date: string) {
  return request<WorkshopIssueResponse>(`/api/workshop/issues?date=${encodeURIComponent(date)}`);
}

export type WorkshopIssueInput = {
  issue_date: string;
  cause: string;
  primary_owner?: string;
  secondary_owner?: string;
  notes?: string;
  category: WorkshopIssueCategory;
  severity?: WorkshopIssueSeverity;
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
};

/** 创建现场问题草稿；图片通过独立接口上传，避免 JSON 请求体承载二进制内容。 */
export function createWorkshopIssue(values: WorkshopIssueInput) {
  return request<{ message: string; issue: WorkshopIssue }>("/api/workshop/issues", {
    method: "POST", body: JSON.stringify(values),
  });
}

/**
 * 更新现场问题草稿或已发布记录，并携带最后读取的更新时间做乐观并发校验。
 * 若其他用户已经修改，服务端会拒绝覆盖，调用页面应刷新后重新编辑。
 */
export function updateWorkshopIssue(id: string, values: WorkshopIssueInput, expectedUpdatedAt: string) {
  return request<{ message: string; issue: WorkshopIssue }>(`/api/workshop/issues/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...values, expected_updated_at: expectedUpdatedAt }),
  });
}

/**
 * 上传单张现场图片并报告传输阶段和服务端处理阶段。
 * 每张图片的大小、格式与总张数由服务端再次校验，前端进度只用于体验反馈。
 */
export function uploadWorkshopIssueImage(
  issueId: string,
  file: File,
  onProgress?: (progress: number) => void,
  onProcessing?: () => void,
): Promise<{ message: string; issue: WorkshopIssue }> {
  return new Promise((resolve, reject) => {
    const query = new URLSearchParams({ name: file.name });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/workshop/issues/${issueId}/images?${query}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("X-Session-Token", token);
    xhr.withCredentials = true;
    xhr.timeout = 150_000;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100));
    };
    xhr.upload.onload = () => onProcessing?.(); // 文件传输结束后仍可能进行图片校验、尺寸读取和安全落盘。
    xhr.onerror = () => reject(new Error(`上传 ${file.name} 失败，请检查网络连接`));
    xhr.onabort = () => reject(new Error(`上传 ${file.name} 已取消`));
    xhr.ontimeout = () => reject(new Error(`上传 ${file.name} 超时，请检查公网连接后重试`));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try { data = JSON.parse(xhr.responseText || "{}"); }
      catch { reject(new Error(`上传 ${file.name} 失败`)); return; }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(String(data.error || `上传 ${file.name} 失败`)));
        return;
      }
      onProgress?.(100);
      resolve(data as { message: string; issue: WorkshopIssue });
    };
    xhr.send(file);
  });
}

/** 发布已满足分类字段和图片要求的现场问题；网络异常最多额外尝试一次。 */
export function publishWorkshopIssue(id: string) {
  return request<{ message: string; issue: WorkshopIssue }>(`/api/workshop/issues/${id}/publish`, {
    method: "POST",
    body: "{}",
    timeoutMs: 20_000,
    timeoutMessage: "发布确认超时，请检查网络连接后重试",
    retryNetwork: true,
    retryAttempts: 2,
  });
}

/** 标记问题已解决并保存解决说明，更新时间用于阻止覆盖他人的最新修改。 */
export function resolveWorkshopIssue(id: string, resolutionNote: string, expectedUpdatedAt: string) {
  return request<{ message: string; issue: WorkshopIssue }>(`/api/workshop/issues/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolution_note: resolutionNote, expected_updated_at: expectedUpdatedAt }),
  });
}

/** 将已解决问题重新打开，同时执行乐观并发校验。 */
export function reopenWorkshopIssue(id: string, expectedUpdatedAt: string) {
  return request<{ message: string; issue: WorkshopIssue }>(`/api/workshop/issues/${id}/reopen`, {
    method: "POST",
    body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }),
  });
}

/** 删除指定问题中的一张图片，并返回服务端更新后的完整问题对象。 */
export function deleteWorkshopIssueImage(issueId: string, imageId: string) {
  return request<{ message: string; issue: WorkshopIssue }>(`/api/workshop/issues/${issueId}/images/${imageId}`, {
    method: "DELETE",
  });
}

/** 按角色权限删除现场问题，服务端实际执行回收站策略。 */
export function deleteWorkshopIssue(id: string) {
  return request<{ message: string }>(`/api/workshop/issues/${id}`, { method: "DELETE" });
}

/** 把服务端返回的同源相对图片地址补全为当前部署环境可访问的地址。 */
export function workshopImageUrl(path: string) {
  return `${API_BASE}${path}`;
}

/**
 * 导出闭区间内的现场问题报表；起止日期相同即为默认单日报表。
 * 服务端负责套用标准问题模板和多图片排版，前端只保存返回的工作簿。
 */
export async function downloadWorkshopIssues(startDate: string, endDate = startDate): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const response = await fetch(`${API_BASE}/api/workshop/issues/export?${params.toString()}`, {
    headers, credentials: "same-origin",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "现场问题报表导出失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const rangeLabel = startDate === endDate ? startDate : `${startDate}至${endDate}`;
  link.download = `异常问题报告-${rangeLabel}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** 导出指定业务日期的完整日清报告工作簿。 */
export async function downloadDailyReport(date: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}/api/daily-report/export?date=${encodeURIComponent(date)}`, {
    headers, credentials: "same-origin",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "日清报告导出失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `日清报告-${date}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * 上传生产计划成品表，并在服务端完成解析、图表洞察和日清关联。
 * XHR 进度只表示网络上传比例，解析完成以 `load` 返回成功结果为准。
 */
export function uploadDailyProductionPlan(file: File, date: string, onProgress?: (progress: number) => void): Promise<{ message: string; plan: DailyProductionPlan }> {
  return new Promise((resolve, reject) => {
    const query = new URLSearchParams({ name: file.name, date });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/admin/daily-production-plans?${query}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("X-Session-Token", token);
    xhr.withCredentials = true;
    xhr.timeout = 180_000;
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100)); };
    xhr.onerror = () => reject(new Error(`上传 ${file.name} 失败，请检查网络连接`));
    xhr.ontimeout = () => reject(new Error(`解析 ${file.name} 超时，请缩小表格后重试`));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try { data = JSON.parse(xhr.responseText || "{}"); }
      catch { reject(new Error(`解析 ${file.name} 失败`)); return; }
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(String(data.error || `上传 ${file.name} 失败`))); return; }
      onProgress?.(100);
      resolve(data as { message: string; plan: DailyProductionPlan });
    };
    xhr.send(file);
  });
}

/** 下载生产计划原文件，文件名使用服务端保存的原始名称。 */
export async function downloadDailyProductionPlan(plan: DailyProductionPlan): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}${plan.download_url}`, { headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "生产计划下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = plan.original_name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** 删除生产计划记录并交由服务端移入回收站。 */
export function deleteDailyProductionPlan(id: string) {
  return request<{ message: string }>(`/api/admin/daily-production-plans/${id}`, { method: "DELETE" });
}

/**
 * 上传已制作完成的到料或安全检查表，让日清看板直接解析展示。
 * 日期和资料类型用于归档，批次、数量等业务信息仍从表格内容读取。
 */
export function uploadDailySource(file: File, values: { kind: "arrival" | "safety"; date: string }, onProgress?: (progress: number) => void): Promise<{ message: string; upload: DailySourceUpload }> {
  return new Promise((resolve, reject) => {
    const query = new URLSearchParams({ name: file.name, date: values.date, kind: values.kind });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/admin/daily-source-uploads?${query}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("X-Session-Token", token);
    xhr.withCredentials = true;
    xhr.timeout = 180_000;
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100)); };
    xhr.onerror = () => reject(new Error(`上传 ${file.name} 失败，请检查网络连接`));
    xhr.ontimeout = () => reject(new Error(`解析 ${file.name} 超时，请缩小表格后重试`));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch { reject(new Error(`解析 ${file.name} 失败`)); return; }
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(String(data.error || `上传 ${file.name} 失败`))); return; }
      onProgress?.(100);
      resolve(data as { message: string; upload: DailySourceUpload });
    };
    xhr.send(file);
  });
}

/** 下载管理员上传的日清资料原文件。 */
export async function downloadDailySource(upload: DailySourceUpload): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}${upload.download_url}`, { headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "日清资料下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = upload.original_name; document.body.appendChild(link); link.click(); link.remove(); // 临时插入 DOM 兼容桌面与移动浏览器下载行为。
  URL.revokeObjectURL(url);
}

/** 删除日清资料记录，服务端负责同步回收站和看板聚合结果。 */
export function deleteDailySource(id: string) {
  return request<{ message: string }>(`/api/admin/daily-source-uploads/${id}`, { method: "DELETE" });
}

/** 下载指定管理员备份压缩包，恢复操作不由此函数触发。 */
export async function downloadAdminBackup(id: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}/api/admin/backups/${id}/download`, { headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "备份下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${id}.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * 上传业务任务输入文件并返回隔离的上传句柄。
 * 句柄后续写入任务载荷，服务端据此校验文件所属用户和分组。
 */
export function uploadFile(file: File, group: string, onProgress?: (progress: number) => void): Promise<UploadedFile> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const query = new URLSearchParams({ name: file.name, group });
    xhr.open("POST", `${API_BASE}/api/files/upload?${query}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("X-Session-Token", token);
    xhr.withCredentials = true;
    xhr.timeout = 180_000; // 大文件上传同样需要超时兜底，避免网络挂起时 Promise 永不落定。
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100)); };
    xhr.onerror = () => reject(new Error(`上传 ${file.name} 失败，请检查网络连接`));
    xhr.ontimeout = () => reject(new Error(`上传 ${file.name} 超时，请检查网络后重试`));
    xhr.onabort = () => reject(new Error(`上传 ${file.name} 已取消`));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try { data = JSON.parse(xhr.responseText || "{}"); }
      catch { reject(new Error(`上传 ${file.name} 失败`)); return; } // 服务端返回非 JSON（如反向代理错误页）时也保证 Promise 落定。
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(String(data.error || `上传 ${file.name} 失败`))); return; }
      onProgress?.(100); resolve(data as UploadedFile);
    };
    xhr.send(file);
  });
}

/** 创建持久化业务任务；服务端返回任务编号后由页面轮询进度。 */
export function createJob(action: string, title: string, payload: Record<string, unknown>) {
  return request<{ job_id: string }>("/api/jobs", { method: "POST", body: JSON.stringify({ action, title, payload }) });
}

// 任务查询、重试、预检、取消、人工复核和模板接口。
export function getJob(id: string) { return request<{ job: WebJob }>(`/api/jobs/${id}`); }
export function listJobs() { return request<{ jobs: WebJob[] }>("/api/jobs"); }
export function retryJob(id: string) { return request<{ job_id: string }>(`/api/jobs/${id}/retry`, { method: "POST", body: "{}" }); }
export function preflightJob(action: string, payload: Record<string, unknown>) { return request<{ ok: boolean; files: Array<{ name: string; size: number; suffix: string }>; missing: string[]; warnings: string[] }>("/api/jobs/preflight", { method: "POST", body: JSON.stringify({ action, payload }) }); }
export function cancelJob(id: string) { return request<{ message: string }>(`/api/jobs/${id}/cancel`, { method: "POST", body: "{}" }); }
export function submitJobReview(id: string, choices: Record<string, unknown>) { return request<{ job_id: string }>(`/api/jobs/${id}/review`, { method: "POST", body: JSON.stringify({ choices }) }); }
export function searchAll(query: string) { return request<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`); }
export function listTemplates() { return request<{ templates: JobTemplate[] }>("/api/templates"); }
export function createTemplate(name: string, action: string, payload: Record<string, unknown>) { return request<{ id: string; message: string }>("/api/templates", { method: "POST", body: JSON.stringify({ name, action, payload }) }); }
export function updateTemplate(id: string, name: string, payload: Record<string, unknown>) { return request<{ message: string }>(`/api/templates/${id}`, { method: "PATCH", body: JSON.stringify({ name, payload }) }); }
export function deleteTemplate(id: string) { return request<{ message: string }>(`/api/templates/${id}`, { method: "DELETE" }); }
export function previewJobFile(file: JobFile): Promise<PreviewData> { return request<PreviewData>(`${file.url}/preview`); }

/** 下载任务产物；下载 URL 仍需会话鉴权并由服务端校验任务归属。 */
export async function downloadJobFile(file: JobFile): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}${file.url}`, { headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
