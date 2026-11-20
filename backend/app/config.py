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

    # --- Google Gemini ---
    gemini_api_key: SecretStr | None = None
    # "gemini-flash-latest" is Google's alias for the current Flash model; set an exact model id to pin one.
    gemini_model: str = "gemini-flash-latest"
    agent_max_tokens: int = 32000

    # --- CORS (comma-separated origins, plus an optional regex for Vercel previews) ---
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str | None = None

    # --- Crawler limits ---
    crawl_max_pages: int = Field(25, description="Internal pages in addition to the home page")
    crawl_timeout_seconds: float = 10.0
    crawl_total_budget_seconds: float = 120.0
    crawl_max_bytes: int = 2_000_000
    crawl_concurrency: int = 4
    # Name matched against robots.txt rules (sites can still opt out of this crawler by name).
    crawl_user_agent: str = "GTMStrategyBot/0.1 (+strategy research crawler)"
    # User-Agent header sent with page requests. Many sites refuse requests that don't look like a browser.
    crawl_browser_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
    # Reader service for JavaScript-heavy or bot-protected pages (renders the page, returns its text).
    # Set to an empty string to turn it off. JINA_API_KEY is optional and raises its rate limit.
    crawl_reader_url: str = "https://r.jina.ai/"
    jina_api_key: SecretStr | None = None
    crawl_reader_max_pages: int = 12
    # Try likely pages (/pricing, /about, ...) when a home page exposes few links.
    crawl_guess_paths: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
