import { useEffect, useState } from "react";
import { Chip, Empty, Note, Section } from "../components/ui";
import { act, run } from "../lib/api";
import { useAction, useRun } from "../lib/hooks";
import { onDecided, onEvent, useStore } from "../lib/store";
import { openTitanApp } from "../shell/Desktop";

interface Project { path: string; name: string; kinds: string[]; git: boolean; venv: string | null; commands: Record<string, string> }
const GIT = ["status", "log", "diff", "branch", "remote"] as const;

export default function Developer() {
  const projects = useAction<{ projects: Project[] }>("dev.projects", { depth: 4 });
  const [sel, setSel] = useState<Project | null>(null);
  const [git, setGit] = useState<{ op: string; output: string } | null>(null);
  const [job, setJob] = useState<{ label: string; taskId?: string; approvalId?: number; lines: string[] } | null>(null);
  const [custom, setCustom] = useState("");
  const tasks = useStore((s) => s.tasks);
  const m = useRun();
  const task = job?.taskId ? tasks.find((t) => t.id === job.taskId) : undefined;

  useEffect(() => { setGit(null); if (sel?.git) m.go(async () => setGit(await run("dev.git", { path: sel.path, op: "status" }))); }, [sel?.path]);
  useEffect(() => onEvent("terminal.output", (d: { task_id: string; line: string }) =>
    setJob((j) => (j && j.taskId === d.task_id ? { ...j, lines: [...j.lines, d.line].slice(-400) } : j))), []);
  useEffect(() => onDecided((a) => setJob((j) => {
    if (!j || j.approvalId !== a.id) return j;
    const r = a.result;
    if (r && r.status === "ok") return { ...j, approvalId: undefined, taskId: (r.result as { task_id: string }).task_id };
    return { ...j, approvalId: undefined, lines: [a.status === "denied" ? "You declined; nothing ran." : `Failed: ${r && "error" in r ? r.error : a.status}`] };
  })), []);

  const start = async (label: string, command: string) => {
    if (!sel) return;
    const cmd = sel.venv && /^(python|pytest|pip)\b/.test(command) ? `${sel.venv}/bin/${command}` : command;
    setJob({ label, lines: [] });
    const out = await act<{ task_id: string }>("terminal.run", { command: cmd, cwd: sel.path, background: true });
    if (out.status === "ok") setJob({ label, taskId: out.result.task_id, lines: [] });
    else if (out.status === "approval_required") setJob({ label, approvalId: out.approval_id, lines: [] });
    else setJob({ label, lines: [out.error] });
  };

  return (
    <div className="flex h-full">
      <aside className="scroll w-56 shrink-0 border-r border-line p-2">
        <div className="mb-1 flex items-center justify-between px-1"><span className="label">Projects</span><button className="text-xs text-muted hover:text-text" onClick={projects.reload}>Rescan</button></div>
        {projects.error && <Note>{projects.error}</Note>}
        {(projects.data?.projects ?? []).map((p) => (
          <button key={p.path} data-selected={sel?.path === p.path} className="row block w-full px-2 py-1.5 text-left" onClick={() => setSel(p)}>
            <span className="block truncate text-[13px]">{p.name}</span><span className="block truncate text-[11px] text-muted">{p.kinds.join(", ") || "git"}{p.git ? " · git" : ""}</span>
          </button>
        ))}
        {projects.data && !projects.data.projects.length && <div className="px-2 text-xs text-muted">No projects found under your home directory.</div>}
      </aside>
      {!sel ? <Empty>Select a project to see its Git state and run its build, test and dev commands.</Empty> : (
        <div className="scroll min-w-0 flex-1 space-y-3 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">{sel.name}</h2><span className="truncate font-mono text-xs text-muted">{sel.path}</span>
            <span className="ml-auto flex gap-1.5">
              <button className="btn" onClick={() => openTitanApp("files", { path: sel.path })}>Files</button>
              <button className="btn" onClick={() => openTitanApp("terminal", { cwd: sel.path })}>Terminal</button>
              <button className="btn" onClick={() => m.go(() => run("terminal.run", { command: `code ${JSON.stringify(sel.path)}`, background: true }))} title="Opens VS Code if the `code` command is installed (asks first)">Open in editor</button>
              <button className="btn" onClick={() => openTitanApp("assistant", { prompt: `I'm working on the project at ${sel.path}. ` })}>Ask TITAN</button>
            </span>
          </div>
          {(m.error || m.notice) && <Note kind={m.error ? "error" : "info"}>{m.error ?? m.notice}</Note>}
          <Section title="Run" aside={sel.kinds.includes("python") && (sel.venv ? <span className="text-xs text-ok">virtualenv: {sel.venv}</span> :
            <button className="btn !py-0.5 text-xs" onClick={() => m.go(async () => { await run("dev.venv_create", { path: sel.path }); projects.reload(); setSel({ ...sel, venv: ".venv" }); })}>Create .venv</button>)}>
            <div className="flex flex-wrap gap-2">
              {Object.entries(sel.commands).map(([label, cmd]) => <button key={label} className="btn" title={cmd} onClick={() => start(label, cmd)}>{label}</button>)}
              {sel.kinds.includes("node") && <button className="btn" onClick={() => start("install", "npm install")}>npm install</button>}
              <form className="flex min-w-48 flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) start(custom, custom); }}>
                <input className="field flex-1 font-mono text-xs" placeholder="other command…" aria-label="Custom command" value={custom} onChange={(e) => setCustom(e.target.value)} />
              </form>
            </div>
            {job && (
              <div className="mt-3">
                <div className="mb-1 flex items-center gap-2 text-[13px]"><span className="font-medium">{job.label}</span>
                  {job.approvalId !== undefined ? <Chip value="approval_required">awaiting approval</Chip> : task ? <Chip value={task.status} /> : null}
                  {task && (task.status === "running" || task.status === "queued") && <button className="btn !py-0 text-xs" onClick={() => act("tasks.cancel", { id: task.id })}>Stop</button>}
                  {task?.status === "failed" && <button className="btn !py-0 text-xs" onClick={() => openTitanApp("assistant", { prompt: `Explain this build error from ${sel.path} and how to fix it:\n\n${job.lines.slice(-60).join("\n")}` })}>Explain error</button>}
                </div>
                <pre className="scroll max-h-56 whitespace-pre-wrap break-words rounded-lg border border-line bg-[var(--field)] p-2 font-mono text-xs">{job.lines.join("\n") || (job.approvalId !== undefined ? "Waiting for your approval…" : "…")}</pre>
              </div>
            )}
          </Section>
          <Section title="Git" aside={sel.git && <span className="flex gap-1">{GIT.map((op) => <button key={op} className={`btn !py-0.5 text-xs ${git?.op === op ? "!border-accent" : "btn-ghost"}`} onClick={() => m.go(async () => setGit(await run("dev.git", { path: sel.path, op })))}>{op}</button>)}</span>}>
            {sel.git ? <pre className="scroll max-h-64 whitespace-pre-wrap break-words font-mono text-xs">{git ? git.output || "(no output)" : "…"}</pre> : <span className="text-[13px] text-muted">Not a Git repository.</span>}
          </Section>
        </div>
      )}
    </div>
  );
}
