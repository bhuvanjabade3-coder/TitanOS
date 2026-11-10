export interface Metrics {
  ts: number;
  cpu: { percent: number; per_core: number[]; cores: number; load_avg: number[] };
  memory: { total: number; used: number; percent: number };
  disk: { total: number; used: number; percent: number };
  network: { bytes_sent: number; bytes_recv: number };
  battery: { percent: number; plugged: boolean | null; seconds_left: number | null } | null;
  temperatures: Record<string, number> | null;
}

export interface Status {
  version: string;
  ai_configured: boolean;
  system: { hostname: string; os: string; kernel: string; arch: string; python: string; boot_time: number };
}

export interface Proc {
  pid: number;
  name: string;
  user: string | null;
  cpu_percent: number;
  rss: number;
  status: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal });
  if (!res.ok) throw new ApiError(res.status, `${path} → ${res.status}`);
  return (await res.json()) as T;
}
