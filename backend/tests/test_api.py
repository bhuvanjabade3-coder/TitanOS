import stat

import pytest
from starlette.websockets import WebSocketDisconnect


def test_health_is_public(anon):
    r = anon.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["schema"] >= 1


@pytest.mark.parametrize("path", ["/api/status", "/api/system/metrics", "/api/preferences", "/api/audit"])
def test_api_requires_token(anon, path):
    assert anon.get(path).status_code == 401
    assert anon.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_token_file_is_private_and_stable(app, settings):
    mode = stat.S_IMODE(settings.token_path.stat().st_mode)
    assert mode == 0o600
    from titan.auth import load_or_create_token

    assert load_or_create_token(settings.token_path) == app.state.api_token


def test_status_never_leaks_key(tmp_path):
    from fastapi.testclient import TestClient
    from titan.config import Settings
    from titan.main import create_app

    s = Settings(data_dir=tmp_path, anthropic_api_key="sk-ant-test-0123456789abcdef", _env_file=None)
    app = create_app(s)
    c = TestClient(app, headers={"Authorization": f"Bearer {app.state.api_token}"})
    body = c.get("/api/status").text
    assert '"ai_configured":true' in body
    assert "sk-ant" not in body
    assert "sk-ant" not in repr(s)
    assert "sk-ant" not in (s.log_dir / "titan.log").read_text()


def test_metrics_are_live_values(client):
    m = client.get("/api/system/metrics").json()
    assert m["memory"]["total"] > 0
    assert 0 <= m["memory"]["percent"] <= 100
    assert m["disk"]["total"] > 0
    assert m["cpu"]["cores"] >= 1
    assert len(m["cpu"]["per_core"]) == m["cpu"]["cores"]


def test_processes(client):
    import os

    procs = client.get("/api/system/processes?limit=500").json()
    assert any(p["pid"] == os.getpid() for p in procs)
    assert client.get("/api/system/processes?sort=bogus").status_code == 422


def test_preferences_roundtrip_and_audit(client):
    assert client.put("/api/preferences/theme.accent", json={"value": "#7c5cff"}).status_code == 200
    assert client.put("/api/preferences/dock.pinned", json={"value": ["firefox"]}).status_code == 200
    assert client.get("/api/preferences").json() == {
        "dock.pinned": ["firefox"],
        "theme.accent": "#7c5cff",
    }
    assert client.delete("/api/preferences/theme.accent").status_code == 200
    assert client.delete("/api/preferences/theme.accent").status_code == 404
    assert client.put("/api/preferences/Bad Key!", json={"value": 1}).status_code == 422
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert actions == ["preference.delete", "preference.set", "preference.set"]


def test_classify_endpoint(client):
    r = client.post("/api/terminal/classify", json={"command": "sudo rm -rf /"}).json()
    assert r["risk"] == "high" and r["requires_approval"] is True


def test_ws_metrics_stream(app, anon):
    with anon.websocket_connect(f"/ws/metrics?token={app.state.api_token}") as ws:
        a, b = ws.receive_json(), ws.receive_json()
    assert a["memory"]["total"] > 0
    assert b["ts"] >= a["ts"]


def test_ws_rejects_without_token(anon):
    with pytest.raises(WebSocketDisconnect) as e:
        with anon.websocket_connect("/ws/metrics") as ws:
            ws.receive_json()
    assert e.value.code == 4401
