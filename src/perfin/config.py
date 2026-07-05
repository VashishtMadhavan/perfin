"""Application configuration and filesystem paths.

Settings resolve with precedence: environment variables (``PERFIN_*`` and a few
well-known vendor vars) > ``config.toml`` > defaults. Paths follow the platform
conventions provided by :mod:`platformdirs` (XDG on Linux, Application Support on
macOS) so the DB lands in a data dir and config in a config dir.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from platformdirs import PlatformDirs
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DIRS = PlatformDirs(appname="perfin", appauthor=False)

CONFIG_DIR = Path(_DIRS.user_config_dir)
DATA_DIR = Path(_DIRS.user_data_dir)
CONFIG_FILE = CONFIG_DIR / "config.toml"
DB_PATH = DATA_DIR / "perfin.db"
SECRETS_FALLBACK_PATH = DATA_DIR / "secrets.json"
ASK_CONSENT_PATH = DATA_DIR / "ask_consent.json"


class PlaidSettings(BaseSettings):
    """Plaid connection settings. Client credentials come from the environment."""

    model_config = SettingsConfigDict(env_prefix="PLAID_", extra="ignore")

    env: str = "sandbox"  # sandbox | development | production
    client_id: str | None = None
    secret: str | None = None


class SyncSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PERFIN_SYNC_", extra="ignore")

    staleness_hours: float = 6.0
    default_source: str = "fake"


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PERFIN_LLM_", extra="ignore")

    model: str = "claude-opus-4-8"
    effort: str = "high"  # low | medium | high | xhigh | max
    max_iterations: int = 15
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")


class Settings(BaseSettings):
    """Top-level settings aggregating the sub-sections."""

    model_config = SettingsConfigDict(extra="ignore")

    plaid: PlaidSettings = Field(default_factory=PlaidSettings)
    sync: SyncSettings = Field(default_factory=SyncSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)

    db_path: Path = DB_PATH
    config_dir: Path = CONFIG_DIR
    data_dir: Path = DATA_DIR

    @property
    def db_url(self) -> str:
        """SQLAlchemy connection URL. Swap for ``postgresql+psycopg://…`` later."""
        return f"sqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build the effective settings, layering config.toml under env overrides.

    Env vars win because pydantic-settings reads them when each section is
    constructed; the TOML file provides the base values passed in here.
    """
    raw = _load_toml(CONFIG_FILE)
    settings = Settings(
        plaid=PlaidSettings(**raw.get("plaid", {})),
        sync=SyncSettings(**raw.get("sync", {})),
        llm=LLMSettings(**raw.get("llm", {})),
    )
    settings.ensure_dirs()
    return settings
