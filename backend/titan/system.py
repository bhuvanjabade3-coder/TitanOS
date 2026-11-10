"""Live system telemetry via psutil. No simulated values: anything the host
does not expose is reported as ``None``."""
from __future__ import annotations

import platform
import time
from typing import Any

import psutil


def prime() -> None:
    """cpu_percent(interval=None) needs a prior sample to return real data."""
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None, percpu=True)


def _battery() -> dict[str, Any] | None:
    try:
        b = psutil.sensors_battery()
    except Exception:
        return None
    if b is None:
        return None
    secs = b.secsleft if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else None
    return {"percent": b.percent, "plugged": b.power_plugged, "seconds_left": secs}


def _temperatures() -> dict[str, float] | None:
    fn = getattr(psutil, "sensors_temperatures", None)
    if fn is None:
        return None
    try:
        temps = fn()
    except Exception:
        return None
    out = {name: max(e.current for e in entries) for name, entries in temps.items() if entries}
    return out or None


def snapshot() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    return {
        "ts": time.time(),
        "cpu": {
            "percent": psutil.cpu_percent(interval=None),
            "per_core": psutil.cpu_percent(interval=None, percpu=True),
            "cores": psutil.cpu_count(logical=True),
            "load_avg": list(psutil.getloadavg()),
        },
        "memory": {"total": vm.total, "used": vm.total - vm.available, "percent": vm.percent},
        "disk": {"total": disk.total, "used": disk.used, "percent": disk.percent},
        "network": {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv},
        "battery": _battery(),
        "temperatures": _temperatures(),
    }


def info() -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "os": platform.system(),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "boot_time": psutil.boot_time(),
    }


def processes(limit: int = 25, sort: str = "memory") -> list[dict[str, Any]]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "status"]):
        i = p.info
        procs.append(
            {
                "pid": i["pid"],
                "name": i["name"] or "",
                "user": i["username"],
                "cpu_percent": i["cpu_percent"] or 0.0,
                "rss": i["memory_info"].rss if i["memory_info"] else 0,
                "status": i["status"],
            }
        )
    key = "cpu_percent" if sort == "cpu" else "rss"
    procs.sort(key=lambda x: x[key], reverse=True)
    return procs[:limit]
