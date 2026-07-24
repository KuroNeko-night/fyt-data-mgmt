import { confirm, open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { isTauriRuntime } from "./bridge";

export interface FileFilter {
  name: string;
  extensions: string[];
}

export async function chooseFiles(options: {
  title: string;
  multiple?: boolean;
  directory?: boolean;
  filters?: FileFilter[];
}): Promise<string[]> {
  if (!isTauriRuntime()) {
    throw new Error("文件选择仅在 Tauri 桌面窗口中可用。");
  }
  const selected = await open({
    title: options.title,
    multiple: options.multiple ?? false,
    directory: options.directory ?? false,
    filters: options.filters,
  });
  if (!selected) return [];
  return Array.isArray(selected) ? selected : [selected];
}

export async function openLocalPath(path: string): Promise<void> {
  if (!path) return;
  if (!isTauriRuntime()) {
    throw new Error("打开本地路径仅在 Tauri 桌面窗口中可用。");
  }
  await invoke("open_local_path", { path });
}

export async function confirmAction(message: string): Promise<boolean> {
  if (!isTauriRuntime()) return window.confirm(message);
  return confirm(message, { title: "峰运通数据管理系统", kind: "warning" });
}

export function fileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) || path;
}
