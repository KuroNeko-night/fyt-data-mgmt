/** Tauri 文件选择、受控本地路径打开、危险操作确认和文件名展示辅助函数。 */
import { confirm, open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { isTauriRuntime } from "./bridge";

/** 原生文件选择器的扩展名筛选器，`name` 为客户可读分类名。 */
export interface FileFilter {
  name: string;
  extensions: string[];
}

/**
 * 调用原生文件选择器，并把单选、多选和取消统一归一为路径数组。
 *
 * 浏览器预览不能伪造本机绝对路径，因此直接提示需要桌面版；筛选器只改善选择体验，
 * 业务 Core 仍会再次校验扩展名和文件内容。
 */
export async function chooseFiles(options: {
  title: string;
  multiple?: boolean;
  directory?: boolean;
  filters?: FileFilter[];
}): Promise<string[]> {
  if (!isTauriRuntime()) {
    throw new Error("当前窗口不支持选择本机文件，请在桌面版中继续。");
  }
  const selected = await open({
    title: options.title,
    multiple: options.multiple ?? false,
    directory: options.directory ?? false,
    filters: options.filters,
  });
  if (!selected) return [];
  // 单选返回字符串、多选返回数组，这里统一成数组，调用方只需处理一种形状。
  return Array.isArray(selected) ? selected : [selected];
}

/**
 * 通过自有 Rust 命令打开文件或目录，不向 WebView 授予通用 opener 路径权限。
 * Rust 侧会再次要求绝对路径存在，前端空值在此直接忽略。
 */
export async function openLocalPath(path: string): Promise<void> {
  if (!path) return;
  if (!isTauriRuntime()) {
    throw new Error("当前窗口不支持打开本机路径，请在桌面版中继续。");
  }
  await invoke("open_local_path", { path });
}

/** 桌面端使用原生警告对话框，浏览器预览回退到同步确认框。 */
export async function confirmAction(message: string): Promise<boolean> {
  if (!isTauriRuntime()) return window.confirm(message);
  return confirm(message, { title: "峰运通数据管理系统", kind: "warning" });
}

/** 同时兼容 Windows 与 Unix 分隔符，从完整路径提取客户可读文件名。 */
export function fileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) || path;
}
