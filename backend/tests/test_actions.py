import json
import os
import stat
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from titan.tasks import TaskConflict


def ok(out):
    assert out["status"] == "ok", out
    return out["result"]


def wait_task(core, tid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        t = core.tasks.get(tid)
        if t["status"] not in ("queued", "running"):
            return t
        time.sleep(0.05)
    raise AssertionError(f"task still {t['status']}")


# ------------------------------------------------------------------ files
def test_file_basics(act, home):
    ok(act("fs.mkdir", path="~/Projects"))
    assert (home / "Projects").is_dir()
    assert act("fs.mkdir", path="~/Projects")["status"] == "error"
    ok(act("fs.write", path="Projects/a.txt", content="hello"))
    assert ok(act("fs.read", path="~/Projects/a.txt"))["text"] == "hello"
    names = [e["name"] for e in ok(act("fs.list", path="~/Projects"))["entries"]]
    assert names == ["a.txt"]
    ok(act("fs.rename", path="~/Projects/a.txt", new_name="b.txt"))
    assert (home / "Projects/b.txt").read_text() == "hello"
    assert act("fs.rename", path="~/Projects/b.txt", new_name="../x")["status"] == "error"
    (home / "bin.dat").write_bytes(b"\x00\x01\x02")
    assert ok(act("fs.read", path="~/bin.dat"))["binary"] is True


def test_write_never_overwrites_silently(act, core, home):
    (home / "a.txt").write_text("old")
    assert act("fs.write", path="~/a.txt", content="new")["status"] == "error"
    out = act("fs.write", path="~/a.txt", content="new", overwrite=True)
    assert out["status"] == "approval_required" and out["risk"] == "medium"
    assert (home / "a.txt").read_text() == "old"
    res = core.registry.decide(out["approval_id"], True)
    assert res["outcome"]["status"] == "ok" and (home / "a.txt").read_text() == "new"


@pytest.mark.parametrize("path", ["/etc/passwd", "~/../outside", "/", "~/.ssh/id_rsa", "~/.gnupg/x",
                                  "~/.mozilla/firefox/logins.json", ""])
def test_paths_are_confined(act, path):
    for name, extra in (("fs.read", {}), ("fs.list", {}), ("fs.write", {"content": "x"}), ("fs.delete", {})):
        params = {"paths": [path]} if name == "fs.delete" else {"path": path}
        out = act(name, **params, **extra)
        assert out["status"] == "error", (name, path, out)


def test_symlink_cannot_escape_home(act, home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("s")
    (home / "link").symlink_to(outside)
    assert act("fs.read", path="~/link/secret")["status"] == "error"
    assert act("fs.write", path="~/link/new", content="x")["status"] == "error"


def test_own_data_dir_is_off_limits(act, settings, tmp_path):
    # even when the data dir lives inside home
    from titan.actions.files import resolve
    from titan.core import ActionError, Ctx

    class S:  # minimal settings stand-in
        home = tmp_path
        data_dir = tmp_path / "titan"
    with pytest.raises(ActionError):
        resolve(Ctx(type("C", (), {"settings": S})(), "user"), str(tmp_path / "titan" / "api_token"))


@pytest.mark.parametrize("path", ["~/.bashrc", "~/.profile", "~/.config/autostart/x.desktop",
                                  "~/.config/systemd/user/x.service", "~/.local/share/applications/x.desktop",
                                  "~/.local/bin/ls"])
def test_persistence_paths_need_high_approval(act, core, home, path):
    core.db.set_preference("permissions.files", "allow")  # cannot pre-authorise high risk
    out = act("fs.write", path=path, content="x")
    assert out["status"] == "approval_required" and out["risk"] == "high"
    (home / "evil.desktop").write_text("x")
    (home / ".config/autostart").mkdir(parents=True, exist_ok=True)
    out = act("fs.move", sources=["~/evil.desktop"], dest_dir="~/.config/autostart")
    assert out["status"] == "approval_required" and out["risk"] == "high"


def test_move_copy_and_bulk_gate(act, core, home):
    (home / "dst").mkdir()
    for i in range(7):
        (home / f"f{i}.txt").write_text(str(i))
    ok(act("fs.copy", sources=["~/f0.txt"], dest_dir="~/dst"))
    assert (home / "f0.txt").exists() and (home / "dst/f0.txt").exists()
    assert act("fs.move", sources=["~/f0.txt"], dest_dir="~/dst")["status"] == "error"  # would overwrite
    assert (home / "f0.txt").read_text() == "0"
    bulk = [f"~/f{i}.txt" for i in range(1, 7)]
    out = act("fs.move", sources=bulk, dest_dir="~/dst")
    assert out["status"] == "approval_required" and out["risk"] == "medium"
    assert (home / "f1.txt").exists()
    core.db.set_preference("permissions.files", "allow")
    assert len(ok(act("fs.move", sources=bulk, dest_dir="~/dst"))["done"]) == 6
    assert not (home / "f1.txt").exists()
    assert act("fs.move", sources=["~/dst"], dest_dir="~/dst")["status"] == "error"


def test_trash_is_recoverable(act, home):
    (home / "doc.txt").write_text("keep me")
    ok(act("fs.trash", paths=["~/doc.txt"]))
    assert not (home / "doc.txt").exists()
    trash = home / ".local/share/Trash"
    assert (trash / "files/doc.txt").read_text() == "keep me"
    assert f"Path={home}/doc.txt" in (trash / "info/doc.txt.trashinfo").read_text()
    (home / "doc.txt").write_text("second")
    ok(act("fs.trash", paths=["~/doc.txt"]))
    assert (trash / "files/doc.txt.1").read_text() == "second"
    assert act("fs.trash", paths=["~"])["status"] == "error"


def test_ai_trash_needs_approval(act, home):
    (home / "x.txt").write_text("x")
    out = act("fs.trash", _actor="ai", paths=["~/x.txt"])
    assert out["status"] == "approval_required" and (home / "x.txt").exists()


def test_permanent_delete_always_needs_approval(act, core, home):
    core.db.set_preference("permissions.files", "allow")
    (home / "a").write_text("a")
    (home / "b").write_text("b")
    out = act("fs.delete", paths=["~/a"])
    assert out["status"] == "approval_required" and out["risk"] == "high"
    assert (home / "a").exists()
    denied = core.registry.decide(out["approval_id"], False)
    assert denied["outcome"]["status"] == "denied" and (home / "a").exists()
    from titan.core import ActionError
    with pytest.raises(ActionError):  # single use
        core.registry.decide(out["approval_id"], True)
    out = act("fs.delete", paths=["~/b"])
    res = core.registry.decide(out["approval_id"], True)
    assert res["approval"]["status"] == "executed" and not (home / "b").exists()
    with pytest.raises(ActionError):
        core.registry.decide(out["approval_id"], True)


def test_approval_executes_stored_params_and_expires(act, core, home):
    (home / "a").write_text("a")
    out = act("fs.delete", paths=["~/a"])
    aid = out["approval_id"]
    assert core.registry.get_approval(aid)["params"] == {"paths": ["~/a"]}
    old = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat(timespec="seconds")
    core.db.x("UPDATE approvals SET created_at=? WHERE id=?", (old, aid))
    from titan.core import ActionError
    with pytest.raises(ActionError, match="expired"):
        core.registry.decide(aid, True)
    assert (home / "a").exists()


def test_approved_action_that_fails_is_reported_failed(act, core, home):
    (home / "a").write_text("a")
    out = act("fs.delete", paths=["~/a"])
    (home / "a").unlink()  # disappears before the user approves
    res = core.registry.decide(out["approval_id"], True)
    assert res["outcome"]["status"] == "error" and res["approval"]["status"] == "failed"


def test_search(act, home):
    (home / "proj/node_modules/pkg").mkdir(parents=True)
    (home / "proj/node_modules/pkg/report.py").write_text("")
    (home / "proj/Report_final.py").write_text("")
    (home / "proj/notes.md").write_text("")
    r = ok(act("fs.search", query="report"))
    assert [Path(x["path"]).name for x in r["results"]] == ["Report_final.py"]
    assert len(ok(act("fs.search", query="*.md"))["results"]) == 1
    assert ok(act("fs.storage"))["home"]["total"] > 0


# ------------------------------------------------------------------ policy
def test_policy_deny_and_ask(act, core, home):
    core.db.set_preference("permissions.files", "deny")
    assert act("fs.list", path="~")["status"] == "denied"
    core.db.set_preference("permissions.files", "ask")
    assert act("fs.list", path="~")["status"] == "approval_required"
    assert act("no.such")["status"] == "error"
    assert act("fs.list", bogus=1)["status"] == "error"
    assert act("fs.read")["status"] == "error"
    assert act("fs.read", path=5)["status"] == "error"
    assert act("fs.search", query="x", limit=True)["status"] == "error"


def test_everything_is_audited(act, core, home):
    act("fs.mkdir", path="~/A")
    act("fs.delete", paths=["~/A"])
    act("fs.read", path="/etc/passwd")
    act("fs.write", path="~/big.txt", content="x" * 5000)
    log = core.db.audit_entries()
    outcomes = {e["action"]: e["outcome"] for e in log}
    assert outcomes["fs.mkdir"] == "ok"
    assert outcomes["fs.delete"].startswith("approval_required")
    assert outcomes["fs.read"].startswith("error")
    big = next(e for e in log if e["action"] == "fs.write")
    assert len(json.dumps(big["detail"])) < 1000  # file contents are not copied into the log


def test_ai_cannot_change_permissions_without_approval(act, core):
    out = act("prefs.set", _actor="ai", key="permissions.terminal", value="allow")
    assert out["status"] == "approval_required" and out["risk"] == "high"
    assert core.db.pref("permissions.terminal") is None
    assert act("prefs.set", key="permissions.terminal", value="everything")["status"] == "error"
    ok(act("prefs.set", key="theme.accent", value="#3b9dff"))
    ok(act("prefs.set", _actor="ai", key="theme.mode", value="light"))
    assert ok(act("prefs.get")) == {"theme.accent": "#3b9dff", "theme.mode": "light"}


# ------------------------------------------------------------------ terminal
def test_terminal_gating(act, core, home):
    r = ok(act("terminal.run", command="echo hi && pwd"))
    assert r["stdout"].splitlines() == ["hi", str(home)] and r["exit_code"] == 0
    r = ok(act("terminal.run", command="ls /nonexistent-zzz"))
    assert r["exit_code"] != 0 and "No such file" in r["stderr"]
    out = act("terminal.run", command="touch made.txt")
    assert out["status"] == "approval_required" and not (home / "made.txt").exists()
    core.registry.decide(out["approval_id"], True)
    assert (home / "made.txt").exists()
    core.db.set_preference("permissions.terminal", "allow")
    ok(act("terminal.run", command="touch made2.txt"))
    out = act("terminal.run", command="sudo true")
    assert out["status"] == "approval_required" and out["risk"] == "high"
    assert act("terminal.run", command="rm made.txt")["status"] == "approval_required"
    assert act("terminal.run", command="ls", cwd="/etc")["status"] == "error"


def test_terminal_timeout_and_env_scrub(act, core, monkeypatch):
    core.db.set_preference("permissions.terminal", "allow")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    monkeypatch.setenv("TITAN_SOMETHING", "internal")
    out = ok(act("terminal.run", command="env"))["stdout"]
    assert "should-not-leak" not in out and "TITAN_SOMETHING" not in out and "PATH=" in out
    t0 = time.time()
    r = ok(act("terminal.run", command="sleep 30", timeout=1))
    assert r["timed_out"] and r["exit_code"] is None and time.time() - t0 < 8


def test_terminal_background_and_cancel(act, core):
    core.db.set_preference("permissions.terminal", "allow")
    tid = ok(act("terminal.run", command="echo one; echo two", background=True))["task_id"]
    t = wait_task(core, tid)
    assert t["status"] == "done" and t["result"]["output"] == "one\ntwo\n"
    tid = ok(act("terminal.run", command="exit 3", background=True))["task_id"]
    t = wait_task(core, tid)
    assert t["status"] == "failed" and "exit code 3" in t["error"]
    tid = ok(act("terminal.run", command="sleep 60", background=True))["task_id"]
    time.sleep(0.4)
    ok(act("tasks.cancel", id=tid))
    assert wait_task(core, tid)["status"] == "cancelled"
    assert act("tasks.cancel", id=tid)["status"] == "error"


def test_proc_kill_needs_approval(act):
    assert act("proc.kill", pid=os.getpid())["status"] == "error"
    assert act("proc.kill", pid=1)["status"] == "error"
    import subprocess
    p = subprocess.Popen(["sleep", "30"])
    try:
        out = act("proc.kill", pid=p.pid)
        assert out["status"] == "approval_required" and out["risk"] == "high" and p.poll() is None
    finally:
        p.kill()
    assert any(x["pid"] == os.getpid() for x in ok(act("proc.list", limit=500)))


# ------------------------------------------------------------------ tasks
def test_task_locks_progress_and_failure(core, tmp_path):
    gate, started = threading.Event(), threading.Event()

    def hold(ctl):
        ctl.progress(0.5, "half")
        started.set()
        gate.wait(5)
        return {"n": 1}

    a = core.tasks.submit("a", hold, locks=[tmp_path / "proj"])
    started.wait(2)
    assert core.tasks.get(a["id"])["progress"] == 0.5
    for clash in (tmp_path / "proj", tmp_path / "proj" / "sub" / "f.txt", tmp_path):
        with pytest.raises(TaskConflict):
            core.tasks.submit("b", lambda c: None, locks=[clash])
    other = core.tasks.submit("c", lambda c: "fine", locks=[tmp_path / "elsewhere"])
    assert wait_task(core, other["id"])["result"] == "fine"
    gate.set()
    assert wait_task(core, a["id"])["result"] == {"n": 1}
    again = core.tasks.submit("d", lambda c: 1 / 0, locks=[tmp_path / "proj"])  # lock released
    t = wait_task(core, again["id"])
    assert t["status"] == "failed" and "ZeroDivisionError" in t["error"]


def test_tasks_marked_interrupted_after_restart(core, settings):
    from titan.db import Database
    from titan.events import EventBus
    from titan.tasks import TaskManager
    core.db.x("INSERT INTO tasks(id,name,status,created_at) VALUES('zz','x','running','2026-01-01')")
    TaskManager(Database(settings.db_path), EventBus()).shutdown()
    assert core.tasks.get("zz")["status"] == "interrupted"


# ------------------------------------------------------------------ notifications / memory
def test_notifications_and_reminders(act, core):
    n = ok(act("notify.send", title="Hello", body="b"))
    assert n["category"] == "app" and n["read"] == 0
    core.db.set_preference("notifications.muted", ["download"])
    assert core.notifier.notify("download", "muted") is None
    assert act("notify.send", title="x", category="nope")["status"] == "error"
    assert len(ok(act("notify.list"))) == 1
    ok(act("notify.read"))
    assert ok(act("notify.list", unread_only=True)) == []
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    ok(act("reminders.add", text="stand up", due_at=past))
    ok(act("reminders.add", text="later", due_at=future))
    assert act("reminders.add", text="x", due_at="tomorrow-ish")["status"] == "error"
    assert core.notifier.tick() == 1 and core.notifier.tick() == 0
    assert core.notifier.list()[0]["body"] == "stand up"
    assert [r["done"] for r in ok(act("reminders.list"))] == [0, 1]


def test_memory_is_user_approved_and_controllable(act, core):
    out = act("memory.save", _actor="ai", content="Prefers dark mode", kind="preference")
    assert out["status"] == "approval_required" and ok(act("memory.search")) == []
    core.registry.decide(out["approval_id"], True)
    m = ok(act("memory.save", content="Project Apollo lives in ~/code/apollo", kind="project"))
    assert m["source"] == "user"
    assert [x["content"] for x in ok(act("memory.search", query="dark prefers"))] == ["Prefers dark mode"]
    assert ok(act("memory.search", query="100%")) == []
    assert len(ok(act("memory.search", kind="project"))) == 1
    ok(act("memory.update", id=m["id"], content="Apollo moved to ~/work/apollo"))
    exported = ok(act("memory.export"))
    assert {x["content"] for x in exported["memories"]} == {"Prefers dark mode", "Apollo moved to ~/work/apollo"}
    ok(act("memory.delete", id=m["id"]))
    assert act("memory.delete", id=m["id"])["status"] == "error"
    assert act("memory.save", content="x", kind="bogus")["status"] == "error"
    assert act("memory.delete", _actor="ai", id=1)["status"] == "approval_required"


# ------------------------------------------------------------------ apps / desktop
@pytest.fixture
def desktop_apps(home, tmp_path, monkeypatch):
    share = tmp_path / "share"
    (share / "applications").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_DIRS", str(share))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "userdata"))
    marker = tmp_path / "launched"
    (share / "applications/firefox.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName=Firefox Web Browser\nExec=touch {marker} %u\nIcon=firefox\n"
        "Categories=Network;WebBrowser;\nKeywords=internet;web;\n\n[Desktop Action new]\nExec=false\n")
    (share / "applications/org.gnome.TextEditor.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Text Editor\nExec=true %U\nCategories=Utility;TextEditor;\n")
    (share / "applications/hidden.desktop").write_text("[Desktop Entry]\nType=Application\nName=Hidden\nExec=true\nNoDisplay=true\n")
    (share / "applications/htop.desktop").write_text("[Desktop Entry]\nType=Application\nName=Htop\nExec=htop\nTerminal=true\n")
    (share / "applications/broken.desktop").write_text("not a desktop file")
    return marker


def test_apps(act, desktop_apps):
    listing = ok(act("apps.list"))
    assert [a["name"] for a in listing["apps"]] == ["Firefox Web Browser", "Htop", "Text Editor"]
    assert listing["apps"][0]["category"] == "Internet"
    assert [a["id"] for a in ok(act("apps.list", query="browser"))["apps"]] == ["firefox"]
    r = ok(act("apps.launch", app="Firefox"))
    assert r["id"] == "firefox"
    for _ in range(40):
        if desktop_apps.exists():
            break
        time.sleep(0.05)
    assert desktop_apps.exists(), "Exec line did not run"
    assert act("apps.launch", app="no-such-app")["status"] == "error"
    assert "terminal" in act("apps.launch", app="htop")["error"]
    ok(act("apps.pin", app="org.gnome.TextEditor"))
    listing = ok(act("apps.list"))
    assert listing["pinned"] == ["org.gnome.TextEditor"] and listing["recent"] == ["firefox"]
    assert ok(act("apps.pin", app="org.gnome.TextEditor", pinned=False))["pinned"] == []
    assert act("apps.pin", app="nope")["status"] == "error"


WMCTRL_L = """0x03a00007  0 4321   firefox.Firefox      vm Mozilla Firefox
0x04000003  1 5555   gnome-terminal-server.Gnome-terminal  vm user@vm: ~/code
0x01200002 -1 900    desktop_window.Nautilus vm Desktop
"""
WMCTRL_D = "0  * DG: 1920x1080  VP: 0,0  WA: 0,27 1920x1053  Workspace 1\n1  - DG: 1920x1080  VP: N/A  WA: 0,27 1920x1053  Workspace 2\n"


def test_window_control(act, core, fakebin, tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    assert "Xorg" in act("windows.list")["error"]
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    log = tmp_path / "calls"
    (tmp_path / "l").write_text(WMCTRL_L)
    (tmp_path / "d").write_text(WMCTRL_D)
    fakebin("wmctrl", f'echo "wmctrl $@" >> {log}\ncase "$1" in -lpx) cat {tmp_path}/l;; -d) cat {tmp_path}/d;; esac')
    fakebin("xdotool", f'echo "xdotool $@" >> {log}')
    r = ok(act("windows.list"))
    assert [(w["id"], w["workspace"], w["title"]) for w in r["windows"]] == [
        ("0x03a00007", 0, "Mozilla Firefox"), ("0x04000003", 1, "user@vm: ~/code")]
    assert [(w["index"], w["current"]) for w in r["workspaces"]] == [(0, True), (1, False)]
    ok(act("windows.focus", window="0x03a00007"))
    ok(act("windows.maximize", window="0x03a00007"))
    ok(act("windows.minimize", window="0x03a00007"))
    ok(act("workspace.switch", index=1))
    assert act("windows.focus", window="1; rm -rf ~")["status"] == "error"
    assert act("windows.close", window="0x03a00007")["status"] == "approval_required"
    out = act("input.type", text="hello")
    assert out["status"] == "approval_required"
    assert act("input.key", keys="ctrl+alt+Delete")["status"] == "error"
    assert act("input.key", keys="ctrl+l; reboot")["status"] == "error"
    core.db.set_preference("permissions.input", "allow")
    ok(act("input.type", text="-rf hello"))
    ok(act("input.key", keys="ctrl+l"))
    ok(act("input.click", x=10, y=20))
    ok(act("input.scroll", amount=3))
    calls = log.read_text().splitlines()
    assert "wmctrl -ia 0x03a00007" in calls
    assert "wmctrl -ir 0x03a00007 -b add,maximized_vert,maximized_horz" in calls
    assert f"xdotool windowminimize {0x03a00007}" in calls
    assert "wmctrl -s 1" in calls
    assert "xdotool type --clearmodifiers --delay 12 -- -rf hello" in calls
    assert "xdotool mousemove 10 20 click 1" in calls
    assert "xdotool click --repeat 3 5" in calls


def test_missing_tool_is_reported_not_faked(act, monkeypatch, tmp_path):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing installed
    out = act("windows.list")
    assert out["status"] == "error" and "sudo apt install wmctrl" in out["error"]
    assert "xdg-utils" in act("browser.open", url="https://example.com")["error"]


# ------------------------------------------------------------------ browser
def test_url_checks():
    from titan.actions.browser import check_url
    from titan.core import ActionError
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "http://localhost:8710/api", "http://127.0.0.1/",
                "http://169.254.169.254/latest", "http://10.0.0.5/", "https://user:pw@example.com/", "http://[::1]/"):
        with pytest.raises(ActionError):
            check_url(bad)
    assert check_url("http://localhost:3000/", public_only=False) == "http://localhost:3000/"


def test_extract():
    from titan.actions.browser import extract
    html = ("<html><head><title> My Page </title><style>.x{}</style></head><body><script>evil()</script>"
            "<h1>Heading</h1><p>First   para <a href='/a'>link A</a></p><p>Second</p></body></html>")
    d = extract(html, "https://ex.com/dir/")
    assert d["title"] == "My Page" and "evil" not in d["text"] and ".x" not in d["text"]
    assert d["text"].split("\n") == ["Heading", "First para link A", "Second"]
    assert d["links"] == [{"text": "link A", "url": "https://ex.com/a"}]


@pytest.fixture
def webserver(tmp_path, monkeypatch):
    import http.server
    import socketserver
    from titan.actions import browser

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/private":
                self.send_response(403); self.end_headers(); return
            if self.path == "/redir":
                self.send_response(302); self.send_header("Location", "/page"); self.end_headers(); return
            if self.path == "/file.bin":
                body, ctype = b"x" * 5000, "application/octet-stream"
            else:
                body, ctype = b"<title>T</title><p>Body text</p>", "text/html"
            self.send_response(200); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    real = browser.check_url
    monkeypatch.setattr(browser, "check_url", lambda url, public_only=True: real(url, public_only=False))
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_fetch_download_bookmarks(act, core, home, webserver):
    r = ok(act("browser.fetch", url=f"{webserver}/redir"))
    assert r["title"] == "T" and r["text"] == "Body text" and r["url"].endswith("/page")
    assert "does not bypass" in act("browser.fetch", url=f"{webserver}/private")["error"]
    assert act("browser.fetch", url=f"{webserver}/file.bin")["status"] == "error"
    out = act("browser.download", url=f"{webserver}/file.bin")
    assert out["status"] == "approval_required" and not (home / "Downloads").exists()
    res = core.registry.decide(out["approval_id"], True)["outcome"]["result"]
    t = wait_task(core, res["task_id"])
    assert t["status"] == "done" and (home / "Downloads/file.bin").stat().st_size == 5000
    assert core.notifier.list()[0]["title"] == "Download complete"
    b = ok(act("bookmarks.add", url="https://example.com/docs", title="Docs"))
    assert [x["title"] for x in ok(act("bookmarks.list"))] == ["Docs"]
    ok(act("bookmarks.delete", id=b["id"]))
    assert act("bookmarks.add", url="ftp://x")["status"] == "error"


def test_real_fetch_blocks_local_addresses(act):
    assert "private" in act("browser.fetch", url="http://127.0.0.1:8710/api/status")["error"]


def test_open_and_search_use_default_browser(act, fakebin, tmp_path):
    log = tmp_path / "opened"
    fakebin("xdg-open", f'echo "$@" >> {log}')
    ok(act("browser.open", url="example.com/a b"))
    ok(act("browser.search", query="python tutorials & more"))
    for _ in range(40):
        if log.exists() and len(log.read_text().splitlines()) == 2:
            break
        time.sleep(0.05)
    lines = sorted(log.read_text().splitlines())
    assert lines == ["https://duckduckgo.com/?q=python+tutorials+%26+more", "https://example.com/a b"]


# ------------------------------------------------------------------ security / settings / dev
def test_security_overview(act, home):
    (home / ".ssh").mkdir(mode=0o755)
    (home / ".ssh/id_ed25519").write_text("k")
    (home / ".ssh/id_ed25519").chmod(0o644)
    (home / ".ssh/id_ed25519.pub").write_text("p")
    r = ok(act("security.overview"))
    assert {"connections", "firewall", "ssh", "updates", "logins", "file_permissions", "alerts"} <= set(r)
    issues = {Path(f["path"]).name for f in r["file_permissions"]["findings"]}
    assert issues == {".ssh", "id_ed25519"}
    assert any("id_ed25519" in a["text"] for a in r["alerts"])
    assert isinstance(ok(act("security.audit_log")), list)


def test_settings_status_reports_availability(act, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    r = ok(act("settings.status"))
    for section in ("display", "sound", "bluetooth", "appearance"):
        assert r[section]["available"] is False and r[section]["reason"]
    assert r["network"]["available"] is True and r["storage"]["total"] > 0
    assert "pulseaudio-utils" in act("settings.set_volume", percent=50)["error"]
    assert act("settings.set_volume", percent=500)["status"] == "error"


def test_dev(act, home):
    import subprocess
    proj = home / "code/app"
    proj.mkdir(parents=True)
    (proj / "package.json").write_text(json.dumps({"scripts": {"dev": "vite", "test": "vitest"}}))
    (proj / "pyproject.toml").write_text("[project]\nname='x'\n")
    (proj / "tests").mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=proj, check=True)
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=proj, check=True, env=env)
    (proj / "new.txt").write_text("x")
    found = ok(act("dev.projects"))["projects"]
    assert [p["name"] for p in found] == ["app"]
    assert found[0]["kinds"] == ["node", "python"] and found[0]["git"]
    assert found[0]["commands"] == {"dev": "npm run dev", "test": "npm run test"}
    assert "?? new.txt" in ok(act("dev.git", path="~/code/app", op="status"))["output"]
    assert "first" in ok(act("dev.git", path="~/code/app", op="log"))["output"]
    assert act("dev.git", path="~/code/app", op="push")["status"] == "error"
    v = ok(act("dev.venv_create", path="~/code/app"))
    assert Path(v["python"]).exists()
    assert act("dev.venv_create", path="~/code/app")["status"] == "error"
    assert ok(act("dev.project_info", path="~/code/app"))["venv"] == ".venv"


# ------------------------------------------------------------------ plugins
def make_plugin(core, pid, perms, code, **manifest):
    d = core.plugins.dir / pid
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"id": pid, "name": pid.title(), "version": "1.0.0",
                                                 "permissions": perms, **manifest}))
    (d / "plugin.py").write_text(code)


