import { AnimatePresence, motion } from "framer-motion";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Chip, Empty, Icon, Note } from "../components/ui";
import { act, rawUrl, type AppInfo, type Approval } from "../lib/api";
import { formatWhen } from "../lib/format";
import { useAction, useClock } from "../lib/hooks";
import {
  closeWin, connectEvents, cycleWindows, decide, focusWin, get, markAllRead, minimizeWin, openApp, set,
  setPref, setWorkspace, toast, usePref, useStore,
} from "../lib/store";
import { APP, APPS, DEFAULT_DOCK } from "./apps";
import { Window } from "./Window";

export const DEFAULT_SHORTCUTS: Record<string, string> = {
  launcher: "ctrl+k", assistant: "ctrl+j", close: "alt+w", minimize: "alt+m", cycle: "alt+`",
  workspace1: "alt+1", workspace2: "alt+2", workspace3: "alt+3", workspace4: "alt+4",
};
const WORKSPACES = 4;

function combo(e: KeyboardEvent): string {
  const parts = [];
  if (e.ctrlKey) parts.push("ctrl");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  if (e.metaKey) parts.push("super");
  parts.push(e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase());
  return parts.join("+");
}

const open = (id: string, props?: Record<string, unknown>) => openApp(id, APP[id].title, props);

async function launchSystem(app: AppInfo) {
  const out = await act<{ launched: string }>("apps.launch", { app: app.id });
  if (out.status === "ok") toast(`Opening ${out.result.launched}`);
  else if (out.status !== "approval_required") toast(`Could not open ${app.name}`, out.error, "warning");
  set({ launcher: false });
}

