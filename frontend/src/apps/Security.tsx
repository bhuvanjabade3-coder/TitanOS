import { useState } from "react";
import { Chip, Empty, Note, Section } from "../components/ui";
import { formatWhen } from "../lib/format";
import { useAction } from "../lib/hooks";
import { setPref, usePref } from "../lib/store";

interface Overview {
  alerts: { level: string; text: string }[];
  firewall: { available: boolean; enabled?: boolean; reason?: string };
  ssh: { available: boolean; active: boolean | null; installed: boolean; settings: Record<string, string> };
  updates: { available: boolean; count?: number; security?: number; packages?: string[]; reason?: string };
  logins: { sessions: { user: string; terminal: string | null; host: string | null; started: number }[]; recent: string[] };
  connections: { available: boolean; reason?: string; listening?: { address: string; port: number; process: string | null; exposed: boolean }[]; active?: { remote: string; remote_port: number; process: string | null; status: string }[] };
  file_permissions: { findings: { path: string; mode: string; issue: string }[] };
}
interface Audit { id: number; ts: string; actor: string; action: string; outcome: string; detail: Record<string, unknown> }

export const CATEGORIES: [string, string][] = [
  ["files", "File operations"], ["terminal", "Terminal commands"], ["apps", "Launching applications"], ["windows", "Window management"],
  ["input", "Keyboard and mouse automation"], ["browser", "Browser and downloads"], ["memory", "Memory and reminders"],
  ["settings", "System settings"], ["dev", "Developer tools"], ["voice", "Voice"], ["system", "Process control"],
];

function Permission({ cat, label }: { cat: string; label: string }) {
  const value = usePref<string>(`permissions.${cat}`, "default");
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line py-1.5 text-[13px] first:border-0">
      <span>{label}</span>
      <select className="field !py-1 text-xs" aria-label={`${label} permission`} value={value}
        onChange={(e) => setPref(`permissions.${cat}`, e.target.value === "default" ? null : e.target.value)}>
        <option value="default">Default (ask when risky)</option>
        <option value="allow">Allow medium risk without asking</option>
        <option value="ask">Always ask</option>
        <option value="deny">Deny</option>
      </select>
    </div>
  );
}

