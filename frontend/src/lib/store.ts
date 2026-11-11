import { useSyncExternalStore } from "react";
import { act, post, req, wsUrl, type Approval, type Notification, type Task } from "./api";

export interface Win {
  id: number; app: string; title: string; x: number; y: number; w: number; h: number;
  z: number; minimized: boolean; maximized: boolean; workspace: number; props?: Record<string, unknown>;
}
export type Link = "connecting" | "live" | "offline";
export interface Toast { id: number; title: string; body: string; level: string }

interface State {
  link: Link;
  wins: Win[]; z: number; workspace: number; focused: number | null;
  launcher: boolean; panel: boolean;
  approvals: Approval[]; notifications: Notification[]; tasks: Task[];
  prefs: Record<string, unknown>; prefsLoaded: boolean; toasts: Toast[];
}

let state: State = {
  link: "connecting", wins: [], z: 1, workspace: 0, focused: null, launcher: false, panel: false,
  approvals: [], notifications: [], tasks: [], prefs: {}, prefsLoaded: false, toasts: [],
};
const listeners = new Set<() => void>();
export const get = () => state;
export function set(patch: Partial<State> | ((s: State) => Partial<State>)) {
  state = { ...state, ...(typeof patch === "function" ? patch(state) : patch) };
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => (listeners.add(l), () => listeners.delete(l));
export function useStore<T>(selector: (s: State) => T): T {
  return useSyncExternalStore(subscribe, () => selector(state));
}
export const pref = <T,>(key: string, fallback: T): T => (state.prefs[key] as T) ?? fallback;
export const usePref = <T,>(key: string, fallback: T): T => useStore((s) => (s.prefs[key] as T) ?? fallback);

export async function setPref(key: string, value: unknown) {
  set((s) => { const prefs = { ...s.prefs, [key]: value }; if (value === null) delete prefs[key]; return { prefs }; }); // optimistic
  try {
    if (value === null) await req(`/api/preferences/${key}`, { method: "DELETE" }).catch((e) => { if (e.status !== 404) throw e; });
    else await req(`/api/preferences/${key}`, { method: "PUT", body: JSON.stringify({ value }) });
  } catch (e) {
    toast("Could not save setting", String((e as Error).message), "warning");
    loadPrefs();
  }
}

let toastId = 1;
export function toast(title: string, body = "", level = "info") {
  const id = toastId++;
  set((s) => ({ toasts: [...s.toasts, { id, title, body, level }].slice(-4) }));
  setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 6000);
}

// --- windows ------------------------------------------------------------------
let winId = 1;
export const SIZES: Record<string, [number, number]> = {};
export function openApp(app: string, title: string, props?: Record<string, unknown>) {
  const existing = state.wins.find((w) => w.app === app && !props);
  if (existing) return focusWin(existing.id);
  const [w, h] = SIZES[app] ?? [860, 560];
  const n = state.wins.length;
  const vw = window.innerWidth, vh = window.innerHeight;
  const win: Win = {
    id: winId++, app, title, w: Math.min(w, vw - 40), h: Math.min(h, vh - 150),
    x: Math.max(20, Math.min(vw - w - 20, 90 + (n % 6) * 34)), y: 56 + (n % 6) * 28,
    z: state.z + 1, minimized: false, maximized: false, workspace: state.workspace, props,
  };
  set((s) => ({ wins: [...s.wins, win], z: s.z + 1, focused: win.id, launcher: false }));
}
export function focusWin(id: number) {
  set((s) => {
    const w = s.wins.find((x) => x.id === id);
    if (!w) return {};
    return {
      wins: s.wins.map((x) => (x.id === id ? { ...x, z: s.z + 1, minimized: false } : x)),
      z: s.z + 1, focused: id, workspace: w.workspace, launcher: false,
    };
  });
}
export const patchWin = (id: number, p: Partial<Win>) =>
  set((s) => ({ wins: s.wins.map((x) => (x.id === id ? { ...x, ...p } : x)) }));
function refocus(s: State, wins: Win[], workspace = s.workspace): number | null {
  const top = wins.filter((w) => w.workspace === workspace && !w.minimized).sort((a, b) => b.z - a.z)[0];
  return top?.id ?? null;
}
export const closeWin = (id: number) =>
  set((s) => { const wins = s.wins.filter((x) => x.id !== id); return { wins, focused: refocus(s, wins) }; });
