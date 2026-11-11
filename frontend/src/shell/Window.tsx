import { motion } from "framer-motion";
import { useRef, type PointerEvent as RPE, type ReactNode } from "react";
import { Icon } from "../components/ui";
import { closeWin, focusWin, minimizeWin, patchWin, toggleMax, type Win } from "../lib/store";

const TOP = 44, BOTTOM = 84, MIN_W = 360, MIN_H = 240;

type Mode = "move" | "e" | "s" | "se";

/** Minimised windows and windows on other workspaces stay mounted (hidden) so
 *  their state, such as terminal output, survives. */
export function Window({ win, focused, icon, hidden, children }: { win: Win; focused: boolean; icon: string; hidden: boolean; children: ReactNode }) {
  const drag = useRef<{ mode: Mode; px: number; py: number; x: number; y: number; w: number; h: number } | null>(null);

  const start = (mode: Mode) => (e: RPE) => {
    if (e.button !== 0 || win.maximized) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { mode, px: e.clientX, py: e.clientY, x: win.x, y: win.y, w: win.w, h: win.h };
  };
  const move = (e: RPE) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.px, dy = e.clientY - d.py;
    if (d.mode === "move") {
      patchWin(win.id, {
        x: Math.max(-d.w + 120, Math.min(window.innerWidth - 120, d.x + dx)),
        y: Math.max(TOP, Math.min(window.innerHeight - BOTTOM, d.y + dy)),
      });
    } else {
      patchWin(win.id, {
        w: d.mode === "s" ? d.w : Math.max(MIN_W, d.w + dx),
        h: d.mode === "e" ? d.h : Math.max(MIN_H, d.h + dy),
      });
    }
  };
  const end = () => { drag.current = null; };

  const box = win.maximized
    ? { left: 8, top: TOP, width: window.innerWidth - 16, height: window.innerHeight - TOP - BOTTOM }
    : { left: win.x, top: win.y, width: win.w, height: win.h };

  return (
    <motion.div
      role="dialog" aria-label={win.title}
      initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.16, ease: [0.2, 0.8, 0.2, 1] }}
      className="window absolute flex flex-col overflow-hidden"
      data-focused={focused} style={{ ...box, zIndex: win.z, display: hidden ? "none" : undefined }}
      onPointerDownCapture={() => { if (!focused) focusWin(win.id); }}
    >
      <header className="flex h-10 shrink-0 cursor-default select-none items-center gap-2 border-b border-line pl-3 pr-1.5"
        onPointerDown={start("move")} onPointerMove={move} onPointerUp={end} onPointerCancel={end}
        onDoubleClick={() => toggleMax(win.id)}>
        <Icon name={icon} size={15} className="text-muted" />
        <span className="flex-1 truncate text-[13px] font-medium">{win.title}</span>
        <div className="flex" onPointerDown={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
          <button className="btn btn-ghost !px-2" aria-label="Minimize" onClick={() => minimizeWin(win.id)}><Icon name="min" size={14} /></button>
          <button className="btn btn-ghost !px-2" aria-label={win.maximized ? "Restore" : "Maximize"} onClick={() => toggleMax(win.id)}><Icon name="max" size={13} /></button>
          <button className="btn btn-ghost !px-2 hover:!text-danger" aria-label="Close" onClick={() => closeWin(win.id)}><Icon name="x" size={14} /></button>
        </div>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
      {!win.maximized && (
        <>
          <div className="absolute right-0 top-10 bottom-3 w-1.5 cursor-ew-resize" onPointerDown={start("e")} onPointerMove={move} onPointerUp={end} />
          <div className="absolute bottom-0 left-0 right-3 h-1.5 cursor-ns-resize" onPointerDown={start("s")} onPointerMove={move} onPointerUp={end} />
          <div className="absolute bottom-0 right-0 h-3.5 w-3.5 cursor-nwse-resize" data-testid="resize-se" onPointerDown={start("se")} onPointerMove={move} onPointerUp={end} />
        </>
      )}
    </motion.div>
  );
}
