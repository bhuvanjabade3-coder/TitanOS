import { useEffect, useRef, useState } from "react";
import { Chip, Empty, Icon, Note } from "../components/ui";
import { act, post, req, type Step } from "../lib/api";
import { formatWhen } from "../lib/format";
import { decide, onDecided, onEvent, useStore } from "../lib/store";

interface Msg { role: "user" | "assistant"; text: string; steps?: Step[]; error?: string; via?: string }
interface Conv { id: number; title: string; updated_at: string }
interface ChatOut { conversation_id: number; reply: string; steps: Step[]; pending_approvals: number[]; stop_reason: string }

function StepRow({ s }: { s: Step }) {
  const pending = useStore((st) => st.approvals.some((a) => a.id === s.approval_id));
  return (
    <div className="flex items-start gap-2 text-xs">
      <Chip value={s.status} />
      <span className="min-w-0 flex-1 break-words font-mono text-muted">
        {s.action}{s.input && Object.keys(s.input).length > 0 ? ` ${JSON.stringify(s.input).slice(0, 160)}` : ""}
        {s.detail && <span className="block font-sans text-text/80">{s.detail}</span>}
      </span>
      {s.status === "approval_required" && s.approval_id !== undefined && pending && (
        <span className="flex shrink-0 gap-1">
          <button className="btn !px-2 !py-0.5 text-xs" onClick={() => decide(s.approval_id!, false)}>Deny</button>
          <button className="btn btn-primary !px-2 !py-0.5 text-xs" onClick={() => decide(s.approval_id!, true)}>Approve</button>
        </span>
      )}
    </div>
  );
}

