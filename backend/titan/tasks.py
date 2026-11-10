"""Background task engine: queue, progress, cancellation, path locks."""
from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from .db import Database, now
from .events import EventBus

ACTIVE = ("queued", "running")


class TaskConflict(Exception):
    pass


class TaskCancelled(Exception):
    pass


class TaskControl:
    def __init__(self, mgr: "TaskManager", task_id: str):
        self._mgr, self.id = mgr, task_id
        self.cancel_event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise TaskCancelled()

    def progress(self, fraction: float, message: str = "") -> None:
        self._mgr._update(self.id, progress=max(0.0, min(1.0, fraction)), message=message[:500])


def _overlaps(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


class TaskManager:
    def __init__(self, db: Database, bus: EventBus, max_workers: int = 4):
        self.db, self.bus = db, bus
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="titan-task")
        self._lock = threading.Lock()
        self._controls: dict[str, TaskControl] = {}
        self._locks: dict[str, list[Path]] = {}
        # Tasks cannot survive a restart; say so instead of leaving them "running".
        db.x(
            "UPDATE tasks SET status='interrupted', finished_at=?, error='TITAN Core restarted' "
            "WHERE status IN ('queued','running')",
            (now(),),
        )

    def submit(self, name: str, fn: Callable[[TaskControl], Any], locks: list[Path] | None = None) -> dict:
        locks = [Path(p) for p in (locks or [])]
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            for other, held in self._locks.items():
                for a in locks:
                    for b in held:
                        if _overlaps(a, b):
                            raise TaskConflict(
                                f"Task {other} is already working on {b}; wait for it or cancel it first"
                            )
            self._locks[task_id] = locks
            ctl = self._controls[task_id] = TaskControl(self, task_id)
        self.db.x(
            "INSERT INTO tasks(id, name, status, created_at) VALUES(?,?,?,?)",
            (task_id, name, "queued", now()),
        )
        self._emit(task_id)
        self._pool.submit(self._run, ctl, fn)
        return self.get(task_id)

    def _run(self, ctl: TaskControl, fn: Callable[[TaskControl], Any]) -> None:
        try:
            if ctl.cancelled:
                raise TaskCancelled()
            self._update(ctl.id, status="running")
            result = fn(ctl)
            if ctl.cancelled:
                raise TaskCancelled()
            self._update(ctl.id, status="done", progress=1.0, result=json.dumps(result, default=str), finished_at=now())
        except TaskCancelled:
            self._update(ctl.id, status="cancelled", finished_at=now())
        except Exception as e:  # report, never swallow
            self._update(ctl.id, status="failed", error=f"{type(e).__name__}: {e}"[:2000], finished_at=now())
        finally:
            with self._lock:
                self._locks.pop(ctl.id, None)
                self._controls.pop(ctl.id, None)

    def _update(self, task_id: str, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.x(f"UPDATE tasks SET {sets} WHERE id=?", (*fields.values(), task_id))
        self._emit(task_id)

    def _emit(self, task_id: str) -> None:
        self.bus.publish("task", self.get(task_id))

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            ctl = self._controls.get(task_id)
        if ctl is None:
            return False
        ctl.cancel_event.set()
        return True

    def get(self, task_id: str) -> dict:
        rows = self.db.q("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not rows:
            raise KeyError(task_id)
        t = rows[0]
        t["result"] = json.loads(t["result"]) if t["result"] else None
        return t

    def list(self, limit: int = 50) -> list[dict]:
        rows = self.db.q("SELECT * FROM tasks ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        for t in rows:
            t["result"] = json.loads(t["result"]) if t["result"] else None
        return rows

    def shutdown(self) -> None:
        with self._lock:
            for c in self._controls.values():
                c.cancel_event.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
