import { useState } from "react";
import { Gauge } from "../components/Gauge";
import { Bar, Empty, Note, Section } from "../components/ui";
import { run, type Metrics, type Proc } from "../lib/api";
import { formatBytes, rate } from "../lib/format";
import { useAction, useMetrics, useRun } from "../lib/hooks";

function Spark({ values, max = 100 }: { values: number[]; max?: number }) {
  if (values.length < 2) return <div className="h-12 text-xs text-muted">Collecting…</div>;
  const top = Math.max(max, ...values) || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${40 - (v / top) * 38}`).join(" ");
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-12 w-full" role="img" aria-label="history">
      <polyline points={pts} fill="none" stroke="var(--color-accent)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function netRates(series: Metrics[]) {
  const out: { down: number; up: number }[] = [];
  for (let i = 1; i < series.length; i++) {
    const dt = series[i].ts - series[i - 1].ts;
    const down = rate(series[i - 1].network.bytes_recv, series[i].network.bytes_recv, dt);
    const up = rate(series[i - 1].network.bytes_sent, series[i].network.bytes_sent, dt);
    if (down !== null && up !== null) out.push({ down, up });
  }
  return out;
}

export default function Monitor() {
  const { current: m, series } = useMetrics(90);
  const [sort, setSort] = useState<"memory" | "cpu">("cpu");
  const procs = useAction<Proc[]>("proc.list", { limit: 40, sort }, 3000);
  const k = useRun();
  const net = netRates(series);
  const last = net[net.length - 1];
  if (!m) return <Empty>Waiting for live data from TITAN Core…</Empty>;
  return (
    <div className="scroll grid h-full auto-rows-min gap-3 p-3 md:grid-cols-2">
      <Section title="CPU">
        <Gauge label="Total" percent={m.cpu.percent} detail={`load ${m.cpu.load_avg.map((x) => x.toFixed(2)).join(" · ")}`} />
        <Spark values={series.map((s) => s.cpu.percent)} />
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5">
          {m.cpu.per_core.map((p, i) => (
            <div key={i} className="flex items-center gap-2 text-xs"><span className="w-10 text-muted">CPU {i}</span><Bar percent={p} className="flex-1" /><span className="tabular w-9 text-right">{p.toFixed(0)}%</span></div>
          ))}
        </div>
      </Section>
      <div className="grid auto-rows-min gap-3">
        <Section title="Memory">
          <Gauge label="In use" percent={m.memory.percent} detail={`${formatBytes(m.memory.used)} of ${formatBytes(m.memory.total)}`} />
          <Spark values={series.map((s) => s.memory.percent)} />
        </Section>
        <Section title="Network">
          <div className="tabular flex gap-6 text-sm"><span>↓ {last ? `${formatBytes(last.down)}/s` : "—"}</span><span>↑ {last ? `${formatBytes(last.up)}/s` : "—"}</span></div>
          <Spark values={net.map((n) => n.down + n.up)} max={1} />
        </Section>
        <Section title="Disk, power, temperature">
          <dl className="tabular grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
            <dt className="text-muted">Disk /</dt><dd>{formatBytes(m.disk.used)} of {formatBytes(m.disk.total)} ({m.disk.percent.toFixed(0)}%)</dd>
            <dt className="text-muted">Battery</dt><dd>{m.battery ? `${m.battery.percent.toFixed(0)}%${m.battery.plugged ? " · charging" : ""}` : "Not available on this machine"}</dd>
            <dt className="text-muted">Sensors</dt>
            <dd>{m.temperatures ? Object.entries(m.temperatures).map(([n, t]) => `${n} ${t.toFixed(0)}°C`).join(" · ") : "No temperature sensors exposed"}</dd>
          </dl>
        </Section>
      </div>
      <Section title="Processes" className="md:col-span-2" aside={
        <div className="flex gap-1 text-xs">{(["cpu", "memory"] as const).map((s) => <button key={s} className={`btn !py-0.5 ${sort === s ? "!border-accent" : "btn-ghost"}`} onClick={() => setSort(s)}>by {s}</button>)}</div>}>
        {(k.error || k.notice) && <div className="mb-2"><Note kind={k.error ? "error" : "info"}>{k.error ?? k.notice}</Note></div>}
        {procs.error && <Note>{procs.error}</Note>}
        <table className="tabular w-full text-[13px]">
          <thead><tr className="text-left text-xs text-muted"><th className="pb-1 font-normal">PID</th><th className="font-normal">Name</th><th className="font-normal">User</th><th className="text-right font-normal">CPU</th><th className="text-right font-normal">Memory</th><th /></tr></thead>
          <tbody>
            {(procs.data ?? []).map((p) => (
              <tr key={p.pid} className="border-t border-line">
                <td className="py-1 pr-3 font-mono text-xs text-muted">{p.pid}</td>
                <td className="max-w-0 w-1/2 truncate">{p.name}</td>
                <td className="text-muted">{p.user ?? "—"}</td>
                <td className="text-right">{p.cpu_percent.toFixed(1)}%</td>
                <td className="text-right">{formatBytes(p.rss)}</td>
                <td className="pl-3 text-right"><button className="btn btn-ghost !px-1.5 !py-0 text-xs text-danger" aria-label={`End process ${p.name} ${p.pid}`} onClick={() => k.go(() => run("proc.kill", { pid: p.pid }))}>End</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
