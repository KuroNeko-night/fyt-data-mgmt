/**
 * 桌面桥接任务的 React 状态管理。
 *
 * 长任务 Hook 负责日志、进度、取消、结果展示与桌面通知；轻量动作 Hook 只管理加载、
 * 错误和返回值。两者都使用代际编号忽略已经过时的异步响应，避免重置或新请求后旧请求
 * 反向覆盖当前界面。
 */
import { useCallback, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { message } from "@tauri-apps/plugin-dialog";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import { bridgeRequest, cancelBridgeRequest, isTauriRuntime, type AppSettings, type BridgePayload } from "../lib/bridge";
import { openLocalPath } from "../lib/files";

// 通知授权属于整个应用进程而非单个组件；模块级缓存可避免每次任务完成都重复查询或弹窗申请。
let notifyPermission: boolean | null = null;

/** 业务结果投影统一使用的语气色枚举，与设计令牌状态色一一对应。 */
export type BusinessResultTone = "neutral" | "info" | "success" | "warning" | "danger";

/**
 * Core 返回的结构化业务结果投影。
 *
 * 前端只负责在线展示这些已经规范化、可信度分析后的数据，不重新分析输出文件；
 * 各页面不应绕过本结构自行解析 Excel/PDF 结果。
 */
export interface BusinessResultPresentation {
  kind: string;
  title: string;
  summary: string;
  metrics: Array<{ key: string; label: string; value: string; note: string; tone: BusinessResultTone }>;
  quality?: {
    score: number;
    level: string;
    tone: BusinessResultTone;
    summary: string;
    checks: Array<{ tone: BusinessResultTone; title: string; message: string }>;
  };
  parameters?: Array<{ key: string; label: string; value: string }>;
  sections: Array<{
    key: string;
    title: string;
    description: string;
    columns: Array<{ key: string; label: string }>;
    rows: Array<Record<string, string>>;
    total: number;
    truncated: boolean;
  }>;
  notices: Array<{ tone: Exclude<BusinessResultTone, "neutral">; title: string; message: string }>;
}

/** 尽力发送桌面系统通知；权限拒绝或插件异常不能改变已经完成的业务状态。 */
async function notifyTask(title: string, body: string) {
  if (!isTauriRuntime()) return;
  try {
    if (notifyPermission === null) {
      notifyPermission = await isPermissionGranted() || await requestPermission() === "granted";
    }
    if (notifyPermission) sendNotification({ title, body });
  } catch {
    // 通知失败不影响业务结果。
  }
}

/**
 * 长任务桥接响应的信封结构。
 *
 * 除业务结果外还携带任务编号、输出目录和日志，日志由桥接事件合并得到。
 */
export interface TaskEnvelope<T> {
  result: T;
  logs: string[];
  task_id: string;
  out_dir: string;
  presentation?: BusinessResultPresentation | null;
}

/** `useBridgeTask` 对外暴露的长任务状态与方法。 */
export interface BridgeTaskState<T> {
  busy: boolean;
  error: string;
  logs: string[];
  progress: number | null;
  outDir: string;
  result: T | null;
  presentation: BusinessResultPresentation | null;
  run: (action: string, payload?: BridgePayload) => Promise<T | null>;
  reset: () => void;
  cancel: () => Promise<void>;
}

/** `useBridgeAction` 对外暴露的轻量动作状态与方法。 */
export interface BridgeActionState<T> {
  busy: boolean;
  error: string;
  result: T | null;
  run: (action: string, payload?: BridgePayload) => Promise<T | null>;
  reset: () => void;
}

/**
 * 管理一个可取消长任务的完整生命周期。
 *
 * 每次运行都会生成独立请求编号并订阅同编号事件；结束时无条件注销监听器。`generationRef`
 * 是不触发渲染的代际令牌，重置或再次运行会使旧 Promise 的结果失效，从而避免竞态更新。
 */
export function useBridgeTask<T>(): BridgeTaskState<T> {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [outDir, setOutDir] = useState("");
  const [result, setResult] = useState<T | null>(null);
  const [presentation, setPresentation] = useState<BusinessResultPresentation | null>(null);
  const requestIdRef = useRef("");
  const cancelledRef = useRef(false);
  const generationRef = useRef(0);

  const run = useCallback(async (action: string, payload: BridgePayload = {}) => {
    const generation = ++generationRef.current; // 捕获本次代际，所有异步返回前都要确认它仍是最新请求。
    setBusy(true);
    setError("");
    setLogs([]);
    setProgress(0);
    setOutDir("");
    setResult(null);
    setPresentation(null);
    cancelledRef.current = false;
    const requestId = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `task-${Date.now()}-${Math.random().toString(16).slice(2)}`; // 旧 WebView 缺少 randomUUID 时提供足够区分并发任务的兼容编号。
    requestIdRef.current = requestId;
    let unlisten: () => void = () => undefined;
    if (isTauriRuntime()) {
      try {
        unlisten = await listen<{ request_id: string; kind: string; value: unknown }>("bridge-task-event", (event) => {
          if (event.payload.request_id !== requestId) return; // 全局事件总线会承载其他任务，必须按编号精确过滤。
          if (event.payload.kind === "log") setLogs((current) => [...current, String(event.payload.value)]); // 函数式更新防止连续日志事件丢失前一条。
          if (event.payload.kind === "progress") setProgress(Number(event.payload.value));
        });
      } catch {
        unlisten = () => undefined; // 事件订阅失败时任务仍可完成，只是不展示实时进度。
      }
    }
    try {
      const response = await bridgeRequest<TaskEnvelope<T>>(action, payload, requestId);
      if (generation !== generationRef.current) return null; // 用户已经重置或启动新任务时丢弃旧响应。
      setLogs(response.logs || []);
      setProgress(100);
      setOutDir(response.out_dir || "");
      setResult(response.result);
      setPresentation(response.presentation || null);
      void notifyTask("业务处理完成", "处理结果已生成，可查看或打开结果文件。");  // 完成通知不等待权限与发送结果，避免阻塞状态收尾
      if (isTauriRuntime()) {
        try {
          const settings = await bridgeRequest<AppSettings>("settings.get");
          if (settings.auto_open_output && response.out_dir) await openLocalPath(response.out_dir);  // 按用户偏好自动打开输出目录
          if (settings.show_done_dialog) await message("业务处理已完成。", {  // 完成后弹窗提示，用户可在设置中关闭该偏好
            title: "峰运通数据管理系统", kind: "info",
          });
        } catch {
          // 收尾动作失败不应把已经成功的业务任务改判为失败。
        }
      }
      return response.result;
    } catch (reason) {
      if (generation !== generationRef.current) return null;
      setError(cancelledRef.current ? "任务已取消。" : reason instanceof Error ? reason.message : String(reason));
      if (!cancelledRef.current) void notifyTask("业务处理失败", "处理未完成，请查看处理提示后重试。");
      return null;
    } finally {
      unlisten(); // 无论成功、失败、取消或代际失效都释放原生事件监听器。
      if (generation === generationRef.current) {
        requestIdRef.current = "";
        setBusy(false);
      }
    }
  }, []);

  const cancel = useCallback(async () => {
    const requestId = requestIdRef.current;
    if (!requestId) return;
    cancelledRef.current = true; // 先记录用户意图，子进程终止导致的异常随后显示为“已取消”。
    await cancelBridgeRequest(requestId);
  }, []);

  const reset = useCallback(() => {
    generationRef.current += 1; // 立即让所有在途 Promise 失去更新当前状态的资格。
    const requestId = requestIdRef.current;
    requestIdRef.current = "";
    if (requestId) void cancelBridgeRequest(requestId);  // 重置时取消在途任务，防止其回调污染新状态
    setBusy(false);
    setError("");
    setLogs([]);
    setProgress(null);
    setOutDir("");
    setResult(null);
    setPresentation(null);
  }, []);

  return { busy, error, logs, progress, outDir, result, presentation, run, reset, cancel };
}

/**
 * 管理无需日志、进度和取消能力的轻量桥接查询或设置动作。
 *
 * 仍使用代际编号处理快速重复点击和页面重置竞态，但不订阅事件，也不执行完成通知与
 * 自动打开输出目录，避免为普通查询引入额外原生开销。
 */
export function useBridgeAction<T>(): BridgeActionState<T> {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<T | null>(null);
  const generationRef = useRef(0);

  const run = useCallback(async (action: string, payload: BridgePayload = {}) => {
    const generation = ++generationRef.current;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await bridgeRequest<T>(action, payload);
      if (generation !== generationRef.current) return null; // 后发请求或重置优先，旧响应不得回写。
      setResult(response);
      return response;
    } catch (reason) {
      if (generation !== generationRef.current) return null;
      setError(reason instanceof Error ? reason.message : String(reason));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const reset = useCallback(() => {
    generationRef.current += 1; // 轻量动作无法终止底层查询，但可以阻止其结果污染已重置界面。
    setError("");
    setResult(null);
  }, []);

  return { busy, error, result, run, reset };
}
