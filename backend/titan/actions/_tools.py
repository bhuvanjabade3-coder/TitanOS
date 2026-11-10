"""Helpers for optional external programs. A missing tool is reported as a
clear, actionable error rather than a fake success."""
from __future__ import annotations

import shutil
import subprocess

from ..core import ActionError

PACKAGES = {"wmctrl": "wmctrl", "xdotool": "xdotool", "xdg-open": "xdg-utils", "nmcli": "network-manager",
            "pactl": "pulseaudio-utils", "bluetoothctl": "bluez", "xrandr": "x11-xserver-utils",
            "espeak-ng": "espeak-ng", "arecord": "alsa-utils", "git": "git"}


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        pkg = PACKAGES.get(tool)
        hint = f" Install it with: sudo apt install {pkg}" if pkg else ""
        raise ActionError(f"`{tool}` is not installed on this system.{hint}")
    return path


def sh(args: list[str], timeout: float = 10, check: bool = True, cwd=None) -> str:
    """Run a fixed argv (never a shell string)."""
    need(args[0])
    try:
        p = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout, cwd=cwd,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ActionError(f"`{args[0]}` timed out after {timeout}s")
    if check and p.returncode != 0:
        raise ActionError(f"`{' '.join(args[:3])}` failed: {(p.stderr or p.stdout).strip()[:400]}")
    return p.stdout


def spawn(args: list[str], cwd=None, env=None) -> int:
    """Start a detached GUI process; returns its pid."""
    try:
        p = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        raise ActionError(f"`{args[0]}` is not installed")
    except OSError as e:
        raise ActionError(f"could not start `{args[0]}`: {e}")
    return p.pid
