import { useEffect, useState } from "react";
import { Empty, Note, Toggle } from "../components/ui";
import { post, req } from "../lib/api";

interface Plugin { id: string; name: string; version: string; description: string; permissions: string[]; enabled: boolean; loaded: boolean; error: string | null; valid: boolean; actions: string[] }

export default function Plugins() {
  const [list, setList] = useState<Plugin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => req<Plugin[]>("/api/plugins").then(setList).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  const toggle = async (p: Plugin, on: boolean) => {
    setError(null);
    if (on && p.permissions.length && !confirm(`Enable “${p.name}”?\n\nIt will be allowed to use: ${p.permissions.join(", ")}.\nHigh-risk actions will still ask you first.`)) return;
    try { await post(`/api/plugins/${p.id}/${on ? "enable" : "disable"}`); } catch (e) { setError(`${p.name}: ${(e as Error).message}`); }
    load();
  };
  return (
    <div className="scroll h-full space-y-2 p-3">
      <p className="text-xs text-muted">Plugins live in TITAN's data directory under <span className="font-mono">plugins/</span>. They are off until you enable them, and can only use the permissions listed. Plugins run inside TITAN Core, so only enable ones you trust.</p>
      {error && <Note>{error}</Note>}
      {list?.map((p) => (
        <div key={p.id} className="glass !rounded-xl p-3">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium">{p.name} <span className="text-xs font-normal text-muted">v{p.version}</span></div>
              {p.description && <div className="text-[13px] text-muted">{p.description}</div>}
              <div className="mt-1 text-xs">{p.permissions.length ? <>Permissions: {p.permissions.map((x) => <span key={x} className="mr-1 rounded border border-line px-1.5 py-0.5">{x}</span>)}</> : <span className="text-muted">Requests no system permissions</span>}</div>
              {p.actions.length > 0 && <div className="mt-1 font-mono text-[11px] text-muted">{p.actions.join("  ")}</div>}
              {p.error && <div className="mt-1 text-[13px] text-danger">{p.valid ? "Failed to load: " : "Invalid: "}{p.error}</div>}
            </div>
            {p.valid && <Toggle checked={p.enabled} onChange={(v) => toggle(p, v)} label={p.enabled ? "Enabled" : "Disabled"} />}
          </div>
        </div>
      ))}
      {list && !list.length && <Empty>No plugins installed. See docs/PLUGINS.md and the example in plugins/.</Empty>}
    </div>
  );
}
