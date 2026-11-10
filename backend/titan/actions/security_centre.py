"""Security Centre: read-only, defensive overview of this machine."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import psutil

from ..core import Ctx
from ._tools import have


def _run(args: list[str], timeout: float = 8) -> str | None:
    if not have(args[0]):
        return None
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return p.stdout if p.returncode == 0 or p.stdout else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def connections() -> dict:
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        return {"available": False, "reason": "not permitted to list sockets"}
    names: dict[int, str] = {}

    def name(pid):
        if pid and pid not in names:
            try:
                names[pid] = psutil.Process(pid).name()
            except psutil.Error:
                names[pid] = "?"
        return names.get(pid)

    listening, active = [], []
    for c in conns:
        if c.status == psutil.CONN_LISTEN and c.laddr:
            listening.append({"address": c.laddr.ip, "port": c.laddr.port, "pid": c.pid, "process": name(c.pid),
                              "exposed": c.laddr.ip not in ("127.0.0.1", "::1")})
        elif c.raddr:
            active.append({"local_port": c.laddr.port if c.laddr else None, "remote": c.raddr.ip,
                           "remote_port": c.raddr.port, "pid": c.pid, "process": name(c.pid), "status": c.status})
    listening.sort(key=lambda x: x["port"])
    return {"available": True, "listening": listening, "active": active[:200]}


def firewall() -> dict:
    conf = Path("/etc/ufw/ufw.conf")
    try:
        text = conf.read_text()
    except OSError:
        return {"available": False, "reason": "ufw is not installed or its config is unreadable"}
    return {"available": True, "tool": "ufw", "enabled": "ENABLED=yes" in text.replace(" ", "")}


def ssh() -> dict:
    active = None
    for unit in ("ssh", "sshd"):
        out = _run(["systemctl", "is-active", unit])
        if out is not None and out.strip() == "active":
            active = True
            break
        if out is not None:
            active = False
    cfg, settings = Path("/etc/ssh/sshd_config"), {}
    try:
        for line in cfg.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("PermitRootLogin", "PasswordAuthentication", "Port"):
                settings[parts[0]] = parts[1]
    except OSError:
        pass
    return {"available": active is not None or bool(settings), "active": active, "settings": settings,
            "installed": cfg.exists()}


def updates() -> dict:
    out = _run(["apt", "list", "--upgradable"], timeout=20)
    if out is None:
        return {"available": False, "reason": "apt is not available"}
    pkgs = [l.split("/")[0] for l in out.splitlines() if "/" in l and "upgradable" in l]
    return {"available": True, "count": len(pkgs), "security": sum("-security" in l for l in out.splitlines()),
            "packages": pkgs[:50]}


def logins() -> dict:
    sessions = [{"user": u.name, "terminal": u.terminal, "host": u.host, "started": u.started} for u in psutil.users()]
    recent = _run(["last", "-n", "10", "-F"])
    return {"sessions": sessions,
            "recent": [l for l in (recent or "").splitlines() if l.strip() and not l.startswith(("wtmp", "btmp"))][:10]}


def file_permissions(home: Path) -> dict:
    findings = []

    def check(p: Path, max_mode: int, what: str) -> None:
        try:
            mode = stat.S_IMODE(p.stat().st_mode)
        except OSError:
            return
        if mode & ~max_mode:
            findings.append({"path": str(p), "mode": oct(mode), "issue": f"{what} should be at most {oct(max_mode)}"})

    check(home, 0o755, "home directory")
    sshd = home / ".ssh"
    if sshd.is_dir():
        check(sshd, 0o700, "~/.ssh")
        for f in sshd.iterdir():
            if f.is_file() and not f.name.endswith(".pub") and f.name not in ("known_hosts", "config", "authorized_keys"):
                check(f, 0o600, "private key")
        check(sshd / "authorized_keys", 0o644, "authorized_keys")
    try:
        for f in home.iterdir():
            if f.name.startswith(".") and f.name != ".ssh" and f.is_file():
                try:
                    if stat.S_IMODE(f.stat().st_mode) & 0o002:
                        findings.append({"path": str(f), "mode": oct(stat.S_IMODE(f.stat().st_mode)),
                                         "issue": "world-writable dotfile"})
                except OSError:
                    pass
    except OSError:
        pass
    return {"findings": findings}


def overview(ctx: Ctx, a: dict) -> dict:
    data = {"connections": connections(), "firewall": firewall(), "ssh": ssh(), "updates": updates(),
            "logins": logins(), "file_permissions": file_permissions(ctx.settings.home),
            "permissions": {k: v for k, v in ctx.db.get_preferences().items() if k.startswith("permissions.")},
            "is_root": os.geteuid() == 0}
    alerts = []
    fw = data["firewall"]
    if fw.get("available") and not fw["enabled"]:
        alerts.append({"level": "warning", "text": "The firewall (ufw) is disabled"})
    if data["ssh"].get("settings", {}).get("PermitRootLogin") == "yes":
        alerts.append({"level": "warning", "text": "SSH permits root login"})
    if data["ssh"].get("active") and data["ssh"].get("settings", {}).get("PasswordAuthentication") == "yes":
        alerts.append({"level": "info", "text": "SSH accepts password logins; keys are safer"})
    up = data["updates"]
    if up.get("available") and up["count"]:
        alerts.append({"level": "warning" if up["security"] else "info",
                       "text": f"{up['count']} package update(s) available ({up['security']} security)"})
    for f in data["file_permissions"]["findings"]:
        alerts.append({"level": "warning", "text": f"{f['path']}: {f['issue']} (is {f['mode']})"})
    conns = data["connections"]
    if conns.get("available"):
        exposed = [l for l in conns["listening"] if l["exposed"]]
        if exposed:
            alerts.append({"level": "info", "text": f"{len(exposed)} service(s) listening on all interfaces: "
                           + ", ".join(sorted({str(l['port']) for l in exposed})[:12])})
    if data["is_root"]:
        alerts.append({"level": "warning", "text": "TITAN Core is running as root; run it as your normal user"})
    data["alerts"] = alerts
    return data


def register(reg) -> None:
    reg.add("security.overview", "security", "Security overview: firewall, SSH, updates, logins, listening ports, "
            "risky file permissions and alerts (read-only)", overview, readonly=True)
    reg.add("security.audit_log", "security", "Recent TITAN audit log entries",
            lambda c, a: c.db.audit_entries(min(int(a.get("limit", 100)), 1000)), {"limit": {"type": "integer"}},
            readonly=True, ai=False)
