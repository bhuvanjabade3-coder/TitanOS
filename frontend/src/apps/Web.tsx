import { useState } from "react";
import { Empty, Icon, Note, Section } from "../components/ui";
import { run } from "../lib/api";
import { useAction, useRun } from "../lib/hooks";
import { openTitanApp } from "../shell/Desktop";

interface Page { url: string; title: string; text: string; truncated: boolean; links: { text: string; url: string }[] }
interface Bookmark { id: number; title: string; url: string }

export default function Web() {
  const [input, setInput] = useState("");
  const [page, setPage] = useState<Page | null>(null);
  const marks = useAction<Bookmark[]>("bookmarks.list");
  const m = useRun();
  const isUrl = /^(https?:\/\/)?[\w-]+(\.[\w-]+)+(\/\S*)?$/i.test(input.trim());
  const read = (url: string) => m.go(async () => { setPage(null); setPage(await run<Page>("browser.fetch", { url })); });
  const change = (fn: () => Promise<unknown>) => m.go(async () => { await fn(); marks.reload(); });
  return (
    <div className="flex h-full flex-col">
      <form className="flex gap-2 border-b border-line p-2" onSubmit={(e) => { e.preventDefault(); if (input.trim()) m.go(() => run(isUrl ? "browser.open" : "browser.search", isUrl ? { url: input.trim() } : { query: input.trim() })); }}>
        <input className="field flex-1" placeholder="Search the web or enter an address" aria-label="Search or address" value={input} onChange={(e) => setInput(e.target.value)} />
        <button className="btn btn-primary" disabled={!input.trim()}>{isUrl ? "Open in browser" : "Search"}</button>
        <button type="button" className="btn" disabled={!isUrl || m.busy} onClick={() => read(input.trim())} title="Fetch the page text here, without opening the browser">Read here</button>
        <button type="button" className="btn" disabled={!isUrl} onClick={() => change(() => run("bookmarks.add", { url: input.trim(), title: page?.title || input.trim() }))}>Bookmark</button>
        <button type="button" className="btn" disabled={!isUrl} onClick={() => m.go(() => run("browser.download", { url: input.trim() }))} title="Asks for approval, then downloads to ~/Downloads">Download</button>
      </form>
      {(m.error || m.notice) && <div className="p-2"><Note kind={m.error ? "error" : "info"}>{m.error ?? m.notice}</Note></div>}
      <div className="flex min-h-0 flex-1">
        <aside className="scroll w-56 shrink-0 border-r border-line p-2">
          <div className="label mb-1 px-1">Bookmarks</div>
          {(marks.data ?? []).map((b) => (
            <div key={b.id} className="row group flex items-center gap-1 px-2 py-1.5">
              <button className="min-w-0 flex-1 truncate text-left text-[13px]" title={b.url} onClick={() => { setInput(b.url); m.go(() => run("browser.open", { url: b.url })); }}>{b.title}</button>
              <button className="opacity-0 group-hover:opacity-100" aria-label={`Delete bookmark ${b.title}`} onClick={() => change(() => run("bookmarks.delete", { id: b.id }))}><Icon name="x" size={12} /></button>
            </div>
          ))}
          {marks.data && !marks.data.length && <div className="px-2 text-xs text-muted">None yet.</div>}
        </aside>
        <div className="scroll min-w-0 flex-1 p-3">
          {m.busy && !page && <Empty>Fetching…</Empty>}
          {!page && !m.busy && <Empty>Pages open in your default browser. “Read here” fetches a public page's text so you can read it or have TITAN summarise it. TITAN does not store website passwords or sign in for you.</Empty>}
          {page && (
            <Section title={page.title || page.url} aside={<button className="btn btn-primary !py-0.5 text-xs" onClick={() => openTitanApp("assistant", { prompt: `Summarise this page: ${page.url}` })}>Summarise with TITAN</button>}>
              <div className="mb-2 break-all font-mono text-xs text-muted">{page.url}</div>
              <div className="whitespace-pre-wrap break-words text-[13px] leading-relaxed">{page.text}{page.truncated && "\n\n… (truncated)"}</div>
              {page.links.length > 0 && <div className="mt-3 border-t border-line pt-2">{page.links.slice(0, 20).map((l, i) => <button key={i} className="mr-2 text-xs text-azure hover:underline" onClick={() => { setInput(l.url); read(l.url); }}>{l.text}</button>)}</div>}
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
