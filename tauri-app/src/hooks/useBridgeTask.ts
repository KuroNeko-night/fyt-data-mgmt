import { useCallback, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { message } from "@tauri-apps/plugin-dialog";
import { bridgeRequest, cancelBridgeRequest, isTauriRuntime, type AppSettings, type BridgePayload } from "../lib/bridge";
import { openLocalPath } from "../lib/files";

export interface TaskEnvelope<T> {
  result: T;
  logs: string[];
  task_id: string;
  out_dir: string;
}

export interface BridgeTaskState<T> {
  busy: boolean;
  error: string;
  logs: string[];
  progress: number | null;
  outDir: string;
  result: T | null;
  run: (action: string, payload?: BridgePayload) => Promise<T | null>;
  reset: () => void;
  cancel: () => Promise<void>;
}

export interface BridgeActionState<T> {
  busy: boolean;
  error: string;
  result: T | null;
  run: (action: string, payload?: BridgePayload) => Promise<T | null>;
  reset: () => void;
}

export function useBridgeTask<T>(): BridgeTaskState<T> {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [outDir, setOutDir] = useState("");
  const [result, setResult] = useState<T | null>(null);
  const requestIdRef = useRef("");
  const cancelledRef = useRef(false);
  const generationRef = useRef(0);

  const run = useCallback(async (action: string, payload: BridgePayload = {}) => {
    const generation = ++generationRef.current;
    setBusy(true);
    setError("");
    setLogs([]);
    setProgress(0);
    setOutDir("");
    setResult(null);
    cancelledRef.current = false;
    const requestId = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    requestIdRef.current = requestId;
    let unlisten: () => void = () => undefined;
    if (isTauriRuntime()) {
      try {
        unlisten = await listen<{ request_id: string; kind: string; value: unknown }>("bridge-task-event", (event) => {
          if (event.payload.request_id !== requestId) return;
          if (event.payload.kind === "log") setLogs((current) => [...current, String(event.payload.value)]);
          if (event.payload.kind === "progress") setProgress(Number(event.payload.value));
        });
      } catch {
        unlisten = () => undefined;
      }
    }
    try {
      const response = await bridgeRequest<TaskEnvelope<T>>(action, payload, requestId);
      if (generation !== generationRef.current) return null;
      setLogs(response.logs || []);
      setProgress(100);
      setOutDir(response.out_dir || "");
      setResult(response.result);
      if (isTauriRuntime()) {
        try {
          const settings = await bridgeRequest<AppSettings>("settings.get");
          if (settings.auto_open_output && response.out_dir) await openLocalPath(response.out_dir);
          if (settings.show_done_dialog) await message("业务处理已完成。", {
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
      return null;
    } finally {
      unlisten();
      if (generation === generationRef.current) {
        requestIdRef.current = "";
        setBusy(false);
      }
    }
  }, []);

  const cancel = useCallback(async () => {
    const requestId = requestIdRef.current;
    if (!requestId) return;
    cancelledRef.current = true;
    await cancelBridgeRequest(requestId);
  }, []);

  const reset = useCallback(() => {
    generationRef.current += 1;
    const requestId = requestIdRef.current;
    requestIdRef.current = "";
    if (requestId) void cancelBridgeRequest(requestId);
    setBusy(false);
    setError("");
    setLogs([]);
    setProgress(null);
    setOutDir("");
    setResult(null);
  }, []);

  return { busy, error, logs, progress, outDir, result, run, reset, cancel };
}

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
      if (generation !== generationRef.current) return null;
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
    generationRef.current += 1;
    setError("");
    setResult(null);
  }, []);

  return { busy, error, result, run, reset };
}
