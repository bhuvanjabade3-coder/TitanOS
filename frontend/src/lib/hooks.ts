import { useCallback, useEffect, useRef, useState } from "react";
import { act, NeedsApproval, wsUrl, type Metrics } from "./api";
import { useStore } from "./store";

/** Load an action's result; exposes loading, error and a reload function.
 *  While TITAN Core is offline it holds no data rather than stale data. */
export function useAction<T>(name: string, params: Record<string, unknown> = {}, pollMs = 0) {
  const live = useStore((s) => s.link === "live");
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const key = JSON.stringify(params);
  const seq = useRef(0);
  const reload = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const out = await act<T>(name, JSON.parse(key));
      if (mine !== seq.current) return;
      if (out.status === "ok") { setData(out.result); setError(null); }
      else setError(out.status === "approval_required" ? `Needs approval: ${out.summary}` : out.error);
    } catch (e) {
      if (mine === seq.current) setError((e as Error).message);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [name, key]);
  useEffect(() => {
    if (!live) { setData(null); return; }
    setLoading(true);
    reload();
    if (!pollMs) return;
    const t = setInterval(reload, pollMs);
    return () => clearInterval(t);
  }, [reload, live, pollMs]);
  return { data, error, loading, reload };
}

/** Wrap a mutation: tracks busy state and turns failures into a message. A
 *  NeedsApproval is not an error; the shell's approval dialog handles it. */
export function useRun() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const go = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null); setNotice(null);
    try {
      return await fn();
    } catch (e) {
      if (e instanceof NeedsApproval) setNotice(e.message);
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, notice, go, clear: () => { setError(null); setNotice(null); } };
}

export function useMetrics(history = 60) {
  const [current, setCurrent] = useState<Metrics | null>(null);
  const [series, setSeries] = useState<Metrics[]>([]);
  const [live, setLive] = useState(false);
  useEffect(() => {
    let ws: WebSocket | null = null, timer: ReturnType<typeof setTimeout> | undefined, closed = false, attempt = 0;
    const connect = () => {
      ws = new WebSocket(wsUrl("/ws/metrics"));
      ws.onmessage = (e) => {
        attempt = 0;
        const m = JSON.parse(e.data) as Metrics;
        setCurrent(m); setLive(true);
        setSeries((s) => [...s, m].slice(-history));
      };
      ws.onclose = () => {
        if (closed) return;
        setLive(false); setCurrent(null); setSeries([]); // no stale numbers
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10000));
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); ws?.close(); };
  }, [history]);
  return { current, series, live };
}

export function useClock(everyMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(t);
  }, [everyMs]);
  return now;
}
