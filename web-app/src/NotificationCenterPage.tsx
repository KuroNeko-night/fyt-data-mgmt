import { useCallback, useEffect, useMemo, useState } from "react";
import { markAllNotificationsRead, markNotificationRead, notifications, type NotificationItem } from "./api";
import { Icon } from "./icons";
import PageHeader from "./ui/PageHeader";

type Props = { onChanged: (count: number) => void };

/** 格式化消息时间，保留月、日和分钟，避免列表中展示冗长年份与秒数。 */
function dateLabel(value: string) {
  return new Date(value).toLocaleString("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** 消息中心：展示公告和定向消息，并把未读数量同步回应用壳徽标。 */
export function NotificationCenterPage({ onChanged }: Props) {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  /** 读取消息列表，并使用服务端汇总的未读数更新全局导航。 */
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const result = await notifications(); setItems(result.notifications); onChanged(result.unread_count); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "消息加载失败"); }
    finally { setLoading(false); }
  }, [onChanged]);
  useEffect(() => { void load(); }, [load]);
  const unread = useMemo(() => items.filter((item) => !item.read_at), [items]);
  const visible = filter === "unread" ? unread : items;
  /** 标记单条消息已读，并只更新对应 kind 与 id 的本地记录。 */
  async function read(item: NotificationItem) {
    if (item.read_at || busy) return;
    setBusy(true); setError("");
    // 公告和定向消息可能使用各自的数字 id，因此必须同时比较 kind 才能唯一定位。
    try { const result = await markNotificationRead(item.kind, item.id); setItems((current) => current.map((entry) => entry.id === item.id && entry.kind === item.kind ? { ...entry, read_at: result.read_at } : entry)); onChanged(Math.max(0, unread.length - 1)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "更新消息状态失败"); }
    finally { setBusy(false); }
  }
  /** 一次性标记全部消息已读，并用当前时间做即时乐观更新。 */
  async function readAll() {
    if (!unread.length || busy) return;
    setBusy(true); setError("");
    // 已有 read_at 保持服务端原时间，只有原未读记录使用当前时间作为界面占位。
    try { await markAllNotificationsRead(); setItems((current) => current.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() }))); onChanged(0); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "更新消息状态失败"); }
    finally { setBusy(false); }
  }
  return <div className="fyt-page fyt-content-container fyt-ops-page fyt-notification-page">
    <PageHeader eyebrow="工作协作" title="消息中心" description="公告和管理员发来的提醒会保存在这里。" actions={<div className="fyt-notification-actions"><button className="fyt-action-icon" onClick={() => void load()} title="刷新消息" aria-label="刷新消息"><Icon name="refresh" size={17} /></button><button className="fyt-action-secondary" disabled={!unread.length || busy} onClick={() => void readAll()}><Icon name="check" size={15} />全部已读</button></div>} />
    <div className="fyt-notification-toolbar"><div className="fyt-task-filter-bar" role="tablist"><button className={filter === "all" ? "selected" : ""} onClick={() => setFilter("all")}>全部 <span>{items.length}</span></button><button className={filter === "unread" ? "selected" : ""} onClick={() => setFilter("unread")}>未读 <span>{unread.length}</span></button></div><span className="fyt-notification-count">共 {items.length} 条消息</span></div>
    {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}
    <section className="fyt-notification-list">{loading ? <div className="fyt-empty-row">正在加载消息...</div> : visible.length ? visible.map((item) => <article className={`fyt-notification-card ${item.read_at ? "read" : "unread"}`} key={`${item.kind}-${item.id}`}><span className={`fyt-notification-mark ${item.kind}`}><Icon name={item.kind === "announcement" ? "bell" : "users"} size={17} /></span><div className="fyt-notification-card-main"><div className="fyt-notification-card-head"><strong>{item.title}</strong><span>{item.kind === "announcement" ? "系统公告" : "定向提醒"}</span></div><p>{item.content}</p><time dateTime={item.created_at}>{dateLabel(item.created_at)}</time></div><button className="fyt-notification-read-button" disabled={Boolean(item.read_at) || busy} onClick={() => void read(item)}>{item.read_at ? "已读" : "标记已读"}</button></article>) : <div className="fyt-empty-row">{filter === "unread" ? "没有未读消息" : "暂时没有消息"}</div>}</section>
  </div>;
}
