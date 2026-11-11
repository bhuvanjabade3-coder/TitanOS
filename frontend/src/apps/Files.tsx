import { useEffect, useState } from "react";
import { Bar, Empty, Icon, Note } from "../components/ui";
import { rawUrl, run, type Entry } from "../lib/api";
import { formatBytes, formatWhen } from "../lib/format";
import { useAction, useRun } from "../lib/hooks";
import { onDecided } from "../lib/store";

interface Listing { path: string; parent: string | null; entries: Entry[] }
interface Preview { text: string | null; binary: boolean; truncated: boolean; size: number; mime: string | null }
interface Storage { home: { path: string; total: number; used: number; free: number } }

export default function Files({ props }: { props?: Record<string, unknown> }) {
  const [path, setPath] = useState(typeof props?.path === "string" ? props.path : "~");
  const [hidden, setHidden] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [clip, setClip] = useState<{ op: "copy" | "move"; paths: string[] } | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ results: Entry[]; complete: boolean } | null>(null);
  const [preview, setPreview] = useState<{ entry: Entry; data: Preview | null; error?: string } | null>(null);
  const list = useAction<Listing>("fs.list", { path, show_hidden: hidden });
  const storage = useAction<Storage>("fs.storage");
  const m = useRun();

  useEffect(() => { setSel(new Set()); setResults(null); setQuery(""); }, [path]);
  useEffect(() => onDecided(() => { setPreview(null); list.reload(); storage.reload(); }), [list.reload, storage.reload]);

  const entries = results?.results ?? list.data?.entries ?? [];
  const chosen = [...sel];
  const mutate = (fn: () => Promise<unknown>) => m.go(async () => { await fn(); setSel(new Set()); setPreview(null); list.reload(); storage.reload(); });

  const openEntry = async (e: Entry) => {
    if (e.is_dir) return setPath(e.path);
    setPreview({ entry: e, data: null });
    if (e.mime?.startsWith("image/")) return;
    try { setPreview({ entry: e, data: await run<Preview>("fs.read", { path: e.path, max_bytes: 200000 }) }); }
    catch (err) { setPreview({ entry: e, data: null, error: (err as Error).message }); }
  };
  const toggle = (p: string) => setSel((s) => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n; });
  const search = () => m.go(async () => setResults(await run("fs.search", { query, root: path, show_hidden: hidden })));
  const crumbs = (list.data?.path ?? "").split("/").filter(Boolean);
  const home = storage.data?.home;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-2">
        <button className="btn !px-2" aria-label="Up" disabled={!list.data?.parent} onClick={() => list.data?.parent && setPath(list.data.parent)}><Icon name="up" size={15} /></button>
        <button className="btn !px-2" aria-label="Home" onClick={() => setPath("~")}><Icon name="home" size={15} /></button>
        <button className="btn !px-2" aria-label="Refresh" onClick={list.reload}><Icon name="refresh" size={15} /></button>
        <nav className="scroll flex min-w-0 flex-1 items-center gap-0.5 text-[13px]" aria-label="Path">
          {crumbs.map((c, i) => (
            <span key={i} className="flex shrink-0 items-center gap-0.5">
              <span className="text-muted">/</span>
              <button className="rounded px-1 hover:bg-line" onClick={() => setPath("/" + crumbs.slice(0, i + 1).join("/"))}>{c}</button>
            </span>
          ))}
        </nav>
        <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); if (query.trim()) search(); }}>
          <input className="field w-44" placeholder="Search here (name or *.ext)" aria-label="Search files" value={query} onChange={(e) => setQuery(e.target.value)} />
          {results && <button type="button" className="btn" onClick={() => { setResults(null); setQuery(""); }}>Clear</button>}
        </form>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-2 py-1.5">
        <button className="btn" onClick={() => { const name = prompt("New folder name"); if (name) mutate(() => run("fs.mkdir", { path: `${list.data!.path}/${name}` })); }}>New folder</button>
        <button className="btn" disabled={chosen.length !== 1} onClick={() => { const cur = chosen[0].split("/").pop()!; const name = prompt("Rename to", cur); if (name && name !== cur) mutate(() => run("fs.rename", { path: chosen[0], new_name: name })); }}>Rename</button>
        <button className="btn" disabled={!chosen.length} onClick={() => { setClip({ op: "copy", paths: chosen }); setSel(new Set()); }}>Copy</button>
        <button className="btn" disabled={!chosen.length} onClick={() => { setClip({ op: "move", paths: chosen }); setSel(new Set()); }}>Cut</button>
        <button className="btn" disabled={!clip || !!results} onClick={() => clip && mutate(async () => { await run(`fs.${clip.op}`, { sources: clip.paths, dest_dir: list.data!.path }); setClip(null); })}>
          Paste{clip ? ` ${clip.paths.length} (${clip.op})` : ""}
        </button>
        <button className="btn" disabled={!chosen.length} onClick={() => mutate(() => run("fs.trash", { paths: chosen }))}>Move to Trash</button>
        <button className="btn btn-danger" disabled={!chosen.length} title="Always asks for confirmation" onClick={() => mutate(() => run("fs.delete", { paths: chosen }))}>Delete permanently</button>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-muted"><input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />Hidden files</label>
      </div>
      {(m.error || m.notice || list.error) && <div className="p-2"><Note kind={m.error || list.error ? "error" : "info"}>{m.error ?? m.notice ?? list.error}</Note></div>}
      <div className="flex min-h-0 flex-1">
        <div className="scroll min-w-0 flex-1 p-1.5">
          {results && <div className="px-2 py-1 text-xs text-muted">{results.results.length} result(s) for “{query}”{results.complete ? "" : " — search stopped early; narrow it down"}</div>}
          {entries.map((e) => (
            <div key={e.path} data-selected={sel.has(e.path)} className="row flex items-center gap-2 px-2 py-1.5">
              <input type="checkbox" aria-label={`Select ${e.name}`} checked={sel.has(e.path)} onChange={() => toggle(e.path)} />
              <button className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => openEntry(e)}>
                <Icon name={e.is_dir ? "folder" : "file"} size={16} className={e.is_dir ? "text-accent" : "text-muted"} />
                <span className="min-w-0 flex-1 truncate">{e.name}{results && <span className="ml-2 text-xs text-muted">{e.path.slice(0, -e.name.length - 1)}</span>}</span>
              </button>
              <span className="tabular w-20 text-right text-xs text-muted">{e.is_dir ? "" : formatBytes(e.size)}</span>
              <span className="w-20 text-right text-xs text-muted">{formatWhen(e.mtime)}</span>
            </div>
          ))}
          {!entries.length && !list.loading && !list.error && <Empty>{results ? "No matches." : "This folder is empty."}</Empty>}
        </div>
        {preview && (
          <aside className="flex w-[42%] min-w-0 flex-col border-l border-line">
            <header className="flex items-center gap-2 border-b border-line px-3 py-2">
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{preview.entry.name}</span>
              <span className="text-xs text-muted">{formatBytes(preview.entry.size)}</span>
              <button aria-label="Close preview" onClick={() => setPreview(null)}><Icon name="x" size={14} /></button>
            </header>
            <div className="scroll min-h-0 flex-1 p-3">
              {preview.error ? <Note>{preview.error}</Note>
                : preview.entry.mime?.startsWith("image/") ? <img src={rawUrl(preview.entry.path)} alt={preview.entry.name} className="max-w-full rounded-lg" />
                : !preview.data ? <Empty>Loading…</Empty>
                : preview.data.binary ? <Empty>No preview for this file type ({preview.data.mime ?? "binary"}).</Empty>
                : <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">{preview.data.text}{preview.data.truncated && "\n\n… (preview truncated)"}</pre>}
            </div>
          </aside>
        )}
      </div>
      <footer className="flex items-center gap-3 border-t border-line px-3 py-1.5 text-xs text-muted">
        <span>{entries.length} item(s){chosen.length ? ` · ${chosen.length} selected` : ""}</span>
        {home && (<><Bar percent={(home.used / home.total) * 100} className="ml-auto w-40" /><span className="tabular">{formatBytes(home.free)} free of {formatBytes(home.total)}</span></>)}
      </footer>
    </div>
  );
}
