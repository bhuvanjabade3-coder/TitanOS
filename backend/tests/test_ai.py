"""AI core tests with a scripted stand-in for the Anthropic client. These verify
TITAN's loop, gating and honesty guarantees; they do not exercise the real model."""
import json
from types import SimpleNamespace as NS

import pytest

from titan.ai import AIError, AIUnavailable, Assistant


def text(t):
    return NS(type="text", text=t)


def tool(name, _id="tu_1", **inp):
    return NS(type="tool_use", id=_id, name=name, input=inp)


def resp(stop, *blocks, **extra):
    return NS(stop_reason=stop, content=list(blocks), **extra)


class Fake:
    """Returns scripted responses and records every request it was sent."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: vars(o))))
        nxt = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture
def ai(core):
    def make(*script):
        fake = Fake(*script)
        core._ai = Assistant(core, client=fake)
        return core._ai, fake
    return make


def test_executes_tool_and_reports(ai, home, core):
    a, fake = ai(resp("tool_use", text("Creating it."), tool("fs_mkdir", path="~/Projects")),
                 resp("end_turn", text("Created the Projects folder.")))
    out = a.chat("Create a folder called Projects")
    assert (home / "Projects").is_dir()
    assert out["reply"] == "Created the Projects folder." and out["stop_reason"] == "end_turn"
    assert out["steps"] == [{"action": "fs.mkdir", "input": {"path": "~/Projects"}, "status": "ok"}]
    first, second = fake.calls
    assert first["model"] == "claude-opus-5-5" and first["thinking"] == {"type": "adaptive"}
    assert first["fallbacks"] == "default" and first["betas"] == ["server-side-fallback-2026-07-01"]
    assert first["output_config"] == {"effort": "medium"}
    assert all("." not in t["name"] and t["input_schema"]["additionalProperties"] is False for t in first["tools"])
    assert first["messages"] == [{"role": "user", "content": "Create a folder called Projects"}]
    # the model is shown the real result, attached to the right tool call, in one user message
    assert second["messages"][1]["role"] == "assistant"
    (result,) = second["messages"][2]["content"]
    assert result["tool_use_id"] == "tu_1" and str(home / "Projects") in result["content"] and "is_error" not in result
    assert core.db.audit_entries()[0]["actor"] == "ai"


def test_risky_action_waits_for_approval_and_model_is_told(ai, home, core):
    (home / "thesis.docx").write_text("important")
    a, fake = ai(resp("tool_use", tool("fs_delete", paths=["~/thesis.docx"])),
                 resp("end_turn", text("That needs your approval before I can delete it.")))
    out = a.chat("delete my thesis")
    assert (home / "thesis.docx").exists()
    assert out["steps"][0]["status"] == "approval_required" and out["pending_approvals"] == [out["steps"][0]["approval_id"]]
    told = fake.calls[1]["messages"][2]["content"][0]["content"]
    assert told.startswith("NOT EXECUTED") and "has not run" in told
    core.registry.decide(out["pending_approvals"][0], True)
    assert not (home / "thesis.docx").exists()
    assert core.notifier.list()[0]["title"] == "fs.delete completed"


def test_failures_are_passed_to_the_model_as_errors(ai, core):
    a, fake = ai(resp("tool_use", tool("fs_read", "a", path="~/missing.txt"), tool("made_up_tool", "b"),
                      tool("terminal_run", "c", command="sudo rm -rf /")),
                 resp("end_turn", text("I couldn't read that file.")))
    out = a.chat("summarise missing.txt")
    assert [s["status"] for s in out["steps"]] == ["error", "error", "approval_required"]
    results = fake.calls[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b", "c"]
    assert results[0]["is_error"] and "does not exist" in results[0]["content"]
    assert results[1]["is_error"] and "No such tool" in results[1]["content"]


def test_denied_permission_is_reported(ai, core):
    core.db.set_preference("permissions.terminal", "deny")
    a, fake = ai(resp("tool_use", tool("terminal_run", command="ls")), resp("end_turn", text("Terminal access is off.")))
    out = a.chat("list files")
    assert out["steps"][0]["status"] == "denied"
    assert fake.calls[1]["messages"][2]["content"][0]["content"].startswith("DENIED")


def test_plan_mode_offers_only_read_only_tools(ai, home):
    a, fake = ai(resp("end_turn", text("1. Create folder (will run directly)\n2. Move files (needs approval)")))
    out = a.chat("organise my downloads", mode="plan")
    names = {t["name"] for t in fake.calls[0]["tools"]}
    assert {"fs_list", "fs_search", "fs_read", "windows_list"} <= names
    assert not names & {"fs_mkdir", "fs_move", "fs_delete", "terminal_run", "apps_launch", "input_type", "memory_save"}
    assert "PLAN MODE" in fake.calls[0]["system"][0]["text"] and out["mode"] == "plan"


def test_step_limit_is_reported_honestly(ai, settings):
    settings.ai_max_steps = 3
    a, fake = ai(resp("tool_use", tool("fs_list", path="~")))
    out = a.chat("loop forever")
    assert len(fake.calls) == 3 and out["stop_reason"] == "step_limit"
    assert "stopped after 3 steps without finishing" in out["reply"]


def test_refusal_and_truncation(ai):
    a, _ = ai(resp("refusal", stop_details=NS(explanation="Policy.")))
    assert a.chat("x")["reply"] == "The model declined this request. Policy."
    a, _ = ai(resp("max_tokens", text("Partial"), tool("fs_mkdir", path="~/never")))
    out = a.chat("x")
    assert out["steps"] == [] and "cut off" in out["reply"]  # incomplete tool calls are not executed


def test_history_memory_and_personality_are_sent(ai, core):
    core.db.set_preference("ai.personality", "dry and brief")
    core.registry.perform("user", "memory.save", {"content": "Editor of choice is Zed", "kind": "preference"})
    a, fake = ai(resp("end_turn", text("Hello.")))
    first = a.chat("hi")
    a.chat("and again", conversation_id=first["conversation_id"])
    assert fake.calls[1]["messages"] == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello."},
                                         {"role": "user", "content": "and again"}]
    system = fake.calls[1]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"} and "Editor of choice is Zed" not in system[0]["text"]
    assert "Editor of choice is Zed" in system[1]["text"] and "dry and brief" in system[1]["text"]
    conv = a.conversation(first["conversation_id"])
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    assert a.conversations()[0]["title"] == "hi"
    assert a.delete_conversation(first["conversation_id"]) and a.conversations() == []


def test_api_errors_surface_and_are_recorded(ai):
    a, _ = ai(AIError("Could not reach the Claude API."))
    with pytest.raises(AIError):
        a.chat("hello")
    conv = a.conversation(a.conversations()[0]["id"])
    assert conv["messages"][-1]["content"]["error"] == "Could not reach the Claude API."
    with pytest.raises(AIError):
        a.chat("   ")


def test_chat_endpoint_status_codes(client, core):
    class Down:
        def chat(self, *a, **k):
            raise AIUnavailable("No Anthropic credentials available.")
    core._ai = Down()
    r = client.post("/api/ai/chat", json={"message": "hi"})
    assert r.status_code == 503 and "credentials" in r.json()["detail"]
    assert client.post("/api/ai/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/ai/chat", json={"message": "x", "mode": "yolo"}).status_code == 422
    fake = Fake(resp("end_turn", text("Hi there.")))
    core._ai = Assistant(core, client=fake)
    r = client.post("/api/ai/chat", json={"message": "hi"}).json()
    assert r["reply"] == "Hi there."
    assert client.get("/api/ai/conversations").json()[0]["id"] == r["conversation_id"]
    assert client.get(f"/api/ai/conversations/{r['conversation_id']}").json()["messages"][1]["content"]["text"] == "Hi there."
    assert client.get("/api/ai/conversations/999").status_code == 404
    assert client.delete(f"/api/ai/conversations/{r['conversation_id']}").status_code == 200
