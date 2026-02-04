"""Application configuration loaded from environment."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)


class Settings:
    # ── Odds-API.io (replaces the-odds-api.com) ─────────────────
    ODDS_API_KEY: str = os.getenv("ODDS_API_KEY", "")
    ODDS_API_BASE: str = "https://api.odds-api.io/v3"

    # Legacy fallback: if old key name is set, use it
    THE_ODDS_API_KEY: str = os.getenv("THE_ODDS_API_KEY", "")

    # ── Prediction markets (unchanged) ──────────────────────────
    POLYMARKET_GAMMA_BASE: str = "https://gamma-api.polymarket.com"
    POLYMARKET_CLOB_BASE: str = "https://clob.polymarket.com"
    KALSHI_API_BASE: str = "https://api.elections.kalshi.com/trade-api/v2"

    # ── Telegram alerts ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_ALERT_EDGE: float = float(os.getenv("TELEGRAM_ALERT_EDGE", "0.07"))
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"

    # ── Edge calculation ────────────────────────────────────────
    FEE_BUFFER: float = float(os.getenv("FEE_BUFFER", "0.03"))
    MIN_EDGE: float = float(os.getenv("MIN_EDGE", "0.02"))
    MIN_BOOKS: int = int(os.getenv("MIN_BOOKS", "2"))
    MATCH_CONFIDENCE_THRESHOLD: int = int(
        os.getenv("MATCH_CONFIDENCE_THRESHOLD", "92")
    )

    # ── Polling (aggressive 24/7 scanning) ──────────────────────
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    LIVE_POLL_INTERVAL_SECONDS: int = int(
        os.getenv("LIVE_POLL_INTERVAL_SECONDS", "15")
    )

    # ── Database ────────────────────────────────────────────────
    DB_PATH: str = os.getenv(
        "DB_PATH",
        str(Path(__file__).resolve().parents[2] / "scanner.db"),
    )

    CACHE_TTL: int = 30  # seconds (lowered from 60 for more real-time)

    @property
    def has_odds_api_key(self) -> bool:
        return bool(self.ODDS_API_KEY or self.THE_ODDS_API_KEY)

    @property
    def active_odds_key(self) -> str:
        """Return whichever odds API key is set (prefer new name)."""
        return self.ODDS_API_KEY or self.THE_ODDS_API_KEY

    @property
    def has_telegram(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID and self.TELEGRAM_ENABLED)


settings = Settings()