// --------------------------------------------------------------------- top bar
function TopBar() {
  const now = useClock();
  const link = useStore((s) => s.link);
  const workspace = useStore((s) => s.workspace);
  const wins = useStore((s) => s.wins);
  const unread = useStore((s) => s.notifications.filter((n) => !n.read).length);
  const running = useStore((s) => s.tasks.filter((t) => t.status === "running" || t.status === "queued").length);
  const pending = useStore((s) => s.approvals.length);
  const dot = link === "live" ? "bg-ok" : link === "connecting" ? "bg-warn" : "bg-danger";
  return (
    <header className="glass absolute left-2 right-2 top-2 z-[9000] flex h-9 items-center gap-3 !rounded-xl px-3 text-[13px]">
      <button className="flex items-center gap-2" onClick={() => set((s) => ({ launcher: !s.launcher }))} aria-label="Open launcher">
        <span className="h-4 w-4 rounded-[5px] bg-gradient-to-br from-accent to-azure" />
        <span className="font-semibold tracking-[0.28em]">TITAN</span>
      </button>
      <nav className="ml-2 flex gap-1" aria-label="Workspaces">
        {Array.from({ length: WORKSPACES }, (_, i) => {
          const count = wins.filter((w) => w.workspace === i).length;
          return (
            <button key={i} onClick={() => setWorkspace(i)} aria-label={`Workspace ${i + 1}`} aria-current={workspace === i}
              className={`tabular flex h-6 min-w-6 items-center justify-center gap-1 rounded-md px-1.5 text-xs transition-colors ${workspace === i ? "bg-accent/25 text-text" : "text-muted hover:bg-line"}`}>
              {i + 1}{count > 0 && <span className="h-1 w-1 rounded-full bg-current" />}
            </button>
          );
        })}
      </nav>
      <div className="flex-1" />
      {link !== "live" && <span className="text-warn">{link === "connecting" ? "Connecting to TITAN Core…" : "TITAN Core offline — retrying"}</span>}
      {pending > 0 && <span className="text-warn">{pending} awaiting approval</span>}
      {running > 0 && <button className="text-azure" onClick={() => open("tasks")}>{running} task{running > 1 ? "s" : ""} running</button>}
      <span className={`h-2 w-2 rounded-full ${dot}`} role="status" aria-label={`Core ${link}`} />
      <button className="relative" aria-label={`Notifications, ${unread} unread`} onClick={() => set((s) => ({ panel: !s.panel }))}>
        <Icon name="bell" size={16} />
        {unread > 0 && <span className="tabular absolute -right-1.5 -top-1.5 rounded-full bg-accent px-1 text-[9px] font-semibold text-white">{unread}</span>}
      </button>
      <time className="tabular text-muted">
        {now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}{" "}
        <span className="text-text">{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
      </time>
    </header>
  );
}

// ------------------------------------------------------------------------ dock
function Dock() {
  const pinned = usePref<string[]>("dock.titan", DEFAULT_DOCK);
  const size = usePref<number>("dock.size", 44);
  const wins = useStore((s) => s.wins);
  const focused = useStore((s) => s.focused);
  const sys = useAction<{ apps: AppInfo[]; pinned: string[] }>("apps.list");
  const sysPinned = (sys.data?.pinned ?? []).map((id) => sys.data!.apps.find((a) => a.id === id)).filter(Boolean) as AppInfo[];
  const ids = [...pinned.filter((id) => APP[id]), ...wins.map((w) => w.app).filter((a, i, all) => !pinned.includes(a) && all.indexOf(a) === i)];

  const click = (id: string) => {
    const mine = wins.filter((w) => w.app === id);
    if (!mine.length) return open(id);
    const top = [...mine].sort((a, b) => b.z - a.z)[0];
    if (top.id === focused && !top.minimized) minimizeWin(top.id);
    else focusWin(top.id);
  };
  return (
    <nav aria-label="Dock" className="glass absolute bottom-3 left-1/2 z-[9000] flex -translate-x-1/2 items-end gap-1.5 !rounded-2xl p-2">
      <DockButton label="Applications" size={size} onClick={() => set((s) => ({ launcher: !s.launcher }))}><Icon name="grid" size={size * 0.45} /></DockButton>
      <span className="mx-0.5 h-8 w-px self-center bg-line" />
      {ids.map((id) => (
        <DockButton key={id} label={APP[id].title} size={size} onClick={() => click(id)} running={wins.some((w) => w.app === id)}
          active={wins.some((w) => w.app === id && w.id === focused)}>
          <Icon name={APP[id].icon} size={size * 0.45} />
        </DockButton>
      ))}
      {sysPinned.length > 0 && <span className="mx-0.5 h-8 w-px self-center bg-line" />}
      {sysPinned.map((a) => (
        <DockButton key={a.id} label={a.name} size={size} onClick={() => launchSystem(a)}>
          <span className="text-sm font-semibold">{a.name.slice(0, 2)}</span>
        </DockButton>
      ))}
    </nav>
  );
}

function DockButton({ label, size, onClick, running, active, children }:
  { label: string; size: number; onClick: () => void; running?: boolean; active?: boolean; children: React.ReactNode }) {
  return (
    <motion.button whileHover={{ y: -4, scale: 1.08 }} whileTap={{ scale: 0.95 }} transition={{ type: "spring", stiffness: 400, damping: 22 }}
      onClick={onClick} aria-label={label} title={label} style={{ width: size, height: size }}
      className={`relative flex items-center justify-center rounded-xl border border-line ${active ? "bg-accent/25" : "bg-[var(--field)]"}`}>
      {children}
      {running && <span className="absolute -bottom-1.5 h-1 w-1 rounded-full bg-accent" data-testid="running-dot" />}
    </motion.button>
  );
}

// -------------------------------------------------------------------- launcher
function Launcher() {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("All");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const sys = useAction<{ apps: AppInfo[]; pinned: string[]; recent: string[] }>("apps.list");
  useEffect(() => { input.current?.focus(); }, []);

  type Item = { key: string; name: string; sub: string; icon?: string; run: () => void; cat: string; sysId?: string };
  const items = useMemo<Item[]>(() => {
    const titan: Item[] = APPS.map((a) => ({ key: `t:${a.id}`, name: a.title, sub: a.blurb, icon: a.icon, cat: "TITAN", run: () => open(a.id) }));
    const system: Item[] = (sys.data?.apps ?? []).map((a) => ({ key: `s:${a.id}`, name: a.name, sub: a.comment || a.category, cat: a.category, sysId: a.id, run: () => launchSystem(a) }));
    return [...titan, ...system];
  }, [sys.data]);
  const cats = useMemo(() => ["All", "Recent", ...Array.from(new Set(items.map((i) => i.cat)))], [items]);
  const recent = sys.data?.recent ?? [];
  const needle = q.trim().toLowerCase();
  const rank = (i: Item) => { // name matches outrank description matches
    const n = i.name.toLowerCase();
    return n === needle ? 0 : n.startsWith(needle) ? 1 : n.includes(needle) ? 2 : i.sub.toLowerCase().includes(needle) ? 3 : -1;
  };
  const shown = needle
    ? items.filter((i) => rank(i) >= 0).sort((a, b) => rank(a) - rank(b))
    : items.filter((i) => (cat === "Recent" ? i.sysId !== undefined && recent.includes(i.sysId) : cat === "All" || i.cat === cat));
  useEffect(() => { setSel(0); }, [q, cat]);
  const pinnedSet = new Set(sys.data?.pinned ?? []);
  const togglePin = async (id: string) => { await act("apps.pin", { app: id, pinned: !pinnedSet.has(id) }); sys.reload(); toast(pinnedSet.has(id) ? "Unpinned from dock" : "Pinned to dock"); };

  return (
    <motion.div className="absolute inset-0 z-[9500] flex items-start justify-center bg-black/40 pt-[12vh] backdrop-blur-sm"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} onPointerDown={() => set({ launcher: false })}>
      <motion.div role="dialog" aria-label="Application launcher" className="glass flex max-h-[70vh] w-[680px] max-w-[92vw] flex-col p-3"
        initial={{ y: -12, scale: 0.98 }} animate={{ y: 0, scale: 1 }} onPointerDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-2 pb-3">
          <Icon name="search" className="text-muted" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search applications…" aria-label="Search applications"
            className="flex-1 bg-transparent text-base outline-none placeholder:text-muted"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(shown.length - 1, s + 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
              if (e.key === "Enter" && shown[sel]) shown[sel].run();
            }} />
        </div>
        {!q && (
          <div className="scroll flex gap-1 px-1 py-2">
            {cats.map((c) => <button key={c} onClick={() => setCat(c)} className={`btn !py-1 ${cat === c ? "!border-accent" : "btn-ghost"}`}>{c}</button>)}
          </div>
        )}
        <div className="scroll min-h-0 flex-1 p-1" role="listbox">
          {shown.map((i, n) => (
            <div key={i.key} role="option" aria-selected={n === sel} data-selected={n === sel} className="row flex cursor-pointer items-center gap-3 px-2 py-2" onClick={i.run} onMouseEnter={() => setSel(n)}>
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-[var(--field)]">
                {i.icon ? <Icon name={i.icon} size={16} /> : <span className="text-xs font-semibold">{i.name.slice(0, 2)}</span>}
              </span>
              <span className="min-w-0 flex-1"><span className="block truncate">{i.name}</span><span className="block truncate text-xs text-muted">{i.sub}</span></span>
              {i.sysId && (
                <button className={`btn btn-ghost !px-2 ${pinnedSet.has(i.sysId) ? "text-accent" : "text-muted"}`} aria-label={`${pinnedSet.has(i.sysId) ? "Unpin" : "Pin"} ${i.name}`}
                  onClick={(e) => { e.stopPropagation(); togglePin(i.sysId!); }}><Icon name="pin" size={14} /></button>
              )}
              <span className="text-[11px] text-muted">{i.cat}</span>
            </div>
          ))}
          {!shown.length && <Empty>{cat === "Recent" && !q ? "No recently used applications yet." : "No applications match."}</Empty>}
        </div>
        {sys.error && <Note kind="warn">Installed applications unavailable: {sys.error}</Note>}
      </motion.div>
    </motion.div>
  );
}

