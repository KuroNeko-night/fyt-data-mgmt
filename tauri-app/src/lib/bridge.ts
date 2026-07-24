import { invoke } from "@tauri-apps/api/core";

export type BridgePayload = Record<string, unknown>;

export interface HealthInfo {
  app_name: string;
  version: string;
  python: string;
  platform: string;
  project_root: string;
  features: string[];
}

export interface AppSettings {
  output_mode: "unified" | "beside" | "custom";
  custom_output_root: string;
  theme_mode: "auto" | "light" | "dark";
  reduce_motion: boolean;
  check_update_on_start: boolean;
  auto_open_output: boolean;
  show_done_dialog: boolean;
  minimize_to_tray: boolean;
  enable_incremental_cache: boolean;
}

export interface TaskItem {
  id: string;
  feature: string;
  title: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  message: string;
  output_dir: string;
}

export interface TaskResult {
  summary: Record<string, number>;
  items: TaskItem[];
}

export interface LibrarySummary {
  counts: Record<string, number>;
  storage: Record<string, number>;
  titles: Record<string, string>;
  items: LibraryItem[];
  library_dir: string;
}

export interface LibraryItem {
  name: string;
  category: string;
  categories?: string[];
  path: string;
  updated: string;
  size: number;
  confidence: number;
  signals?: string[];
}

let previewSettings: AppSettings = {
  output_mode: "unified",
  custom_output_root: "",
  theme_mode: "light",
  reduce_motion: false,
  check_update_on_start: false,
  auto_open_output: true,
  show_done_dialog: true,
  minimize_to_tray: true,
  enable_incremental_cache: true,
};

export function isTauriRuntime(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

async function previewResponse<T>(action: string, payload: BridgePayload): Promise<T> {
  if (action === "settings.update") {
    const values = payload.values;
    if (values && typeof values === "object") previewSettings = { ...previewSettings, ...values };
    return previewSettings as T;
  }
  const responses: Record<string, unknown> = {
    "system.health": {
      app_name: "峰运通数据管理系统",
      version: "1.3.0",
      python: "浏览器预览",
      platform: "web-preview",
      project_root: "仅 Tauri 桌面运行时连接 Python 核心",
      features: ["settings", "tasks", "library", "currency"],
    },
    "settings.get": previewSettings,
    "system.paths": {
      app_data_dir: "文档/峰运通数据管理系统",
      library_dir: "文档/峰运通数据管理系统/数据库",
      default_output_root: "文档/峰运通数据管理系统/输出",
      crash_log: "文档/峰运通数据管理系统/crash.log",
      crash_log_exists: false,
    },
    "cache.stats": { entries: 6, hits: 18, bytes: 4096 },
    "tasks.list": {
      summary: { total: 3, running: 0, ok: 2, failed: 1, interrupted: 0 },
      items: [
        { id: "preview-1", feature: "pivot", title: "销售表透视", status: "ok",
          started_at: "2026-07-22T12:08:00", finished_at: "2026-07-22T12:08:18",
          duration_ms: 18420, message: "分组 126 项", output_dir: "文档/峰运通数据管理系统/输出/销售表透视" },
        { id: "preview-2", feature: "attendance", title: "考勤数据填报", status: "ok",
          started_at: "2026-07-22T11:42:00", finished_at: "2026-07-22T11:42:07",
          duration_ms: 7310, message: "已处理 4 个文件", output_dir: "文档/峰运通数据管理系统/输出/考勤数据填报" },
      ],
    },
    "library.summary": {
      counts: { att_source: 8, rec_source: 5, pivot_src: 12, deliv_bom: 4, unknown: 2 },
      storage: { files: 31, bytes: 186646528 },
      titles: { att_source: "考勤来源", rec_source: "对账来源", pivot_src: "透视数据源", deliv_bom: "物料清单" },
      items: [],
      library_dir: "文档/峰运通数据管理系统/数据库",
    },
  };
  if (!(action in responses)) {
    throw new Error("浏览器预览不连接 Python 核心，请在 Tauri 桌面窗口中运行此操作。");
  }
  return responses[action] as T;
}

export async function bridgeRequest<T>(action: string, payload: BridgePayload = {}, requestId = ""): Promise<T> {
  if (!isTauriRuntime()) {
    return previewResponse<T>(action, payload);
  }
  return invoke<T>("bridge_request", { request: { action, payload, requestId } });
}

export async function cancelBridgeRequest(requestId: string): Promise<boolean> {
  if (!requestId || !isTauriRuntime()) return false;
  return invoke<boolean>("cancel_bridge_request", { requestId });
}

export async function installUpdate(path: string): Promise<void> {
  if (!isTauriRuntime()) throw new Error("安装更新仅在 Tauri 桌面窗口中可用。");
  await invoke("install_update", { path });
}

export async function syncRuntimeSettings(settings: AppSettings): Promise<void> {
  if (!isTauriRuntime()) return;
  await invoke("set_minimize_to_tray", { enabled: settings.minimize_to_tray });
}
