"""Notification engine and reminder scheduler."""
from __future__ import annotations

import shutil
import subprocess
import threading
from datetime import datetime, timezone

from .db import Database, now
from .events import EventBus

CATEGORIES = ("system", "ai", "download", "app", "reminder", "task", "security")


class Notifier:
    def __init__(self, db: Database, bus: EventBus):
        self.db, self.bus = db, bus
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def notify(self, category: str, title: str, body: str = "", level: str = "info") -> dict | None:
        """Returns the stored notification, or None when the category is muted."""
        if category in (self.db.pref("notifications.muted", []) or []):
            return None
        nid = self.db.x(
            "INSERT INTO notifications(ts, category, title, body, level) VALUES(?,?,?,?,?)",
            (now(), category, title[:200], body[:2000], level),
        )
        n = self.db.q("SELECT * FROM notifications WHERE id=?", (nid,))[0]
        self.bus.publish("notification", n)
        if self.db.pref("notifications.desktop", False) and shutil.which("notify-send"):
            try:
                subprocess.Popen(["notify-send", "--app-name=TITAN", title, body],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
        return n

    def list(self, limit: int = 100, unread_only: bool = False) -> list[dict]:
        where = "WHERE read=0" if unread_only else ""
        return self.db.q(f"SELECT * FROM notifications {where} ORDER BY id DESC LIMIT ?", (limit,))

    def mark_read(self, nid: int | None = None) -> int:
        if nid is None:
            return self.db.x("UPDATE notifications SET read=1 WHERE read=0")
        return self.db.x("UPDATE notifications SET read=1 WHERE id=?", (nid,))

    def clear(self) -> int:
        return self.db.x("DELETE FROM notifications")

    # --- reminders ---------------------------------------------------------
    def tick(self, at: datetime | None = None) -> int:
        """Fire due reminders. Returns how many fired."""
        at = at or datetime.now(timezone.utc)
        due = self.db.q("SELECT * FROM reminders WHERE done=0 AND due_at<=? ORDER BY due_at", (at.isoformat(timespec="seconds"),))
        for r in due:
            self.db.x("UPDATE reminders SET done=1 WHERE id=?", (r["id"],))
            self.notify("reminder", "Reminder", r["text"])
        return len(due)

    def start(self, interval: float = 15.0) -> None:
        def loop() -> None:
            while not self._stop.wait(interval):
                try:
                    self.tick()
                except Exception:
                    pass
        self._thread = threading.Thread(target=loop, name="titan-reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
