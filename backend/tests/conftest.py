import pytest
from fastapi.testclient import TestClient

from titan.config import Settings
from titan.main import create_app


@pytest.fixture
def settings(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return Settings(data_dir=tmp_path / "titan", home=home, metrics_interval=0.01,
                    static_dir=tmp_path / "nostatic", _env_file=None)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def anon(app):
    return TestClient(app)


@pytest.fixture
def client(app):
    return TestClient(app, headers={"Authorization": f"Bearer {app.state.api_token}"})


@pytest.fixture
def core(app):
    yield app.state.core
    app.state.core.shutdown()


@pytest.fixture
def home(settings):
    return settings.home


@pytest.fixture
def act(core):
    def _act(_n, /, _actor="user", **params):
        return core.registry.perform(_actor, _n, params)
    return _act


@pytest.fixture
def fakebin(tmp_path, monkeypatch):
    """Create fake executables on PATH: fakebin(name, script_body)."""
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", f"{d}:" + __import__("os").environ["PATH"])

    def make(name, body):
        f = d / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
        return f
    return make
