"""Unit tests for odds conversion, de-vig, consensus, and edge math."""

import pytest
from datetime import datetime, timezone

from app.core.calculations import (
    build_opportunity,
    compute_consensus,
    compute_edge,
    decimal_to_implied,
    devig_two_outcome,
    devig_bookmaker,
)
from app.models.schemas import (
    BookmakerOdds,
    BookmakerOutcome,
    ConsensusLine,
    MarketSource,
    MatchResult,
    PredictionMarket,
    SportsEvent,
)


class TestDecimalToImplied:
    def test_even_odds(self):
        assert abs(decimal_to_implied(2.0) - 0.5) < 1e-6

    def test_heavy_favorite(self):
        assert abs(decimal_to_implied(1.25) - 0.8) < 1e-6

    def test_big_underdog(self):
        assert abs(decimal_to_implied(5.0) - 0.2) < 1e-6

    def test_even_money(self):
        assert abs(decimal_to_implied(1.0) - 1.0) < 1e-6

    def test_zero_returns_zero(self):
        assert decimal_to_implied(0) == 0.0

    def test_negative_returns_zero(self):
        assert decimal_to_implied(-2.0) == 0.0

    def test_large_odds(self):
        result = decimal_to_implied(100.0)
        assert abs(result - 0.01) < 1e-6


class TestDeVig:
    def test_fair_market(self):
        p1, p2 = devig_two_outcome(0.5, 0.5)
        assert abs(p1 - 0.5) < 1e-6
        assert abs(p2 - 0.5) < 1e-6

    def test_symmetric_vig(self):
        # Both sides at 1.91 → implied ~0.5236 each
        raw = 1 / 1.91
        p1, p2 = devig_two_outcome(raw, raw)
        assert abs(p1 - 0.5) < 1e-4
        assert abs(p2 - 0.5) < 1e-4

    def test_sums_to_one(self):
        p1, p2 = devig_two_outcome(0.6, 0.45)
        assert abs(p1 + p2 - 1.0) < 1e-6

    def test_asymmetric(self):
        p1, p2 = devig_two_outcome(0.7, 0.35)
        assert p1 > p2
        assert abs(p1 + p2 - 1.0) < 1e-6

    def test_zero_zero(self):
        p1, p2 = devig_two_outcome(0.0, 0.0)
        assert abs(p1 - 0.5) < 1e-6

    def test_preserves_ratio(self):
        """De-vigged probs should preserve the ratio of raw probs."""
        p1, p2 = devig_two_outcome(0.6, 0.4)
        assert abs(p1 / p2 - 0.6 / 0.4) < 1e-6


class TestDeVigBookmaker:
    def test_standard_bookmaker(self):
        bm = BookmakerOdds(
            bookmaker="test",
            home=BookmakerOutcome(name="Home", price=1.91),
            away=BookmakerOutcome(name="Away", price=1.91),
        )
        result = devig_bookmaker(bm)
        assert result.bookmaker == "test"
        assert abs(result.home_prob - 0.5) < 0.01
        assert abs(result.away_prob - 0.5) < 0.01
        assert abs(result.home_prob + result.away_prob - 1.0) < 1e-6


class TestConsensus:
    def _make_event(self, prices: list[tuple[float, float]]) -> SportsEvent:
        bookmakers = []
        for i, (hp, ap) in enumerate(prices):
            bookmakers.append(
                BookmakerOdds(
                    bookmaker=f"book{i}",
                    home=BookmakerOutcome(name="Home", price=hp),
                    away=BookmakerOutcome(name="Away", price=ap),
                )
            )
        return SportsEvent(
            event_id="test",
            sport_key="basketball_nba",
            sport_title="NBA",
            league="NBA",
            home_team="Home",
            away_team="Away",
            commence_time=datetime.now(tz=timezone.utc),
            bookmakers=bookmakers,
        )

    def test_single_book(self):
        ev = self._make_event([(1.91, 1.91)])
        cl = compute_consensus(ev)
        assert cl is not None
        assert cl.num_books == 1
        assert abs(cl.consensus_home - 0.5) < 0.01

    def test_multiple_books(self):
        ev = self._make_event([(1.91, 1.91), (2.10, 1.74), (1.80, 2.05)])
        cl = compute_consensus(ev)
        assert cl is not None
        assert cl.num_books == 3
        assert abs(cl.consensus_home + cl.consensus_away - 1.0) < 0.02

    def test_empty_bookmakers(self):
        ev = self._make_event([])
        cl = compute_consensus(ev)
        assert cl is None

    def test_median_computed(self):
        ev = self._make_event([(1.50, 2.80), (1.91, 1.91), (2.50, 1.55)])
        cl = compute_consensus(ev)
        assert cl is not None
        assert cl.median_home > 0
        assert cl.median_away > 0


class TestEdge:
    def test_positive_edge(self):
        edge, ev = compute_edge(0.55, 0.50, fee_buffer=0.03)
        assert abs(edge - 0.05) < 1e-6
        assert abs(ev - 0.02) < 1e-6

    def test_negative_edge(self):
        edge, ev = compute_edge(0.45, 0.50, fee_buffer=0.03)
        assert abs(edge - (-0.05)) < 1e-6
        assert abs(ev - (-0.08)) < 1e-6

    def test_zero_edge(self):
        edge, ev = compute_edge(0.50, 0.50, fee_buffer=0.03)
        assert abs(edge) < 1e-6
        assert abs(ev - (-0.03)) < 1e-6

    def test_custom_fee_buffer(self):
        edge, ev = compute_edge(0.60, 0.50, fee_buffer=0.05)
        assert abs(edge - 0.10) < 1e-6
        assert abs(ev - 0.05) < 1e-6


class TestBuildOpportunity:
    def test_home_side(self):
        cl = ConsensusLine(
            event_id="e1",
            home_team="Team A",
            away_team="Team B",
            league="NBA",
            commence_time=datetime.now(tz=timezone.utc),
            books=[],
            consensus_home=0.60,
            consensus_away=0.40,
            median_home=0.61,
            median_away=0.39,
            num_books=4,
        )
        pm = PredictionMarket(
            source=MarketSource.POLYMARKET,
            market_id="p1",
            event_title="A vs B",
            outcome="Team A",
            yes_price=0.55,
            mid=0.54,
        )
        mr = MatchResult(
            consensus=cl, prediction_market=pm, matched_side="home", confidence=95
        )
        opp = build_opportunity(mr)
        assert opp.consensus_prob == 0.60
        assert opp.market_price == 0.54
        assert opp.edge > 0
        assert opp.id != ""

    def test_away_side(self):
        cl = ConsensusLine(
            event_id="e2",
            home_team="Team A",
            away_team="Team B",
            league="NFL",
            commence_time=datetime.now(tz=timezone.utc),
            books=[],
            consensus_home=0.40,
            consensus_away=0.60,
            median_home=0.39,
            median_away=0.61,
            num_books=3,
        )
        pm = PredictionMarket(
            source=MarketSource.KALSHI,
            market_id="k1",
            event_title="A vs B",
            outcome="Team B",
            yes_price=0.55,
        )
        mr = MatchResult(
            consensus=cl, prediction_market=pm, matched_side="away", confidence=98
        )
        opp = build_opportunity(mr)
        assert opp.consensus_prob == 0.60
        assert opp.market_price == 0.55
