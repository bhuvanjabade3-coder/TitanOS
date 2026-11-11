/** Client for TITAN Core. In production the launcher passes the API token in
 *  the URL fragment (never sent over HTTP); in development the Vite proxy adds
 *  it server-side and the browser holds no token at all. */

function readToken(): string | null {
  const m = location.hash.match(/token=([\w-]+)/);
  if (m) {
    sessionStorage.setItem("titan-token", m[1]);
    history.replaceState(null, "", location.pathname + location.search);
  }
  return sessionStorage.getItem("titan-token");
}
const TOKEN = typeof window === "undefined" ? null : readToken();

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (TOKEN) headers.set("Authorization", `Bearer ${TOKEN}`);
  if (init.body) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "TITAN Core is not reachable");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const post = <T,>(path: string, body?: unknown) =>
  req<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}${TOKEN ? `?token=${TOKEN}` : ""}`;
}

export function rawUrl(path: string): string {
  return `/api/files/raw?path=${encodeURIComponent(path)}${TOKEN ? `&token=${TOKEN}` : ""}`;
}

export type Outcome<T> =
  | { status: "ok"; result: T }
  | { status: "approval_required"; approval_id: number; risk: string; reasons: string[]; summary: string }
  | { status: "error" | "denied"; error: string };

/** Perform an action as the user and return whatever really happened. */
export const act = <T = unknown,>(name: string, params: Record<string, unknown> = {}) =>
  post<Outcome<T>>(`/api/actions/${name}`, { params });

export class NeedsApproval extends Error {
  constructor(public approvalId: number, summary: string) {
    super(`Waiting for your approval: ${summary}`);
  }
}

/** Like `act`, but returns the result directly and throws otherwise. An action
 *  that needs approval throws NeedsApproval; the shell shows the dialog. */
export async function run<T = unknown>(name: string, params: Record<string, unknown> = {}): Promise<T> {
  const out = await act<T>(name, params);
  if (out.status === "ok") return out.result;
  if (out.status === "approval_required") throw new NeedsApproval(out.approval_id, out.summary);
  throw new Error(out.error);
}

// --- shared types -----------------------------------------------------------
export interface Metrics {
  ts: number;
  cpu: { percent: number; per_core: number[]; cores: number; load_avg: number[] };
  memory: { total: number; used: number; percent: number };
  disk: { total: number; used: number; percent: number };
  network: { bytes_sent: number; bytes_recv: number };
  battery: { percent: number; plugged: boolean | null; seconds_left: number | null } | null;
  temperatures: Record<string, number> | null;
}
export interface Status {
  version: string;
  ai_configured: boolean;
  system: { hostname: string; os: string; kernel: string; arch: string; python: string; boot_time: number };
}
export interface Proc { pid: number; name: string; user: string | null; cpu_percent: number; rss: number; status: string }
export interface Approval {
  id: number; created_at: string; actor: string; action: string; params: Record<string, unknown>;
  summary: string; risk: "low" | "medium" | "high"; reasons: string[]; status: string;
  result: Outcome<unknown> | null;
}
export interface Notification { id: number; ts: string; category: string; title: string; body: string; level: string; read: number }
export interface Task {
  id: string; name: string; status: string; progress: number; message: string;
  result: unknown; error: string | null; created_at: string; finished_at: string | null;
}
export interface Entry { name: string; path: string; is_dir: boolean; size: number; mtime: number; mime: string | null }
export interface AppInfo { id: string; name: string; comment: string; icon: string; category: string }
export interface Step { action: string; input?: Record<string, unknown>; status: string; detail?: string; approval_id?: number }
