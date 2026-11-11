import { Bar, Chip, Empty } from "../components/ui";
import { act } from "../lib/api";
import { formatWhen } from "../lib/format";
import { toast, useStore } from "../lib/store";

export default function Tasks() {
  const tasks = useStore((s) => s.tasks);
  if (!tasks.length) return <Empty>No background tasks. Downloads, background commands and voice listening appear here.</Empty>;
  return (
    <div className="scroll h-full space-y-2 p-3">
      {tasks.map((t) => {
        const active = t.status === "running" || t.status === "queued";
        return (
          <div key={t.id} className="glass !rounded-xl p-3">
            <div className="flex items-center gap-3">
              <span className="min-w-0 flex-1 truncate font-medium">{t.name}</span>
              <span className="text-xs text-muted">{formatWhen(t.created_at)}</span><Chip value={t.status} />
              {active && <button className="btn !py-0.5 text-xs" onClick={async () => { const o = await act("tasks.cancel", { id: t.id }); if (o.status !== "ok" && o.status !== "approval_required") toast("Could not cancel", o.error, "warning"); }}>Cancel</button>}
            </div>
            {active && t.progress > 0 && <Bar percent={t.progress * 100} className="mt-2" />}
            {active && t.message && <div className="mt-1 truncate font-mono text-xs text-muted">{t.message}</div>}
            {t.error && <pre className="scroll mt-2 max-h-32 whitespace-pre-wrap font-mono text-xs text-danger">{t.error}</pre>}
            {t.status === "done" && t.result !== null && <pre className="scroll mt-2 max-h-32 whitespace-pre-wrap break-words font-mono text-xs text-muted">{typeof t.result === "string" ? t.result : JSON.stringify(t.result, null, 2)}</pre>}
          </div>
        );
      })}
    </div>
  );
}
