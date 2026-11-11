import { useEffect, useState } from "react";
import { Bar, Empty, Note, Section, Toggle } from "../components/ui";
import { run } from "../lib/api";
import { formatBytes } from "../lib/format";
import { useAction, useRun } from "../lib/hooks";
import { setPref, usePref, useStore } from "../lib/store";
import { APPS, DEFAULT_DOCK } from "../shell/apps";
import { DEFAULT_SHORTCUTS } from "../shell/Desktop";
import { WIDGETS } from "./Home";

interface Avail { available: boolean; reason?: string }
interface SysStatus {
  display: Avail & { outputs?: { name: string; primary: boolean; width: number; height: number }[] };
  sound: Avail & { volume?: number | null; muted?: boolean };
  network: { interfaces: { name: string; up: boolean | null; addresses: string[] }[]; wifi: { ssid: string; signal: number | null } | null };
  bluetooth: Avail & { powered?: boolean };
  power: { available: boolean; battery: { percent: number; plugged: boolean | null } | null };
  appearance: Avail & { color_scheme?: string };
  storage: { total: number; used: number; percent: number };
}
interface VoiceStatus { stt: { available: boolean; binary: string | null; model: string | null }; tts: { available: boolean; engine: string | null }; microphone: { available: boolean; recorder: string | null }; wake_listening: boolean; missing: string[] }

const ACCENTS = ["#8b5cf6", "#3b9dff", "#22d3ee", "#34d399", "#f472b6", "#fb923c"];
const TABS = ["Appearance", "Desktop", "System", "Notifications", "Voice", "Assistant", "Shortcuts"] as const;
const NOTIFY = ["system", "ai", "download", "app", "reminder", "task", "security"];

function Text({ k, fallback, label, placeholder }: { k: string; fallback: string; label: string; placeholder?: string }) {
  const saved = usePref<string>(k, fallback);
  const [v, setV] = useState(saved);
  useEffect(() => setV(saved), [saved]);
  return (
    <label className="block py-1.5 text-sm">
      <span className="mb-1 block">{label}</span>
      <input className="field w-full" value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={() => v !== saved && setPref(k, v || null)} />
    </label>
  );
}

