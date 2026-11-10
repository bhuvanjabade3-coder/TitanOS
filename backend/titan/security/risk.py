"""Shell command risk classification.

This module only *classifies*; it never executes. The policy is an allowlist:
a command is LOW only if every segment is a known read-only program used in a
read-only way. Anything unknown is MEDIUM, anything destructive, privileged or
security-sensitive is HIGH. MEDIUM and HIGH require explicit user approval.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import asdict, dataclass, field
from enum import Enum


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_ORDER = {Risk.LOW: 0, Risk.MEDIUM: 1, Risk.HIGH: 2}

READ_ONLY = {
    "ls", "pwd", "cat", "echo", "whoami", "date", "uname", "df", "du", "free",
    "ps", "uptime", "head", "tail", "wc", "grep", "which", "id", "hostname",
    "stat", "file", "lsb_release", "nproc", "lscpu", "lsblk", "tree", "sort",
    "uniq", "cut", "true", "basename", "dirname", "realpath", "printf",
}
GIT_READ_ONLY = {"status", "log", "diff", "show", "branch", "remote", "rev-parse", "describe"}

HIGH_PROGRAMS = {
    "sudo": "privilege escalation", "su": "privilege escalation", "doas": "privilege escalation",
    "pkexec": "privilege escalation",
    "rm": "deletes files", "rmdir": "deletes directories", "shred": "destroys file contents",
    "dd": "raw device/file overwrite", "mkfs": "formats a filesystem", "fdisk": "partitioning",
    "parted": "partitioning", "wipefs": "erases filesystem signatures", "truncate": "truncates files",
    "shutdown": "power state change", "reboot": "power state change", "poweroff": "power state change",
    "halt": "power state change",
    "chmod": "changes permissions", "chown": "changes ownership", "chgrp": "changes ownership",
    "kill": "terminates processes", "killall": "terminates processes", "pkill": "terminates processes",
    "systemctl": "service management", "service": "service management",
    "apt": "package management", "apt-get": "package management", "dpkg": "package management",
    "snap": "package management",
    "ufw": "firewall change", "iptables": "firewall change", "nft": "firewall change",
    "passwd": "credential change", "useradd": "account change", "usermod": "account change",
    "userdel": "account change", "visudo": "sudoers change", "crontab": "scheduled execution",
    "mount": "mounts filesystems", "umount": "unmounts filesystems",
    "ssh-keygen": "SSH key change", "eval": "evaluates arbitrary code", "exec": "replaces the shell",
}
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "python", "python3", "perl", "ruby", "node"}
SENSITIVE_PATHS = re.compile(
    r"(^|[\s=])(/etc/|/boot/|/dev/|/sys/|/proc/|/usr/|/var/|/root/|~?/?\.ssh/|.*\.gnupg/|.*authorized_keys)"
)
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")


@dataclass
class Assessment:
    command: str
    risk: Risk
    requires_approval: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk"] = self.risk.value
        return d


def _segment(tokens: list[str], raw: str) -> tuple[Risk, str]:
    # strip leading VAR=value assignments
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return Risk.MEDIUM, "environment assignment only"
    prog = tokens[0].rsplit("/", 1)[-1]
    args = tokens[1:]
    if prog in HIGH_PROGRAMS or prog.startswith("mkfs."):
        return Risk.HIGH, f"`{prog}`: {HIGH_PROGRAMS.get(prog, 'formats a filesystem')}"
    if prog in SHELLS:
        return Risk.HIGH, f"`{prog}`: runs arbitrary code through an interpreter"
    if prog == "find":
        if any(a in ("-delete", "-exec", "-execdir", "-ok", "-fprint", "-fls") for a in args):
            return Risk.HIGH, "`find` with an action that modifies or executes"
        return Risk.LOW, "`find`: read-only search"
    if prog == "git":
        sub = next((a for a in args if not a.startswith("-")), "")
        if sub in GIT_READ_ONLY:
            return Risk.LOW, f"`git {sub}`: read-only"
        if sub in ("push", "reset", "clean", "rebase", "filter-branch"):
            return Risk.HIGH, f"`git {sub}`: rewrites or publishes history"
        return Risk.MEDIUM, f"`git {sub}`: modifies the repository"
    if prog in ("curl", "wget"):
        return Risk.MEDIUM, f"`{prog}`: network transfer"
    if prog in ("mv", "cp"):
        if SENSITIVE_PATHS.search(raw):
            return Risk.HIGH, f"`{prog}` touching a system or credential path"
        return Risk.MEDIUM, f"`{prog}`: can overwrite files"
    if prog in READ_ONLY:
        if SENSITIVE_PATHS.search(raw) and re.search(r"shadow|\.ssh/|\.gnupg/|authorized_keys", raw):
            return Risk.HIGH, f"`{prog}` reading credential material"
        return Risk.LOW, f"`{prog}`: read-only"
    return Risk.MEDIUM, f"`{prog}`: not on the read-only allowlist"


def classify(command: str) -> Assessment:
    cmd = command.strip()
    reasons: list[str] = []
    risk = Risk.LOW

    def bump(level: Risk, why: str) -> None:
        nonlocal risk
        reasons.append(why)
        if _ORDER[level] > _ORDER[risk]:
            risk = level

    if not cmd:
        return Assessment(command, Risk.LOW, False, ["empty command"])

    if "$(" in cmd or "`" in cmd or "<(" in cmd or ">(" in cmd:
        bump(Risk.HIGH, "command/process substitution hides what actually runs")
    if re.search(r"\|\s*(sudo\s+)?(ba|z|da)?sh\b", cmd):
        bump(Risk.HIGH, "pipes data into a shell")
    if re.search(r"(?<![0-9&])>>?|\btee\b", cmd):
        target = re.search(r">>?\s*(\S+)", cmd)
        if target and target.group(1) in ("/dev/null", "&1", "&2"):
            pass
        elif SENSITIVE_PATHS.search(cmd):
            bump(Risk.HIGH, "writes to a system or credential path")
        else:
            bump(Risk.MEDIUM, "output redirection writes files")
    if re.search(r":\(\)\s*\{", cmd):
        bump(Risk.HIGH, "fork bomb pattern")

    for raw in _SEGMENT_SPLIT.split(cmd):
        raw = raw.strip()
        if not raw:
            continue
        try:
            tokens = shlex.split(raw)
        except ValueError:
            bump(Risk.HIGH, "unparseable shell syntax")
            continue
        level, why = _segment(tokens, raw)
        bump(level, why)

    return Assessment(command, risk, risk is not Risk.LOW, reasons)