export default function Assistant({ props }: { props?: Record<string, unknown> }) {
  const [convs, setConvs] = useState<Conv[]>([]);
  const [cid, setCid] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState(typeof props?.prompt === "string" ? props.prompt : "");
  const [mode, setMode] = useState<"execute" | "plan">("execute");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<Step[]>([]);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const cidRef = useRef(cid);
  cidRef.current = cid;

  const loadConvs = () => req<Conv[]>("/api/ai/conversations").then(setConvs).catch(() => {});
  const loadConv = async (id: number) => {
    const c = await req<{ messages: { role: Msg["role"]; content: Msg }[] }>(`/api/ai/conversations/${id}`);
    setCid(id);
    setMsgs(c.messages.map((m) => ({ ...m.content, role: m.role })));
  };
  useEffect(() => { loadConvs(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, live, busy]);
  useEffect(() => onEvent("ai.step", (d) => {
    if (d.status === "running") setLive((l) => [...l, { action: d.action, status: "running" }]);
    else setLive((l) => [...l.filter((x) => !(x.action === d.action && x.status === "running")), d]);
  }), []);
  // When an approval for this conversation is decided, record what really happened.
  useEffect(() => onDecided((a) => {
    setMsgs((ms) => {
      if (!ms.some((m) => m.steps?.some((s) => s.approval_id === a.id))) return ms;
      const outcome = a.status === "executed" ? "Approved and completed" : a.status === "denied" ? "You declined" : `Approved but failed: ${a.result && "error" in a.result ? a.result.error : a.status}`;
      return ms.map((m) => ({ ...m, steps: m.steps?.map((s) => s.approval_id === a.id
        ? { ...s, status: a.status === "executed" ? "ok" : a.status === "denied" ? "denied" : "error", detail: `${outcome}: ${a.summary}` } : s) }));
    });
  }), []);
  useEffect(() => onEvent("voice.command", () => { loadConvs(); }), []);

  const send = async (text: string) => {
    text = text.trim();
    if (!text || busy) return;
    setInput(""); setError(null); setBusy(true); setLive([]);
    setMsgs((m) => [...m, { role: "user", text }]);
    try {
      const out = await post<ChatOut>("/api/ai/chat", { message: text, conversation_id: cidRef.current, mode });
      setCid(out.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", text: out.reply, steps: out.steps }]);
      loadConvs();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false); setLive([]);
    }
  };

  const talk = async () => {
    setListening(true); setError(null);
    const out = await act<{ transcript: string }>("voice.listen", { seconds: 6 }).catch((e) => ({ status: "error" as const, error: (e as Error).message }));
    setListening(false);
    if (out.status === "ok") { if (out.result.transcript) send(out.result.transcript); else setError("I didn't catch anything."); }
    else if (out.status !== "approval_required") setError(out.error);
  };

  return (
    <div className="flex h-full">
      <aside className="scroll flex w-48 shrink-0 flex-col gap-1 border-r border-line p-2">
        <button className="btn btn-primary mb-1" onClick={() => { setCid(null); setMsgs([]); setError(null); }}>New conversation</button>
        {convs.map((c) => (
          <div key={c.id} data-selected={c.id === cid} className="row group flex cursor-pointer items-center gap-1 px-2 py-1.5" onClick={() => loadConv(c.id)}>
            <span className="min-w-0 flex-1"><span className="block truncate text-[13px]">{c.title}</span><span className="text-[11px] text-muted">{formatWhen(c.updated_at)}</span></span>
            <button className="opacity-0 group-hover:opacity-100" aria-label={`Delete conversation ${c.title}`}
              onClick={async (e) => { e.stopPropagation(); await req(`/api/ai/conversations/${c.id}`, { method: "DELETE" }); if (c.id === cid) { setCid(null); setMsgs([]); } loadConvs(); }}>
              <Icon name="x" size={12} />
            </button>
          </div>
        ))}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="scroll min-h-0 flex-1 space-y-3 p-4">
          {!msgs.length && !busy && (
            <Empty>
              <div>
                <div className="mb-3 text-base text-text">Tell TITAN what you want done.</div>
                <div className="flex flex-wrap justify-center gap-2">
                  {["Create a folder called Projects", "Find my Python project", "What is using the most memory?", "Open my browser and search for Python tutorials"].map((s) => (
                    <button key={s} className="btn" onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </div>
            </Empty>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
              <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 ${m.role === "user" ? "bg-accent/20" : "border border-line bg-[var(--field)]"}`}>
                {m.steps && m.steps.length > 0 && <div className="mb-2 space-y-1.5 border-b border-line pb-2">{m.steps.map((s, j) => <StepRow key={j} s={s} />)}</div>}
                {m.text && <div className="whitespace-pre-wrap break-words leading-relaxed">{m.text}</div>}
                {m.error && <div className="text-danger">{m.error}</div>}
                {m.via === "voice" && <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">voice</div>}
              </div>
            </div>
          ))}
          {busy && (
            <div className="max-w-[85%] rounded-2xl border border-line bg-[var(--field)] px-3.5 py-2.5">
              {live.map((s, j) => <StepRow key={j} s={s} />)}
              <div className="mt-1 animate-pulse text-muted">{mode === "plan" ? "Planning…" : "Working…"}</div>
            </div>
          )}
          {error && <Note>{error}</Note>}
          <div ref={end} />
        </div>
        <form className="flex items-end gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <div className="flex overflow-hidden rounded-lg border border-line text-xs" role="radiogroup" aria-label="Mode">
            {(["execute", "plan"] as const).map((x) => (
              <button type="button" key={x} role="radio" aria-checked={mode === x} onClick={() => setMode(x)}
                className={`px-2.5 py-2 capitalize ${mode === x ? "bg-accent/25" : "text-muted"}`} title={x === "plan" ? "Read-only: TITAN proposes a plan and changes nothing" : "TITAN carries out permitted actions"}>{x}</button>
            ))}
          </div>
          <textarea className="field max-h-32 flex-1 resize-none" rows={1} value={input} placeholder={mode === "plan" ? "Describe what to plan…" : "Ask TITAN…"} aria-label="Message"
            onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
          <button type="button" className={`btn !px-2.5 ${listening ? "!border-danger text-danger" : ""}`} aria-label="Push to talk" title="Push to talk (records 6 seconds, transcribed locally)" disabled={busy || listening} onClick={talk}><Icon name="mic" size={16} /></button>
          <button className="btn btn-primary" disabled={busy || !input.trim()}>Send</button>
        </form>
      </div>
    </div>
  );
}