PLUGIN = '''
def register(api):
    api.register_action("hello", lambda a: {"hi": a.get("name", "world")}, "Say hello", {"name": {"type": "string"}})
    api.register_action("mk", lambda a: api.perform("fs.mkdir", {"path": "~/from_plugin"}), "Make a folder")
    api.register_action("wipe", lambda a: api.perform("fs.delete", {"paths": ["~/keep"]}), "Delete")
    api.register_action("danger", lambda a: "ran", "Risky thing", risk="high")
    api.register_action("boom", lambda a: 1 / 0, "Crash")
'''


def test_plugins(act, core, home):
    make_plugin(core, "greeter", ["notifications"], PLUGIN)
    make_plugin(core, "filer", ["files"], PLUGIN)
    listing = {p["id"]: p for p in core.plugins.list()}
    assert listing["greeter"]["enabled"] is False and listing["greeter"]["permissions"] == ["notifications"]
    assert act("plugin.greeter.hello")["status"] == "error"  # nothing registered until the user enables it
    info = core.plugins.enable("greeter")
    assert info["enabled"] and "plugin.greeter.hello" in info["actions"]
    assert ok(act("plugin.greeter.hello", name="Bhu")) == {"hi": "Bhu"}
    # no `files` permission: the plugin's attempt is refused and nothing is created
    inner = ok(act("plugin.greeter.mk"))
    assert inner["status"] == "denied" and not (home / "from_plugin").exists()
    assert act("plugin.greeter.danger")["status"] == "approval_required"
    crash = act("plugin.greeter.boom")
    assert crash["status"] == "error" and "ZeroDivisionError" in crash["error"]
    # with `files` permission it works, but high-risk actions still need the user
    core.plugins.enable("filer")
    assert ok(act("plugin.filer.mk"))["status"] == "ok" and (home / "from_plugin").is_dir()
    (home / "keep").write_text("k")
    assert ok(act("plugin.filer.wipe"))["status"] == "approval_required" and (home / "keep").exists()
    core.plugins.disable("greeter")
    assert act("plugin.greeter.hello")["status"] == "error"
    assert ok(act("plugin.filer.hello")) == {"hi": "world"}