export default function Security() {
  const [tab, setTab] = useState<"overview" | "network" | "permissions" | "audit">("overview");
  const o = useAction<Overview>("security.overview", {}, 30000);
  const audit = useAction<Audit[]>("security.audit_log", { limit: 200 }, tab === "audit" ? 5000 : 0);
  const d = o.data;
  const flag = (ok: boolean | null | undefined, yes: string, no: string, unknown = "Unknown") =>
    ok === true ? <span className="text-ok">{yes}</span> : ok === false ? <span className="text-warn">{no}</span> : <span className="text-muted">{unknown}</span>;
  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-line p-2" role="tablist">
        {(["overview", "network", "permissions", "audit"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`btn capitalize ${tab === t ? "!border-accent" : "btn-ghost"}`} onClick={() => setTab(t)}>{t === "audit" ? "Audit log" : t}</button>
        ))}
        <button className="btn btn-ghost ml-auto" onClick={() => { o.reload(); audit.reload(); }}>Refresh</button>
      </div>
      <div className="scroll min-h-0 flex-1 p-3">
        {o.error && <Note>{o.error}</Note>}
        {!d && !o.error && <Empty>Checking this machine…</Empty>}
        {d && tab === "overview" && (
          <div className="grid gap-3 md:grid-cols-2">
            <Section title="Alerts" className="md:col-span-2">
              {d.alerts.length ? d.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 py-1 text-[13px]"><Chip value={a.level === "warning" ? "medium" : "low"}>{a.level}</Chip><span className="break-all">{a.text}</span></div>
              )) : <div className="text-[13px] text-ok">No issues found by TITAN's checks.</div>}
            </Section>
            <Section title="Firewall">{d.firewall.available ? flag(d.firewall.enabled, "ufw is enabled", "ufw is disabled") : <span className="text-muted">{d.firewall.reason}</span>}</Section>
            <Section title="SSH server">
              {!d.ssh.installed && d.ssh.active === null ? <span className="text-muted">Not installed</span> : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
                  <dt className="text-muted">Service</dt><dd>{flag(d.ssh.active === null ? null : !d.ssh.active, "Not running", "Running")}</dd>
                  {Object.entries(d.ssh.settings).map(([k, v]) => <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd>{v}</dd></div>)}
                </dl>
              )}
            </Section>
            <Section title="System updates">
              {d.updates.available ? (d.updates.count ? <div className="text-[13px]"><span className="text-warn">{d.updates.count} update(s) available</span>, {d.updates.security} security<div className="mt-1 break-words text-xs text-muted">{d.updates.packages!.join(", ")}</div></div> : <span className="text-ok">Up to date</span>) : <span className="text-muted">{d.updates.reason}</span>}
            </Section>
            <Section title="File permissions">
              {d.file_permissions.findings.length ? d.file_permissions.findings.map((f) => <div key={f.path} className="break-all py-0.5 text-[13px]"><span className="font-mono text-xs">{f.path}</span> <span className="text-warn">{f.issue} (is {f.mode})</span></div>) : <span className="text-ok">Home and SSH key permissions look right.</span>}
            </Section>
            <Section title="Login sessions" className="md:col-span-2">
              {d.logins.sessions.length ? d.logins.sessions.map((s, i) => <div key={i} className="text-[13px]">{s.user} on {s.terminal ?? "?"} {s.host ? `from ${s.host}` : ""} · since {formatWhen(s.started)}</div>) : <span className="text-[13px] text-muted">No interactive sessions reported.</span>}
              {d.logins.recent.length > 0 && <pre className="scroll mt-2 font-mono text-[11px] text-muted">{d.logins.recent.join("\n")}</pre>}
            </Section>
          </div>
        )}
        {d && tab === "network" && (!d.connections.available ? <Note kind="warn">{d.connections.reason}</Note> : (
          <div className="grid gap-3 md:grid-cols-2">
            <Section title="Listening services">
              {d.connections.listening!.map((l, i) => <div key={i} className="tabular flex items-center justify-between gap-2 border-t border-line py-1 text-[13px] first:border-0"><span className="font-mono text-xs">{l.address}:{l.port}</span><span className="truncate text-muted">{l.process ?? "—"}</span><Chip value={l.exposed ? "medium" : "low"}>{l.exposed ? "all interfaces" : "local only"}</Chip></div>)}
              {!d.connections.listening!.length && <Empty>Nothing is listening.</Empty>}
            </Section>
            <Section title="Active connections">
              {d.connections.active!.slice(0, 60).map((c, i) => <div key={i} className="tabular flex justify-between gap-2 border-t border-line py-1 text-[13px] first:border-0"><span className="font-mono text-xs">{c.remote}:{c.remote_port}</span><span className="truncate text-muted">{c.process ?? "—"}</span></div>)}
              {!d.connections.active!.length && <Empty>No active connections.</Empty>}
            </Section>
          </div>
        ))}
        {tab === "permissions" && (
          <Section title="What TITAN may do without asking">
            <p className="mb-2 text-[13px] text-muted">High-risk actions — permanent deletion, privileged or destructive commands, ending processes, changing these settings — always ask, whatever is chosen here.</p>
            {CATEGORIES.map(([c, l]) => <Permission key={c} cat={c} label={l} />)}
          </Section>
        )}
        {tab === "audit" && (
          <table className="w-full text-[13px]">
            <thead><tr className="text-left text-xs text-muted"><th className="pb-1 font-normal">When</th><th className="font-normal">Who</th><th className="font-normal">Action</th><th className="font-normal">Outcome</th><th className="font-normal">Detail</th></tr></thead>
            <tbody>
              {(audit.data ?? []).map((a) => (
                <tr key={a.id} className="border-t border-line align-top">
                  <td className="whitespace-nowrap py-1 pr-3 text-xs text-muted">{formatWhen(a.ts)}</td><td className="pr-3">{a.actor}</td><td className="pr-3 font-mono text-xs">{a.action}</td>
                  <td className={`pr-3 ${a.outcome === "ok" ? "text-ok" : a.outcome.startsWith("approval") ? "text-warn" : "text-danger"}`}>{a.outcome.slice(0, 60)}</td>
                  <td className="max-w-0 w-1/3 truncate font-mono text-xs text-muted">{JSON.stringify(a.detail)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
