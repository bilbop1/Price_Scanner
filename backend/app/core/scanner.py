"""Scanner orchestrator: pulls data, computes consensus, matches, finds edges.

Integrates odds-api.io (value bets, arb bets), prediction markets,
and Telegram alerts for high-edge opportunities.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.clients.odds_api import (
    fetch_arbitrage_bets,
    fetch_live_events,
    fetch_sportsbook_odds,
    fetch_value_bets,
)
from app.clients.polymarket import fetch_polymarket_markets
from app.clients.kalshi import fetch_kalshi_markets
from app.core.calculations import build_opportunity, compute_consensus
from app.core.config import settings
from app.core.database import save_opportunities, save_scan_log
from app.core.matching import match_markets
from app.core.telegram import (
    send_arbitrage_alert,
    send_opportunity_alert,
    send_value_bet_alert,
)
from app.models.schemas import (
    ArbitrageBet,
    ConsensusLine,
    Opportunity,
    PredictionMarket,
    SportsEvent,
    ValueBet,
)

logger = logging.getLogger(__name__)


class ScanResult:
    def __init__(self):
        self.sportsbook_events: list[SportsEvent] = []
        self.consensus_lines: list[ConsensusLine] = []
        self.polymarket_markets: list[PredictionMarket] = []
        self.kalshi_markets: list[PredictionMarket] = []
        self.opportunities: list[Opportunity] = []
        self.unmatched: list[PredictionMarket] = []
        self.value_bets: list[ValueBet] = []
        self.arbitrage_bets: list[ArbitrageBet] = []
        self.live_events: list[SportsEvent] = []
        self.errors: list[str] = []
        self.timestamp: datetime = datetime.utcnow()
        self.has_live_games: bool = False


# Module-level latest scan result for the API to serve
_latest: ScanResult | None = None


def get_latest_scan() -> ScanResult | None:
    return _latest


async def run_scan() -> ScanResult:
    """Execute a full scan cycle."""
    global _latest
    result = ScanResult()

    # 1) Fetch sportsbook odds from odds-api.io
    try:
        result.sportsbook_events = await fetch_sportsbook_odds()
    except Exception as e:
        result.errors.append(f"sportsbook_fetch: {e}")
        logger.error("Sportsbook fetch failed: %s", e)

    # 2) Check for live games (for adaptive polling)
    try:
        result.live_events = await fetch_live_events()
        result.has_live_games = len(result.live_events) > 0
    except Exception as e:
        logger.debug("Live events check failed: %s", e)

    # 3) Compute consensus lines
    for ev in result.sportsbook_events:
        cl = compute_consensus(ev)
        if cl and cl.num_books >= settings.MIN_BOOKS:
            result.consensus_lines.append(cl)

    # 4) Fetch prediction markets
    try:
        result.polymarket_markets = await fetch_polymarket_markets()
    except Exception as e:
        result.errors.append(f"polymarket_fetch: {e}")
        logger.error("Polymarket fetch failed: %s", e)

    try:
        result.kalshi_markets = await fetch_kalshi_markets()
    except Exception as e:
        result.errors.append(f"kalshi_fetch: {e}")
        logger.error("Kalshi fetch failed: %s", e)

    all_prediction = result.polymarket_markets + result.kalshi_markets

    # 5) Match consensus lines to prediction markets
    if result.consensus_lines and all_prediction:
        matches, result.unmatched = match_markets(
            result.consensus_lines, all_prediction
        )

        # 6) Compute edges
        for m in matches:
            opp = build_opportunity(m)
            if abs(opp.edge) >= settings.MIN_EDGE:
                result.opportunities.append(opp)

        # Sort by absolute edge descending
        result.opportunities.sort(key=lambda o: abs(o.edge), reverse=True)
    else:
        result.unmatched = all_prediction

    # 7) Fetch value bets from odds-api.io
    try:
        result.value_bets = await fetch_value_bets()
    except Exception as e:
        result.errors.append(f"value_bets_fetch: {e}")
        logger.error("Value bets fetch failed: %s", e)

    # 8) Fetch arbitrage bets from odds-api.io
    try:
        result.arbitrage_bets = await fetch_arbitrage_bets()
    except Exception as e:
        result.errors.append(f"arb_bets_fetch: {e}")
        logger.error("Arb bets fetch failed: %s", e)

    # 9) Send Telegram alerts for super profitable opportunities
    await _send_alerts(result)

    # 10) Persist
    try:
        if result.opportunities:
            await save_opportunities(result.opportunities)
        await save_scan_log(
            num_sportsbook=len(result.sportsbook_events),
            num_poly=len(result.polymarket_markets),
            num_kalshi=len(result.kalshi_markets),
            num_matches=len(result.opportunities),
            num_opps=len(result.opportunities),
            errors=result.errors,
        )
    except Exception as e:
        result.errors.append(f"db_persist: {e}")
        logger.error("DB persist failed: %s", e)

    _latest = result
    logger.info(
        "Scan complete: %d events, %d consensus, %d poly, %d kalshi, "
        "%d opps, %d value_bets, %d arb_bets, live=%s",
        len(result.sportsbook_events),
        len(result.consensus_lines),
        len(result.polymarket_markets),
        len(result.kalshi_markets),
        len(result.opportunities),
        len(result.value_bets),
        len(result.arbitrage_bets),
        result.has_live_games,
    )
    return result


async def _send_alerts(result: ScanResult) -> None:
    """Send Telegram alerts for high-edge opportunities."""
    if not settings.has_telegram:
        return

    # Alert on high-edge consensus vs market opportunities
    for opp in result.opportunities:
        try:
            await send_opportunity_alert(opp)
        except Exception as e:
            logger.debug("Telegram opportunity alert failed: %s", e)

    # Alert on value bets
    for vb in result.value_bets:
        try:
            await send_value_bet_alert(vb)
        except Exception as e:
            logger.debug("Telegram value bet alert failed: %s", e)

    # Alert on arbitrage opportunities
    for arb in result.arbitrage_bets:
        try:
            await send_arbitrage_alert(arb)
        except Exception as e:
            logger.debug("Telegram arb alert failed: %s", e)
