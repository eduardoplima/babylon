"""Runtime settings (.env / environment) plus per-platform config (config/platforms.yaml)."""
from functools import cached_property
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All paths are relative to `home` unless absolute."""

    model_config = SettingsConfigDict(env_prefix="PUBLISHER_", env_file=".env", extra="ignore")

    home: Path = Path.cwd()
    content_dir: Path = Path("content")
    db_path: Path = Path("data/publisher.sqlite")
    log_path: Path = Path("data/publisher.log.jsonl")
    secrets_dir: Path = Path(".secrets")
    platforms_file: Path = Path("config/platforms.yaml")
    babylon_root: Path = Path("..")
    timezone: str = "America/Sao_Paulo"
    youtube_client_secrets: Path = Path(".secrets/youtube_client_secret.json")

    def path(self, p: Path) -> Path:
        return p if p.is_absolute() else self.home / p

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @cached_property
    def platforms(self) -> dict[str, Any]:
        return yaml.safe_load(self.path(self.platforms_file).read_text())

    def platform(self, name: str) -> dict[str, Any]:
        return self.platforms[name]

    @property
    def taxonomy(self) -> dict[str, list[str]]:
        return self.platforms["taxonomy"]