// ---------------------------------------------------------- approvals + panels
function ApprovalDialog({ a, more }: { a: Approval; more: number }) {
  const [busy, setBusy] = useState(false);
  const go = async (ok: boolean) => { setBusy(true); await decide(a.id, ok); setBusy(false); };
  const who = a.actor === "user" ? "You asked for this" : a.actor === "ai" ? "The assistant wants to do this" : a.actor === "voice" ? "A voice command wants to do this" : `${a.actor} wants to do this`;
  return (
    <motion.div className="absolute inset-0 z-[9800] flex items-center justify-center bg-black/50 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <motion.div role="alertdialog" aria-label="Approval required" className="glass w-[520px] max-w-[92vw] p-5" initial={{ scale: 0.96 }} animate={{ scale: 1 }}>
        <div className="mb-3 flex items-center justify-between"><h2 className="text-base font-semibold">Approval required</h2><Chip value={a.risk}>{a.risk} risk</Chip></div>
        <p className="break-words text-[15px]">{a.summary}</p>
        <p className="mt-1 text-xs text-muted">{who} · {a.action}</p>
        {a.reasons.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-[13px] text-muted">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
        <pre className="scroll mt-3 max-h-36 rounded-lg border border-line bg-[var(--field)] p-2 font-mono text-xs">{JSON.stringify(a.params, null, 2)}</pre>
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-muted">{more > 0 ? `${more} more waiting` : "Nothing runs until you choose."}</span>
          <div className="flex gap-2">
            <button className="btn" disabled={busy} onClick={() => go(false)}>Deny</button>
            <button className={`btn ${a.risk === "high" ? "btn-danger" : "btn-primary"}`} disabled={busy} onClick={() => go(true)}>Approve</button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function NotificationPanel() {
  const list = useStore((s) => s.notifications);
  return (
    <motion.aside aria-label="Notifications" className="glass absolute right-2 top-14 z-[9400] flex max-h-[70vh] w-[360px] flex-col p-3"
      initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="label">Notifications</h2>
        <div className="flex gap-1">
          <button className="btn btn-ghost !py-1 text-xs" onClick={markAllRead}>Mark read</button>
          <button className="btn btn-ghost !py-1 text-xs" onClick={async () => { await act("notify.clear"); set({ notifications: [] }); }}>Clear</button>
        </div>
      </div>
      <div className="scroll min-h-0 flex-1 space-y-1.5">
        {list.map((n) => (
          <div key={n.id} className={`rounded-lg border border-line p-2.5 ${n.read ? "opacity-60" : ""}`}>
            <div className="flex justify-between gap-2"><span className="font-medium">{n.title}</span><span className="shrink-0 text-[11px] text-muted">{formatWhen(n.ts)}</span></div>
            {n.body && <p className="mt-0.5 break-words text-[13px] text-muted">{n.body}</p>}
            <span className="text-[10px] uppercase tracking-wider text-muted">{n.category}</span>
          </div>
        ))}
        {!list.length && <Empty>No notifications.</Empty>}
      </div>
    </motion.aside>
  );
}

function Toasts() {
  const toasts = useStore((s) => s.toasts);
  return (
    <div className="pointer-events-none absolute right-3 top-14 z-[9700] flex w-[320px] flex-col gap-2" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} layout initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 30 }} className="glass !rounded-xl p-3">
            <div className={`font-medium ${t.level === "warning" ? "text-warn" : ""}`}>{t.title}</div>
            {t.body && <div className="mt-0.5 line-clamp-3 break-words text-[13px] text-muted">{t.body}</div>}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

// --------------------------------------------------------------------- desktop
export function Desktop() {
  const wins = useStore((s) => s.wins);
  const workspace = useStore((s) => s.workspace);
  const focused = useStore((s) => s.focused);
  const launcher = useStore((s) => s.launcher);
  const panel = useStore((s) => s.panel);
  const approvals = useStore((s) => s.approvals);
  const theme = usePref<string>("theme.mode", "dark");
  const accent = usePref<string>("theme.accent", "#8b5cf6");
  const wallpaper = usePref<string>("theme.wallpaper", "aurora");
  const shortcuts = usePref<Record<string, string>>("shortcuts", {});
  const startup = usePref<string[]>("startup.apps", ["home"]);
  const started = useRef(false);

  useEffect(() => connectEvents(), []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.setProperty("--color-accent", /^#[0-9a-f]{6}$/i.test(accent) ? accent : "#8b5cf6");
  }, [theme, accent]);
  const prefsLoaded = useStore((s) => s.prefsLoaded);
  useEffect(() => { // open startup apps once, after preferences have arrived
    if (!prefsLoaded || started.current) return;
    started.current = true;
    startup.filter((id) => APP[id]).forEach((id) => open(id));
  }, [prefsLoaded, startup]);

  useEffect(() => {
    const map = { ...DEFAULT_SHORTCUTS, ...shortcuts };
    const onKey = (e: KeyboardEvent) => {
      const c = combo(e);
      const name = Object.keys(map).find((k) => map[k] === c);
      if (e.key === "Escape") { if (get().launcher || get().panel) { set({ launcher: false, panel: false }); e.preventDefault(); } return; }
      if (!name) return;
      e.preventDefault();
      const f = get().focused;
      if (name === "launcher") set((s) => ({ launcher: !s.launcher }));
      else if (name === "assistant") open("assistant");
      else if (name === "close" && f !== null) closeWin(f);
      else if (name === "minimize" && f !== null) minimizeWin(f);
      else if (name === "cycle") cycleWindows();
      else if (name.startsWith("workspace")) setWorkspace(Number(name.slice(9)) - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcuts]);

  const preset = ["aurora", "horizon", "grid", "plain"].includes(wallpaper);
  return (
    <div className="relative h-full w-full overflow-hidden">
      <div className={`wallpaper ${preset ? `wp-${wallpaper}` : ""}`} style={preset ? undefined : { backgroundImage: `url("${rawUrl(wallpaper)}")` }} />
      <TopBar />
      <main aria-label={`Workspace ${workspace + 1}`}>
        {/* No exit animations on windows or modals: a hung exit would leave a
            dead overlay on screen, which is not acceptable for approval prompts. */}
          {wins.map((w) => {
            const app = APP[w.app];
            const Body = app.component;
            return (
              <Window key={w.id} win={w} focused={w.id === focused} icon={app.icon} hidden={w.minimized || w.workspace !== workspace}>
                <Suspense fallback={<Empty>Loading…</Empty>}><Body props={w.props} /></Suspense>
              </Window>
            );
          })}
      </main>
      <Dock />
      {panel && <NotificationPanel />}
      {launcher && <Launcher />}
      <Toasts />
      {approvals.length > 0 && <ApprovalDialog key={approvals[approvals.length - 1].id} a={approvals[approvals.length - 1]} more={approvals.length - 1} />}
    </div>
  );
}

export { open as openTitanApp, setPref };