function Appearance() {
  const mode = usePref<string>("theme.mode", "dark");
  const accent = usePref<string>("theme.accent", ACCENTS[0]);
  const wallpaper = usePref<string>("theme.wallpaper", "aurora");
  const m = useRun();
  const setMode = (v: string) => { setPref("theme.mode", v); m.go(() => run("settings.set_color_scheme", { scheme: v })); };
  return (
    <>
      <Section title="Theme">
        <div className="flex gap-2">{["dark", "light"].map((t) => <button key={t} className={`btn capitalize ${mode === t ? "!border-accent" : ""}`} aria-pressed={mode === t} onClick={() => setMode(t)}>{t}</button>)}</div>
        {m.error && <p className="mt-2 text-xs text-muted">TITAN's theme changed. The GNOME desktop theme was not: {m.error}</p>}
      </Section>
      <Section title="Accent colour">
        <div className="flex items-center gap-2">
          {ACCENTS.map((c) => <button key={c} aria-label={`Accent ${c}`} aria-pressed={accent === c} onClick={() => setPref("theme.accent", c)} className={`h-7 w-7 rounded-full border-2 ${accent === c ? "border-text" : "border-transparent"}`} style={{ background: c }} />)}
          <input type="color" aria-label="Custom accent" value={accent} onChange={(e) => setPref("theme.accent", e.target.value)} className="h-7 w-10 cursor-pointer rounded border border-line bg-transparent" />
        </div>
      </Section>
      <Section title="Wallpaper">
        <div className="flex flex-wrap gap-2">{["aurora", "horizon", "grid", "plain"].map((w) => <button key={w} className={`btn capitalize ${wallpaper === w ? "!border-accent" : ""}`} aria-pressed={wallpaper === w} onClick={() => setPref("theme.wallpaper", w)}>{w}</button>)}</div>
        <Text k="theme.wallpaper" fallback="aurora" label="Or an image in your home folder" placeholder="~/Pictures/wallpaper.jpg" />
      </Section>
    </>
  );
}

function DesktopTab() {
  const dock = usePref<string[]>("dock.titan", DEFAULT_DOCK);
  const size = usePref<number>("dock.size", 44);
  const widgets = usePref<string[]>("home.widgets", [...WIDGETS]);
  const startup = usePref<string[]>("startup.apps", ["home"]);
  const flip = (key: string, list: string[], id: string, order: readonly string[]) =>
    setPref(key, list.includes(id) ? list.filter((x) => x !== id) : order.filter((x) => x === id || list.includes(x)));
  const ids = APPS.map((a) => a.id);
  return (
    <>
      <Section title="Dock">
        <label className="flex items-center gap-3 py-1 text-sm">Icon size<input type="range" min={36} max={64} value={size} aria-label="Dock icon size" onChange={(e) => setPref("dock.size", Number(e.target.value))} /><span className="tabular text-muted">{size}px</span></label>
        <div className="grid grid-cols-2 gap-x-6">{APPS.map((a) => <Toggle key={a.id} label={a.title} checked={dock.includes(a.id)} onChange={() => flip("dock.titan", dock, a.id, ids)} />)}</div>
      </Section>
      <Section title="Home widgets"><div className="grid grid-cols-2 gap-x-6">{WIDGETS.map((w) => <Toggle key={w} label={w[0].toUpperCase() + w.slice(1)} checked={widgets.includes(w)} onChange={() => flip("home.widgets", widgets, w, WIDGETS)} />)}</div></Section>
      <Section title="Open at startup"><div className="grid grid-cols-2 gap-x-6">{APPS.map((a) => <Toggle key={a.id} label={a.title} checked={startup.includes(a.id)} onChange={() => flip("startup.apps", startup, a.id, ids)} />)}</div></Section>
    </>
  );
}

function System() {
  const s = useAction<SysStatus>("settings.status", {}, 10000);
  const m = useRun();
  const d = s.data;
  if (s.error) return <Note>{s.error}</Note>;
  if (!d) return <Empty>Reading system status…</Empty>;
  const na = (a: Avail) => <span className="text-muted">Not available: {a.reason}</span>;
  return (
    <>
      {m.error && <Note>{m.error}</Note>}
      <Section title="Display">{d.display.available ? d.display.outputs!.map((o) => <div key={o.name} className="text-[13px]">{o.name}: {o.width}×{o.height}{o.primary ? " (primary)" : ""}</div>) : na(d.display)}</Section>
      <Section title="Sound">
        {d.sound.available ? (
          <div className="flex items-center gap-3 text-sm">
            <input type="range" min={0} max={100} defaultValue={d.sound.volume ?? 0} aria-label="Volume" onChange={(e) => m.go(() => run("settings.set_volume", { percent: Number(e.target.value) }))} />
            <span className="tabular text-muted">{d.sound.volume ?? "—"}%</span>
            <button className="btn" onClick={() => m.go(async () => { await run("settings.set_mute", { muted: !d.sound.muted }); s.reload(); })}>{d.sound.muted ? "Unmute" : "Mute"}</button>
          </div>
        ) : na(d.sound)}
      </Section>
      <Section title="Network">
        {d.network.wifi && <div className="mb-1 text-[13px]">Wi-Fi: {d.network.wifi.ssid}{d.network.wifi.signal !== null ? ` (${d.network.wifi.signal}%)` : ""}</div>}
        {d.network.interfaces.map((i) => <div key={i.name} className="flex gap-2 text-[13px]"><span className="w-24 shrink-0 font-mono text-xs">{i.name}</span><span className={i.up ? "text-ok" : "text-muted"}>{i.up ? "up" : "down"}</span><span className="truncate text-muted">{i.addresses.join(", ")}</span></div>)}
        {!d.network.interfaces.length && <span className="text-muted">No network interfaces.</span>}
      </Section>
      <Section title="Bluetooth">{d.bluetooth.available ? <span className="text-[13px]">{d.bluetooth.powered ? "On" : "Off"}</span> : na(d.bluetooth)}</Section>
      <Section title="Power">{d.power.battery ? <span className="text-[13px]">{d.power.battery.percent.toFixed(0)}%{d.power.battery.plugged ? ", charging" : ""}</span> : <span className="text-muted">No battery reported (desktop or virtual machine).</span>}</Section>
      <Section title="Storage"><Bar percent={d.storage.percent} /><div className="tabular mt-1 text-[13px] text-muted">{formatBytes(d.storage.used)} used of {formatBytes(d.storage.total)}</div></Section>
    </>
  );
}

function Notifications() {
  const muted = usePref<string[]>("notifications.muted", []);
  const desktop = usePref<boolean>("notifications.desktop", false);
  return (
    <>
      <Section title="Show notifications for">{NOTIFY.map((c) => <Toggle key={c} label={c[0].toUpperCase() + c.slice(1)} checked={!muted.includes(c)} onChange={(on) => setPref("notifications.muted", on ? muted.filter((x) => x !== c) : [...muted, c])} />)}</Section>
      <Section title="Delivery"><Toggle label="Also show as GNOME desktop notifications" checked={desktop} onChange={(v) => setPref("notifications.desktop", v)} /></Section>
    </>
  );
}

function Voice() {
  const v = useAction<VoiceStatus>("voice.status", {}, 5000);
  const spoken = usePref<boolean>("voice.spoken_replies", true);
  const continuous = usePref<boolean>("voice.continuous", false);
  const rate = usePref<number>("voice.rate", 165);
  const m = useRun();
  const d = v.data;
  const dot = (ok: boolean) => <span className={ok ? "text-ok" : "text-warn"}>{ok ? "Ready" : "Not set up"}</span>;
  return (
    <>
      <Section title="Status">
        {d ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
            <dt className="text-muted">Speech-to-text</dt><dd>{dot(d.stt.available)} {d.stt.binary && <span className="text-muted">· whisper.cpp</span>}</dd>
            <dt className="text-muted">Text-to-speech</dt><dd>{dot(d.tts.available)} {d.tts.engine && <span className="text-muted">· {d.tts.engine}</span>}</dd>
            <dt className="text-muted">Microphone</dt><dd>{dot(d.microphone.available)} {d.microphone.recorder && <span className="text-muted">· {d.microphone.recorder}</span>}</dd>
            <dt className="text-muted">Wake word</dt><dd>{d.wake_listening ? <span className="text-ok">Listening</span> : "Off"}</dd>
          </dl>
        ) : <Empty>{v.error ?? "Checking…"}</Empty>}
        {d && d.missing.length > 0 && <div className="mt-2"><Note kind="warn">Missing: {d.missing.join("; ")}</Note></div>}
        {(m.error || m.notice) && <div className="mt-2"><Note kind={m.error ? "error" : "info"}>{m.error ?? m.notice}</Note></div>}
        <div className="mt-3 flex gap-2">
          <button className="btn" disabled={m.busy} onClick={() => m.go(async () => { await run(d?.wake_listening ? "voice.wake_stop" : "voice.wake_start"); v.reload(); })}>{d?.wake_listening ? "Stop wake-word listening" : "Start wake-word listening"}</button>
          <button className="btn" disabled={m.busy} onClick={() => m.go(() => run("voice.speak", { text: "This is TITAN." }))}>Test voice</button>
        </div>
      </Section>
      <Section title="Options">
        <Text k="voice.wake_word" fallback="hey titan" label="Wake phrase" />
        <Text k="voice.voice" fallback="en" label="Voice (espeak-ng voice name, e.g. en, en-us, en-gb)" />
        <label className="flex items-center gap-3 py-1 text-sm">Speaking rate<input type="range" min={110} max={240} value={rate} aria-label="Speaking rate" onChange={(e) => setPref("voice.rate", Number(e.target.value))} /><span className="tabular text-muted">{rate} wpm</span></label>
        <Toggle label="Speak replies aloud" checked={spoken} onChange={(x) => setPref("voice.spoken_replies", x)} />
        <Toggle label="Continuous conversation (no wake word between turns)" checked={continuous} onChange={(x) => setPref("voice.continuous", x)} />
      </Section>
    </>
  );
}