def test_bad_plugins_are_contained(core):
    from titan.plugins import PluginError
    make_plugin(core, "crashy", [], "raise RuntimeError('nope')")
    make_plugin(core, "quitter", [], "import sys\ndef register(api):\n    sys.exit(1)")
    make_plugin(core, "greedy", ["root"], "def register(api): pass")
    make_plugin(core, "noreg", [], "x = 1")
    (core.plugins.dir / "junk").mkdir()
    listing = {p["id"]: p for p in core.plugins.list()}
    assert listing["greedy"]["valid"] is False and "unknown permission" in listing["greedy"]["error"]
    assert listing["junk"]["valid"] is False
    for pid, msg in (("crashy", "RuntimeError: nope"), ("quitter", "exit"), ("greedy", "unknown permission"),
                     ("noreg", "no register"), ("../etc", "No plugin")):
        with pytest.raises(PluginError, match=msg):
            core.plugins.enable(pid)
    assert {p["id"]: p for p in core.plugins.list()}["crashy"]["error"] == "RuntimeError: nope"
    assert not any(k.startswith("plugin.") for k in core.registry.actions)


def test_enabled_plugins_reload_on_restart(core, settings, home):
    make_plugin(core, "greeter", [], PLUGIN)
    core.plugins.enable("greeter")
    from titan.core import Core
    from titan.db import Database
    again = Core(settings, Database(settings.db_path))
    try:
        assert again.registry.perform("user", "plugin.greeter.hello", {})["status"] == "ok"
        (again.plugins.dir / "greeter/plugin.py").write_text("raise ValueError('broke after update')")
        third = Core(settings, Database(settings.db_path))  # must still start
        assert "broke after update" in {p["id"]: p for p in third.plugins.list()}["greeter"]["error"]
        third.shutdown()
    finally:
        again.shutdown()