export const minimizeWin = (id: number) =>
  set((s) => { const wins = s.wins.map((x) => (x.id === id ? { ...x, minimized: true } : x)); return { wins, focused: refocus(s, wins) }; });
export const toggleMax = (id: number) =>
  set((s) => ({ wins: s.wins.map((x) => (x.id === id ? { ...x, maximized: !x.maximized } : x)) }));
export const setWorkspace = (n: number) => set((s) => ({ workspace: n, focused: refocus(s, s.wins, n) }));
export function cycleWindows() {
  const here = state.wins.filter((w) => w.workspace === state.workspace).sort((a, b) => a.z - b.z);
  if (here.length) focusWin(here[0].id);
}

// --- server data ----------------------------------------------------------------
export const loadPrefs = () => req<Record<string, unknown>>("/api/preferences").then((prefs) => set({ prefs, prefsLoaded: true })).catch(() => {});
export const loadApprovals = () => req<Approval[]>("/api/approvals").then((approvals) => set({ approvals })).catch(() => {});
export const loadNotifications = () => req<Notification[]>("/api/notifications").then((notifications) => set({ notifications })).catch(() => {});
export const loadTasks = () => req<Task[]>("/api/tasks").then((tasks) => set({ tasks })).catch(() => {});

export async function decide(id: number, approve: boolean) {
  try {
    const r = await post<{ approval: Approval; outcome: { status: string; error?: string } }>(
      `/api/approvals/${id}/${approve ? "approve" : "deny"}`);
    if (approve && r.outcome.status !== "ok") toast("Action failed", r.outcome.error ?? r.outcome.status, "warning");
    lastDecided.set(id, r.approval);
    decidedListeners.forEach((l) => l(r.approval));
  } catch (e) {
    toast("Could not record decision", (e as Error).message, "warning");
  }
  loadApprovals();
}
/** Apps that submitted an action needing approval can learn its real outcome. */
const lastDecided = new Map<number, Approval>();
const decidedListeners = new Set<(a: Approval) => void>();
export const onDecided = (l: (a: Approval) => void) => (decidedListeners.add(l), () => { decidedListeners.delete(l); });

export async function markAllRead() {
  await act("notify.read");
  loadNotifications();
}

type Handler = (data: any) => void;
const eventHandlers = new Map<string, Set<Handler>>();
/** Subscribe to a server event type (e.g. "ai.step", "terminal.output"). */
export function onEvent(type: string, h: Handler) {
  if (!eventHandlers.has(type)) eventHandlers.set(type, new Set());
  eventHandlers.get(type)!.add(h);
  return () => { eventHandlers.get(type)!.delete(h); };
}

export function connectEvents(): () => void {
  let ws: WebSocket | null = null, timer: ReturnType<typeof setTimeout> | undefined, closed = false, attempt = 0;
  const connect = () => {
    ws = new WebSocket(wsUrl("/ws/events"));
    ws.onmessage = (m) => {
      const e = JSON.parse(m.data) as { type: string; data: any };
      if (e.type === "hello") {
        attempt = 0;
        set({ link: "live" });
        loadPrefs(); loadApprovals(); loadNotifications(); loadTasks();
      } else if (e.type === "approval") {
        loadApprovals();
        if (e.data.status !== "pending") decidedListeners.forEach((l) => l(e.data));
      } else if (e.type === "notification") {
        set((s) => ({ notifications: [e.data, ...s.notifications].slice(0, 100) }));
        toast(e.data.title, e.data.body, e.data.level);
      } else if (e.type === "task") {
        set((s) => ({ tasks: [e.data, ...s.tasks.filter((t) => t.id !== e.data.id)].slice(0, 50) }));
      } else if (e.type === "preference") {
        loadPrefs();
      }
      eventHandlers.get(e.type)?.forEach((h) => h(e.data));
    };
    ws.onclose = () => {
      if (closed) return;
      set({ link: "offline" });
      timer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10000));
    };
  };
  connect();
  return () => { closed = true; clearTimeout(timer); ws?.close(); };
}
