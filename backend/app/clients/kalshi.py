"""Client for Kalshi – public market data endpoints."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from app.core.config import settings
from app.models.schemas import MarketSource, PredictionMarket

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, list[PredictionMarket]]] = {}

SPORT_KEYWORDS = [
    "nfl", "nba", "mlb", "nhl", "ncaa", "ncaaf", "ncaab",
    "football", "basketball", "baseball", "hockey", "soccer", "mls",
    "super bowl", "world series", "stanley cup", "march madness",
]

SPORT_CATEGORIES = [
    "sports",
    "football",
    "basketball",
    "baseball",
    "hockey",
]


async def fetch_kalshi_markets() -> list[PredictionMarket]:
    """Fetch sports-related markets from Kalshi public API."""
    cache_key = "kalshi"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL:
            return data

    markets: list[PredictionMarket] = []
    try:
        raw_events = await _fetch_kalshi_events()
        raw_markets = await _fetch_kalshi_market_data(raw_events)

        for rmkt in raw_markets:
            parsed = _parse_kalshi_market(rmkt)
            if parsed:
                markets.append(parsed)

    except Exception as e:
        logger.error("Kalshi fetch error: %s", e)

    _cache[cache_key] = (now, markets)
    return markets


async def _fetch_kalshi_events() -> list[dict]:
    """Fetch events from Kalshi, focusing on sports categories."""
    all_events: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # Try the events endpoint with status filter
            resp = await client.get(
                f"{settings.KALSHI_API_BASE}/events",
                params={
                    "status": "open",
                    "limit": 200,
                    "with_nested_markets": "true",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", data if isinstance(data, list) else [])
                for ev in events:
                    if _is_sports_event_kalshi(ev):
                        all_events.append(ev)
        except Exception as e:
            logger.debug("Kalshi events fetch: %s", e)

        # Also search by category
        for cat in SPORT_CATEGORIES:
            try:
                resp = await client.get(
                    f"{settings.KALSHI_API_BASE}/events",
                    params={
                        "series_ticker": cat,
                        "status": "open",
                        "limit": 100,
                        "with_nested_markets": "true",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("events", data if isinstance(data, list) else [])
                    all_events.extend(events)
            except Exception as e:
                logger.debug("Kalshi category '%s': %s", cat, e)

    # Deduplicate
    seen: set[str] = set()
    unique: list[dict] = []
    for ev in all_events:
        eid = ev.get("event_ticker", ev.get("ticker", str(id(ev))))
        if eid not in seen:
            seen.add(eid)
            unique.append(ev)
    return unique


async def _fetch_kalshi_market_data(events: list[dict]) -> list[dict]:
    """Fetch market-level data including orderbook midpoints."""
    markets_out: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for ev in events:
            nested = ev.get("markets", [])
            if nested:
                for mkt in nested:
                    mkt["_event"] = ev
                    markets_out.append(mkt)
                continue

            # Fetch markets for this event separately
            ticker = ev.get("event_ticker", ev.get("ticker"))
            if not ticker:
                continue
            try:
                resp = await client.get(
                    f"{settings.KALSHI_API_BASE}/markets",
                    params={"event_ticker": ticker, "limit": 50},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    mkt_list = data.get("markets", [])
                    for mkt in mkt_list:
                        mkt["_event"] = ev
                        markets_out.append(mkt)
            except Exception as e:
                logger.debug("Kalshi markets for %s: %s", ticker, e)

    # Enrich with orderbook midpoints
    markets_out = await _enrich_orderbook(client=None, markets=markets_out)
    return markets_out


async def _enrich_orderbook(client, markets: list[dict]) -> list[dict]:
    """Try to get orderbook-level bid/ask for each market."""
    async with httpx.AsyncClient(timeout=10.0) as c:
        for mkt in markets:
            ticker = mkt.get("ticker")
            if not ticker:
                continue
            try:
                resp = await c.get(
                    f"{settings.KALSHI_API_BASE}/markets/{ticker}/orderbook",
                )
                if resp.status_code == 200:
                    ob = resp.json().get("orderbook", resp.json())
                    mkt["_orderbook"] = ob
            except Exception:
                pass
    return markets


def _is_sports_event_kalshi(ev: dict) -> bool:
    text = " ".join([
        ev.get("title", ""),
        ev.get("category", ""),
        ev.get("sub_title", ""),
        ev.get("series_ticker", ""),
    ]).lower()
    return any(kw in text for kw in SPORT_KEYWORDS)


def _parse_kalshi_market(raw: dict) -> PredictionMarket | None:
    ev = raw.get("_event", {})
    title = ev.get("title", raw.get("title", ""))
    subtitle = raw.get("subtitle", raw.get("title", ""))

    # Price: use yes_price from API, or compute from orderbook
    yes_price = 0.0
    for field in ("yes_price", "last_price", "yes_sub_title"):
        val = raw.get(field)
        if val is not None:
            try:
                p = float(val)
                # Kalshi prices are in cents (0-100) or dollars (0-1)
                if p > 1:
                    p = p / 100.0
                yes_price = p
                break
            except (ValueError, TypeError):
                continue

    bid, ask, mid = None, None, None
    ob = raw.get("_orderbook", {})
    if ob:
        yes_bids = ob.get("yes", ob.get("bids", []))
        yes_asks = ob.get("no", ob.get("asks", []))
        if isinstance(yes_bids, list) and yes_bids:
            try:
                bid = float(yes_bids[0].get("price", yes_bids[0])) / 100
            except (ValueError, TypeError, AttributeError):
                pass
        if isinstance(yes_asks, list) and yes_asks:
            try:
                ask = 1 - float(yes_asks[0].get("price", yes_asks[0])) / 100
            except (ValueError, TypeError, AttributeError):
                pass
        if bid is not None and ask is not None:
            mid = round((bid + ask) / 2, 4)

    if yes_price <= 0 and mid:
        yes_price = mid
    if yes_price <= 0:
        return None

    if mid is None:
        mid = yes_price

    # League inference
    league = _infer_league_kalshi(ev, raw)

    # Start time
    start_time = None
    for field in ("expected_expiration_time", "close_time", "expiration_time"):
        val = raw.get(field) or ev.get(field)
        if val:
            try:
                start_time = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                break
            except ValueError:
                continue

    ticker = raw.get("ticker", "")

    return PredictionMarket(
        source=MarketSource.KALSHI,
        market_id=ticker,
        event_title=title,
        outcome=subtitle,
        yes_price=round(yes_price, 4),
        no_price=round(1 - yes_price, 4),
        bid=bid,
        ask=ask,
        mid=mid,
        league=league,
        start_time=start_time,
        raw_tags=[ev.get("category", ""), ev.get("series_ticker", "")],
    )


def _infer_league_kalshi(ev: dict, mkt: dict) -> str:
    text = " ".join([
        ev.get("title", ""),
        ev.get("category", ""),
        mkt.get("ticker", ""),
        ev.get("series_ticker", ""),
    ]).lower()
    if "nfl" in text or "football" in text:
        return "NFL"
    if "nba" in text or "basketball" in text:
        return "NBA"
    if "mlb" in text or "baseball" in text:
        return "MLB"
    if "nhl" in text or "hockey" in text:
        return "NHL"
    if "ncaaf" in text:
        return "NCAAF"
    if "ncaab" in text:
        return "NCAAB"
    if "mls" in text or "soccer" in text:
        return "MLS"
    return ""
