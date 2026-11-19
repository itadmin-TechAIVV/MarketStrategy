"""Application settings, loaded from environment variables / backend/.env.

Secrets (ANTHROPIC_API_KEY, JWT_SECRET, MONGO_URI) are only ever read here and
are never logged or returned by the API.
"""
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    mongo_uri: SecretStr = SecretStr("mongodb://localhost:27017")
    mongo_db: str = "gtm_strategy_dev"

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr("change-me-in-env")
    jwt_expiry_hours: int = 72

    # --- Anthropic ---
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    agent_effort: str = "high"  # low | medium | high | xhigh | max
    agent_max_tokens: int = 32000
    # Server-side refusal fallbacks ("default" routes by refusal category). Empty string disables.
    anthropic_fallbacks: str = "default"

    # --- CORS (comma-separated origins, plus an optional regex for Vercel previews) ---
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str | None = None

    # --- Crawler limits ---
    crawl_max_pages: int = Field(25, description="Internal pages in addition to the home page")
    crawl_timeout_seconds: float = 10.0
    crawl_total_budget_seconds: float = 90.0
    crawl_max_bytes: int = 2_000_000
    crawl_concurrency: int = 4
    crawl_user_agent: str = "GTMStrategyBot/0.1 (+strategy research crawler)"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