# ------------------------------------------------------------------ voice
def test_wake_word_parsing():
    from titan.voice import clean_transcript, parse_wake
    assert parse_wake("Hey TITAN, open my browser.") == "open my browser"
    assert parse_wake("hey tighten open firefox") == "open firefox"
    assert parse_wake("um, hey Titan") == ""
    assert parse_wake("open my browser") is None
    assert parse_wake("the titanic sank") is None
    assert parse_wake("okay computer, play music", wake="okay computer") == "play music"
    assert clean_transcript(" [BLANK_AUDIO]  (music) hello \n there ") == "hello there"


def test_voice_status_reports_what_is_missing(act, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    st = ok(act("voice.status"))
    assert not st["stt"]["available"] and not st["tts"]["available"] and not st["microphone"]["available"]
    assert len(st["missing"]) == 4
    assert "espeak-ng" in act("voice.speak", text="hi")["error"]
    assert act("voice.listen")["status"] == "error"
    assert act("voice.wake_start")["status"] == "error"


def test_voice_pipeline_with_stub_engines(act, core, settings, fakebin, tmp_path):
    (settings.data_dir / "models").mkdir()
    (settings.data_dir / "models/ggml-base.en.bin").write_bytes(b"model")
    said = tmp_path / "said"
    # arecord writes the file given as its last argument; whisper prints a transcript for it
    fakebin("arecord", 'head -c 4000 /dev/zero > "${@: -1}"')
    fakebin("whisper-cli", 'echo " [BLANK_AUDIO] Hey Titan, create a folder called Projects."')
    fakebin("espeak-ng", f'echo "${{@: -1}}" >> {said}')
    st = ok(act("voice.status"))
    assert st["stt"]["available"] and st["tts"]["available"] and st["microphone"]["available"] and not st["missing"]
    assert ok(act("voice.listen", seconds=1))["transcript"] == "Hey Titan, create a folder called Projects."
    ok(act("voice.speak", text="Opening Firefox."))
    assert said.read_text().strip() == "Opening Firefox."

    heard = []
    class FakeAI:
        def chat(self, text, conversation_id=None, actor="ai", **kw):
            heard.append((text, actor))
            return {"conversation_id": 7, "reply": "Created the Projects folder.", "steps": []}
    core._ai = FakeAI()
    out = ok(act("voice.command", seconds=1))
    assert out["reply"] == "Created the Projects folder."
    assert heard == [("Hey Titan, create a folder called Projects.", "voice")]
    assert said.read_text().splitlines()[-1] == "Created the Projects folder."
    assert core.db.pref("voice.conversation_id") == 7
