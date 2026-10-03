from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / "backend" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: SecretStr | None = None
    openrouter_site_url: str = "http://localhost:8000"
    openrouter_app_name: str = "Adaptive LLM Router Checkpoint 2"
    max_daily_provider_requests: int = Field(default=40, ge=1, le=1000)
    data_dir: Path = REPOSITORY_ROOT / "data"
    frontend_dist_dir: Path = REPOSITORY_ROOT / "frontend" / "dist"

    @property
    def credential_configured(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
