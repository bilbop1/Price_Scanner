"""Client for Polymarket – Gamma API (listings) + CLOB API (pricing)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.models.schemas import MarketSource, PredictionMarket

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, list[PredictionMarket]]] = {}

# Sport-related tags / slugs to filter for
SPORT_KEYWORDS = [
    "nfl", "nba", "mlb", "nhl", "ncaa", "ncaaf", "ncaab",
    "football", "basketball", "baseball", "hockey", "soccer", "mls",
    "super bowl", "world series", "stanley cup", "march madness",
]


async def fetch_polymarket_markets() -> list[PredictionMarket]:
    """Fetch sports-related markets from Polymarket."""
    cache_key = "polymarket"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < settings.CACHE_TTL:
            return data

    markets: list[PredictionMarket] = []
    try:
        events = await _fetch_gamma_events()
        for ev in events:
            for mkt in ev.get("markets", []):
                parsed = _parse_gamma_market(mkt, ev)
                if parsed:
                    markets.append(parsed)

        if markets:
            markets = await _enrich_clob_prices(markets)

    except Exception as e:
        logger.error("Polymarket fetch error: %s", e)

    _cache[cache_key] = (now, markets)
    return markets


async def _fetch_gamma_events() -> list[dict]:
    """Pull events from Gamma API, filtering for sports."""
    all_events: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Gamma events endpoint with sports tag filter
        for keyword in ["nfl", "nba", "mlb", "nhl", "mls", "ncaa"]:
            try:
                resp = await client.get(
                    f"{settings.POLYMARKET_GAMMA_BASE}/events",
                    params={
                        "tag": keyword,
                        "closed": "false",
                        "limit": 100,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        all_events.extend(data)
                    elif isinstance(data, dict) and "data" in data:
                        all_events.extend(data["data"])
            except Exception as e:
                logger.debug("Gamma events search '%s': %s", keyword, e)

        # Also try broader sports search
        try:
            resp = await client.get(
                f"{settings.POLYMARKET_GAMMA_BASE}/events",
                params={
                    "tag": "sports",
                    "closed": "false",
                    "limit": 200,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    all_events.extend(data)
                elif isinstance(data, dict) and "data" in data:
                    all_events.extend(data["data"])
        except Exception as e:
            logger.debug("Gamma events sports: %s", e)

    # Deduplicate by event id
    seen: set[str] = set()
    unique: list[dict] = []
    for ev in all_events:
        eid = str(ev.get("id", ev.get("slug", "")))
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(ev)
    return unique


def _is_sports_market(ev: dict, mkt: dict) -> bool:
    """Check if event/market is sports-related."""
    text = " ".join([
        ev.get("title", ""),
        ev.get("description", ""),
        mkt.get("question", ""),
        " ".join(ev.get("tags", [])),
    ]).lower()
    return any(kw in text for kw in SPORT_KEYWORDS)


def _parse_gamma_market(mkt: dict, ev: dict) -> PredictionMarket | None:
    """Parse a Gamma market dict into our schema."""
    if not _is_sports_market(ev, mkt):
        return None

    question = mkt.get("question", mkt.get("groupItemTitle", ""))
    outcome = mkt.get("outcome", mkt.get("groupItemTitle", question))

    # Extract price
    yes_price = 0.0
    outcomes_list = mkt.get("outcomes", [])
    prices_list = mkt.get("outcomePrices", [])
    if isinstance(prices_list, list) and prices_list:
        try:
            yes_price = float(prices_list[0])
        except (ValueError, IndexError):
            pass
    elif mkt.get("lastTradePrice"):
        try:
            yes_price = float(mkt["lastTradePrice"])
        except ValueError:
            pass

    if yes_price <= 0:
        return None

    # Determine league from tags
    tags = [t.lower() if isinstance(t, str) else str(t).lower() for t in ev.get("tags", [])]
    league = _infer_league(tags, ev.get("title", ""))

    # Parse start time
    start_time = None
    for field in ("startDate", "start_date", "endDate", "end_date"):
        val = ev.get(field) or mkt.get(field)
        if val:
            try:
                start_time = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                break
            except ValueError:
                continue

    condition_id = str(mkt.get("conditionId", mkt.get("id", "")))

    return PredictionMarket(
        source=MarketSource.POLYMARKET,
        market_id=condition_id,
        event_title=ev.get("title", question),
        outcome=outcome if isinstance(outcome, str) else str(outcome),
        yes_price=yes_price,
        no_price=round(1 - yes_price, 4) if yes_price else 0.0,
        league=league,
        start_time=start_time,
        raw_tags=tags,
    )


def _infer_league(tags: list[str], title: str) -> str:
    text = " ".join(tags) + " " + title.lower()
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
    if "ncaab" in text or "march madness" in text:
        return "NCAAB"
    if "mls" in text or "soccer" in text:
        return "MLS"
    return ""


async def _enrich_clob_prices(markets: list[PredictionMarket]) -> list[PredictionMarket]:
    """Enrich markets with CLOB bid/ask/mid prices."""
    token_ids = [m.market_id for m in markets if m.market_id]
    if not token_ids:
        return markets

    price_map: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Batch fetch in chunks of 20
        for i in range(0, len(token_ids), 20):
            batch = token_ids[i : i + 20]
            try:
                resp = await client.get(
                    f"{settings.POLYMARKET_CLOB_BASE}/prices",
                    params={"token_ids": ",".join(batch)},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        price_map.update(data)
            except Exception as e:
                logger.debug("CLOB prices batch error: %s", e)

            # Also try midpoints endpoint
            try:
                resp = await client.get(
                    f"{settings.POLYMARKET_CLOB_BASE}/midpoints",
                    params={"token_ids": ",".join(batch)},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        for tid, mid_val in data.items():
                            if tid not in price_map:
                                price_map[tid] = {}
                            price_map[tid]["mid"] = mid_val
            except Exception as e:
                logger.debug("CLOB midpoints batch error: %s", e)

    for m in markets:
        if m.market_id in price_map:
            pdata = price_map[m.market_id]
            if isinstance(pdata, dict):
                m.bid = _safe_float(pdata.get("bid"))
                m.ask = _safe_float(pdata.get("ask"))
                mid = _safe_float(pdata.get("mid"))
                if m.bid is not None and m.ask is not None:
                    spread = (m.ask or 0) - (m.bid or 0)
                    if spread <= 0.10:
                        m.mid = round(((m.bid or 0) + (m.ask or 0)) / 2, 4)
                    else:
                        m.mid = m.last_trade or m.yes_price
                elif mid is not None:
                    m.mid = mid
            elif isinstance(pdata, (int, float)):
                m.mid = float(pdata)

    return markets


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
