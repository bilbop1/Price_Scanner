"""Scanner orchestrator: pulls data, computes consensus, matches, finds edges."""

from __future__ import annotations

import logging
from datetime import datetime

from app.clients.odds_api import fetch_sportsbook_odds
from app.clients.polymarket import fetch_polymarket_markets
from app.clients.kalshi import fetch_kalshi_markets
from app.core.calculations import build_opportunity, compute_consensus
from app.core.config import settings
from app.core.database import save_opportunities, save_scan_log
from app.core.matching import match_markets
from app.models.schemas import (
    ConsensusLine,
    Opportunity,
    PredictionMarket,
    SportsEvent,
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
        self.errors: list[str] = []
        self.timestamp: datetime = datetime.utcnow()


# Module-level latest scan result for the API to serve
_latest: ScanResult | None = None


def get_latest_scan() -> ScanResult | None:
    return _latest


async def run_scan() -> ScanResult:
    """Execute a full scan cycle."""
    global _latest
    result = ScanResult()

    # 1) Fetch sportsbook odds
    try:
        result.sportsbook_events = await fetch_sportsbook_odds()
    except Exception as e:
        result.errors.append(f"sportsbook_fetch: {e}")
        logger.error("Sportsbook fetch failed: %s", e)

    # 2) Compute consensus lines
    for ev in result.sportsbook_events:
        cl = compute_consensus(ev)
        if cl and cl.num_books >= settings.MIN_BOOKS:
            result.consensus_lines.append(cl)

    # 3) Fetch prediction markets
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

    # 4) Match
    if result.consensus_lines and all_prediction:
        matches, result.unmatched = match_markets(
            result.consensus_lines, all_prediction
        )

        # 5) Compute edges
        for m in matches:
            opp = build_opportunity(m)
            if abs(opp.edge) >= settings.MIN_EDGE:
                result.opportunities.append(opp)

        # Sort by absolute edge descending
        result.opportunities.sort(key=lambda o: abs(o.edge), reverse=True)
    else:
        result.unmatched = all_prediction

    # 6) Persist
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
        "Scan complete: %d events, %d consensus, %d poly, %d kalshi, %d opps",
        len(result.sportsbook_events),
        len(result.consensus_lines),
        len(result.polymarket_markets),
        len(result.kalshi_markets),
        len(result.opportunities),
    )
    return result
