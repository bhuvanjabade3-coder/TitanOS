"""Window management and input automation for GNOME on Xorg.

Windows: EWMH via ``wmctrl``. Input: ``xdotool``. Accessibility: AT-SPI through
PyGObject when installed. None of this works under Wayland; the handlers say so
instead of silently doing nothing.
"""
from __future__ import annotations

import os
import re

from ..core import ActionError, Ctx, Gate
from ..security.risk import Risk
from ._tools import sh

_WID = re.compile(r"^0x[0-9a-fA-F]{1,16}$")
_KEYS = re.compile(r"^[A-Za-z0-9_+ ]{1,100}$")
BLOCKED_COMBOS = {"ctrl+alt+delete", "ctrl+alt+backspace", "super+l", "ctrl+alt+f1", "ctrl+alt+f2", "ctrl+alt+f3"}


def _x11() -> None:
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or not os.environ.get("DISPLAY"):
        raise ActionError("Window and input control need an Xorg session (log in with “Ubuntu on Xorg”); "
                          "no X display is available to TITAN Core")


def _wid(a: dict) -> str:
    if not _WID.match(a["window"]):
        raise ActionError("window must be an id like 0x03a00007 (from windows.list)")
    return a["window"]


def parse_windows(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^(0x[0-9a-f]+)\s+(-?\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s?(.*)$", line)
        if m:
            out.append({"id": m[1], "workspace": int(m[2]), "pid": int(m[3]), "class": m[4], "title": m[6]})
    return out


def parse_workspaces(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^(\d+)\s+([*-])\s.*?(\S+)$", line)
        if m:
            out.append({"index": int(m[1]), "current": m[2] == "*", "name": line.split(None, 9)[-1] if len(line.split()) >= 10 else m[3]})
    return out


def windows_list(ctx: Ctx, a: dict) -> dict:
    _x11()
    wins = [w for w in parse_windows(sh(["wmctrl", "-lpx"])) if w["workspace"] >= 0 or a.get("all")]
    return {"windows": wins, "workspaces": parse_workspaces(sh(["wmctrl", "-d"]))}


def _wm(args_for):
    def handler(ctx: Ctx, a: dict) -> dict:
        _x11()
        sh(args_for(a))
        return {"ok": True, "window": a.get("window")}
    return handler


def workspace_switch(ctx: Ctx, a: dict) -> dict:
    _x11()
    if a["index"] < 0:
        raise ActionError("workspace index must be >= 0")
    sh(["wmctrl", "-s", str(a["index"])])
    return {"workspace": a["index"]}


def g_input(what: str):
    def gate(ctx: Ctx, a: dict) -> Gate:
        if "keys" in a:
            combo = a["keys"].lower().replace(" ", "")
            if not _KEYS.match(a["keys"]):
                raise ActionError("keys must look like 'ctrl+l' or 'Return'")
            if combo in BLOCKED_COMBOS:
                raise ActionError(f"{a['keys']} is a session-control shortcut TITAN will not send")
        detail = a.get("text") or a.get("keys") or f"({a.get('x')}, {a.get('y')})" if what != "scroll" else str(a.get("amount"))
        return Gate(Risk.MEDIUM, ["synthetic input goes to whichever window has focus"], f"{what}: {str(detail)[:120]}")
    return gate


def input_type(ctx: Ctx, a: dict) -> dict:
    _x11()
    if len(a["text"]) > 5000:
        raise ActionError("text too long (5000 characters max)")
    sh(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", a["text"]], timeout=90)
    return {"typed": len(a["text"])}


def input_key(ctx: Ctx, a: dict) -> dict:
    _x11()
    sh(["xdotool", "key", "--clearmodifiers", *a["keys"].split()])
    return {"sent": a["keys"]}


def input_click(ctx: Ctx, a: dict) -> dict:
    _x11()
    button = {"left": "1", "middle": "2", "right": "3"}.get(a.get("button", "left"))
    if button is None or a["x"] < 0 or a["y"] < 0:
        raise ActionError("button must be left/middle/right and coordinates non-negative")
    sh(["xdotool", "mousemove", str(a["x"]), str(a["y"]), "click", button])
    return {"clicked": [a["x"], a["y"]], "button": a.get("button", "left")}


def input_scroll(ctx: Ctx, a: dict) -> dict:
    _x11()
    n = max(-50, min(50, a["amount"]))
    if n:
        sh(["xdotool", "click", "--repeat", str(abs(n)), "5" if n > 0 else "4"])
    return {"scrolled": n}


def a11y_tree(ctx: Ctx, a: dict) -> dict:
    """Read names and roles of UI elements in the focused application via AT-SPI."""
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError):
        raise ActionError("AT-SPI bindings are not installed. Install with: sudo apt install python3-gi gir1.2-atspi-2.0 "
                          "(and create TITAN's virtualenv with --system-site-packages)")
    max_depth, budget = min(int(a.get("depth", 6)), 12), [400]

    def walk(node, depth):
        if node is None or budget[0] <= 0:
            return None
        budget[0] -= 1
        try:
            item = {"role": node.get_role_name(), "name": node.get_name() or ""}
            if depth < max_depth:
                kids = [walk(node.get_child_at_index(i), depth + 1) for i in range(min(node.get_child_count(), 40))]
                kids = [k for k in kids if k and (k["name"] or k.get("children"))]
                if kids:
                    item["children"] = kids
            return item
        except Exception:
            return None

    desktop = Atspi.get_desktop(0)
    want = (a.get("app") or "").lower()
    apps = []
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is None:
            continue
        name = app.get_name() or ""
        if want and want not in name.lower():
            continue
        apps.append(walk(app, 0) if want else {"role": "application", "name": name})
    return {"applications": [x for x in apps if x], "truncated": budget[0] <= 0}


def register(reg) -> None:
    S, I = {"type": "string"}, {"type": "integer"}
    W = {"window": {"type": "string", "description": "Window id from windows.list"}}
    reg.add("windows.list", "windows", "List open windows and workspaces", windows_list,
            {"all": {"type": "boolean"}}, readonly=True)
    reg.add("windows.focus", "windows", "Switch to (raise and focus) a window", _wm(lambda a: ["wmctrl", "-ia", _wid(a)]), W, ["window"])
    reg.add("windows.minimize", "windows", "Minimize a window",
            _wm(lambda a: ["xdotool", "windowminimize", str(int(_wid(a), 16))]), W, ["window"])
    reg.add("windows.maximize", "windows", "Maximize a window",
            _wm(lambda a: ["wmctrl", "-ir", _wid(a), "-b", "add,maximized_vert,maximized_horz"]), W, ["window"])
    reg.add("windows.restore", "windows", "Un-maximize a window",
            _wm(lambda a: ["wmctrl", "-ir", _wid(a), "-b", "remove,maximized_vert,maximized_horz"]), W, ["window"])
    reg.add("windows.move_to_workspace", "windows", "Move a window to a workspace",
            _wm(lambda a: ["wmctrl", "-ir", _wid(a), "-t", str(max(0, a["index"]))]), {**W, "index": I}, ["window", "index"])
    reg.add("windows.close", "windows", "Ask a window to close (the app may prompt to save)",
            _wm(lambda a: ["wmctrl", "-ic", _wid(a)]), W, ["window"],
            gate=lambda c, a: Gate(Risk.MEDIUM, ["closing a window can discard unsaved work"], f"Close window {a['window']}"))
    reg.add("workspace.switch", "windows", "Switch to a workspace by index (0-based)", workspace_switch, {"index": I}, ["index"])
    reg.add("input.type", "input", "Type text into the focused window", input_type, {"text": S}, ["text"], gate=g_input("Type"))
    reg.add("input.key", "input", "Send a keyboard shortcut to the focused window, e.g. 'ctrl+l' or 'Return'",
            input_key, {"keys": S}, ["keys"], gate=g_input("Press"))
    reg.add("input.click", "input", "Click at screen coordinates", input_click,
            {"x": I, "y": I, "button": S}, ["x", "y"], gate=g_input("Click"))
    reg.add("input.scroll", "input", "Scroll the focused window (positive = down)", input_scroll,
            {"amount": I}, ["amount"], gate=g_input("scroll"))
    reg.add("a11y.tree", "input", "Read accessible UI element names/roles of a running application (AT-SPI)",
            a11y_tree, {"app": S, "depth": I}, readonly=True)
