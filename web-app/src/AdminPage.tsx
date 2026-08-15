import { useCallback, useEffect, useMemo, useState } from "react";
import { CatalogPanel } from "./CatalogPanel";
import {
  adminAnnouncements,
  adminAudit,
  adminBackups,
  adminData,
  assignJob,
  adminTrash,
  createAdminBackup,
  deleteAdminBackup,
  deleteAdminJob,
  deleteAdminTrash,
  deleteAdminUpload,
  deleteAnnouncement,
  deleteUser,
  downloadAdminBackup,
  publishAnnouncement,
  publishMessage,
  reviewUser,
  revokeUserSessions,
  resetUserPassword,
  restoreAdminBackup,
  restoreAdminTrash,
  updateAnnouncement,
  updateUser,
  updateUserAccess,
  updateUserRole,
  type AdminData,
  type Announcement,
  type AuditEntry,
  type BackupItem,
  type TrashItem,
} from "./api";
import { Icon } from "./icons";
import PageHeader from "./ui/PageHeader";

type AdminTab = "users" | "data" | "safety" | "messages" | "audit" | "catalog";
type AdminUser = AdminData["users"][number];

/** 把字节数转换成管理页使用的四级文件大小标签。 */
function sizeLabel(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/** 将服务端账号状态翻译为面向管理员的中文状态。 */
function statusLabel(status: string) {
  const labels: Record<string, string> = { approved: "正常使用", pending: "待审核", rejected: "未通过", disabled: "已暂停" };
  return labels[status] || "未知状态";
}

/** 将后台任务状态转换成业务人员可理解的处理进度。 */
function jobStatusLabel(status: string) {
  const labels: Record<string, string> = { completed: "已完成", failed: "处理失败", running: "处理中", queued: "排队中", cancelled: "已取消", interrupted: "已中断" };
  return labels[status] || "未知状态";
}

const AUDIT_ACTION_LABELS: Readonly<Record<string, string>> = {
  approved: "通过账号审核",
  rejected: "拒绝账号申请",
  update_user: "更新账号资料",
  grant_admin: "授予管理员权限",
  grant_team_leader: "授予班组长权限",
  revoke_admin: "撤销管理员权限",
  revoke_team_leader: "撤销班组长权限",
  revoke_privileged_role: "恢复业务成员权限",
  revoke_sessions: "强制退出账号",
  disable_user: "暂停账号使用",
  enable_user: "恢复账号使用",
  change_password: "修改账号密码",
  reset_password: "重置账号密码",
  publish_message: "发布定向消息",
  publish_announcement: "发布全局公告",
  master_data_upload: "上传主数据库学习表",
  master_data_resolve: "处理主数据库冲突",
  master_data_confirm: "确认主数据库导入",
  master_data_merge: "合并主数据库导入",
  master_data_reject: "拒绝主数据库导入",
  master_data_export: "导出正式主数据库",
  master_data_auto_merge: "自动合并主数据库导入",
};

/** 带资源编号的审计动作按稳定前缀翻译，顺序只影响存在包含关系的前缀。 */
const AUDIT_PREFIX_LABELS: ReadonlyArray<readonly [string, string]> = [
  ["library_reclassify:", "重新分类数据库文件"],
  ["delete_user:", "删除账号及资料"],
  ["trash_job:", "将任务移入回收站"],
  ["trash_upload:", "将上传资料移入回收站"],
  ["library_upload:", "上传数据库文件"],
  ["library_update:", "修改数据库文件信息"],
  ["library_replace:", "替换数据库文件内容"],
  ["library_trash:", "将数据库文件移入回收站"],
  ["restore_trash:", "恢复回收站数据"],
  ["delete_trash:", "彻底删除回收站数据"],
  ["create_backup:", "创建系统备份"],
  ["restore_backup:", "恢复系统备份"],
  ["delete_backup:", "删除系统备份"],
  ["download_backup:", "下载系统备份"],
  ["update_announcement:", "更新全局公告"],
  ["disable_announcement:", "撤下全局公告"],
  ["download_job_version:", "下载任务历史结果"],
  ["download_job:", "下载任务结果文件"],
  ["download_library:", "下载数据库文件"],
  ["export_workshop:", "导出车间问题"],
  ["daily_person_create:", "添加日清人员"],
  ["daily_person_update:", "更新日清人员"],
  ["daily_person_delete:", "删除或停用日清人员"],
  ["daily_production_group_create:", "添加生产班组"],
  ["daily_production_group_update:", "更新生产班组"],
  ["daily_production_group_delete:", "删除或停用生产班组"],
  ["daily_attendance_save:", "保存每日考勤"],
  ["daily_brief_create:", "添加日清事项"],
  ["daily_brief_update:", "更新日清事项"],
  ["daily_brief_delete:", "删除日清事项"],
  ["daily_plan_upload:", "上传生产计划"],
  ["daily_plan_download:", "下载生产计划"],
  ["daily_plan_trash:", "将生产计划移入回收站"],
  ["daily_source_upload:", "上传日清资料"],
  ["daily_source_download:", "下载日清资料"],
  ["daily_source_trash:", "将日清资料移入回收站"],
  ["export_daily_report:", "导出日清报告"],
];

/** 把审计日志中的稳定动作键映射成人员可读描述，不向界面暴露内部 key。 */
function auditActionLabel(action: string) {
  const exactLabel = AUDIT_ACTION_LABELS[action];
  if (exactLabel) return exactLabel;
  return AUDIT_PREFIX_LABELS.find(([prefix]) => action.startsWith(prefix))?.[1]
    ?? "执行系统管理操作";
}

/** 为审计记录生成人员或数据范围描述，同时兼容对象账号已经被删除的情况。 */
function auditTargetLabel(item: AuditEntry) {
  if (item.target_display_name) return `${item.target_display_name}（${item.target_username}）`;
  if (item.target_user_id) return "已删除的账号";
  // 带冒号后缀通常表示针对某条数据；无后缀的动作通常作用于系统或当前管理员自身。
  const suffix = item.action.split(":")[1];
  return suffix ? "数据记录" : "系统范围";
}

/** 管理员中心：统一处理账号权限、数据资料、备份恢复、消息公告、审计和主数据。 */
export function AdminPage({ currentUserId, onChanged }: { currentUserId: number; onChanged: () => void }) {
  const [tab, setTab] = useState<AdminTab>("users");
  const [data, setData] = useState<AdminData | null>(null);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [trash, setTrash] = useState<TrashItem[]>([]);
  const [auditQuery, setAuditQuery] = useState("");
  const [names, setNames] = useState<Record<number, string>>({});
  const [messageTitle, setMessageTitle] = useState("");
  const [messageContent, setMessageContent] = useState("");
  const [messageUser, setMessageUser] = useState("");
  const [announcementTitle, setAnnouncementTitle] = useState("");
  const [announcementContent, setAnnouncementContent] = useState("");
  const [announcementExpiry, setAnnouncementExpiry] = useState("");
  const [announcementDraft, setAnnouncementDraft] = useState<{ id: number; title: string; content: string } | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<AdminUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<BackupItem | null>(null);
  const [restoreConfirmation, setRestoreConfirmation] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // busy 保存具体操作键，既用于锁定互斥写操作，也用于在对应按钮显示局部进度。
  const [busy, setBusy] = useState("");

  /** 并行刷新所有管理分区，确保跨分区操作后数量、记录和回收站保持一致。 */
  const load = useCallback(async () => {
    setLoading(true);
    try {
      // 五组接口互不依赖，并行请求可显著减少管理员中心首次加载等待时间。
      const [nextData, nextAnnouncements, nextAudit, nextBackups, nextTrash] = await Promise.all([adminData(), adminAnnouncements(), adminAudit(), adminBackups(), adminTrash()]);
      setData(nextData);
      setAnnouncements(nextAnnouncements.announcements);
      setAudit(nextAudit.audit);
      setBackups(nextBackups.backups);
      setTrash(nextTrash.trash);
      // 姓名编辑使用独立草稿表，避免输入过程中直接改写服务端数据快照。
      setNames(Object.fromEntries(nextData.users.map((user) => [user.id, user.display_name])));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "管理数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /**
   * 管理写操作的统一执行器：设置互斥状态、提取提示、刷新管理数据并通知应用壳更新。
   * 返回布尔值让需要清空表单的调用方只在服务端真正成功后执行收尾。
   */
  async function run(key: string, action: () => Promise<unknown>) {
    setBusy(key);
    setNotice("");
    setError("");
    try {
      const result = await action();
      // 管理接口大多返回 message；兼容没有消息体的动作，避免成功后界面空白。
      const message = result && typeof result === "object" && "message" in result ? String((result as { message: string }).message) : "操作已完成";
      setNotice(message);
      await load();
      // 账号、公告等变化还会影响侧栏徽标和当前会话信息，由父组件统一重取。
      onChanged();
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
      return false;
    } finally {
      setBusy("");
    }
  }

  /** 对不可逆或影响他人的操作增加浏览器确认，再交给统一执行器处理。 */
  function confirmRun(message: string, key: string, action: () => Promise<unknown>) {
    if (window.confirm(message)) void run(key, action);
  }

  /** 校验接收人和内容后发布单账号消息，成功时保留接收人便于连续发送。 */
  async function sendMessage() {
    if (!messageUser || !messageTitle.trim() || !messageContent.trim()) {
      setError("请填写接收账号、消息标题和内容");
      return;
    }
    const sent = await run("message", () => publishMessage({ user_id: Number(messageUser), title: messageTitle.trim(), content: messageContent.trim() }));
    if (sent) { setMessageTitle(""); setMessageContent(""); }
  }

  /** 发布全局公告；截止日期按业务时区当日 23:59:59 转换为 UTC 字符串。 */
  async function sendAnnouncement() {
    if (!announcementTitle.trim() || !announcementContent.trim()) {
      setError("请填写公告标题和内容");
      return;
    }
    const sent = await run("announcement", () => publishAnnouncement({
      title: announcementTitle.trim(),
      content: announcementContent.trim(),
      // date 输入没有时区信息，明确拼接 +08:00 才能保证中国时区的截止日完整显示一天。
      ...(announcementExpiry ? { expires_at: new Date(`${announcementExpiry}T23:59:59+08:00`).toISOString() } : {}),
    }));
    if (sent) { setAnnouncementTitle(""); setAnnouncementContent(""); setAnnouncementExpiry(""); }
  }

  /** 保存正在编辑的公告正文，继续沿用原公告的启用状态。 */
  async function saveAnnouncement(item: Announcement) {
    if (!announcementDraft?.title.trim() || !announcementDraft.content.trim()) {
      setError("公告标题和内容不能为空");
      return;
    }
    const saved = await run(`notice-edit-${item.id}`, () => updateAnnouncement(item.id, {
      title: announcementDraft.title.trim(), content: announcementDraft.content.trim(), active: item.active,
    }));
    if (saved) setAnnouncementDraft(null);
  }

  /** 管理员重置其他账号密码；成功后服务端会撤销该账号全部现有会话。 */
  async function submitPasswordReset() {
    if (!passwordTarget || !resetPassword) return;
    const completed = await run(`password-${passwordTarget.id}`, () => resetUserPassword(passwordTarget.id, resetPassword));
    if (completed) { setPasswordTarget(null); setResetPassword(""); }
  }

  /**
   * 恢复整套系统备份。
   * 成功后数据库和会话密钥都可能改变，直接整页刷新比局部状态修补更可靠。
   */
  async function restoreBackup() {
    if (!restoreTarget) return;
    setBusy(`restore-${restoreTarget.id}`); setError(""); setNotice("");
    try {
      await restoreAdminBackup(restoreTarget.id, restoreConfirmation);
      // 恢复完成后不再执行普通 load，强制浏览器重新建立与新数据状态一致的会话。
      window.location.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "备份恢复失败");
      setBusy("");
    }
  }

  /**
   * 根据账号角色、状态和是否为当前账号组合可执行按钮。
   * 服务端仍会逐项鉴权；这里的分支用于防止管理员看到无意义或危险的自操作入口。
   */
  function userActions(user: AdminUser) {
    // 当前管理员不能在本页重置或降级自己，以免误锁账号；改密走专门的账号安全流程。
    if (user.id === currentUserId) return <span className="fyt-muted-cell">当前账号请在“账号安全”中改密</span>;
    if (user.role === "admin") return <>
      {user.is_primary_admin ? <span className="fyt-muted-cell">内置管理员</span> : <><button className="fyt-action-info" disabled={Boolean(busy)} onClick={() => confirmRun(`确定将“${user.display_name}”转为班组长吗？`, `fyt-role-${user.id}`, () => updateUserRole(user.id, "team_leader"))}>转为班组长</button><button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => confirmRun(`确定撤销“${user.display_name}”的管理权限吗？`, `fyt-role-${user.id}-user`, () => updateUserRole(user.id, "user"))}>恢复业务成员</button></>}
      <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => { setPasswordTarget(user); setResetPassword(""); }}>重置密码</button>
      {user.session_count > 0 ? <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => confirmRun(`确定让“${user.display_name}”退出所有设备吗？`, `sessions-${user.id}`, () => revokeUserSessions(user.id))}>强制退出</button> : null}
    </>;
    if (user.role === "team_leader") return <>
      <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`save-${user.id}`, () => updateUser(user.id, { display_name: names[user.id] || user.display_name, status: user.status }))}>保存姓名</button>
      <button className="fyt-action-info" disabled={Boolean(busy)} onClick={() => confirmRun(`确定授予“${user.display_name}”管理员权限吗？该账号将可以管理成员和系统数据。`, `fyt-role-${user.id}-admin`, () => updateUserRole(user.id, "admin"))}>设为管理员</button>
      <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => confirmRun(`确定撤销“${user.display_name}”的班组长权限吗？`, `fyt-role-${user.id}-user`, () => updateUserRole(user.id, "user"))}>恢复业务成员</button>
      {user.session_count > 0 ? <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => confirmRun(`确定让“${user.display_name}”退出所有设备吗？`, `sessions-${user.id}`, () => revokeUserSessions(user.id))}>强制退出</button> : null}
      {user.status === "approved" ? <button className="fyt-action-warning" disabled={Boolean(busy)} onClick={() => confirmRun(`确定暂停“${user.display_name}”的账号吗？该账号会立即退出所有设备。`, `access-${user.id}`, () => updateUserAccess(user.id, false))}>暂停使用</button> : null}
      {user.status === "disabled" ? <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`access-${user.id}`, () => updateUserAccess(user.id, true))}>恢复使用</button> : null}
      {user.status !== "pending" ? <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => { setPasswordTarget(user); setResetPassword(""); }}>重置密码</button> : null}
      {user.status !== "pending" ? <button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmRun(`确定删除账号“${user.username}”及其全部资料吗？此操作无法恢复。`, `delete-${user.id}`, () => deleteUser(user.id))}>删除</button> : null}
    </>;
    return <>
      <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`save-${user.id}`, () => updateUser(user.id, { display_name: names[user.id] || user.display_name, status: user.status }))}>保存姓名</button>
      {user.status === "pending" ? <>
        <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`review-${user.id}`, () => reviewUser(user.id, "approve"))}>通过</button>
        <button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => void run(`review-${user.id}`, () => reviewUser(user.id, "reject"))}>拒绝</button>
      </> : null}
      {user.status === "rejected" ? <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`review-${user.id}`, () => reviewUser(user.id, "approve"))}>重新通过</button> : null}
      {user.status === "approved" ? <>
        <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => confirmRun(`确定授予“${user.display_name}”班组长权限吗？该账号可以维护自己发布的现场问题，并使用数据库和批次跟踪。`, `fyt-role-${user.id}-leader`, () => updateUserRole(user.id, "team_leader"))}>设为班组长</button>
        <button className="fyt-action-info" disabled={Boolean(busy)} onClick={() => confirmRun(`确定授予“${user.display_name}”管理员权限吗？该账号将可以管理成员和系统数据。`, `fyt-role-${user.id}`, () => updateUserRole(user.id, "admin"))}>设为管理员</button>
        {user.session_count > 0 ? <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => confirmRun(`确定让“${user.display_name}”退出所有设备吗？`, `sessions-${user.id}`, () => revokeUserSessions(user.id))}>强制退出</button> : null}
        <button className="fyt-action-warning" disabled={Boolean(busy)} onClick={() => confirmRun(`确定暂停“${user.display_name}”的账号吗？该账号会立即退出所有设备。`, `access-${user.id}`, () => updateUserAccess(user.id, false))}>暂停使用</button>
      </> : null}
      {user.status !== "pending" ? <button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => { setPasswordTarget(user); setResetPassword(""); }}>重置密码</button> : null}
      {user.status === "disabled" ? <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`access-${user.id}`, () => updateUserAccess(user.id, true))}>恢复使用</button> : null}
      {user.status !== "pending" ? <button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmRun(`确定删除账号“${user.username}”及其全部资料吗？此操作无法恢复。`, `delete-${user.id}`, () => deleteUser(user.id))}>删除</button> : null}
    </>;
  }

  // 定向消息只发给其他正常账号，排除自己和待审核、拒绝、停用账号。
  const recipients = useMemo(() => (data?.users || []).filter((user) => user.id !== currentUserId && user.status === "approved"), [data, currentUserId]);
  const filteredAudit = useMemo(() => {
    const query = auditQuery.trim().toLowerCase();
    if (!query) return audit;
    // 把操作者、对象和翻译后的动作拼成搜索语料，界面不要求管理员记忆内部动作键。
    return audit.filter((item) => `${item.actor_display_name || ""} ${item.actor_username || ""} ${item.target_display_name || ""} ${item.target_username || ""} ${auditActionLabel(item.action)}`.toLowerCase().includes(query));
  }, [audit, auditQuery]);
  const summary = data?.summary;

  return <div className="fyt-page fyt-content-container fyt-ops-page fyt-admin-page">
    <PageHeader eyebrow="管理员中心" title="系统管理" description="管理成员权限、业务资料和工作台通知。" actions={<button className="fyt-action-icon" onClick={() => void load()} title="刷新管理数据" aria-label="刷新管理数据"><Icon name="refresh" size={17} /></button>} />
    <div className="fyt-admin-tabs" role="tablist">
      <button className={tab === "users" ? "selected" : ""} onClick={() => setTab("users")}>账号与权限</button>
      <button className={tab === "data" ? "selected" : ""} onClick={() => setTab("data")}>数据资料</button>
      <button className={tab === "safety" ? "selected" : ""} onClick={() => setTab("safety")}>备份与回收站</button>
      <button className={tab === "messages" ? "selected" : ""} onClick={() => setTab("messages")}>消息发布</button>
      <button className={tab === "audit" ? "selected" : ""} onClick={() => setTab("audit")}>管理记录</button>
      <button className={tab === "catalog" ? "selected" : ""} onClick={() => setTab("catalog")}>主数据</button>
    </div>
    {notice ? <div className="fyt-notice fyt-notice-success">{notice}</div> : null}
    {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}
    {loading && !data ? <div className="fyt-loading-state">正在读取管理数据...</div> : null}

    {tab === "users" && data ? <section className="fyt-admin-section">
      <div className="fyt-admin-summary-grid">
        <div><span>账号总数</span><strong>{summary?.users || 0}</strong></div>
        <div><span>管理员</span><strong>{summary?.admins || 0}</strong></div><div><span>班组长</span><strong>{summary?.team_leaders || 0}</strong></div>
        <div><span>待审核</span><strong>{summary?.pending_users || 0}</strong></div>
        <div><span>已暂停</span><strong>{summary?.disabled_users || 0}</strong></div>
      </div>
      {passwordTarget ? <div className="fyt-admin-card fyt-inline-security-form"><div className="fyt-admin-card-head"><div><h3>重置“{passwordTarget.display_name}”的密码</h3><p>保存后该账号会立即退出所有设备，新密码不会显示在管理记录中。</p></div><button className="fyt-action-icon" onClick={() => { setPasswordTarget(null); setResetPassword(""); }} aria-label="关闭密码重置"><Icon name="x" size={16} /></button></div><div className="fyt-admin-form fyt-inline-form"><label>新密码<input type="password" autoComplete="new-password" minLength={10} value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} placeholder="至少 10 位，包含字母和数字" /></label><button className="fyt-action-primary" disabled={!resetPassword || Boolean(busy)} onClick={() => void submitPasswordReset()}>确认重置</button></div></div> : null}
      <div className="fyt-admin-table fyt-account-table">
        <div className="fyt-admin-table-head"><span>成员</span><span>权限</span><span>账号状态</span><span>使用情况</span><span>操作</span></div>
        {data.users.map((user) => <div className="fyt-admin-table-row" key={user.id}>
          <div className="fyt-member-cell"><div className="avatar table-avatar">{user.display_name.slice(0, 1)}</div><div><input className="fyt-admin-name-input" value={names[user.id] || ""} disabled={user.role === "admin"} onChange={(event) => setNames((current) => ({ ...current, [user.id]: event.target.value }))} /><small>@{user.username}</small></div></div>
          <span className={`fyt-role-badge fyt-role-${user.role}`}>{user.role === "admin" ? user.is_primary_admin ? "内置管理员" : "管理员" : user.role === "team_leader" ? "班组长" : "业务成员"}</span>
          <span className={`fyt-status fyt-status-${user.status}`}>{statusLabel(user.status)}</span>
          <span className="fyt-account-usage">{user.session_count > 0 ? `${user.session_count} 个会话` : "未登录"}<small>{user.job_count} 项任务</small></span>
          <div className="fyt-row-actions fyt-account-actions">{userActions(user)}</div>
        </div>)}
      </div>
    </section> : null}

    {tab === "data" && data ? <section className="fyt-admin-section">
      <div className="fyt-admin-summary-grid"><div><span>结果文件</span><strong>{summary?.job_files || 0}</strong></div><div><span>结果占用</span><strong>{sizeLabel(summary?.job_bytes || 0)}</strong></div><div><span>上传占用</span><strong>{sizeLabel(summary?.upload_bytes || 0)}</strong></div><div><span>可管理记录</span><strong>{(summary?.jobs || 0) + (summary?.uploads || 0)}</strong></div></div>
      <div className="fyt-admin-card"><div className="fyt-admin-card-head"><div><h3>任务与结果文件</h3><p>移除后可在回收站恢复任务记录和结果文件。</p></div></div><div className="fyt-admin-table compact"><div className="fyt-admin-table-head"><span>任务</span><span>所属账号</span><span>状态</span><span>文件</span><span>操作</span></div>{data.jobs.map((job) => <div className="fyt-admin-table-row" key={job.id}><div><strong>{job.title}</strong><small>{new Date(job.created_at).toLocaleString("zh-CN")}</small></div><span>{job.display_name}</span><span className={`fyt-status fyt-status-${job.status}`}>{jobStatusLabel(job.status)}</span><span>{job.file_count} 个 · {sizeLabel(job.file_size)}</span><div className="fyt-row-actions"><select className="fyt-admin-assign" value={job.assignee_id ?? ""} disabled={Boolean(busy)} title="指派给谁处理" onChange={(event) => void run(`assign-${job.id}`, () => assignJob(job.id, event.target.value ? Number(event.target.value) : null))}><option value="">未指派</option>{data.users.filter((user) => user.status === "approved").map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select><button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmRun("确定将这条任务及结果文件移入回收站吗？", `job-${job.id}`, () => deleteAdminJob(job.id))}>移入回收站</button></div></div>)}{!data.jobs.length ? <div className="fyt-empty-row">暂无任务记录</div> : null}</div></div>
      <div className="fyt-admin-card"><div className="fyt-admin-card-head"><div><h3>上传资料</h3><p>移除后可在回收站恢复到原上传位置。</p></div></div><div className="fyt-admin-table compact"><div className="fyt-admin-table-head"><span>文件</span><span>所属账号</span><span>大小</span><span>上传时间</span><span>操作</span></div>{data.uploads.map((file) => <div className="fyt-admin-table-row" key={file.handle}><div><strong>{file.name}</strong><small>上传文件</small></div><span>{file.display_name}</span><span>{sizeLabel(file.size)}</span><span>{new Date(file.created_at).toLocaleString("zh-CN")}</span><div className="fyt-row-actions"><button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmRun(`确定将“${file.name}”移入回收站吗？`, `upload-${file.handle}`, () => deleteAdminUpload(file.handle))}>移入回收站</button></div></div>)}{!data.uploads.length ? <div className="fyt-empty-row">暂无上传资料</div> : null}</div></div>
    </section> : null}

    {tab === "safety" ? <section className="fyt-admin-section fyt-safety-section">
      <div className="fyt-admin-summary-grid"><div><span>可用备份</span><strong>{backups.filter((item) => item.status === "ready").length}</strong></div><div><span>备份占用</span><strong>{sizeLabel(backups.reduce((total, item) => total + item.size, 0))}</strong></div><div><span>回收站项目</span><strong>{trash.length}</strong></div><div><span>可恢复数据</span><strong>{sizeLabel(trash.reduce((total, item) => total + item.size, 0))}</strong></div></div>
      <div className="fyt-admin-card"><div className="fyt-admin-card-head"><div><h3>系统备份</h3><p>备份包含账号信息、数据库文件、上传资料、任务结果和回收站内容，并带有完整性校验。</p></div><button className="fyt-action-primary fyt-compact-button" disabled={Boolean(busy)} onClick={() => void run("backup", createAdminBackup)}>{busy === "backup" ? "创建中..." : "创建备份"}</button></div>
        {restoreTarget ? <div className="fyt-restore-confirm"><div><strong>恢复系统备份</strong><p>恢复前会自动创建安全备份，完成后所有账号需要重新登录。</p></div><label>输入“恢复备份”确认<input value={restoreConfirmation} onChange={(event) => setRestoreConfirmation(event.target.value)} /></label><div className="fyt-row-actions"><button className="fyt-action-warning" disabled={restoreConfirmation !== "恢复备份" || Boolean(busy)} onClick={() => void restoreBackup()}>开始恢复</button><button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => { setRestoreTarget(null); setRestoreConfirmation(""); }}>取消</button></div></div> : null}
        <div className="fyt-safety-list">{backups.map((item) => <article key={item.id}><div><strong>系统备份</strong><small>{item.created_at ? new Date(item.created_at).toLocaleString("zh-CN") : "无法读取创建时间"} · {item.file_count} 个文件 · {sizeLabel(item.size)}</small></div><span className={`fyt-status ${item.status === "ready" ? "fyt-status-approved" : "fyt-status-failed"}`}>{item.status === "ready" ? "校验清单可读" : "备份损坏"}</span><div className="fyt-row-actions"><button className="fyt-action-neutral" disabled={item.status !== "ready" || Boolean(busy)} onClick={() => void downloadAdminBackup(item.id).catch((reason) => setError(reason instanceof Error ? reason.message : "下载失败"))}>下载</button><button className="fyt-action-warning" disabled={item.status !== "ready" || Boolean(busy)} onClick={() => { setRestoreTarget(item); setRestoreConfirmation(""); }}>恢复</button><button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmRun("确定删除这份备份吗？", `backup-delete-${item.id}`, () => deleteAdminBackup(item.id))}>删除</button></div></article>)}{!backups.length ? <div className="fyt-empty-row">还没有系统备份</div> : null}</div>
      </div>
      <div className="fyt-admin-card"><div className="fyt-admin-card-head"><div><h3>数据回收站</h3><p>任务、上传资料、数据库文件、车间问题和生产计划可以恢复到原位置；彻底删除后无法找回。</p></div></div><div className="fyt-safety-list">{trash.map((item) => <article key={item.id}><div><strong>{item.label}</strong><small>{item.kind === "job" ? "任务与结果" : item.kind === "library_file" ? "数据库文件" : item.kind === "workshop_issue" ? "车间每日问题" : item.kind === "daily_production_plan" ? "日清生产计划" : "上传资料"} · {sizeLabel(item.size)} · {new Date(item.deleted_at).toLocaleString("zh-CN")}</small></div><span>{item.deleted_by_name || item.deleted_by_username || "系统"}</span><div className="fyt-row-actions"><button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`trash-restore-${item.id}`, () => restoreAdminTrash(item.id))}>恢复</button><button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmRun("确定彻底删除这项数据吗？此操作无法恢复。", `trash-delete-${item.id}`, () => deleteAdminTrash(item.id))}>彻底删除</button></div></article>)}{!trash.length ? <div className="fyt-empty-row">回收站为空</div> : null}</div></div>
    </section> : null}

    {tab === "messages" && data ? <section className="fyt-admin-section fyt-admin-message-grid">
      <div className="fyt-admin-card"><div className="fyt-admin-card-head"><div><h3>向指定账号发布</h3><p>消息只会显示给选定的正常账号。</p></div></div><div className="fyt-admin-form"><label>接收账号<select value={messageUser} onChange={(event) => setMessageUser(event.target.value)}><option value="">请选择账号</option>{recipients.map((user) => <option value={user.id} key={user.id}>{user.display_name}（{user.username}）</option>)}</select></label><label>消息标题<input value={messageTitle} maxLength={80} onChange={(event) => setMessageTitle(event.target.value)} placeholder="例如：本周报表提交提醒" /></label><label>消息内容<textarea value={messageContent} maxLength={4000} onChange={(event) => setMessageContent(event.target.value)} placeholder="填写要发送给该账号的内容" /></label><button className="fyt-action-primary" disabled={busy === "message"} onClick={() => void sendMessage()}>{busy === "message" ? "发布中..." : "发布定向消息"}<Icon name="arrow" size={16} /></button></div></div>
      <div className="fyt-admin-card"><div className="fyt-admin-card-head"><div><h3>发布全局公告</h3><p>公告会显示在所有正常使用账号的工作台。</p></div></div><div className="fyt-admin-form"><label>公告标题<input value={announcementTitle} maxLength={80} onChange={(event) => setAnnouncementTitle(event.target.value)} placeholder="例如：系统维护通知" /></label><label>公告内容<textarea value={announcementContent} maxLength={4000} onChange={(event) => setAnnouncementContent(event.target.value)} placeholder="填写所有成员需要了解的内容" /></label><label>显示截止日期<input type="date" value={announcementExpiry} onChange={(event) => setAnnouncementExpiry(event.target.value)} /></label><button className="fyt-action-primary" disabled={busy === "announcement"} onClick={() => void sendAnnouncement()}>{busy === "announcement" ? "发布中..." : "发布全局公告"}<Icon name="arrow" size={16} /></button></div></div>
      <div className="fyt-admin-card fyt-admin-card-wide"><div className="fyt-admin-card-head"><div><h3>已发布公告</h3><p>支持修改、撤下和重新发布。</p></div></div><div className="fyt-announcement-list">{announcements.map((item) => <article key={item.id}>{announcementDraft?.id === item.id ? <div className="fyt-announcement-edit"><input value={announcementDraft.title} maxLength={80} onChange={(event) => setAnnouncementDraft((current) => current ? { ...current, title: event.target.value } : current)} /><textarea value={announcementDraft.content} maxLength={4000} onChange={(event) => setAnnouncementDraft((current) => current ? { ...current, content: event.target.value } : current)} /></div> : <div><strong>{item.title}</strong><small>{new Date(item.created_at).toLocaleString("zh-CN")}{item.expires_at ? ` · 截止 ${new Date(item.expires_at).toLocaleDateString("zh-CN")}` : ""}</small><p>{item.content}</p></div>}<div className="fyt-row-actions">{announcementDraft?.id === item.id ? <><button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void saveAnnouncement(item)}>保存</button><button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => setAnnouncementDraft(null)}>取消</button></> : <><button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => setAnnouncementDraft({ id: item.id, title: item.title, content: item.content })}>编辑</button>{item.active ? <button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => void run(`notice-${item.id}`, () => deleteAnnouncement(item.id))}>撤下</button> : <button className="fyt-action-success" disabled={Boolean(busy)} onClick={() => void run(`notice-${item.id}`, () => updateAnnouncement(item.id, { title: item.title, content: item.content, active: true }))}>重新发布</button>}</>}</div></article>)}{!announcements.length ? <div className="fyt-empty-row">还没有发布公告</div> : null}</div></div>
    </section> : null}

    {tab === "audit" ? <section className="fyt-admin-section">
      <div className="fyt-admin-card fyt-admin-audit-card"><div className="fyt-admin-card-head fyt-admin-audit-head"><div><h3>管理操作记录</h3><p>保留最近 200 条权限、账号、资料和公告操作。</p></div><label className="fyt-admin-audit-search"><Icon name="search" size={15} /><input value={auditQuery} onChange={(event) => setAuditQuery(event.target.value)} placeholder="搜索成员或操作" /></label></div><div className="fyt-admin-audit-list"><div className="fyt-admin-audit-list-head"><span>时间</span><span>操作人</span><span>操作</span><span>对象</span></div>{filteredAudit.map((item) => <div className="fyt-admin-audit-row" key={item.id}><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString("zh-CN")}</time><span>{item.actor_display_name || item.actor_username || "系统"}</span><strong>{auditActionLabel(item.action)}</strong><span>{auditTargetLabel(item)}</span></div>)}{!filteredAudit.length ? <div className="fyt-empty-row">没有符合条件的管理记录</div> : null}</div></div>
    </section> : null}

    {tab === "catalog" ? <CatalogPanel /> : null}
  </div>;
}
