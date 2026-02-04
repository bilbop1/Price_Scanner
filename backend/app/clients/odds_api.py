"""Client for Odds-API.io v3 – sportsbook odds, value bets, arbitrage."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from app.core.config import settings
from app.models.schemas import (
    ArbitrageBet,
    ArbitrageLeg,
    BookmakerOdds,
    BookmakerOutcome,
    SportsEvent,
    ValueBet,
)

logger = logging.getLogger(__name__)

# In-memory caches
_cache: dict[str, tuple[float, object]] = {}
_last_odds_update: float = 0.0  # Unix timestamp for /odds/updated polling

# Sports we scan → odds-api.io sport slugs
SPORT_SLUGS = [
    "american-football",
    "basketball",
    "baseball",
    "ice-hockey",
    "football",  # soccer
]

# Map odds-api.io league names → our internal display names
LEAGUE_DISPLAY: dict[str, str] = {
    "NFL": "NFL",
    "NCAAF": "NCAAF",
    "NCAA Football": "NCAAF",
    "NBA": "NBA",
    "NCAAB": "NCAAB",
    "NCAA Basketball": "NCAAB",
    "MLB": "MLB",
    "NHL": "NHL",
    "MLS": "MLS",
    "Major League Soccer": "MLS",
}

# Map league → sport_key for backward compatibility with the pipeline
LEAGUE_TO_SPORT_KEY: dict[str, str] = {
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NBA": "basketball_nba",
    "NCAAB": "basketball_ncaab",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "MLS": "soccer_usa_mls",
}

SPORT_DISPLAY: dict[str, str] = {
    "americanfootball_nfl": "NFL",
    "americanfootball_ncaaf": "NCAAF",
    "basketball_nba": "NBA",
    "basketball_ncaab": "NCAAB",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "soccer_usa_mls": "MLS",
}


async def fetch_sportsbook_odds() -> list[SportsEvent]:
    """Fetch odds from Odds-API.io for all configured sports.

    Uses /events to get events, then /odds/multi to batch-fetch odds.
    Returns cached data if within TTL.
    Returns empty list if API key is missing.
    """
    if not settings.has_odds_api_key:
        logger.warning("ODDS_API_KEY not set – skipping live odds fetch")
        return []

    cache_key = "sportsbook_odds"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL:
            return data  # type: ignore[return-value]

    events: list[SportsEvent] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for sport_slug in SPORT_SLUGS:
            try:
                sport_events = await _fetch_events_for_sport(client, sport_slug)
                if not sport_events:
                    continue

                # Batch fetch odds using /odds/multi (up to 10 per call)
                event_ids = [e["id"] for e in sport_events]
                for i in range(0, len(event_ids), 10):
                    batch_ids = event_ids[i : i + 10]
                    odds_data = await _fetch_odds_multi(client, batch_ids)

                    # Build a map of event_id → odds data
                    odds_map = _build_odds_map(odds_data)

                    for raw_event in sport_events:
                        eid = str(raw_event["id"])
                        if eid in odds_map:
                            parsed = _parse_event(raw_event, odds_map[eid], sport_slug)
                            if parsed and parsed.bookmakers:
                                events.append(parsed)

                remaining = "unknown"
                logger.info(
                    "OddsAPI.io %s: %d events with odds",
                    sport_slug,
                    len([e for e in events if _sport_slug_matches(e.sport_key, sport_slug)]),
                )
            except httpx.HTTPStatusError as e:
                logger.error(
                    "OddsAPI.io %s HTTP %s: %s", sport_slug, e.response.status_code, e
                )
            except Exception as e:
                logger.error("OddsAPI.io %s error: %s", sport_slug, e)

    _cache[cache_key] = (now, events)
    return events


async def fetch_value_bets(bookmaker: str = "Bet365") -> list[ValueBet]:
    """Fetch pre-computed value bets from Odds-API.io."""
    if not settings.has_odds_api_key:
        return []

    cache_key = f"value_bets_{bookmaker}"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL:
            return data  # type: ignore[return-value]

    value_bets: list[ValueBet] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.ODDS_API_BASE}/value-bets",
                params={
                    "apiKey": settings.active_odds_key,
                    "bookmaker": bookmaker,
                    "includeEventDetails": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            remaining = resp.headers.get("x-ratelimit-remaining", "?")
            logger.info(
                "OddsAPI.io value-bets (%s): %d bets, remaining: %s",
                bookmaker, len(data) if isinstance(data, list) else 0, remaining,
            )

            if isinstance(data, list):
                for item in data:
                    vb = _parse_value_bet(item)
                    if vb:
                        value_bets.append(vb)

    except Exception as e:
        logger.error("OddsAPI.io value-bets error: %s", e)

    _cache[cache_key] = (now, value_bets)
    return value_bets


async def fetch_arbitrage_bets(bookmakers: str = "Bet365,Unibet,SingBet") -> list[ArbitrageBet]:
    """Fetch pre-computed arbitrage opportunities from Odds-API.io."""
    if not settings.has_odds_api_key:
        return []

    cache_key = f"arb_bets_{bookmakers}"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL:
            return data  # type: ignore[return-value]

    arb_bets: list[ArbitrageBet] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.ODDS_API_BASE}/arbitrage-bets",
                params={
                    "apiKey": settings.active_odds_key,
                    "bookmakers": bookmakers,
                    "limit": 500,
                    "includeEventDetails": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            remaining = resp.headers.get("x-ratelimit-remaining", "?")
            logger.info(
                "OddsAPI.io arb-bets: %d opportunities, remaining: %s",
                len(data) if isinstance(data, list) else 0, remaining,
            )

            if isinstance(data, list):
                for item in data:
                    ab = _parse_arbitrage_bet(item)
                    if ab:
                        arb_bets.append(ab)

    except Exception as e:
        logger.error("OddsAPI.io arb-bets error: %s", e)

    _cache[cache_key] = (now, arb_bets)
    return arb_bets


async def fetch_live_events() -> list[SportsEvent]:
    """Fetch currently live events for faster polling during games."""
    if not settings.has_odds_api_key:
        return []

    cache_key = "live_events"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL / 2:  # half TTL for live
            return data  # type: ignore[return-value]

    events: list[SportsEvent] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.ODDS_API_BASE}/events/live",
                params={"apiKey": settings.active_odds_key},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                event_ids = [str(e["id"]) for e in data]
                if event_ids:
                    for i in range(0, len(event_ids), 10):
                        batch = event_ids[i : i + 10]
                        odds_data = await _fetch_odds_multi(client, batch)
                        odds_map = _build_odds_map(odds_data)
                        for raw in data:
                            eid = str(raw["id"])
                            if eid in odds_map:
                                sport = raw.get("sport", "unknown")
                                parsed = _parse_event(raw, odds_map[eid], sport)
                                if parsed and parsed.bookmakers:
                                    events.append(parsed)

                logger.info("OddsAPI.io live events: %d", len(events))

    except Exception as e:
        logger.error("OddsAPI.io live events error: %s", e)

    _cache[cache_key] = (now, events)
    return events


# ── Internal helpers ──────────────────────────────────────────────


async def _fetch_events_for_sport(
    client: httpx.AsyncClient, sport_slug: str
) -> list[dict]:
    """Fetch events for a sport from /events endpoint."""
    resp = await client.get(
        f"{settings.ODDS_API_BASE}/events",
        params={
            "apiKey": settings.active_odds_key,
            "sport": sport_slug,
            "status": "pending",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


async def _fetch_odds_multi(
    client: httpx.AsyncClient, event_ids: list[str]
) -> dict:
    """Batch fetch odds for up to 10 events (counts as 1 API call)."""
    resp = await client.get(
        f"{settings.ODDS_API_BASE}/odds/multi",
        params={
            "apiKey": settings.active_odds_key,
            "eventIds": ",".join(str(eid) for eid in event_ids),
        },
    )
    resp.raise_for_status()
    return resp.json()


def _build_odds_map(odds_data: dict | list) -> dict[str, dict]:
    """Build event_id → bookmaker odds mapping from /odds/multi response.

    Response can be:
    - A dict keyed by event ID: {"12345": {"bookmakers": {...}}, ...}
    - A list of event objects: [{"id": "12345", "bookmakers": {...}}, ...]
    """
    result: dict[str, dict] = {}

    if isinstance(odds_data, dict):
        for event_id, event_odds in odds_data.items():
            if isinstance(event_odds, dict):
                result[str(event_id)] = event_odds
    elif isinstance(odds_data, list):
        for item in odds_data:
            if isinstance(item, dict) and "id" in item:
                result[str(item["id"])] = item

    return result


def _sport_slug_matches(sport_key: str, sport_slug: str) -> bool:
    """Check if a sport_key corresponds to a sport_slug."""
    mapping = {
        "american-football": ["americanfootball_nfl", "americanfootball_ncaaf"],
        "basketball": ["basketball_nba", "basketball_ncaab"],
        "baseball": ["baseball_mlb"],
        "ice-hockey": ["icehockey_nhl"],
        "football": ["soccer_usa_mls"],
    }
    return sport_key in mapping.get(sport_slug, [])


def _parse_event(raw: dict, odds: dict, sport_slug: str) -> SportsEvent | None:
    """Parse an event + odds response into a SportsEvent."""
    home_team = raw.get("home", "")
    away_team = raw.get("away", "")
    if not home_team or not away_team:
        return None

    league_raw = raw.get("league", "")
    league = LEAGUE_DISPLAY.get(league_raw, league_raw)
    sport_key = LEAGUE_TO_SPORT_KEY.get(league, f"{sport_slug}_unknown")

    # Parse bookmaker odds from the odds response
    bookmakers: list[BookmakerOdds] = []
    bm_data = odds.get("bookmakers", {})

    if isinstance(bm_data, dict):
        for bm_name, bm_info in bm_data.items():
            parsed_bm = _parse_bookmaker_odds(bm_name, bm_info, home_team, away_team)
            if parsed_bm:
                bookmakers.append(parsed_bm)
    elif isinstance(bm_data, list):
        # Some responses may have bookmakers as a list
        for bm_item in bm_data:
            bm_name = bm_item.get("key", bm_item.get("name", "unknown"))
            parsed_bm = _parse_bookmaker_odds(bm_name, bm_item, home_team, away_team)
            if parsed_bm:
                bookmakers.append(parsed_bm)

    # Parse commence time
    commence_time = datetime.utcnow()
    date_str = raw.get("date", raw.get("commence_time", ""))
    if date_str:
        try:
            commence_time = datetime.fromisoformat(
                str(date_str).replace("Z", "+00:00")
            )
        except ValueError:
            pass

    return SportsEvent(
        event_id=str(raw.get("id", "")),
        sport_key=sport_key,
        sport_title=league or sport_slug,
        league=league,
        home_team=home_team,
        away_team=away_team,
        commence_time=commence_time,
        bookmakers=bookmakers,
    )


def _parse_bookmaker_odds(
    bm_name: str, bm_info: dict, home_team: str, away_team: str
) -> BookmakerOdds | None:
    """Parse a single bookmaker's odds from the odds-api.io response."""
    markets = bm_info.get("markets", [])
    if not isinstance(markets, list):
        return None

    # Find the ML (moneyline / match result) market
    ml_market = None
    for mkt in markets:
        if isinstance(mkt, dict) and mkt.get("name", "").upper() in ("ML", "MATCH RESULT", "H2H"):
            ml_market = mkt
            break

    if not ml_market:
        # Try first market if it has the right structure
        if markets and isinstance(markets[0], dict):
            ml_market = markets[0]
        else:
            return None

    odds_list = ml_market.get("odds", [])
    if not odds_list or not isinstance(odds_list, list):
        return None

    odds_entry = odds_list[0] if odds_list else {}
    home_price = _safe_decimal(odds_entry.get("home"))
    away_price = _safe_decimal(odds_entry.get("away"))

    if not home_price or not away_price or home_price <= 1 or away_price <= 1:
        return None

    last_update = None
    updated_at = ml_market.get("updatedAt")
    if updated_at:
        try:
            last_update = datetime.fromisoformat(
                str(updated_at).replace("Z", "+00:00")
            )
        except ValueError:
            pass

    return BookmakerOdds(
        bookmaker=bm_name,
        home=BookmakerOutcome(name=home_team, price=home_price),
        away=BookmakerOutcome(name=away_team, price=away_price),
        last_update=last_update,
    )


