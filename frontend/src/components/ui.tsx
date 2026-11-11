import type { ReactNode } from "react";

const PATHS: Record<string, string> = {
  home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  folder: "M3 6a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z",
  terminal: "M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM7 9l3 3-3 3M12 15h5",
  activity: "M3 12h4l3-8 4 16 3-8h4",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  brain: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 0V7a3 3 0 0 0-3-3zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 0",
  tasks: "M4 6h2M4 12h2M4 18h2M9 6h11M9 12h11M9 18h11",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19 12l2-1-1-3-2 .5-1.5-1.5.5-2-3-1-1 2h-2l-1-2-3 1 .5 2L5 8.5 3 8l-1 3 2 1v2l-2 1 1 3 2-.5L6.5 19l-.5 2 3 1 1-2h2l1 2 3-1-.5-2 1.5-1.5 2 .5 1-3-2-1z",
  plug: "M9 3v5M15 3v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3",
  code: "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  bell: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  mic: "M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
  x: "M6 6l12 12M18 6L6 18",
  min: "M5 12h14",
  max: "M5 5h14v14H5z",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  up: "M12 19V5M5 12l7-7 7 7",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  app: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM3 9h18",
  pin: "M9 3h6l-1 6 4 4H6l4-4zM12 13v8",
};

export function Icon({ name, size = 18, className = "" }: { name: string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={PATHS[name] ?? PATHS.app} />
    </svg>
  );
}

export function Note({ kind = "error", children }: { kind?: "error" | "info" | "warn"; children: ReactNode }) {
  if (!children) return null;
  const tone = kind === "error" ? "text-danger border-danger/30" : kind === "warn" ? "text-warn border-warn/30" : "text-muted border-line";
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded-lg border px-3 py-2 text-[13px] ${tone}`}>{children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full min-h-24 items-center justify-center px-6 text-center text-sm text-muted">{children}</div>;
}

const RISK: Record<string, string> = { low: "text-ok", medium: "text-warn", high: "text-danger", ok: "text-ok", error: "text-danger",
  denied: "text-danger", approval_required: "text-warn", running: "text-azure", done: "text-ok", failed: "text-danger",
  cancelled: "text-muted", queued: "text-muted", interrupted: "text-warn" };
export function Chip({ value, children }: { value: string; children?: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] ${RISK[value] ?? "text-muted"}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />{children ?? value.replace("_", " ")}
    </span>
  );
}

export function Section({ title, aside, children, className = "" }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`glass p-4 ${className}`}>
      <header className="mb-3 flex items-center justify-between gap-3">
        <h3 className="label">{title}</h3>{aside}
      </header>
      {children}
    </section>
  );
}

export function Bar({ percent, className = "" }: { percent: number | null; className?: string }) {
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-line ${className}`}>
      <div className="h-full rounded-full bg-gradient-to-r from-accent to-azure transition-[width] duration-500"
        style={{ width: `${percent === null ? 0 : Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 py-1.5 text-sm">
      <span>{label}</span>
      <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? "bg-accent" : "bg-line"}`}>
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${checked ? "left-[18px]" : "left-0.5"}`} />
      </button>
    </label>
  );
}
