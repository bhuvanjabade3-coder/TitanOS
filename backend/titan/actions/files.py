"""File management. All paths are confined to the user's home directory and
never reach credential stores. Nothing here overwrites an existing file unless
explicitly asked, and permanent deletion always needs approval."""
from __future__ import annotations

import fnmatch
import mimetypes
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import psutil

from ..core import ActionError, Ctx, Gate
from ..security.risk import Risk

SENSITIVE = {".ssh", ".gnupg", ".pki", ".password-store", ".aws", ".kube", ".mozilla",
             "google-chrome", "chromium", "keyrings", ".docker"}
PERSISTENCE = (".config/autostart", ".config/systemd", ".local/share/applications", ".local/bin")
SKIP_DIRS = {"node_modules", "__pycache__", ".venv", "venv", ".git", ".cache"}
BULK_ITEMS, BULK_ENTRIES = 5, 50


def resolve(ctx: Ctx, raw: str, must_exist: bool | None = None) -> Path:
    home = ctx.settings.home.resolve()
    raw = (raw or "").strip()
    if not raw:
        raise ActionError("path is empty")
    if raw == "~" or raw.startswith("~/"):
        p = home / raw[2:]
    else:
        p = Path(raw)
        if not p.is_absolute():
            p = home / p
    p = Path(os.path.realpath(p))  # resolves symlinks, so links cannot escape
    if p != home and home not in p.parents:
        raise ActionError(f"{raw}: outside your home directory; TITAN only manages files under {home}")
    if SENSITIVE & set(p.relative_to(home).parts):
        raise ActionError(f"{raw}: credential and browser-profile directories are off limits")
    data = ctx.settings.data_dir.resolve()
    if p == data or data in p.parents:
        raise ActionError(f"{raw}: TITAN's own data directory is off limits")
    if must_exist is True and not p.exists():
        raise ActionError(f"{raw}: does not exist")
    if must_exist is False and p.exists():
        raise ActionError(f"{raw}: already exists (TITAN will not overwrite it)")
    return p


def write_risk(ctx: Ctx, p: Path) -> str | None:
    """Reason a write to ``p`` is security sensitive, or None."""
    rel = p.relative_to(ctx.settings.home.resolve())
    if not rel.parts:
        return None
    if len(rel.parts) == 1 and rel.parts[0].startswith("."):
        return f"{rel} is a shell/login dotfile"
    posix = rel.as_posix()
    for prefix in PERSISTENCE:
        if posix == prefix or posix.startswith(prefix + "/"):
            return f"{prefix} controls what runs on your account"
    return None


def _count(p: Path, cap: int = 10_000) -> int:
    if not p.is_dir() or p.is_symlink():
        return 1
    n = 0
    for _, dirs, files in os.walk(p):
        n += len(dirs) + len(files)
        if n >= cap:
            break
    return n


def _entry(p: Path) -> dict:
    try:
        st = p.lstat()
    except OSError:
        return {"name": p.name, "path": str(p), "is_dir": False, "size": 0, "mtime": 0, "mime": None, "error": True}
    is_dir = p.is_dir()
    return {"name": p.name, "path": str(p), "is_dir": is_dir, "is_link": p.is_symlink(),
            "size": 0 if is_dir else st.st_size, "mtime": st.st_mtime,
            "mime": None if is_dir else mimetypes.guess_type(p.name)[0]}


def _paths(ctx: Ctx, raw: list) -> list[Path]:
    if not raw:
        raise ActionError("no paths given")
    return [resolve(ctx, str(r), must_exist=True) for r in raw]


# --- handlers ----------------------------------------------------------------
def fs_list(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a.get("path", "~"), must_exist=True)
    if not p.is_dir():
        raise ActionError(f"{p}: not a directory")
    try:
        items = [_entry(c) for c in p.iterdir() if a.get("show_hidden") or not c.name.startswith(".")]
    except PermissionError:
        raise ActionError(f"{p}: permission denied")
    items.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    home = ctx.settings.home.resolve()
    return {"path": str(p), "parent": str(p.parent) if p != home else None, "entries": items}


def fs_read(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a["path"], must_exist=True)
    if p.is_dir():
        raise ActionError(f"{p}: is a directory")
    limit = min(int(a.get("max_bytes", 100_000)), 1_000_000)
    size = p.stat().st_size
    with open(p, "rb") as f:
        raw = f.read(limit)
    mime = mimetypes.guess_type(p.name)[0]
    if b"\x00" in raw[:8192]:
        return {"path": str(p), "size": size, "mime": mime, "binary": True, "text": None, "truncated": False}
    return {"path": str(p), "size": size, "mime": mime, "binary": False,
            "text": raw.decode("utf-8", errors="replace"), "truncated": size > limit}


def fs_mkdir(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a["path"], must_exist=False)
    p.mkdir(parents=True)
    return {"created": str(p)}


