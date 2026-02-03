"""Client for The Odds API – sportsbook odds."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from app.core.config import settings
from app.models.schemas import BookmakerOdds, BookmakerOutcome, SportsEvent

logger = logging.getLogger(__name__)

# In-memory cache
_cache: dict[str, tuple[float, list[SportsEvent]]] = {}

# Sports we scan (major US leagues)
SPORT_KEYS = [
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "baseball_mlb",
    "icehockey_nhl",
    "soccer_usa_mls",
]

SPORT_DISPLAY = {
    "americanfootball_nfl": "NFL",
    "americanfootball_ncaaf": "NCAAF",
    "basketball_nba": "NBA",
    "basketball_ncaab": "NCAAB",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "soccer_usa_mls": "MLS",
}


async def fetch_sportsbook_odds() -> list[SportsEvent]:
    """Fetch odds from The Odds API for all configured sports.

    Returns cached data if within TTL.
    Returns empty list (not mock data) if API key is missing.
    """
    if not settings.has_odds_api_key:
        logger.warning("THE_ODDS_API_KEY not set – skipping live odds fetch")
        return []

    cache_key = "sportsbook_odds"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL:
            return data

    events: list[SportsEvent] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for sport_key in SPORT_KEYS:
            try:
                resp = await client.get(
                    f"{settings.ODDS_API_BASE}/sports/{sport_key}/odds",
                    params={
                        "apiKey": settings.THE_ODDS_API_KEY,
                        "regions": "us",
                        "markets": "h2h",
                        "oddsFormat": "decimal",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                remaining = resp.headers.get("x-requests-remaining", "?")
                logger.info(
                    "OddsAPI %s: %d events, requests remaining: %s",
                    sport_key,
                    len(data),
                    remaining,
                )
                for item in data:
                    events.append(_parse_event(item, sport_key))
            except httpx.HTTPStatusError as e:
                logger.error("OddsAPI %s HTTP %s: %s", sport_key, e.response.status_code, e)
            except Exception as e:
                logger.error("OddsAPI %s error: %s", sport_key, e)

    _cache[cache_key] = (now, events)
    return events


def _parse_event(raw: dict, sport_key: str) -> SportsEvent:
    bookmakers: list[BookmakerOdds] = []
    for bm in raw.get("bookmakers", []):
        h2h = next((m for m in bm.get("markets", []) if m["key"] == "h2h"), None)
        if not h2h:
            continue
        outcomes = {o["name"]: o["price"] for o in h2h.get("outcomes", [])}
        home_name = raw["home_team"]
        away_name = raw["away_team"]
        if home_name in outcomes and away_name in outcomes:
            bookmakers.append(
                BookmakerOdds(
                    bookmaker=bm["key"],
                    home=BookmakerOutcome(name=home_name, price=outcomes[home_name]),
                    away=BookmakerOutcome(name=away_name, price=outcomes[away_name]),
                    last_update=bm.get("last_update"),
                )
            )

    return SportsEvent(
        event_id=raw["id"],
        sport_key=sport_key,
        sport_title=raw.get("sport_title", sport_key),
        league=SPORT_DISPLAY.get(sport_key, raw.get("sport_title", sport_key)),
        home_team=raw["home_team"],
        away_team=raw["away_team"],
        commence_time=datetime.fromisoformat(
            raw["commence_time"].replace("Z", "+00:00")
        ),
        bookmakers=bookmakers,
    )
