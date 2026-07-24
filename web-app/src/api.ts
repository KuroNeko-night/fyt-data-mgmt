export type User = {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "user";
  status: "pending" | "approved" | "rejected";
  created_at: string;
  approved_at: string | null;
};

export type Feature = { key: string; title: string; group: string; description: string };
export type Overview = { user: User; features: Feature[]; metrics: { pending_users: number; approved_users: number; output_jobs: number } };
export type DashboardData = {
  user: User;
  generated_at: string;
  metrics: {
    pending_users: number;
    approved_users: number;
    total_jobs: number;
    completed_jobs: number;
    running_jobs: number;
    failed_jobs: number;
  };
  status_breakdown: Record<string, number>;
  trend: Array<{ date: string; total: number; completed: number; failed: number }>;
  feature_usage: Array<{ key: string; title: string; count: number }>;
  recent_jobs: Array<Pick<WebJob, "id" | "action" | "title" | "status" | "progress" | "error" | "created_at" | "updated_at" | "review_pending">>;
  recent_files: Array<{ name: string; size: number; url: string; job_id: string; title: string; created_at: string }>;
};
export type UploadedFile = { handle: string; group: string; name: string; size: number };
export type JobFile = { name: string; size: number; url: string };
export type WebJob = {
  id: string;
  action: string;
  title: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  progress: number;
  logs: string[];
  result: unknown;
  error: string | null;
  files: JobFile[];
  review_pending?: boolean;
  created_at: string;
  updated_at: string;
};

const API_BASE = import.meta.env.VITE_API_BASE || "";
const tokenKey = "fyt_web_session";

export function getToken() { return localStorage.getItem(tokenKey) || ""; }
export function setToken(token: string) { localStorage.setItem(tokenKey, token); }
export function clearToken() { localStorage.removeItem(tokenKey); }

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && typeof options.body === "string") headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data as T;
}

export function login(username: string, password: string) { return request<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }); }
export function register(username: string, display_name: string, password: string) { return request<{ message: string }>("/api/auth/register", { method: "POST", body: JSON.stringify({ username, display_name, password }) }); }
export function me() { return request<{ user: User }>("/api/auth/me"); }
export function overview() { return request<Overview>("/api/overview"); }
export function dashboard() { return request<DashboardData>("/api/dashboard"); }
export function users() { return request<{ users: User[] }>("/api/admin/users"); }
export function reviewUser(id: number, decision: "approve" | "reject") { return request<{ message: string }>(`/api/admin/users/${id}/${decision === "approve" ? "approve" : "reject"}`, { method: "POST", body: "{}" }); }
export function logout() { return request<{ message: string }>("/api/auth/logout", { method: "POST", body: "{}" }); }

export async function uploadFile(file: File, group: string): Promise<UploadedFile> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const query = new URLSearchParams({ name: file.name, group });
  const response = await fetch(`${API_BASE}/api/files/upload?${query}`, { method: "POST", headers, body: file });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `上传 ${file.name} 失败`);
  return data as UploadedFile;
}

export function createJob(action: string, title: string, payload: Record<string, unknown>) {
  return request<{ job_id: string }>("/api/jobs", { method: "POST", body: JSON.stringify({ action, title, payload }) });
}

export function getJob(id: string) { return request<{ job: WebJob }>(`/api/jobs/${id}`); }
export function listJobs() { return request<{ jobs: WebJob[] }>("/api/jobs"); }
export function cancelJob(id: string) { return request<{ message: string }>(`/api/jobs/${id}/cancel`, { method: "POST", body: "{}" }); }
export function submitJobReview(id: string, choices: Record<string, unknown>) { return request<{ job_id: string }>(`/api/jobs/${id}/review`, { method: "POST", body: JSON.stringify({ choices }) }); }

export async function downloadJobFile(file: JobFile): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("X-Session-Token", token);
  const response = await fetch(`${API_BASE}${file.url}`, { headers });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
