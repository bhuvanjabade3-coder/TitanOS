"""System settings: display, sound, network, bluetooth, power, appearance.
Each section reports ``available: false`` with a reason when the host tool is
missing, rather than inventing values."""
from __future__ import annotations

import re
import socket
import subprocess

import psutil

from .. import system
from ..core import ActionError, Ctx
from ._tools import have, sh


def _try(args: list[str]) -> str | None:
    if not have(args[0]):
        return None
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=6, stdin=subprocess.DEVNULL)
        return p.stdout if p.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def display() -> dict:
    out = _try(["xrandr", "--current"])
    if out is None:
        return {"available": False, "reason": "xrandr unavailable or no X display"}
    outs = []
    for m in re.finditer(r"^(\S+) connected( primary)? (\d+)x(\d+)", out, re.M):
        outs.append({"name": m[1], "primary": bool(m[2]), "width": int(m[3]), "height": int(m[4])})
    return {"available": True, "outputs": outs}


def sound() -> dict:
    vol, mute = _try(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]), _try(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
    if vol is None:
        return {"available": False, "reason": "pactl unavailable or no audio server"}
    m = re.search(r"(\d+)%", vol)
    return {"available": True, "volume": int(m[1]) if m else None, "muted": "yes" in (mute or "")}


def network() -> dict:
    stats = psutil.net_if_stats()
    ifaces = []
    for name, addrs in psutil.net_if_addrs().items():
        if name == "lo":
            continue
        ifaces.append({"name": name, "up": stats[name].isup if name in stats else None,
                       "addresses": [a.address for a in addrs if a.family in (socket.AF_INET, socket.AF_INET6)]})
    out = {"available": True, "interfaces": ifaces, "wifi": None}
    nm = _try(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"])
    if nm:
        for line in nm.splitlines():
            parts = line.split(":")
            if parts[0] == "yes" and len(parts) >= 3:
                out["wifi"] = {"ssid": parts[1], "signal": int(parts[2]) if parts[2].isdigit() else None}
    return out


def bluetooth() -> dict:
    out = _try(["bluetoothctl", "show"])
    if not out:
        return {"available": False, "reason": "bluetoothctl unavailable or no controller"}
    return {"available": True, "powered": "Powered: yes" in out, "discoverable": "Discoverable: yes" in out}


def appearance() -> dict:
    out = _try(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    if out is None:
        return {"available": False, "reason": "GNOME settings are not reachable from TITAN Core"}
    return {"available": True, "color_scheme": out.strip().strip("'")}


def status(ctx: Ctx, a: dict) -> dict:
    snap = system.snapshot()
    return {"display": display(), "sound": sound(), "network": network(), "bluetooth": bluetooth(),
            "power": {"available": snap["battery"] is not None, "battery": snap["battery"]},
            "appearance": appearance(), "storage": snap["disk"]}


def set_volume(ctx: Ctx, a: dict) -> dict:
    v = a["percent"]
    if not 0 <= v <= 150:
        raise ActionError("percent must be between 0 and 150")
    sh(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"])
    return {"volume": v}


def set_mute(ctx: Ctx, a: dict) -> dict:
    sh(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if a["muted"] else "0"])
    return {"muted": a["muted"]}


def set_scheme(ctx: Ctx, a: dict) -> dict:
    if a["scheme"] not in ("dark", "light"):
        raise ActionError("scheme must be dark or light")
    sh(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme",
        "prefer-dark" if a["scheme"] == "dark" else "default"])
    ctx.db.set_preference("theme.mode", a["scheme"])
    return {"scheme": a["scheme"]}


def register(reg) -> None:
    reg.add("settings.status", "settings", "Display, sound, network, bluetooth, power and appearance status", status, readonly=True)
    reg.add("settings.set_volume", "settings", "Set output volume (percent)", set_volume, {"percent": {"type": "integer"}}, ["percent"])
    reg.add("settings.set_mute", "settings", "Mute or unmute audio output", set_mute, {"muted": {"type": "boolean"}}, ["muted"])
    reg.add("settings.set_color_scheme", "settings", "Switch the desktop between dark and light", set_scheme,
            {"scheme": {"type": "string", "enum": ["dark", "light"]}}, ["scheme"])
