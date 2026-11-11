import { Gauge } from "../components/Gauge";
import { Chip, Empty, Icon, Section } from "../components/ui";
import { type Status } from "../lib/api";
import { formatBytes, formatUptime, formatWhen, rate } from "../lib/format";
import { useClock, useMetrics } from "../lib/hooks";
import { usePref, useStore } from "../lib/store";
import { openTitanApp } from "../shell/Desktop";
import { useEffect, useState } from "react";
import { req } from "../lib/api";
import { useAction } from "../lib/hooks";

export const WIDGETS = ["clock", "resources", "machine", "quick", "notifications", "reminders", "tasks"] as const;

export default function Home() {
  const now = useClock();
  const { current: m, series } = useMetrics(2);
  const widgets = usePref<string[]>("home.widgets", [...WIDGETS]);
  const notifications = useStore((s) => s.notifications).slice(0, 4);
  const tasks = useStore((s) => s.tasks).slice(0, 4);
  const live = useStore((s) => s.link === "live");
  const [status, setStatus] = useState<Status | null>(null);
  const reminders = useAction<{ id: number; text: string; due_at: string; done: number }[]>("reminders.list", {}, 30000);
  useEffect(() => { if (live) req<Status>("/api/status").then(setStatus).catch(() => setStatus(null)); else setStatus(null); }, [live]);
  const prev = series.length > 1 ? series[series.length - 2] : undefined;
  const dt = m && prev ? m.ts - prev.ts : 0;
  const down = m ? rate(prev?.network.bytes_recv, m.network.bytes_recv, dt) : null;
  const up = m ? rate(prev?.network.bytes_sent, m.network.bytes_sent, dt) : null;
  const hour = now.getHours();
  const on = (w: string) => widgets.includes(w);
  const pending = (reminders.data ?? []).filter((r) => !r.done);

  return (
    <div className="scroll grid h-full auto-rows-min gap-3 p-3 md:grid-cols-3">
      {on("clock") && (
        <Section title={hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"} className="md:col-span-2">
          <div className="tabular text-5xl font-light tracking-tight">{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
          <div className="mt-1 text-muted">{now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</div>
        </Section>
      )}
      {on("machine") && (
        <Section title="This machine">
          {status ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
              <dt className="text-muted">Host</dt><dd className="truncate">{status.system.hostname}</dd>
              <dt className="text-muted">Kernel</dt><dd className="truncate">{status.system.os} {status.system.kernel}</dd>
              <dt className="text-muted">Arch</dt><dd>{status.system.arch}</dd>
              <dt className="text-muted">Uptime</dt><dd>{formatUptime(status.system.boot_time, now.getTime() / 1000)}</dd>
              <dt className="text-muted">Assistant</dt>
              <dd className={status.ai_configured ? "text-ok" : "text-warn"}>{status.ai_configured ? "API key configured" : "No API key set"}</dd>
            </dl>
          ) : <Empty>Waiting for TITAN Core…</Empty>}
        </Section>
      )}
      {on("resources") && (
        <Section title="Resources" className="md:col-span-3" aside={<button className="btn btn-ghost !py-0.5 text-xs" onClick={() => openTitanApp("monitor")}>Open monitor</button>}>
          <div className="grid gap-4 sm:grid-cols-4">
            <Gauge label="CPU" percent={m?.cpu.percent ?? null} detail={m ? `${m.cpu.cores} cores · load ${m.cpu.load_avg[0].toFixed(2)}` : undefined} />
            <Gauge label="Memory" percent={m?.memory.percent ?? null} detail={m ? `${formatBytes(m.memory.used)} of ${formatBytes(m.memory.total)}` : undefined} />
            <Gauge label="Disk" percent={m?.disk.percent ?? null} detail={m ? `${formatBytes(m.disk.used)} of ${formatBytes(m.disk.total)}` : undefined} />
            <dl className="tabular grid grid-cols-[auto_1fr] content-center gap-x-3 gap-y-1 text-[13px]">
              <dt className="text-muted">Down</dt><dd>{down === null ? "—" : `${formatBytes(down)}/s`}</dd>
              <dt className="text-muted">Up</dt><dd>{up === null ? "—" : `${formatBytes(up)}/s`}</dd>
              <dt className="text-muted">Battery</dt><dd>{!m ? "—" : m.battery ? `${m.battery.percent.toFixed(0)}%${m.battery.plugged ? " · charging" : ""}` : "Not available"}</dd>
              <dt className="text-muted">Temp</dt><dd>{!m ? "—" : m.temperatures ? `${Math.max(...Object.values(m.temperatures)).toFixed(0)} °C` : "No sensors"}</dd>
            </dl>
          </div>
        </Section>
      )}
      {on("quick") && (
        <Section title="Quick actions">
          <div className="grid grid-cols-2 gap-2">
            {([["assistant", "Ask TITAN"], ["files", "Files"], ["terminal", "Terminal"], ["web", "Web"], ["developer", "Developer"], ["settings", "Settings"]] as const).map(([id, label]) => (
              <button key={id} className="btn !justify-start" onClick={() => openTitanApp(id)}><Icon name={{ assistant: "spark", files: "folder", terminal: "terminal", web: "globe", developer: "code", settings: "settings" }[id]} size={15} />{label}</button>
            ))}
          </div>
        </Section>
      )}
      {on("notifications") && (
        <Section title="Recent notifications">
          {notifications.length ? notifications.map((n) => (
            <div key={n.id} className="border-t border-line py-1.5 first:border-0 first:pt-0">
              <div className="flex justify-between gap-2 text-[13px]"><span className="truncate">{n.title}</span><span className="shrink-0 text-[11px] text-muted">{formatWhen(n.ts)}</span></div>
              {n.body && <div className="truncate text-xs text-muted">{n.body}</div>}
            </div>
          )) : <Empty>Nothing yet.</Empty>}
        </Section>
      )}
      {on("reminders") && (
        <Section title="Reminders" aside={<button className="btn btn-ghost !py-0.5 text-xs" onClick={() => openTitanApp("memory")}>Manage</button>}>
          {pending.length ? pending.slice(0, 4).map((r) => (
            <div key={r.id} className="flex justify-between gap-2 border-t border-line py-1.5 text-[13px] first:border-0 first:pt-0">
              <span className="truncate">{r.text}</span><span className="shrink-0 text-[11px] text-muted">{new Date(r.due_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</span>
            </div>
          )) : <Empty>No upcoming reminders.</Empty>}
        </Section>
      )}
      {on("tasks") && tasks.length > 0 && (
        <Section title="Background tasks" className="md:col-span-3">
          {tasks.map((t) => <div key={t.id} className="flex items-center justify-between gap-3 py-1 text-[13px]"><span className="truncate">{t.name}</span><Chip value={t.status} /></div>)}
        </Section>
      )}
    </div>
  );
}
