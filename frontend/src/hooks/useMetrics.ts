import { useEffect, useRef, useState } from "react";
import type { Metrics } from "../lib/api";

export type Link = "connecting" | "live" | "offline";

/** Live metrics over WebSocket with backoff reconnect. Keeps the previous
 *  sample so callers can derive rates; never fabricates data while offline. */
export function useMetrics(url = "/ws/metrics") {
  const [link, setLink] = useState<Link>("connecting");
  const [current, setCurrent] = useState<Metrics | null>(null);
  const [previous, setPrevious] = useState<Metrics | null>(null);
  const last = useRef<Metrics | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    let attempt = 0;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}${url}`);
      ws.onmessage = (e) => {
        attempt = 0;
        const m = JSON.parse(e.data) as Metrics;
        setPrevious(last.current);
        last.current = m;
        setCurrent(m);
        setLink("live");
      };
      ws.onclose = () => {
        if (closed) return;
        setLink("offline");
        last.current = null;
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10000));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [url]);

  return { link, current, previous };
}
