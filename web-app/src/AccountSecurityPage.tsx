/**
 * 账号安全页。
 *
 * 提供当前账号的密码修改和登录设备管理；会话撤销、改密后的设备失效和
 * 会话 Cookie 规则均由服务端执行，页面只做表单校验与结果同步。
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { changePassword, deleteLoginSession, loginSessions, type LoginSession } from "./api";
import { Icon } from "./icons";
import PageHeader from "./ui/PageHeader";

/** 从浏览器 User-Agent 中提取粗粒度设备和浏览器名称，不展示完整技术字符串。 */
function deviceLabel(userAgent: string) {
  // 顺序上先判断 Edge，因为它的 User-Agent 同时也包含 Chrome 标记。
  const browser = userAgent.includes("Edg/") ? "Microsoft Edge" : userAgent.includes("Chrome/") ? "Google Chrome" : userAgent.includes("Firefox/") ? "Firefox" : "浏览器或客户端";
  const system = userAgent.includes("Windows") ? "Windows" : userAgent.includes("Android") ? "Android" : userAgent.includes("iPhone") || userAgent.includes("iPad") ? "iOS" : "未知设备";
  return `${browser} · ${system}`;
}

/** 账号安全页：修改当前账号密码，并查看或撤销已建立的登录会话。 */
export function AccountSecurityPage({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [sessions, setSessions] = useState<LoginSession[]>([]);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  // busy 为 password 或会话 id，用于避免同时提交多项安全操作。
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  /** 读取当前账号尚未撤销且未过期的会话设备。 */
  const load = useCallback(async () => {
    try {
      const result = await loginSessions();
      setSessions(result.sessions);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录设备读取失败");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /** 在前端先确认两次新密码一致，再交由服务端验证旧密码和复杂度。 */
  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setError("两次输入的新密码不一致");
      return;
    }
    setBusy("password"); setError(""); setNotice("");
    try {
      const result = await changePassword({ current_password: currentPassword, new_password: newPassword });
      setNotice(result.message);
      setCurrentPassword(""); setNewPassword(""); setConfirmation("");
      // 改密会撤销其他设备会话，重新读取以让设备列表立即反映结果。
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "密码修改失败");
    } finally {
      setBusy("");
    }
  }

  /** 撤销指定会话；若撤销的是当前会话，立即通知应用壳返回登录页。 */
  async function removeSession(session: LoginSession) {
    setBusy(session.id); setError(""); setNotice("");
    try {
      const result = await deleteLoginSession(session.id);
      if (session.current) {
        // 当前令牌已经失效，不能继续请求刷新列表，直接执行统一退出流程。
        onLoggedOut();
        return;
      }
      setNotice(result.message);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "设备退出失败");
    } finally {
      setBusy("");
    }
  }

  return <div className="fyt-page fyt-content-container fyt-ops-page fyt-security-page">
    <PageHeader eyebrow="账号安全" title="密码与登录设备" description="定期更新密码，并移除不再使用的登录设备。" />
    {notice ? <div className="fyt-notice fyt-notice-success">{notice}</div> : null}
    {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}
    <div className="fyt-security-grid">
      <section className="fyt-security-panel">
        <div className="fyt-security-head"><div><h3>修改密码</h3><p>新密码至少 10 位，并同时包含字母和数字。</p></div><Icon name="lock" size={20} /></div>
        <form className="fyt-security-form" onSubmit={submitPassword}>
          <label>当前密码<input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
          <label>新密码<input type="password" autoComplete="new-password" minLength={10} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></label>
          <label>再次输入新密码<input type="password" autoComplete="new-password" minLength={10} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></label>
          <button className="fyt-action-primary" disabled={busy === "password"}>{busy === "password" ? "更新中..." : "更新密码"}</button>
        </form>
      </section>
      <section className="fyt-security-panel fyt-security-sessions">
        <div className="fyt-security-head"><div><h3>登录设备</h3><p>修改密码会让除当前设备外的所有设备退出。</p></div><button className="fyt-action-icon" type="button" onClick={() => void load()} title="刷新登录设备" aria-label="刷新登录设备"><Icon name="refresh" size={16} /></button></div>
        <div className="fyt-session-list">{sessions.map((session) => <article key={session.id}>
          <div className="fyt-session-icon"><Icon name="user" size={18} /></div>
          <div><strong>{deviceLabel(session.user_agent)}{session.current ? <span className="current-session">当前设备</span> : null}</strong><small>{session.ip_address || "本机网络"} · 最近使用 {new Date(session.last_seen_at).toLocaleString("zh-CN")}</small></div>
          <button className={session.current ? "fyt-action-warning" : "fyt-action-neutral"} disabled={Boolean(busy)} onClick={() => void removeSession(session)}>{session.current ? "退出" : "移除"}</button>
        </article>)}{!sessions.length ? <div className="fyt-empty-row">暂无有效登录设备</div> : null}</div>
      </section>
    </div>
  </div>;
}