def g_write(ctx: Ctx, a: dict) -> Gate:
    p = resolve(ctx, a["path"])
    why = write_risk(ctx, p)
    if why:
        return Gate(Risk.HIGH, [why], f"Write {p}")
    if p.exists():
        if not a.get("overwrite"):
            raise ActionError(f"{p}: already exists (pass overwrite to replace it)")
        return Gate(Risk.MEDIUM, ["replaces an existing file"], f"Overwrite {p}")
    return Gate(summary=f"Create {p}")


def fs_write(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a["path"])
    if p.exists() and not a.get("overwrite"):
        raise ActionError(f"{p}: already exists")
    if p.is_dir():
        raise ActionError(f"{p}: is a directory")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a["content"], encoding="utf-8")
    return {"written": str(p), "bytes": len(a["content"].encode())}


def g_rename(ctx: Ctx, a: dict) -> Gate:
    p = resolve(ctx, a["path"], must_exist=True)
    if "/" in a["new_name"] or a["new_name"] in ("", ".", ".."):
        raise ActionError("new_name must be a plain file name")
    target = resolve(ctx, str(p.parent / a["new_name"]), must_exist=False)
    why = write_risk(ctx, target) or write_risk(ctx, p)
    return Gate(Risk.HIGH, [why], f"Rename {p} → {target.name}") if why else Gate(summary=f"Rename {p.name} → {target.name}")


def fs_rename(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a["path"], must_exist=True)
    target = resolve(ctx, str(p.parent / a["new_name"]), must_exist=False)
    p.rename(target)
    return {"renamed": str(target)}


def _transfer_gate(verb: str):
    def gate(ctx: Ctx, a: dict) -> Gate:
        srcs = _paths(ctx, a["sources"])
        dest = resolve(ctx, a["dest_dir"], must_exist=True)
        if not dest.is_dir():
            raise ActionError(f"{dest}: not a directory")
        reasons, risk = [], Risk.LOW
        for s in srcs:
            if (dest / s.name).exists():
                raise ActionError(f"{dest / s.name}: already exists (TITAN will not overwrite it)")
            if s == dest or s in dest.parents:
                raise ActionError(f"cannot {verb} {s} into itself")
            why = write_risk(ctx, dest / s.name) or (write_risk(ctx, s) if verb == "move" else None)
            if why:
                risk, reasons = Risk.HIGH, reasons + [why]
        total = sum(_count(s) for s in srcs)
        if risk is Risk.LOW and (len(srcs) > BULK_ITEMS or total > BULK_ENTRIES):
            risk, reasons = Risk.MEDIUM, [f"bulk operation: {len(srcs)} item(s), {total} entries"]
        return Gate(risk, reasons, f"{verb.capitalize()} {len(srcs)} item(s) to {dest}")
    return gate


def _transfer(verb: str):
    def handler(ctx: Ctx, a: dict) -> dict:
        srcs = _paths(ctx, a["sources"])
        dest = resolve(ctx, a["dest_dir"], must_exist=True)
        done, failed = [], []
        for s in srcs:
            target = dest / s.name
            try:
                if target.exists():
                    raise FileExistsError("target exists")
                if verb == "move":
                    shutil.move(str(s), str(target))
                elif s.is_dir():
                    shutil.copytree(s, target, symlinks=True)
                else:
                    shutil.copy2(s, target)
                done.append(str(target))
            except OSError as e:
                failed.append({"path": str(s), "error": str(e)})
        if failed and not done:
            raise ActionError(f"{verb} failed: {failed[0]['path']}: {failed[0]['error']}")
        return {"done": done, "failed": failed}
    return handler


def g_trash(ctx: Ctx, a: dict) -> Gate:
    srcs = _paths(ctx, a["paths"])
    home = ctx.settings.home.resolve()
    if home in srcs:
        raise ActionError("refusing to trash the home directory")
    total = sum(_count(s) for s in srcs)
    names = ", ".join(s.name for s in srcs[:3]) + ("…" if len(srcs) > 3 else "")
    if len(srcs) > BULK_ITEMS or total > BULK_ENTRIES:
        return Gate(Risk.MEDIUM, [f"bulk operation: {len(srcs)} item(s), {total} entries"], f"Move to Trash: {names}")
    if ctx.actor != "user":
        return Gate(Risk.MEDIUM, ["removes files (recoverable from Trash)"], f"Move to Trash: {names}")
    return Gate(summary=f"Move to Trash: {names}")


