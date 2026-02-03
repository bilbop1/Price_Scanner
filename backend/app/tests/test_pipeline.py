"""Integration test: full pipeline with synthetic data."""

import pytest
from app.core.calculations import build_opportunity, compute_consensus
from app.core.matching import match_markets
from app.fixtures.synthetic import (
    synthetic_kalshi_markets,
    synthetic_polymarket_markets,
    synthetic_sportsbook_events,
)


class TestFullPipeline:
    def test_synthetic_events_valid(self):
        events = synthetic_sportsbook_events()
        assert len(events) >= 3
        for ev in events:
            assert ev.home_team
            assert ev.away_team
            assert len(ev.bookmakers) >= 2

    def test_consensus_from_synthetic(self):
        events = synthetic_sportsbook_events()
        lines = [compute_consensus(e) for e in events]
        lines = [l for l in lines if l is not None]
        assert len(lines) == len(events)
        for cl in lines:
            assert abs(cl.consensus_home + cl.consensus_away - 1.0) < 0.02
            assert cl.num_books >= 2

    def test_matching_synthetic(self):
        events = synthetic_sportsbook_events()
        lines = [compute_consensus(e) for e in events]
        lines = [l for l in lines if l is not None]

        poly = synthetic_polymarket_markets()
        kalshi = synthetic_kalshi_markets()
        all_pm = poly + kalshi

        matches, unmatched = match_markets(lines, all_pm)
        assert len(matches) > 0, "should find at least one match"

        for m in matches:
            assert m.confidence >= 92
            assert m.matched_side in ("home", "away")

    def test_opportunities_from_synthetic(self):
        events = synthetic_sportsbook_events()
        lines = [compute_consensus(e) for e in events]
        lines = [l for l in lines if l is not None]

        poly = synthetic_polymarket_markets()
        kalshi = synthetic_kalshi_markets()

        matches, _ = match_markets(lines, poly + kalshi)
        opps = [build_opportunity(m) for m in matches]

        assert len(opps) > 0
        for opp in opps:
            assert opp.id
            assert opp.league
            assert opp.consensus_prob > 0
            assert opp.market_price > 0

    def test_edge_values_reasonable(self):
        events = synthetic_sportsbook_events()
        lines = [compute_consensus(e) for e in events]
        lines = [l for l in lines if l is not None]

        matches, _ = match_markets(lines, synthetic_polymarket_markets() + synthetic_kalshi_markets())
        for m in matches:
            opp = build_opportunity(m)
            # Edges should be reasonable (not >50%)
            assert abs(opp.edge) < 0.5, f"unreasonable edge: {opp.edge}"
