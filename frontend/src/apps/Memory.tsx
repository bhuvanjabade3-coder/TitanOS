import { useState } from "react";
import { Empty, Icon, Note, Section } from "../components/ui";
import { run } from "../lib/api";
import { formatWhen } from "../lib/format";
import { useAction, useRun } from "../lib/hooks";

interface Mem { id: number; kind: string; content: string; source: string; updated_at: string }
interface Reminder { id: number; text: string; due_at: string; done: number }
const KINDS = ["preference", "project", "fact", "app", "summary"];

export default function Memory() {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("fact");
  const [text, setText] = useState("");
  const [editing, setEditing] = useState<{ id: number; content: string } | null>(null);
  const [rText, setRText] = useState("");
  const [due, setDue] = useState("");
  const mems = useAction<Mem[]>("memory.search", { query });
  const rems = useAction<Reminder[]>("reminders.list", {}, 15000);
  const m = useRun();
  const change = (fn: () => Promise<unknown>) => m.go(async () => { await fn(); mems.reload(); rems.reload(); });
  const exportAll = () => m.go(async () => {
    const data = await run("memory.export");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    a.download = "titan-memory.json"; a.click(); URL.revokeObjectURL(a.href);
  });
  return (
    <div className="scroll grid h-full auto-rows-min gap-3 p-3 md:grid-cols-5">
      <Section title="What TITAN remembers" className="md:col-span-3" aside={<button className="btn !py-0.5 text-xs" onClick={exportAll}>Export JSON</button>}>
        <p className="mb-2 text-xs text-muted">Nothing is stored unless you add it here or approve a suggestion from the assistant.</p>
        <input className="field mb-2 w-full" placeholder="Search memory…" aria-label="Search memory" value={query} onChange={(e) => setQuery(e.target.value)} />
        {(m.error || mems.error) && <div className="mb-2"><Note>{m.error ?? mems.error}</Note></div>}
        {(mems.data ?? []).map((x) => (
          <div key={x.id} className="flex items-start gap-2 border-t border-line py-2 first:border-0">
            {editing?.id === x.id ? (
              <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); change(async () => { await run("memory.update", editing); setEditing(null); }); }}>
                <input className="field flex-1" autoFocus aria-label="Edit memory" value={editing.content} onChange={(e) => setEditing({ ...editing, content: e.target.value })} />
                <button className="btn btn-primary">Save</button><button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button>
              </form>
            ) : (
              <>
                <div className="min-w-0 flex-1"><div className="break-words">{x.content}</div><div className="text-[11px] text-muted">{x.kind} · added by {x.source === "user" ? "you" : `${x.source} (approved)`} · {formatWhen(x.updated_at)}</div></div>
                <button className="btn btn-ghost !px-2 text-xs" onClick={() => setEditing({ id: x.id, content: x.content })}>Edit</button>
                <button className="btn btn-ghost !px-2 text-danger" aria-label={`Delete memory ${x.id}`} onClick={() => change(() => run("memory.delete", { id: x.id }))}><Icon name="x" size={13} /></button>
              </>
            )}
          </div>
        ))}
        {mems.data && !mems.data.length && <Empty>{query ? "Nothing matches." : "Nothing stored yet."}</Empty>}
        <form className="mt-3 flex gap-2 border-t border-line pt-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) change(async () => { await run("memory.save", { content: text, kind }); setText(""); }); }}>
          <select className="field" aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select>
          <input className="field flex-1" placeholder="Add something to remember…" aria-label="New memory" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="btn btn-primary" disabled={!text.trim() || m.busy}>Add</button>
        </form>
      </Section>
      <Section title="Reminders" className="md:col-span-2">
        {(rems.data ?? []).map((r) => (
          <div key={r.id} className={`flex items-center gap-2 border-t border-line py-1.5 text-[13px] first:border-0 ${r.done ? "opacity-50" : ""}`}>
            <div className="min-w-0 flex-1"><div className="truncate">{r.text}</div><div className="text-[11px] text-muted">{new Date(r.due_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}{r.done ? " · delivered" : ""}</div></div>
            <button className="btn btn-ghost !px-2" aria-label={`Delete reminder ${r.text}`} onClick={() => change(() => run("reminders.delete", { id: r.id }))}><Icon name="x" size={13} /></button>
          </div>
        ))}
        {rems.data && !rems.data.length && <Empty>No reminders.</Empty>}
        <form className="mt-3 space-y-2 border-t border-line pt-3" onSubmit={(e) => { e.preventDefault(); change(async () => { await run("reminders.add", { text: rText, due_at: new Date(due).toISOString() }); setRText(""); setDue(""); }); }}>
          <input className="field w-full" placeholder="Remind me to…" aria-label="Reminder text" value={rText} onChange={(e) => setRText(e.target.value)} />
          <div className="flex gap-2"><input className="field flex-1" type="datetime-local" aria-label="When" value={due} onChange={(e) => setDue(e.target.value)} /><button className="btn btn-primary" disabled={!rText.trim() || !due || m.busy}>Add</button></div>
        </form>
      </Section>
    </div>
  );
}