function AssistantTab() {
  return (
    <Section title="Personality">
      <Text k="ai.personality" fallback="" label="How should TITAN talk to you?" placeholder="e.g. concise and a little dry" />
      <p className="mt-2 text-xs text-muted">The API key is read from the ANTHROPIC_API_KEY environment variable of TITAN Core and is never shown or stored here. What TITAN may do without asking is set in Security Centre → Permissions.</p>
    </Section>
  );
}

function Shortcuts() {
  const saved = usePref<Record<string, string>>("shortcuts", {});
  const map = { ...DEFAULT_SHORTCUTS, ...saved };
  const dupes = Object.values(map).filter((v, i, all) => all.indexOf(v) !== i);
  return (
    <Section title="Keyboard shortcuts" aside={<button className="btn !py-0.5 text-xs" onClick={() => setPref("shortcuts", null)}>Reset</button>}>
      {Object.keys(DEFAULT_SHORTCUTS).map((k) => (
        <label key={k} className="flex items-center justify-between gap-3 py-1 text-sm">
          <span className="capitalize">{k.replace(/(\d)/, " $1")}</span>
          <input className={`field w-40 font-mono text-xs ${dupes.includes(map[k]) ? "!border-danger" : ""}`} aria-label={`Shortcut for ${k}`} defaultValue={map[k]} key={map[k]}
            onBlur={(e) => { const v = e.target.value.trim().toLowerCase(); if (v && v !== map[k]) setPref("shortcuts", { ...saved, [k]: v }); }} />
        </label>
      ))}
      {dupes.length > 0 && <Note kind="warn">Two actions share {dupes[0]}; only the first will fire.</Note>}
      <p className="mt-2 text-xs text-muted">Format: modifiers then key, e.g. ctrl+k, alt+1, ctrl+shift+p. GNOME's own shortcuts (Super key) take priority over these.</p>
    </Section>
  );
}

export default function Settings() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Appearance");
  const live = useStore((s) => s.link === "live");
  const Body = { Appearance, Desktop: DesktopTab, System, Notifications, Voice, Assistant: AssistantTab, Shortcuts }[tab];
  return (
    <div className="flex h-full">
      <nav className="w-40 shrink-0 space-y-0.5 border-r border-line p-2" role="tablist" aria-orientation="vertical">
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} data-selected={tab === t} className="row block w-full px-3 py-1.5 text-left" onClick={() => setTab(t)}>{t}</button>)}
      </nav>
      <div className="scroll min-w-0 flex-1 space-y-3 p-3">{live ? <Body /> : <Empty>TITAN Core is offline; settings cannot be read or saved.</Empty>}</div>
    </div>
  );
}
