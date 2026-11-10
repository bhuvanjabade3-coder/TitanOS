import pytest
from fastapi.testclient import TestClient

from titan.config import Settings
from titan.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "titan", metrics_interval=0.01, _env_file=None)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def anon(app):
    return TestClient(app)


@pytest.fixture
def client(app):
    return TestClient(app, headers={"Authorization": f"Bearer {app.state.api_token}"})