def fs_trash(ctx: Ctx, a: dict) -> dict:
    """freedesktop.org Trash spec: recoverable from the system file manager."""
    home = ctx.settings.home.resolve()
    tdir = home / ".local" / "share" / "Trash"
    (tdir / "files").mkdir(parents=True, exist_ok=True)
    (tdir / "info").mkdir(parents=True, exist_ok=True)
    out = []
    for s in _paths(ctx, a["paths"]):
        name, i = s.name, 1
        while (tdir / "files" / name).exists() or (tdir / "info" / f"{name}.trashinfo").exists():
            name, i = f"{s.name}.{i}", i + 1
        (tdir / "info" / f"{name}.trashinfo").write_text(
            f"[Trash Info]\nPath={quote(str(s))}\nDeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
        shutil.move(str(s), str(tdir / "files" / name))
        out.append(str(s))
    return {"trashed": out}


def g_delete(ctx: Ctx, a: dict) -> Gate:
    srcs = _paths(ctx, a["paths"])
    if ctx.settings.home.resolve() in srcs:
        raise ActionError("refusing to delete the home directory")
    total = sum(_count(s) for s in srcs)
    return Gate(Risk.HIGH, [f"permanent deletion of {len(srcs)} item(s), {total} entries; cannot be undone"],
                "Permanently delete: " + ", ".join(str(s) for s in srcs[:5]) + ("…" if len(srcs) > 5 else ""))


def fs_delete(ctx: Ctx, a: dict) -> dict:
    out = []
    for s in _paths(ctx, a["paths"]):
        if s.is_dir() and not s.is_symlink():
            shutil.rmtree(s)
        else:
            s.unlink()
        out.append(str(s))
    return {"deleted": out}


def fs_search(ctx: Ctx, a: dict) -> dict:
    root = resolve(ctx, a.get("root", "~"), must_exist=True)
    query = a["query"].strip()
    if not query:
        raise ActionError("query is empty")
    limit = min(int(a.get("limit", 200)), 1000)
    is_glob = any(c in query for c in "*?[")
    q = query.lower()
    deadline = time.monotonic() + 8
    hits, complete = [], True
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d not in SENSITIVE
                   and (a.get("show_hidden") or not d.startswith("."))]
        for name in dirs + files:
            if (fnmatch.fnmatch(name.lower(), q) if is_glob else q in name.lower()):
                hits.append(_entry(Path(dirpath) / name))
        if len(hits) >= limit or time.monotonic() > deadline:
            complete = False
            break
    return {"root": str(root), "query": query, "results": hits[:limit], "complete": complete}


def fs_storage(ctx: Ctx, a: dict) -> dict:
    parts = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype in ("squashfs", "tmpfs", "devtmpfs", "overlay") and part.mountpoint != "/":
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        parts.append({"device": part.device, "mount": part.mountpoint, "fstype": part.fstype,
                      "total": u.total, "used": u.used, "free": u.free, "percent": u.percent})
    home = ctx.settings.home.resolve()
    u = shutil.disk_usage(home)
    return {"partitions": parts, "home": {"path": str(home), "total": u.total, "used": u.used, "free": u.free}}


S = {"type": "string"}
PATHS = {"type": "array", "items": S, "description": "Absolute or ~-relative paths"}


def register(reg) -> None:
    reg.add("fs.list", "files", "List a directory", fs_list,
            {"path": S, "show_hidden": {"type": "boolean"}}, readonly=True)
    reg.add("fs.read", "files", "Read a text file (for preview, summarising or explaining)", fs_read,
            {"path": S, "max_bytes": {"type": "integer"}}, ["path"], readonly=True)
    reg.add("fs.search", "files", "Find files and folders by name (substring or glob) under a directory", fs_search,
            {"query": S, "root": S, "limit": {"type": "integer"}, "show_hidden": {"type": "boolean"}}, ["query"], readonly=True)
    reg.add("fs.storage", "files", "Disk and home-directory storage usage", fs_storage, readonly=True)
    reg.add("fs.mkdir", "files", "Create a folder", fs_mkdir, {"path": S}, ["path"],
            gate=lambda c, a: Gate(summary=f"Create folder {resolve(c, a['path'], must_exist=False)}"))
    reg.add("fs.write", "files", "Create a text file; refuses to replace an existing file unless overwrite is true",
            fs_write, {"path": S, "content": S, "overwrite": {"type": "boolean"}}, ["path", "content"], gate=g_write)
    reg.add("fs.rename", "files", "Rename a file or folder in place", fs_rename,
            {"path": S, "new_name": S}, ["path", "new_name"], gate=g_rename)
    reg.add("fs.move", "files", "Move files/folders into an existing directory (never overwrites)", _transfer("move"),
            {"sources": PATHS, "dest_dir": S}, ["sources", "dest_dir"], gate=_transfer_gate("move"))
    reg.add("fs.copy", "files", "Copy files/folders into an existing directory (never overwrites)", _transfer("copy"),
            {"sources": PATHS, "dest_dir": S}, ["sources", "dest_dir"], gate=_transfer_gate("copy"))
    reg.add("fs.trash", "files", "Move files/folders to the Trash (recoverable)", fs_trash,
            {"paths": PATHS}, ["paths"], gate=g_trash)
    reg.add("fs.delete", "files", "Permanently delete files/folders. Always requires user approval", fs_delete,
            {"paths": PATHS}, ["paths"], gate=g_delete)