def _parse_value_bet(raw: dict) -> ValueBet | None:
    """Parse a value bet from odds-api.io /value-bets response."""
    try:
        event = raw.get("event", {})
        return ValueBet(
            id=str(raw.get("id", "")),
            event_id=str(raw.get("eventId", "")),
            bookmaker=raw.get("bookmaker", ""),
            market=raw.get("market", "ML"),
            bet_side=raw.get("betSide", ""),
            expected_value=float(raw.get("expectedValue", 0)),
            bookmaker_odds=_safe_decimal(raw.get("bookmakerOdds")) or 0.0,
            home_team=event.get("home", ""),
            away_team=event.get("away", ""),
            league=event.get("league", ""),
            sport=event.get("sport", ""),
            commence_time=_parse_datetime(event.get("date")),
        )
    except Exception as e:
        logger.debug("Failed to parse value bet: %s", e)
        return None


def _parse_arbitrage_bet(raw: dict) -> ArbitrageBet | None:
    """Parse an arbitrage bet from odds-api.io /arbitrage-bets response."""
    try:
        event = raw.get("event", {})
        legs: list[ArbitrageLeg] = []
        for leg in raw.get("legs", []):
            legs.append(
                ArbitrageLeg(
                    bookmaker=leg.get("bookmaker", ""),
                    bet_side=leg.get("betSide", ""),
                    odds=_safe_decimal(leg.get("odds")) or 0.0,
                )
            )

        return ArbitrageBet(
            id=str(raw.get("id", "")),
            event_id=str(raw.get("eventId", "")),
            market=raw.get("market", "ML"),
            profit_margin=float(raw.get("profitMargin", 0)),
            implied_probability=float(raw.get("impliedProbability", 0)),
            total_stake=float(raw.get("totalStake", 100)),
            legs=legs,
            optimal_stakes=[float(s) for s in raw.get("optimalStakes", [])],
            home_team=event.get("home", ""),
            away_team=event.get("away", ""),
            league=event.get("league", ""),
            sport=event.get("sport", ""),
            commence_time=_parse_datetime(event.get("date")),
        )
    except Exception as e:
        logger.debug("Failed to parse arb bet: %s", e)
        return None


def _safe_decimal(val) -> float | None:
    """Safely convert a string or number to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_datetime(val) -> datetime | None:
    """Parse an ISO datetime string."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None
