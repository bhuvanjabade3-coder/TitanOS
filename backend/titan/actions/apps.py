"""Application discovery (freedesktop .desktop entries) and launching."""
from __future__ import annotations

import configparser
import os
import shlex
from pathlib import Path

from ..core import ActionError, Ctx
from ..db import now
from ._tools import spawn
from .terminal import clean_env

CATEGORY_MAP = [
    ("Development", "Development"), ("Network", "Internet"), ("WebBrowser", "Internet"),
    ("Office", "Office"), ("Graphics", "Graphics"), ("AudioVideo", "Media"), ("Audio", "Media"),
    ("Video", "Media"), ("Game", "Games"), ("Settings", "System"), ("System", "System"),
    ("Utility", "Utilities"), ("Education", "Education"), ("Science", "Education"),
]


def _dirs(ctx: Ctx) -> list[Path]:
    home = ctx.settings.home
    base = [Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")]
    base += [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
    base += [Path("/var/lib/snapd/desktop"), Path("/var/lib/flatpak/exports/share"),
             home / ".local/share/flatpak/exports/share"]
    return [d / "applications" for d in base]


def _category(raw: str) -> str:
    cats = [c for c in raw.split(";") if c]
    for key, label in CATEGORY_MAP:
        if key in cats:
            return label
    return "Other"


def scan(ctx: Ctx) -> dict[str, dict]:
    apps: dict[str, dict] = {}
    for d in _dirs(ctx):
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.desktop")):
            app_id = f.stem
            if app_id in apps:  # earlier dirs take precedence (user overrides system)
                continue
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            cp.optionxform = str  # type: ignore[assignment]
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("Type", "Application") != "Application" or not e.get("Exec"):
                continue
            if e.get("NoDisplay", "false").lower() == "true" or e.get("Hidden", "false").lower() == "true":
                continue
            apps[app_id] = {"id": app_id, "name": e.get("Name", app_id), "comment": e.get("Comment", ""),
                            "exec": e["Exec"], "icon": e.get("Icon", ""), "terminal": e.get("Terminal", "false").lower() == "true",
                            "category": _category(e.get("Categories", "")), "keywords": e.get("Keywords", ""),
                            "file": str(f)}
    return apps


def _public(a: dict) -> dict:
    return {k: a[k] for k in ("id", "name", "comment", "icon", "category")}


def find(ctx: Ctx, query: str) -> list[dict]:
    q = query.lower().strip()
    scored = []
    for a in scan(ctx).values():
        name = a["name"].lower()
        hay = f"{a['id']} {a['comment']} {a['keywords']} {a['exec']}".lower()
        score = 0 if name == q or a["id"].lower() == q else 1 if name.startswith(q) else 2 if q in name else 3 if q in hay else None
        if score is not None:
            scored.append((score, name, a))
    return [a for _, _, a in sorted(scored, key=lambda t: t[:2])]


def apps_list(ctx: Ctx, a: dict) -> dict:
    apps = scan(ctx).values() if not a.get("query") else find(ctx, a["query"])
    usage = {r["app_id"]: r for r in ctx.db.q("SELECT * FROM app_usage ORDER BY last_used DESC")}
    pinned = ctx.db.pref("dock.pinned", []) or []
    out = sorted((_public(x) for x in apps), key=lambda x: x["name"].lower()) if not a.get("query") else [_public(x) for x in apps]
    known = {x["id"] for x in out}
    return {"apps": out, "pinned": [p for p in pinned if p in known or not a.get("query")],
            "recent": [k for k in usage if k in known][:8]}


def argv_for(app: dict) -> list[str]:
    """Exec line → argv with field codes (%f, %U …) removed, per the Desktop Entry spec."""
    try:
        parts = shlex.split(app["exec"])
    except ValueError:
        raise ActionError(f"{app['name']}: malformed Exec line")
    argv = [p.replace("%%", "%") for p in parts if not (len(p) == 2 and p[0] == "%" and p[1] != "%")]
    if not argv:
        raise ActionError(f"{app['name']}: empty Exec line")
    return argv


def apps_launch(ctx: Ctx, a: dict) -> dict:
    apps = scan(ctx)
    app = apps.get(a["app"]) or next(iter(find(ctx, a["app"])), None)
    if app is None:
        raise ActionError(f"No installed application matches “{a['app']}”")
    if app["terminal"]:
        raise ActionError(f"{app['name']} is a terminal program; run it with terminal.run instead")
    pid = spawn(argv_for(app), cwd=ctx.settings.home, env=clean_env())
    ctx.db.x("INSERT INTO app_usage(app_id, last_used, count) VALUES(?,?,1) "
             "ON CONFLICT(app_id) DO UPDATE SET last_used=excluded.last_used, count=count+1", (app["id"], now()))
    ctx.core.bus.publish("app.launched", {"id": app["id"], "name": app["name"], "pid": pid})
    return {"launched": app["name"], "id": app["id"], "pid": pid}


def apps_pin(ctx: Ctx, a: dict) -> dict:
    if a["app"] not in scan(ctx):
        raise ActionError(f"Unknown application id “{a['app']}”")
    pinned = [p for p in (ctx.db.pref("dock.pinned", []) or []) if p != a["app"]]
    if a.get("pinned", True):
        pinned.append(a["app"])
    ctx.db.set_preference("dock.pinned", pinned)
    return {"pinned": pinned}


def register(reg) -> None:
    S = {"type": "string"}
    reg.add("apps.list", "apps", "List installed desktop applications, optionally filtered by a search query",
            apps_list, {"query": S}, readonly=True)
    reg.add("apps.launch", "apps", "Launch an installed application by id or name (e.g. 'firefox', 'Text Editor')",
            apps_launch, {"app": S}, ["app"])
    reg.add("apps.pin", "apps", "Pin or unpin an application in the dock", apps_pin,
            {"app": S, "pinned": {"type": "boolean"}}, ["app"])
