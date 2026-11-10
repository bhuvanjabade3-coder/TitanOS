"""Application configuration.

All settings come from environment variables (prefix ``TITAN_``) or an optional
``.env`` file. Secrets are held as ``SecretStr`` so they never appear in logs,
reprs or API responses.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "titan"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITAN_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"  # loopback only; never expose the core service on the LAN
    port: int = 8710
    data_dir: Path = Field(default_factory=_default_data_dir)
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    require_token: bool = True
    metrics_interval: float = 1.0
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "TITAN_ANTHROPIC_API_KEY"),
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "titan.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "api_token"

    @property
    def ai_configured(self) -> bool:
        return self.anthropic_api_key is not None and bool(
            self.anthropic_api_key.get_secret_value()
        )
