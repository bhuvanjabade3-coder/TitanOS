import { useEffect, useRef, useState } from "react";
import { Chip } from "../components/ui";
import { act } from "../lib/api";
import { onDecided, onEvent, useStore } from "../lib/store";
import { openTitanApp } from "../shell/Desktop";

interface RunResult { command: string; exit_code: number | null; stdout: string; stderr: string; timed_out: boolean; truncated: boolean; duration: number; background?: boolean; task_id?: string }
interface Line { id: number; command: string; state: "running" | "done" | "approval" | "denied" | "error" | "background"; out?: RunResult; note?: string; approvalId?: number; taskId?: string; stream?: string[]; risk?: string }

let nextId = 1;

export default function Terminal({ props }: { props?: Record<string, unknown> }) {
  const [lines, setLines] = useState<Line[]>([]);
  const [input, setInput] = useState("");
  const [cwd, setCwd] = useState(typeof props?.cwd === "string" ? props.cwd : "~");
  const [background, setBackground] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [hi, setHi] = useState(-1);
  const tasks = useStore((s) => s.tasks);
  const end = useRef<HTMLDivElement>(null);
  const patch = (id: number, p: Partial<Line>) => setLines((ls) => ls.map((l) => (l.id === id ? { ...l, ...p } : l)));

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [lines]);
  useEffect(() => onEvent("terminal.output", (d: { task_id: string; line: string }) =>
    setLines((ls) => ls.map((l) => (l.taskId === d.task_id ? { ...l, stream: [...(l.stream ?? []), d.line].slice(-500) } : l)))), []);
  useEffect(() => onDecided((a) => setLines((ls) => ls.map((l) => {
    if (l.approvalId !== a.id) return l;
    if (a.status === "denied") return { ...l, state: "denied", note: "You declined this command. It did not run." };
    const r = a.result;
    if (r && r.status === "ok") {
      const out = r.result as RunResult;
      return out.background ? { ...l, state: "background", taskId: out.task_id, note: undefined } : { ...l, state: "done", out, note: undefined };
    }
    return { ...l, state: "error", note: r && "error" in r ? r.error : `Approval ${a.status}` };
  }))), []);

  const submit = async (command: string) => {
    command = command.trim();
    if (!command) return;
    if (command === "clear") { setLines([]); setInput(""); return; }
    const id = nextId++;
    setHistory((h) => [command, ...h.filter((x) => x !== command)].slice(0, 100)); setHi(-1); setInput("");
    setLines((ls) => [...ls, { id, command, state: "running" }]);
    try {
      const out = await act<RunResult>("terminal.run", { command, cwd, background, timeout: 120 });
      if (out.status === "ok") patch(id, out.result.background ? { state: "background", taskId: out.result.task_id } : { state: "done", out: out.result });
      else if (out.status === "approval_required") patch(id, { state: "approval", approvalId: out.approval_id, risk: out.risk, note: out.reasons.join("; ") });
      else patch(id, { state: out.status === "denied" ? "denied" : "error", note: out.error });
    } catch (e) {
      patch(id, { state: "error", note: (e as Error).message });
    }
  };
  const explain = (l: Line) => openTitanApp("assistant", {
    prompt: `Explain this error and how to fix it.\n\nCommand: ${l.command}\nExit code: ${l.out?.exit_code}\n\n${(l.out?.stderr || l.out?.stdout || l.note || "").slice(-3000)}`,
  });

  return (
    <div className="flex h-full flex-col font-mono text-[13px]">
      <div className="scroll min-h-0 flex-1 space-y-3 p-3">
        {!lines.length && <div className="font-sans text-muted">Read-only commands run immediately. Anything that changes the system is shown to you for approval first.</div>}
        {lines.map((l) => {
          const task = l.taskId ? tasks.find((t) => t.id === l.taskId) : undefined;
          const failed = l.out && (l.out.exit_code !== 0 || l.out.timed_out);
          return (
            <div key={l.id}>
              <div className="flex items-start gap-2"><span className="text-accent">❯</span><span className="min-w-0 flex-1 break-words">{l.command}</span>
                {l.state === "running" && <Chip value="running" />}
                {l.state === "approval" && <Chip value={l.risk ?? "medium"}>awaiting approval</Chip>}
                {l.state === "background" && <Chip value={task?.status ?? "queued"} />}
                {l.out && <span className="tabular shrink-0 text-xs text-muted">{l.out.timed_out ? "timed out" : `exit ${l.out.exit_code}`} · {l.out.duration}s</span>}
              </div>
              {l.out?.stdout && <pre className="mt-1 whitespace-pre-wrap break-words pl-5 text-text/90">{l.out.stdout}</pre>}
              {l.out?.stderr && <pre className="mt-1 whitespace-pre-wrap break-words pl-5 text-danger">{l.out.stderr}</pre>}
              {l.out?.truncated && <div className="pl-5 font-sans text-xs text-warn">Output truncated.</div>}
              {l.stream && <pre className="mt-1 whitespace-pre-wrap break-words pl-5 text-text/90">{l.stream.join("\n")}</pre>}
              {task?.error && <pre className="mt-1 whitespace-pre-wrap pl-5 text-danger">{task.error}</pre>}
              {l.note && <div className={`mt-1 pl-5 font-sans ${l.state === "approval" ? "text-warn" : "text-danger"}`}>{l.note}</div>}
              {l.state === "background" && task && (task.status === "running" || task.status === "queued") && (
                <button className="btn ml-5 mt-1 font-sans !py-0.5 text-xs" onClick={() => act("tasks.cancel", { id: task.id })}>Cancel</button>
              )}
              {(failed || l.state === "error") && <button className="btn ml-5 mt-1 font-sans !py-0.5 text-xs" onClick={() => explain(l)}>Explain this error</button>}
            </div>
          );
        })}
        <div ref={end} />
      </div>
      <form className="flex items-center gap-2 border-t border-line p-2 font-sans" onSubmit={(e) => { e.preventDefault(); submit(input); }}>
        <input className="field w-36 font-mono text-xs" aria-label="Working directory" value={cwd} onChange={(e) => setCwd(e.target.value)} />
        <input className="field flex-1 font-mono" autoFocus placeholder="command" aria-label="Command" value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowUp") { e.preventDefault(); const n = Math.min(history.length - 1, hi + 1); if (history[n]) { setHi(n); setInput(history[n]); } }
            if (e.key === "ArrowDown") { e.preventDefault(); const n = hi - 1; setHi(Math.max(-1, n)); setInput(n >= 0 ? history[n] : ""); }
          }} />
        <label className="flex items-center gap-1 text-xs text-muted" title="Run as a background task with live output"><input type="checkbox" checked={background} onChange={(e) => setBackground(e.target.checked)} />Background</label>
        <button className="btn btn-primary">Run</button>
      </form>
    </div>
  );
}
