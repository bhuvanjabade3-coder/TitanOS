import json


def test_action_and_approval_endpoints(client, anon, home):
    assert anon.post("/api/actions/fs.mkdir", json={"params": {"path": "~/x"}}).status_code == 401
    r = client.post("/api/actions/fs.mkdir", json={"params": {"path": "~/Projects"}}).json()
    assert r["status"] == "ok" and (home / "Projects").is_dir()
    names = {a["name"] for a in client.get("/api/actions").json()}
    assert {"fs.delete", "terminal.run", "apps.launch", "voice.speak", "security.overview"} <= names
    r = client.post("/api/actions/fs.delete", json={"params": {"paths": ["~/Projects"]}}).json()
    assert r["status"] == "approval_required"
    aid = r["approval_id"]
    pending = client.get("/api/approvals").json()
    assert [p["id"] for p in pending] == [aid] and pending[0]["risk"] == "high"
    assert client.post(f"/api/approvals/{aid}/maybe").status_code == 404
    assert client.post("/api/approvals/999/approve").status_code == 404
    done = client.post(f"/api/approvals/{aid}/approve").json()
    assert done["outcome"]["status"] == "ok" and not (home / "Projects").exists()
    assert client.post(f"/api/approvals/{aid}/approve").status_code == 409
    assert client.get("/api/approvals").json() == []
    assert client.get("/api/approvals?status=executed").json()[0]["id"] == aid


def test_events_stream(app, client, anon):
    with anon.websocket_connect(f"/ws/events?token={app.state.api_token}") as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post("/api/actions/notify.send", json={"params": {"title": "Ping"}})
        e = ws.receive_json()
        assert e["type"] == "notification" and e["data"]["title"] == "Ping"
        client.post("/api/actions/terminal.run", json={"params": {"command": "touch f"}})
        e = ws.receive_json()
        assert e["type"] == "approval" and e["data"]["status"] == "pending"


def test_plugin_endpoints(client, app):
    d = app.state.core.plugins.dir / "demo"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"id": "demo", "name": "Demo", "version": "0.1.0", "permissions": []}))
    (d / "plugin.py").write_text("def register(api):\n    api.register_action('ping', lambda a: 'pong', 'Ping')")
    assert client.get("/api/plugins").json()[0]["enabled"] is False
    assert client.post("/api/plugins/demo/enable").json()["enabled"] is True
    assert client.post("/api/actions/plugin.demo.ping", json={}).json() == {"status": "ok", "result": "pong"}
    assert client.post("/api/plugins/demo/disable").json()["enabled"] is False
    assert client.post("/api/plugins/nope/enable").status_code == 400


def test_raw_file_endpoint_is_confined(client, home):
    (home / "pic.txt").write_text("hello")
    r = client.get("/api/files/raw", params={"path": "~/pic.txt"})
    assert r.text == "hello" and r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/files/raw", params={"path": "/etc/passwd"}).status_code == 403
    assert client.get("/api/files/raw", params={"path": "~"}).status_code == 400


def test_permission_preference_values_are_validated(client):
    assert client.put("/api/preferences/permissions.files", json={"value": "yes please"}).status_code == 422
    assert client.put("/api/preferences/permissions.files", json={"value": "allow"}).status_code == 200


def test_shell_is_served_without_secrets(tmp_path):
    from fastapi.testclient import TestClient
    from titan.config import Settings
    from titan.main import create_app
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>TITAN</html>")
    (dist / "assets/app.js").write_text("1")
    app = create_app(Settings(data_dir=tmp_path / "t", home=tmp_path, static_dir=dist, _env_file=None))
    c = TestClient(app)
    page = c.get("/")
    assert page.status_code == 200 and app.state.api_token not in page.text
    assert c.get("/assets/app.js").text == "1"
    app.state.core.shutdown()
