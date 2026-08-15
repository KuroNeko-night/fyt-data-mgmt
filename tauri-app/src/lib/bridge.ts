/**
 * Tauri 前端与 Python Core 桥接的唯一调用入口。
 *
 * 桌面运行时通过 Rust 命令启动受控 sidecar；普通浏览器开发预览则只返回本文件定义的
 * 无副作用演示数据。业务页面不应直接调用 `invoke`，否则会绕过预览兼容、请求编号和
 * 桥接协议的统一类型边界。
 */
import { invoke } from "@tauri-apps/api/core";

/** 桥接请求的 JSON 安全载荷，具体键值由 Python Core 白名单动作定义。 */
export type BridgePayload = Record<string, unknown>;

/** Core 健康检查返回的运行时、版本与已启用能力信息。 */
export interface HealthInfo {
  app_name: string;
  version: string;
  python: string;
  platform: string;
  project_root: string;
  features: string[];
}

/**
 * 客户端设置快照。
 *
 * 读取与保存都通过 `settings.get` / `settings.update` 桥接动作进入 Python Core；
 * 其中 `minimize_to_tray` 额外由 Rust 运行时内存状态消费。
 */
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

/** 任务中心单条历史记录，字段与 Python 任务历史保持稳定对应。 */
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

/** 任务中心列表响应：汇总计数与最近任务条目。 */
export interface TaskResult {
  summary: Record<string, number>;
  items: TaskItem[];
}

/** 数据库摘要：分类计数、占用空间、标题映射、最近条目与库目录。 */
export interface LibrarySummary {
  counts: Record<string, number>;
  storage: Record<string, number>;
  titles: Record<string, string>;
  items: LibraryItem[];
  library_dir: string;
}

/** 数据库单条文件记录，含分类、可信度与识别信号。 */
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

// 浏览器预览专用的设置快照，只存在于当前页面会话，刷新后恢复默认值。
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

/** 判断当前页面是否运行在 Tauri 注入了内部对象的桌面 WebView 中。 */
export function isTauriRuntime(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

/**
 * 为纯浏览器预览提供有限、可预测的桥接响应。
 *
 * 预览只模拟设置、健康信息、任务和文件库摘要，不执行本地文件操作。未登记动作直接给出
 * 面向用户的桌面端提示，避免开发预览看似成功却没有产生真实业务结果。
 */
async function previewResponse<T>(action: string, payload: BridgePayload): Promise<T> {
  if (action === "settings.update") {
    const values = payload.values;
    if (values && typeof values === "object") previewSettings = { ...previewSettings, ...values }; // 保留未提交字段，模拟 Core 的局部设置更新。
    return previewSettings as T;
  }
  // 演示数据固定在模块级，页面刷新后自然重置，不写入浏览器持久存储或污染真实配置。
  const responses: Record<string, unknown> = {
    "system.health": {
      app_name: "峰运通数据管理系统",
      version: "1.3.0",
      python: "运行环境",
      platform: "web-preview",
      project_root: "当前工作目录",
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
    throw new Error("当前功能需要在桌面端运行，请从桌面端重新打开。");
  }
  return responses[action] as T;
}

/**
 * 调用一个桥接动作，并在浏览器预览与 Tauri 桌面运行时之间选择正确实现。
 *
 * `requestId` 只对长任务必需，Rust 会用它登记子进程并转发日志和进度事件。普通查询可
 * 留空，仍通过同一 `bridge_request` 白名单进入 Python Core。
 */
export async function bridgeRequest<T>(action: string, payload: BridgePayload = {}, requestId = ""): Promise<T> {
  if (!isTauriRuntime()) {
    return previewResponse<T>(action, payload);
  }
  return invoke<T>("bridge_request", { request: { action, payload, requestId } });
}

/**
 * 请求 Rust 精确终止指定桥接任务；预览环境或空编号直接返回未取消。
 *
 * 这里只表达“已向系统请求取消”，最终任务状态仍由 Python 任务历史与调用 Hook 的异常
 * 分支统一解释。
 */
export async function cancelBridgeRequest(requestId: string): Promise<boolean> {
  if (!requestId || !isTauriRuntime()) return false;
  return invoke<boolean>("cancel_bridge_request", { requestId });
}

/** 通过受控桥接安装已下载更新；浏览器预览禁止触发本机安装。 */
export async function installUpdate(path: string): Promise<void> {
  if (!isTauriRuntime()) throw new Error("安装更新需要桌面版，请在桌面端继续。");
  await invoke("install_update", { path });
}

/**
 * 把影响原生窗口行为的设置同步到 Rust 运行时。
 *
 * 普通界面设置仍由 Python 配置保存，这里只同步“关闭时最小化到托盘”这一项内存状态；
 * 浏览器预览没有原生窗口，因此保持无操作。
 */
export async function syncRuntimeSettings(settings: AppSettings): Promise<void> {
  if (!isTauriRuntime()) return;
  await invoke("set_minimize_to_tray", { enabled: settings.minimize_to_tray });
}
