"""Application configuration loaded from environment."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)


class Settings:
    THE_ODDS_API_KEY: str = os.getenv("THE_ODDS_API_KEY", "")
    ODDS_API_BASE: str = "https://api.the-odds-api.com/v4"

    POLYMARKET_GAMMA_BASE: str = "https://gamma-api.polymarket.com"
    POLYMARKET_CLOB_BASE: str = "https://clob.polymarket.com"

    KALSHI_API_BASE: str = "https://api.elections.kalshi.com/trade-api/v2"

    FEE_BUFFER: float = float(os.getenv("FEE_BUFFER", "0.03"))
    MIN_EDGE: float = float(os.getenv("MIN_EDGE", "0.02"))
    MIN_BOOKS: int = int(os.getenv("MIN_BOOKS", "2"))
    MATCH_CONFIDENCE_THRESHOLD: int = int(
        os.getenv("MATCH_CONFIDENCE_THRESHOLD", "92")
    )

    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

    DB_PATH: str = os.getenv(
        "DB_PATH",
        str(Path(__file__).resolve().parents[2] / "scanner.db"),
    )

    CACHE_TTL: int = 60  # seconds

    @property
    def has_odds_api_key(self) -> bool:
        return bool(self.THE_ODDS_API_KEY)


settings = Settings()
