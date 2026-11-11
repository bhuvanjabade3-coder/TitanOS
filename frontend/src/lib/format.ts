const UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

export function formatBytes(bytes: number, digits = 1): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < UNITS.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : digits)} ${UNITS[i]}`;
}

/** Bytes/second between two cumulative counters; null when it cannot be derived. */
export function rate(prev: number | undefined, next: number, dtSeconds: number): number | null {
  if (prev === undefined || dtSeconds <= 0 || next < prev) return null;
  return (next - prev) / dtSeconds;
}

export function formatUptime(bootTime: number, now = Date.now() / 1000): string {
  const s = Math.max(0, Math.floor(now - bootTime));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function formatWhen(iso: string | number, now = Date.now()): string {
  const t = typeof iso === "number" ? iso * 1000 : Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const s = Math.round((now - t) / 1000);
  if (s < 0) return new Date(t).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(t).toLocaleDateString([], { month: "short", day: "numeric" });
}
