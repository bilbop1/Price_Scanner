"""Startup self-tests: validate schema, parsing, math, and matching logic.

Runs automatically on boot using synthetic fixtures.
Reports pass/fail per subsystem so the UI can show degraded state.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from app.core.calculations import (
    build_opportunity,
    compute_consensus,
    compute_edge,
    decimal_to_implied,
    devig_two_outcome,
)
from app.core.matching import match_markets, normalize_team
from app.models.schemas import (
    ArbitrageBet,
    ArbitrageLeg,
    BookmakerOdds,
    BookmakerOutcome,
    ConsensusLine,
    MarketSource,
    MatchResult,
    PredictionMarket,
    SportsEvent,
    SubsystemStatus,
    ValueBet,
)

logger = logging.getLogger(__name__)


def _approx(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(a - b) < tol


def run_all_selftests() -> list[SubsystemStatus]:
    """Run every self-test and return per-subsystem results."""
    results: list[SubsystemStatus] = []
    tests = [
        ("odds_conversion", _test_odds_conversion),
        ("devig_math", _test_devig),
        ("consensus_calc", _test_consensus),
        ("edge_calc", _test_edge),
        ("team_normalization", _test_normalization),
        ("matching_engine", _test_matching),
        ("opportunity_build", _test_opportunity_build),
        ("schema_validation", _test_schema_validation),
        ("value_bet_schema", _test_value_bet_schema),
        ("arbitrage_schema", _test_arbitrage_schema),
    ]
    for name, fn in tests:
        try:
            fn()
            results.append(SubsystemStatus(name=name, ok=True, message="passed"))
            logger.info("Self-test %s: PASSED", name)
        except Exception as e:
            results.append(SubsystemStatus(name=name, ok=False, message=str(e)))
            logger.error("Self-test %s: FAILED – %s", name, e)
    return results


# ── Individual tests ─────────────────────────────────────────────

def _test_odds_conversion():
    """Decimal odds to implied probability."""
    assert _approx(decimal_to_implied(2.0), 0.5), "2.0 -> 0.5"
    assert _approx(decimal_to_implied(1.5), 2 / 3), "1.5 -> 0.6667"
    assert _approx(decimal_to_implied(3.0), 1 / 3), "3.0 -> 0.3333"
    assert _approx(decimal_to_implied(1.0), 1.0), "1.0 -> 1.0"
    assert decimal_to_implied(0) == 0.0, "0 -> 0"
    assert decimal_to_implied(-1) == 0.0, "negative -> 0"


def _test_devig():
    """Two-outcome de-vig normalization."""
    p1, p2 = devig_two_outcome(0.5, 0.5)
    assert _approx(p1, 0.5) and _approx(p2, 0.5), "fair market"

    p1, p2 = devig_two_outcome(0.526, 0.526)
    assert _approx(p1, 0.5) and _approx(p2, 0.5), "symmetric vig"

    p1, p2 = devig_two_outcome(0.6, 0.5)
    assert _approx(p1 + p2, 1.0), "must sum to 1"
    assert _approx(p1, 0.6 / 1.1, tol=1e-3), "asymmetric p1"

    p1, p2 = devig_two_outcome(0.0, 0.0)
    assert _approx(p1, 0.5), "zero/zero"


def _test_consensus():
    """Consensus probability from multiple bookmakers."""
    event = SportsEvent(
        event_id="test1",
        sport_key="basketball_nba",
        sport_title="NBA",
        league="NBA",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc),
        bookmakers=[
            BookmakerOdds(
                bookmaker="fanduel",
                home=BookmakerOutcome(name="Los Angeles Lakers", price=1.91),
                away=BookmakerOutcome(name="Boston Celtics", price=1.91),
            ),
            BookmakerOdds(
                bookmaker="draftkings",
                home=BookmakerOutcome(name="Los Angeles Lakers", price=2.10),
                away=BookmakerOutcome(name="Boston Celtics", price=1.74),
            ),
        ],
    )
    cl = compute_consensus(event)
    assert cl is not None, "consensus must not be None"
    assert cl.num_books == 2, "two books"
    assert _approx(cl.consensus_home + cl.consensus_away, 1.0, tol=0.01), (
        f"consensus sums to 1: {cl.consensus_home} + {cl.consensus_away}"
    )
    assert 0 < cl.consensus_home < 1, "home prob in (0,1)"
    assert 0 < cl.consensus_away < 1, "away prob in (0,1)"
    assert cl.median_home > 0, "median computed"


def _test_edge():
    """Edge and EV proxy calculations."""
    edge, ev = compute_edge(0.55, 0.50, fee_buffer=0.03)
    assert _approx(edge, 0.05), f"edge = 0.05, got {edge}"
    assert _approx(ev, 0.02), f"ev = 0.02, got {ev}"

    edge2, ev2 = compute_edge(0.50, 0.55, fee_buffer=0.03)
    assert _approx(edge2, -0.05), "negative edge"
    assert _approx(ev2, -0.08), "negative ev"


def _test_normalization():
    """Team name normalization."""
    assert normalize_team("KC Chiefs") == "kansas city chiefs"
    assert normalize_team("LA Lakers") == "los angeles lakers"
    assert normalize_team("GSW") == "golden state warriors"
    n = normalize_team("Boston Celtics")
    assert "boston" in n and "celtics" in n


def _test_matching():
    """Matching engine: exact + fuzzy."""
    cl = ConsensusLine(
        event_id="m1",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        league="NBA",
        commence_time=datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc),
        books=[],
        consensus_home=0.55,
        consensus_away=0.45,
        median_home=0.55,
        median_away=0.45,
        num_books=3,
    )

    pm_exact = PredictionMarket(
        source=MarketSource.POLYMARKET,
        market_id="pm1",
        event_title="Lakers vs Celtics",
        outcome="Los Angeles Lakers",
        yes_price=0.52,
        league="NBA",
        start_time=datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc),
    )

    matches, unmatched = match_markets([cl], [pm_exact])
    assert len(matches) == 1, f"expected 1 match, got {len(matches)}"
    assert matches[0].matched_side == "home"
    assert matches[0].confidence >= 92

    pm_fuzzy = PredictionMarket(
        source=MarketSource.KALSHI,
        market_id="k1",
        event_title="LA Lakers to win",
        outcome="LA Lakers",
        yes_price=0.51,
        league="NBA",
        start_time=datetime(2025, 1, 15, 19, 0, tzinfo=timezone.utc),
    )

    matches2, _ = match_markets([cl], [pm_fuzzy])
    assert len(matches2) == 1, f"fuzzy: expected 1 match, got {len(matches2)}"
    assert matches2[0].matched_side == "home"

    pm_wrong_league = PredictionMarket(
        source=MarketSource.POLYMARKET,
        market_id="pm_wrong",
        event_title="Lakers vs Celtics",
        outcome="Los Angeles Lakers",
        yes_price=0.52,
        league="MLB",
        start_time=datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc),
    )
    matches3, unmatched3 = match_markets([cl], [pm_wrong_league])
    assert len(matches3) == 0, "wrong league should not match"


def _test_opportunity_build():
    """Build opportunity from match result."""
    cl = ConsensusLine(
        event_id="opp1",
        home_team="Green Bay Packers",
        away_team="Chicago Bears",
        league="NFL",
        commence_time=datetime(2025, 1, 20, 18, 0, tzinfo=timezone.utc),
        books=[],
        consensus_home=0.60,
        consensus_away=0.40,
        median_home=0.61,
        median_away=0.39,
        num_books=5,
    )
    pm = PredictionMarket(
        source=MarketSource.POLYMARKET,
        market_id="pm_opp",
        event_title="Packers vs Bears",
        outcome="Green Bay Packers",
        yes_price=0.55,
        mid=0.54,
        bid=0.53,
        ask=0.55,
        league="NFL",
    )
    mr = MatchResult(consensus=cl, prediction_market=pm, matched_side="home", confidence=98.0)
    opp = build_opportunity(mr)
    assert opp.edge > 0, "positive edge expected"
    assert opp.consensus_prob == 0.60
    assert opp.market_price == 0.54  # mid used
    assert opp.id, "id must be set"


def _test_schema_validation():
    """Validate Pydantic schemas accept and reject correctly."""
    ev = SportsEvent(
        event_id="s1",
        sport_key="basketball_nba",
        sport_title="NBA",
        home_team="Team A",
        away_team="Team B",
        commence_time=datetime.now(tz=timezone.utc),
    )
    assert ev.event_id == "s1"

    pm = PredictionMarket(
        source=MarketSource.KALSHI,
        market_id="k99",
        event_title="Test",
        outcome="Team A",
        yes_price=0.65,
    )
    assert pm.no_price == 0.35

    data = pm.model_dump()
    pm2 = PredictionMarket(**data)
    assert pm2.yes_price == pm.yes_price


def _test_value_bet_schema():
    """Validate ValueBet schema."""
    vb = ValueBet(
        id="vb1",
        event_id="ev1",
        bookmaker="Bet365",
        market="ML",
        bet_side="home",
        expected_value=0.08,
        bookmaker_odds=2.15,
        home_team="Team A",
        away_team="Team B",
        league="NBA",
    )
    assert vb.expected_value == 0.08
    assert vb.bookmaker == "Bet365"

    data = vb.model_dump()
    vb2 = ValueBet(**data)
    assert vb2.expected_value == vb.expected_value


def _test_arbitrage_schema():
    """Validate ArbitrageBet schema."""
    arb = ArbitrageBet(
        id="arb1",
        event_id="ev1",
        market="ML",
        profit_margin=0.02,
        implied_probability=0.98,
        total_stake=100,
        legs=[
            ArbitrageLeg(bookmaker="Bet365", bet_side="home", odds=2.10),
            ArbitrageLeg(bookmaker="Unibet", bet_side="away", odds=2.05),
        ],
        optimal_stakes=[52.0, 48.0],
        home_team="Team A",
        away_team="Team B",
        league="NFL",
    )
    assert arb.profit_margin == 0.02
    assert len(arb.legs) == 2
    assert arb.optimal_stakes == [52.0, 48.0]

    data = arb.model_dump()
    arb2 = ArbitrageBet(**data)
    assert arb2.profit_margin == arb.profit_margin
