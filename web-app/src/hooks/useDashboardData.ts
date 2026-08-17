/**
 * 并行维护 Web 壳层需要的概览、调度板和通知数据。
 * 单项失败不会丢弃其他已成功分区，页面可继续使用并针对失败区域显示重试入口。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { dashboard, notifications, overview, type DashboardData, type NotificationResponse, type Overview, type User } from "../api";

/** 可独立刷新与重试的三个数据分区。 */
export type DashboardSection = "overview" | "dashboard" | "notifications";

/** 分区错误映射：只记录失败分区，未失败分区保持未定义。 */
type SectionErrors = Partial<Record<DashboardSection, string>>;

/**
 * 并行维护 Web 壳层需要的概览、调度板和通知数据。
 * 单项失败不会丢弃其他已成功分区，页面可继续使用并针对失败区域显示重试入口。
 * @param initialUser 认证阶段获得的用户，作为首次加载期间的用户兜底。
 * @returns 三个分区数据、错误、加载状态、在线状态、合并后的用户/未读数以及刷新/重试方法。
 */
export function useDashboardData(initialUser: User) {
  const [overviewData, setOverviewData] = useState<Overview | null>(null);
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [notificationData, setNotificationData] = useState<NotificationResponse | null>(null);
  const [errors, setErrors] = useState<SectionErrors>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);

  /** 并行刷新三个互不依赖的数据分区，并分别记录错误而不是整体失败。 */
  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true); else setLoading(true);
    const results = await Promise.allSettled([overview(), dashboard(), notifications()]); // 三项无数据依赖，可同时启动降低工作台等待时间。
    const nextErrors: SectionErrors = {};
    const [overviewResult, dashboardResult, notificationResult] = results;
    if (overviewResult.status === "fulfilled") setOverviewData(overviewResult.value);
    else nextErrors.overview = overviewResult.reason instanceof Error ? overviewResult.reason.message : "工作台概览暂时无法读取";
    if (dashboardResult.status === "fulfilled") setDashboardData(dashboardResult.value);
    else nextErrors.dashboard = dashboardResult.reason instanceof Error ? dashboardResult.reason.message : "任务状态暂时无法读取";
    if (notificationResult.status === "fulfilled") setNotificationData(notificationResult.value);
    else nextErrors.notifications = notificationResult.reason instanceof Error ? notificationResult.reason.message : "消息暂时无法读取";
    setErrors(nextErrors);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { void load(); }, [load]); // 首次挂载加载完整壳层数据。
  useEffect(() => {
    // 浏览器恢复联网时主动刷新，离线时只更新状态，不清空仍可查看的旧数据。
    const handleOnline = () => { setOnline(true); void load(true); };  // 恢复联网时主动刷新，离线只更新状态不清空旧数据
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => { window.removeEventListener("online", handleOnline); window.removeEventListener("offline", handleOffline); };
  }, [load]);

  // 服务端最新响应中的用户信息优先，可及时反映显示名或角色调整；首次加载期间使用认证结果兜底。
  const user = useMemo(() => overviewData?.user ?? dashboardData?.user ?? initialUser, [dashboardData?.user, initialUser, overviewData?.user]);  // 服务端最新用户优先，首屏加载期间用认证结果兜底
  // 未读数优先用消息中心响应；老调度板无该字段时，按未读通知列表长度兜底。
  const unreadCount = notificationData?.unread_count ?? dashboardData?.notifications.filter((item) => !item.read_at).length ?? 0;  // 消息响应优先，旧调度板无该字段时按未读列表兜底
  const refresh = useCallback(() => load(true), [load]);
  // 重试仍走全量刷新，成功后把分区名交回调用方，便于聚焦刚恢复的区域。
  const retry = useCallback((section: DashboardSection) => load(true).then(() => section), [load]);
  return { overviewData, dashboardData, notificationData, errors, loading, refreshing, online, user, unreadCount, refresh, retry };
}
