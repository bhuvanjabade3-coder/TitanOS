import { useEffect, useState } from "react";
import { Gauge } from "./components/Gauge";
import { Panel } from "./components/Panel";
import { useMetrics, type Link } from "./hooks/useMetrics";
import { getJSON, type Proc, type Status } from "./lib/api";
import { formatBytes, formatUptime, rate } from "./lib/format";

const LINK: Record<Link, { text: string; dot: string }> = {
  live: { text: "Core online", dot: "bg-ok" },
  connecting: { text: "Connecting to core…", dot: "bg-warn" },
  offline: { text: "Core offline — retrying", dot: "bg-danger" },
};

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

/** Polls an endpoint while the core is reachable; clears data when it is not. */
function usePolled<T>(path: string, live: boolean, everyMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!live) {
      setData(null);
      return;
    }
    const ctl = new AbortController();
    const load = () =>
      getJSON<T>(path, ctl.signal)
        .then((d) => { setData(d); setError(null); })
        .catch((e) => { if (!ctl.signal.aborted) setError(String(e.message ?? e)); });
    load();
    const t = setInterval(load, everyMs);
    return () => { ctl.abort(); clearInterval(t); };
  }, [path, live, everyMs]);
  return { data, error };
}

export function App() {
  const now = useClock();
  const { link, current: m, previous } = useMetrics();
  const live = link === "live";
  const status = usePolled<Status>("/api/status", live, 30000);
  const procs = usePolled<Proc[]>("/api/system/processes?limit=8&sort=memory", live, 3000);

  const shown = live ? m : null; // never show stale numbers as if they were current
  const dt = shown && previous ? shown.ts - previous.ts : 0;
  const down = shown ? rate(previous?.network.bytes_recv, shown.network.bytes_recv, dt) : null;
  const up = shown ? rate(previous?.network.bytes_sent, shown.network.bytes_sent, dt) : null;
  const sys = status.data?.system;

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col gap-5 px-6 py-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-violet to-azure" aria-hidden />
          <span className="text-sm font-semibold tracking-[0.3em]">TITAN</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted" role="status">
          <span className={`h-2 w-2 rounded-full ${LINK[link].dot}`} />
          {LINK[link].text}
        </div>
      </header>

      <div className="grid gap-5 md:grid-cols-3">
        <Panel title="Now" className="md:col-span-2" index={0}>
          <div className="tabular text-6xl font-light tracking-tight">
            {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </div>
          <div className="mt-2 text-muted">
            {now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
          </div>
        </Panel>

        <Panel title="This machine" index={1}>
          {sys ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-muted">Host</dt><dd className="truncate">{sys.hostname}</dd>
              <dt className="text-muted">Kernel</dt><dd className="truncate">{sys.os} {sys.kernel}</dd>
              <dt className="text-muted">Arch</dt><dd>{sys.arch}</dd>
              <dt className="text-muted">Uptime</dt><dd>{formatUptime(sys.boot_time, now.getTime() / 1000)}</dd>
              <dt className="text-muted">AI core</dt>
              <dd className={status.data!.ai_configured ? "text-ok" : "text-warn"}>
                {status.data!.ai_configured ? "API key configured" : "No API key set"}
              </dd>
            </dl>
          ) : (
            <p className="text-sm text-muted">{status.error ?? "Waiting for core…"}</p>
          )}
        </Panel>

        <Panel title="Resources" className="md:col-span-3" index={2}>
          <div className="grid gap-6 sm:grid-cols-3">
            <Gauge label="CPU" percent={shown?.cpu.percent ?? null}
              detail={shown ? `${shown.cpu.cores} cores · load ${shown.cpu.load_avg[0].toFixed(2)}` : undefined} />
            <Gauge label="Memory" percent={shown?.memory.percent ?? null}
              detail={shown ? `${formatBytes(shown.memory.used)} of ${formatBytes(shown.memory.total)}` : undefined} />
            <Gauge label="Disk" percent={shown?.disk.percent ?? null}
              detail={shown ? `${formatBytes(shown.disk.used)} of ${formatBytes(shown.disk.total)}` : undefined} />
          </div>
        </Panel>

        <Panel title="Network & power" index={3}>
          <dl className="tabular grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-muted">Down</dt><dd>{down === null ? "—" : `${formatBytes(down)}/s`}</dd>
            <dt className="text-muted">Up</dt><dd>{up === null ? "—" : `${formatBytes(up)}/s`}</dd>
            <dt className="text-muted">Battery</dt>
            <dd>
              {!shown ? "—" : shown.battery
                ? `${shown.battery.percent.toFixed(0)}%${shown.battery.plugged ? " · charging" : ""}`
                : "Not available"}
            </dd>
            <dt className="text-muted">Temp</dt>
            <dd>
              {!shown ? "—" : shown.temperatures
                ? `${Math.max(...Object.values(shown.temperatures)).toFixed(0)} °C`
                : "No sensors"}
            </dd>
          </dl>
        </Panel>

        <Panel title="Top processes" className="md:col-span-2" index={4}
          aside={<span className="text-[11px] text-muted">by memory</span>}>
          {procs.data ? (
            <table className="tabular w-full text-sm">
              <tbody>
                {procs.data.map((p) => (
                  <tr key={p.pid} className="border-t border-line first:border-0">
                    <td className="py-1.5 pr-3 font-mono text-xs text-muted">{p.pid}</td>
                    <td className="max-w-0 w-full truncate py-1.5">{p.name}</td>
                    <td className="py-1.5 pl-3 text-right text-muted">{p.cpu_percent.toFixed(1)}%</td>
                    <td className="py-1.5 pl-4 text-right whitespace-nowrap">{formatBytes(p.rss)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted">{procs.error ?? "Waiting for core…"}</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
