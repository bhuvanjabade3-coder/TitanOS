"""Developer mode: project discovery, Git inspection, environments."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from ..core import ActionError, Ctx
from ._tools import sh
from .files import SENSITIVE, SKIP_DIRS, resolve

MARKERS = {"pyproject.toml": "python", "requirements.txt": "python", "setup.py": "python",
           "package.json": "node", "tsconfig.json": "typescript", "index.html": "web"}
GIT_OPS = {"status": ["status", "--short", "--branch"], "log": ["log", "--oneline", "-n", "20"],
           "diff": ["diff", "--stat"], "branch": ["branch", "--all"], "remote": ["remote", "-v"]}


def detect(p: Path) -> dict:
    kinds = sorted({k for f, k in MARKERS.items() if (p / f).exists()})
    cmds: dict[str, str] = {}
    pkg = p / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text()).get("scripts", {})
            for s in ("dev", "start", "build", "test", "lint"):
                if s in scripts:
                    cmds[s] = f"npm run {s}"
        except (json.JSONDecodeError, OSError):
            pass
    if "python" in kinds:
        if (p / "tests").is_dir() or (p / "pytest.ini").exists():
            cmds.setdefault("test", "python -m pytest -q")
    venv = next((v for v in (".venv", "venv") if (p / v / "bin" / "python").exists()), None)
    return {"path": str(p), "name": p.name, "kinds": kinds, "git": (p / ".git").exists(), "venv": venv, "commands": cmds}


def projects(ctx: Ctx, a: dict) -> dict:
    root = resolve(ctx, a.get("root", "~"), must_exist=True)
    depth, found, deadline = min(int(a.get("depth", 3)), 6), [], time.monotonic() + 6
    for dirpath, dirs, files in os.walk(root):
        p = Path(dirpath)
        level = len(p.relative_to(root).parts)
        is_project = ".git" in dirs or any(f in MARKERS and f != "index.html" for f in files)
        dirs[:] = [] if (is_project or level >= depth) else [
            d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS and d not in SENSITIVE]
        if is_project and p != root:
            found.append(detect(p))
        if len(found) >= 100 or time.monotonic() > deadline:
            break
    return {"root": str(root), "projects": sorted(found, key=lambda x: x["name"].lower())}


def project_info(ctx: Ctx, a: dict) -> dict:
    return detect(resolve(ctx, a["path"], must_exist=True))


def git(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a["path"], must_exist=True)
    if a["op"] not in GIT_OPS:
        raise ActionError(f"op must be one of {', '.join(GIT_OPS)} (use terminal.run for anything that changes the repo)")
    out = sh(["git", "-C", str(p), "--no-pager", *GIT_OPS[a["op"]]], timeout=20)
    return {"path": str(p), "op": a["op"], "output": out[:50_000]}


def venv_create(ctx: Ctx, a: dict) -> dict:
    p = resolve(ctx, a["path"], must_exist=True)
    target = p / ".venv"
    if target.exists():
        raise ActionError(f"{target} already exists")
    sh([sys.executable, "-m", "venv", str(target)], timeout=120)
    return {"created": str(target), "python": str(target / "bin" / "python")}


def register(reg) -> None:
    S = {"type": "string"}
    reg.add("dev.projects", "dev", "Find software projects (git repos, Python/Node projects) under a directory",
            projects, {"root": S, "depth": {"type": "integer"}}, readonly=True)
    reg.add("dev.project_info", "dev", "Detect a project's type, virtualenv and its dev/build/test commands",
            project_info, {"path": S}, ["path"], readonly=True)
    reg.add("dev.git", "dev", "Read-only Git inspection: status, log, diff, branch or remote", git,
            {"path": S, "op": {"type": "string", "enum": list(GIT_OPS)}}, ["path", "op"], readonly=True)
    reg.add("dev.venv_create", "dev", "Create a Python virtual environment (.venv) inside a project", venv_create, {"path": S}, ["path"])
