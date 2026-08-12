import { useState, type FormEvent } from "react";
import { login, register, setToken, type User } from "../api";
import { Icon } from "../icons";
import Brand from "./Brand";
import ArtAsset from "../ui/ArtAsset";
import "./auth.css";

type AuthMode = "login" | "register";

/** 登录与注册申请共用的身份入口；默认管理员凭据不会在此页面或提示文案中出现。 */
export function AuthScreen({ onAuthed }: { onAuthed: (user: User) => void }) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ type: "error" | "success"; text: string } | null>(null);

  /** 根据当前模式调用登录或注册接口，并只在登录成功后保存会话令牌。 */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      if (mode === "register") {
        const result = await register(username, displayName, password);
        setNotice({ type: "success", text: result.message });
        // 注册只创建待审核申请，不建立会话；切回登录页等待管理员审核。
        setMode("login");
        setPassword("");
      } else {
        const result = await login(username, password);
        // 先写入令牌再通知父组件加载数据，确保紧随其后的 API 请求都带认证头。
        setToken(result.token);
        onAuthed(result.user);
      }
    } catch (error) {
      setNotice({ type: "error", text: error instanceof Error ? error.message : "请求失败" });
    } finally {
      setBusy(false);
    }
  }

  return <main className="fyt-auth-shell">
    <section className="fyt-auth-story">
      <div className="fyt-auth-story-grid" />
      <Brand />
      <div className="fyt-auth-story-copy"><p className="fyt-eyebrow">峰运通工作台</p><h1>让每一张业务表<br /><em>都流向正确的地方。</em></h1><p>从考勤填报到采购对账，峰运通把重复的数据工作放进同一个清晰、可靠的工作台。</p></div>
      <div className="fyt-auth-story-illustration"><ArtAsset name="auth-data-ribbon.webp" loading="eager" /></div>
      <div className="fyt-auth-story-foot"><span><i className="fyt-auth-signal-dot" />专属业务工作区</span></div>
    </section>
    <section className="fyt-auth-panel"><div className="fyt-auth-card">
      <div className="fyt-auth-mobile-brand"><Brand compact /></div>
      <div className="fyt-auth-heading"><span className="fyt-auth-kicker">{mode === "login" ? "欢迎回来" : "加入工作台"}</span><h2>{mode === "login" ? "登录你的账号" : "申请一个账号"}</h2><p>{mode === "login" ? "使用已审核的账号继续处理业务" : "提交后由管理员审核，审核通过即可登录"}</p></div>
      <form onSubmit={submit} className="fyt-auth-form">
        <label>账号<input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="请输入账号" autoComplete="username" required /></label>
        {mode === "register" ? <label>姓名<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="例如：张三" required /></label> : null}
        <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === "login" ? "请输入密码" : "至少 10 位，包含字母和数字"} autoComplete={mode === "login" ? "current-password" : "new-password"} required /></label>
        {notice ? <div className={`fyt-notice fyt-notice-${notice.type}`} role={notice.type === "error" ? "alert" : "status"}>{notice.text}</div> : null}
        <button className="fyt-action-primary fyt-auth-submit" disabled={busy}>{busy ? "请稍候..." : mode === "login" ? "登录工作台" : "提交注册申请"}<Icon name="arrow" size={18} /></button>
      </form>
      <div className="fyt-auth-switch">{mode === "login" ? <>还没有账号？<button type="button" onClick={() => { setMode("register"); setNotice(null); }}>注册申请</button></> : <>已有账号？<button type="button" onClick={() => { setMode("login"); setNotice(null); }}>返回登录</button></>}</div>
    </div></section>
  </main>;
}

export default AuthScreen;
