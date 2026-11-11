import { motion } from "framer-motion";

const R = 42;
const C = 2 * Math.PI * R;

/** Circular gauge. `percent === null` renders an explicit "no data" state. */
export function Gauge({ label, percent, detail }: { label: string; percent: number | null; detail?: string }) {
  const p = percent === null ? 0 : Math.min(100, Math.max(0, percent));
  return (
    <div className="flex items-center gap-4" role="group" aria-label={label}>
      <svg viewBox="0 0 100 100" className="h-20 w-20 -rotate-90">
        <defs>
          <linearGradient id="titan-arc" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" />
            <stop offset="100%" stopColor="var(--color-azure)" />
          </linearGradient>
        </defs>
        <circle cx="50" cy="50" r={R} fill="none" stroke="var(--color-line)" strokeWidth="7" />
        <motion.circle
          cx="50" cy="50" r={R} fill="none" stroke="url(#titan-arc)" strokeWidth="7" strokeLinecap="round"
          strokeDasharray={C}
          initial={false}
          animate={{ strokeDashoffset: C * (1 - p / 100) }}
          transition={{ type: "spring", stiffness: 60, damping: 18 }}
        />
      </svg>
      <div>
        <div className="tabular text-2xl font-semibold leading-none">
          {percent === null ? "—" : `${p.toFixed(0)}%`}
        </div>
        <div className="mt-1.5 text-sm text-text/90">{label}</div>
        {detail && <div className="tabular text-xs text-muted">{detail}</div>}
      </div>
    </div>
  );
}
