"""Application-wide configuration loaded from .env / environment.

Secret keys are stored in ``.env`` (git-ignored).  When a key is
missing or still set to the placeholder ``demo`` value, a warning
is logged so operators notice immediately.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to project root (works inside Docker too)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./asset_dashboard.db"

    # External data providers
    coingecko_api_url: str = "https://api.coingecko.com/api/v3"
    alpha_vantage_api_key: str = "demo"
    exchange_rate_api_url: str = "https://open.er-api.com/v6/latest"

    # Grafana
    grafana_url: str = "http://localhost:3000"
    grafana_api_key: str = ""

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Scheduler
    fetch_interval: int = 300  # seconds


settings = Settings()


# ── Startup key validation ────────────────────────────────────────────

def validate_secrets() -> None:
    """Log warnings / errors for missing or placeholder API keys."""
    if not _ENV_FILE.exists():
        logger.error(
            "Secrets file not found: {}  — API keys will fall back to defaults. "
            "Copy .env.example → .env and fill in real keys.",
            _ENV_FILE,
        )

    if not settings.alpha_vantage_api_key or settings.alpha_vantage_api_key == "demo":
        logger.warning(
            "ALPHA_VANTAGE_API_KEY is '{}' — the demo key only supports MSFT. "
            "Set a real key in .env to fetch all stock symbols.",
            settings.alpha_vantage_api_key,
        )

    if not settings.grafana_api_key:
        logger.info("GRAFANA_API_KEY is not set — Grafana API push is disabled.")

    logger.debug("Config loaded from {}", _ENV_FILE if _ENV_FILE.exists() else "environment / defaults")
