"""FastAPI route definitions."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Query

from app.core.calculations import compute_consensus
from app.core.config import settings
from app.core.matching import match_markets
from app.core.scanner import ScanResult, get_latest_scan, run_scan
from app.core.selftest import run_all_selftests
from app.fixtures.synthetic import (
    synthetic_kalshi_markets,
    synthetic_polymarket_markets,
    synthetic_sportsbook_events,
)
from app.models.schemas import (
    ConsensusLine,
    HealthResponse,
    Opportunity,
    PredictionMarket,
    SubsystemStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Self-test results stored at startup
_selftest_results: list[SubsystemStatus] = []
_boot_time: datetime = datetime.utcnow()


def set_selftest_results(results: list[SubsystemStatus]):
    global _selftest_results
    _selftest_results = results


# ── Health ───────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    subsystems = list(_selftest_results)

    # Add live-data status
    has_key = settings.has_odds_api_key
    subsystems.append(
        SubsystemStatus(
            name="odds_api_key",
            ok=has_key,
            message="configured (odds-api.io)" if has_key else "missing – using synthetic data",
        )
    )

    # Telegram status
    subsystems.append(
        SubsystemStatus(
            name="telegram",
            ok=settings.has_telegram,
            message=(
                f"enabled (alert >= {settings.TELEGRAM_ALERT_EDGE*100:.0f}% edge)"
                if settings.has_telegram
                else "disabled"
            ),
        )
    )

    scan = get_latest_scan()
    if scan:
        subsystems.append(
            SubsystemStatus(
                name="last_scan",
                ok=len(scan.errors) == 0,
                message=(
                    f"{len(scan.opportunities)} opps, "
                    f"{len(scan.value_bets)} value bets, "
                    f"{len(scan.arbitrage_bets)} arbs"
                )
                if not scan.errors
                else f"errors: {', '.join(scan.errors[:3])}",
            )
        )
        subsystems.append(
            SubsystemStatus(
                name="live_games",
                ok=True,
                message=f"{len(scan.live_events)} live" if scan.has_live_games else "no live games",
            )
        )

    all_ok = all(s.ok for s in subsystems)

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        subsystems=subsystems,
    )


# ── Sportsbook odds ─────────────────────────────────────────────

@router.get("/odds/sportsbooks")
async def get_sportsbook_odds():
    scan = get_latest_scan()
    if scan and scan.consensus_lines:
        return {
            "source": "live",
            "count": len(scan.consensus_lines),
            "data": [cl.model_dump() for cl in scan.consensus_lines],
        }

    # Synthetic fallback
    events = synthetic_sportsbook_events()
    lines = [compute_consensus(e) for e in events]
    lines = [l for l in lines if l is not None]
    return {
        "source": "synthetic",
        "count": len(lines),
        "data": [l.model_dump() for l in lines],
    }


# ── Prediction markets ──────────────────────────────────────────

@router.get("/markets/polymarket")
async def get_polymarket():
    scan = get_latest_scan()
    if scan and scan.polymarket_markets:
        return {
            "source": "live",
            "count": len(scan.polymarket_markets),
            "data": [m.model_dump() for m in scan.polymarket_markets],
        }
    markets = synthetic_polymarket_markets()
    return {
        "source": "synthetic",
        "count": len(markets),
        "data": [m.model_dump() for m in markets],
    }


@router.get("/markets/kalshi")
async def get_kalshi():
    scan = get_latest_scan()
    if scan and scan.kalshi_markets:
        return {
            "source": "live",
            "count": len(scan.kalshi_markets),
            "data": [m.model_dump() for m in scan.kalshi_markets],
        }
    markets = synthetic_kalshi_markets()
    return {
        "source": "synthetic",
        "count": len(markets),
        "data": [m.model_dump() for m in markets],
    }


# ── Opportunities ────────────────────────────────────────────────

@router.get("/opportunities")
async def get_opportunities(
    league: str | None = Query(None),
    min_edge: float | None = Query(None),
    min_books: int | None = Query(None),
    min_confidence: float | None = Query(None),
    ev_positive_only: bool = Query(False),
):
    scan = get_latest_scan()

    if scan and scan.opportunities:
        opps = scan.opportunities
    else:
        # Compute from synthetic data
        opps = _synthetic_opportunities()

    # Apply filters
    if league:
        opps = [o for o in opps if o.league.upper() == league.upper()]
    if min_edge is not None:
        opps = [o for o in opps if abs(o.edge) >= min_edge]
    if min_books is not None:
        opps = [o for o in opps if o.num_books >= min_books]
    if min_confidence is not None:
        opps = [o for o in opps if o.confidence >= min_confidence]
    if ev_positive_only:
        opps = [o for o in opps if o.ev_proxy > 0]

    source = "live" if (scan and scan.opportunities) else "synthetic"
    return {
        "source": source,
        "count": len(opps),
        "data": [o.model_dump() for o in opps],
    }


# ── Value Bets (from odds-api.io) ──────────────────────────────

@router.get("/value-bets")
async def get_value_bets(
    min_ev: float | None = Query(None, description="Minimum EV (e.g. 0.05 for 5%)"),
    league: str | None = Query(None),
):
    scan = get_latest_scan()
    if not scan or not scan.value_bets:
        return {"source": "none", "count": 0, "data": []}

    bets = scan.value_bets
    if min_ev is not None:
        bets = [b for b in bets if b.expected_value >= min_ev]
    if league:
        bets = [b for b in bets if b.league.upper() == league.upper()]

    bets.sort(key=lambda b: b.expected_value, reverse=True)

    return {
        "source": "live",
        "count": len(bets),
        "data": [b.model_dump() for b in bets],
    }


# ── Arbitrage Bets (from odds-api.io) ──────────────────────────

@router.get("/arbitrage-bets")
async def get_arbitrage_bets(
    min_profit: float | None = Query(None, description="Min profit margin (e.g. 0.01 for 1%)"),
    league: str | None = Query(None),
):
    scan = get_latest_scan()
    if not scan or not scan.arbitrage_bets:
        return {"source": "none", "count": 0, "data": []}

    bets = scan.arbitrage_bets
    if min_profit is not None:
        bets = [b for b in bets if b.profit_margin >= min_profit]
    if league:
        bets = [b for b in bets if b.league.upper() == league.upper()]

    bets.sort(key=lambda b: b.profit_margin, reverse=True)

    return {
        "source": "live",
        "count": len(bets),
        "data": [b.model_dump() for b in bets],
    }


# ── Unmatched ────────────────────────────────────────────────────

@router.get("/unmatched")
async def get_unmatched():
    scan = get_latest_scan()
    if scan:
        return {
            "count": len(scan.unmatched),
            "data": [m.model_dump() for m in scan.unmatched],
        }
    return {"count": 0, "data": []}


# ── Refresh ──────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh():
    result = await run_scan()
    return {
        "status": "ok",
        "sportsbook_events": len(result.sportsbook_events),
        "consensus_lines": len(result.consensus_lines),
        "polymarket_markets": len(result.polymarket_markets),
        "kalshi_markets": len(result.kalshi_markets),
        "opportunities": len(result.opportunities),
        "value_bets": len(result.value_bets),
        "arbitrage_bets": len(result.arbitrage_bets),
        "live_games": result.has_live_games,
        "errors": result.errors,
    }


# ── Helpers ──────────────────────────────────────────────────────

def _synthetic_opportunities() -> list[Opportunity]:
    """Build opportunities from synthetic data for demo/testing."""
    from app.core.calculations import build_opportunity

    events = synthetic_sportsbook_events()
    consensus_lines = [compute_consensus(e) for e in events]
    consensus_lines = [c for c in consensus_lines if c is not None]

    all_markets = synthetic_polymarket_markets() + synthetic_kalshi_markets()
    matches, _ = match_markets(consensus_lines, all_markets)

    opps: list[Opportunity] = []
    for m in matches:
        opp = build_opportunity(m)
        opps.append(opp)

    opps.sort(key=lambda o: abs(o.edge), reverse=True)
    return opps
