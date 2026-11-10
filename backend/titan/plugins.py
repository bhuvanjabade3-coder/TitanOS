"""Plugin system.

A plugin is a directory ``<data_dir>/plugins/<id>/`` containing ``manifest.json``
and a Python entry module exposing ``register(api)``. Plugins are discovered
disabled; enabling one is the user granting the permissions in its manifest.

A plugin never touches the system directly through TITAN: it receives a
``PluginAPI`` whose ``perform`` goes through the same registry, risk gates and
approvals as everything else, restricted to the action categories it declared.

Honest limitation: plugins are in-process Python, so this is capability
mediation for well-behaved plugins, not a sandbox against hostile code. Only
install plugins you trust.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .security.risk import Risk

if TYPE_CHECKING:
    from .core import Action, Core

log = logging.getLogger("titan.plugins")
PERMISSIONS = {"files", "terminal", "apps", "windows", "input", "browser", "memory", "notifications",
               "system", "settings", "dev", "security", "tasks", "preferences"}
ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class PluginError(Exception):
    pass


def load_manifest(directory: Path) -> dict:
    try:
        m = json.loads((directory / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise PluginError(f"manifest.json unreadable: {e}")
    for key in ("id", "name", "version"):
        if not isinstance(m.get(key), str) or not m[key]:
            raise PluginError(f"manifest is missing `{key}`")
    if not ID.match(m["id"]) or m["id"] != directory.name:
        raise PluginError("manifest id must match its directory name and be lowercase [a-z0-9_]")
    if not re.match(r"^\d+\.\d+\.\d+", m["version"]):
        raise PluginError("version must be semantic (e.g. 1.0.0)")
    perms = m.get("permissions", [])
    if not isinstance(perms, list) or set(perms) - PERMISSIONS:
        raise PluginError(f"unknown permission(s): {sorted(set(perms) - PERMISSIONS) if isinstance(perms, list) else perms}")
    entry = m.get("entry", "plugin.py")
    if "/" in entry or ".." in entry or not (directory / entry).is_file():
        raise PluginError(f"entry file `{entry}` not found in the plugin directory")
    return {"id": m["id"], "name": m["name"], "version": m["version"], "description": m.get("description", ""),
            "permissions": sorted(perms), "entry": entry}


class PluginAPI:
    def __init__(self, core: "Core", manifest: dict):
        self._core, self._m = core, manifest
        self.id = manifest["id"]

    def register_action(self, name: str, handler: Callable[[dict], Any], description: str,
                        params: dict | None = None, required: list[str] | None = None, risk: str = "low") -> None:
        from .core import Gate
        if not re.match(r"^[a-z][a-z0-9_]{0,40}$", name):
            raise PluginError("action names are lowercase [a-z0-9_]")
        level = Risk(risk)
        full = f"plugin.{self.id}.{name}"
        self._core.registry.add(
            full, f"plugin.{self.id}", f"[{self._m['name']}] {description}",
            lambda ctx, a: handler(a), params, required,
            gate=lambda ctx, a: Gate(level, [f"declared {risk} risk by plugin {self.id}"] if level is not Risk.LOW else [], description))

    def perform(self, action: str, params: dict | None = None) -> dict:
        return self._core.registry.perform(f"plugin:{self.id}", action, params or {})

    def notify(self, title: str, body: str = "") -> None:
        if "notifications" not in self._m["permissions"]:
            raise PluginError("plugin lacks the `notifications` permission")
        self._core.notifier.notify("app", title, body)


class PluginManager:
    def __init__(self, core: "Core"):
        self.core = core
        self.dir = core.settings.data_dir / "plugins"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.loaded: dict[str, dict] = {}

    def _state(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.core.db.q("SELECT * FROM plugins")}

    def list(self) -> list[dict]:
        state, out = self._state(), []
        for d in sorted(p for p in self.dir.iterdir() if p.is_dir()):
            st = state.get(d.name, {})
            try:
                m = load_manifest(d)
                out.append({**m, "enabled": bool(st.get("enabled")), "loaded": d.name in self.loaded,
                            "error": st.get("error"), "valid": True,
                            "actions": sorted(k for k in self.core.registry.actions if k.startswith(f"plugin.{d.name}."))})
            except PluginError as e:
                out.append({"id": d.name, "name": d.name, "version": "?", "description": "", "permissions": [],
                            "enabled": False, "loaded": False, "error": str(e), "valid": False, "actions": []})
        return out

    def allowed(self, plugin_id: str, action: "Action") -> bool:
        m = self.loaded.get(plugin_id)
        if m is None:
            return False
        return action.category in m["permissions"] or action.category == f"plugin.{plugin_id}"

    def _set(self, pid: str, enabled: bool, error: str | None) -> None:
        self.core.db.x("INSERT INTO plugins(id, enabled, error) VALUES(?,?,?) "
                       "ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled, error=excluded.error",
                       (pid, int(enabled), error))

    def _load(self, pid: str) -> None:
        d = self.dir / pid
        m = load_manifest(d)
        self.loaded[pid] = m
        try:
            spec = importlib.util.spec_from_file_location(f"titan_plugin_{pid}", d / m["entry"])
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            if not callable(getattr(module, "register", None)):
                raise PluginError("entry module has no register(api) function")
            module.register(PluginAPI(self.core, m))
        except BaseException as e:
            self._unload(pid)
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise PluginError(f"plugin tried to exit the process ({type(e).__name__})")
            raise PluginError(f"{type(e).__name__}: {e}")

    def _unload(self, pid: str) -> None:
        self.loaded.pop(pid, None)
        self.core.registry.remove_prefix(f"plugin.{pid}.")
        sys.modules.pop(f"titan_plugin_{pid}", None)

    def enable(self, pid: str) -> dict:
        if not ID.match(pid) or not (self.dir / pid).is_dir():
            raise PluginError(f"No plugin `{pid}`")
        self._unload(pid)
        try:
            self._load(pid)
        except PluginError as e:
            self._set(pid, False, str(e))
            raise
        self._set(pid, True, None)
        self.core.db.audit("user", "plugin.enable", {"id": pid, "permissions": self.loaded[pid]["permissions"]}, "ok")
        return next(p for p in self.list() if p["id"] == pid)

    def disable(self, pid: str) -> dict:
        self._unload(pid)
        self._set(pid, False, None)
        self.core.db.audit("user", "plugin.disable", {"id": pid}, "ok")
        return next((p for p in self.list() if p["id"] == pid), {"id": pid, "enabled": False})

    def load_enabled(self) -> None:
        for pid, st in self._state().items():
            if st["enabled"]:
                try:
                    self._load(pid)
                except PluginError as e:  # a broken plugin must never stop TITAN starting
                    log.warning("Plugin %s failed to load: %s", pid, e)
                    self._set(pid, False, str(e))
