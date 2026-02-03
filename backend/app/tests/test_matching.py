"""Unit tests for the matching engine."""

import pytest
from datetime import datetime, timezone, timedelta

from app.core.matching import (
    match_markets,
    normalize_team,
    _extract_team_names,
    _times_close,
    _leagues_compatible,
)
from app.models.schemas import (
    ConsensusLine,
    MarketSource,
    PredictionMarket,
)


class TestNormalizeTeam:
    def test_alias_kc(self):
        assert normalize_team("KC Chiefs") == "kansas city chiefs"

    def test_alias_la_lakers(self):
        assert normalize_team("LA Lakers") == "los angeles lakers"

    def test_alias_gsw(self):
        assert normalize_team("GSW") == "golden state warriors"

    def test_full_name(self):
        result = normalize_team("Boston Celtics")
        assert "boston" in result
        assert "celtics" in result

    def test_case_insensitive(self):
        assert normalize_team("kc chiefs") == normalize_team("KC CHIEFS")

    def test_strip_noise(self):
        result = normalize_team("Lakers to win?")
        assert "?" not in result
        assert "win" not in result


class TestExtractTeamNames:
    def test_vs_separator(self):
        names = _extract_team_names("Lakers vs Celtics")
        assert len(names) == 2

    def test_dash_separator(self):
        names = _extract_team_names("Lakers - Celtics")
        assert len(names) == 2

    def test_single_team(self):
        names = _extract_team_names("Los Angeles Lakers")
        assert len(names) == 1


class TestTimesClose:
    def test_same_time(self):
        t = datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc)
        assert _times_close(t, t)

    def test_within_window(self):
        t1 = datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(hours=5)
        assert _times_close(t1, t2)

    def test_outside_window(self):
        t1 = datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(hours=7)
        assert not _times_close(t1, t2)

    def test_none_times(self):
        t = datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc)
        assert _times_close(None, t)
        assert _times_close(t, None)
        assert _times_close(None, None)


class TestLeaguesCompatible:
    def test_same_league(self):
        assert _leagues_compatible("NBA", "NBA")
        assert _leagues_compatible("NFL", "NFL")

    def test_empty_league(self):
        assert _leagues_compatible("", "NBA")
        assert _leagues_compatible("NBA", "")

    def test_incompatible(self):
        assert not _leagues_compatible("NBA", "MLB")
        assert not _leagues_compatible("NFL", "NHL")


def _make_consensus(
    home: str = "Los Angeles Lakers",
    away: str = "Boston Celtics",
    league: str = "NBA",
    time: datetime | None = None,
) -> ConsensusLine:
    return ConsensusLine(
        event_id="test",
        home_team=home,
        away_team=away,
        league=league,
        commence_time=time or datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc),
        books=[],
        consensus_home=0.55,
        consensus_away=0.45,
        median_home=0.55,
        median_away=0.45,
        num_books=3,
    )


def _make_pm(
    outcome: str = "Los Angeles Lakers",
    league: str = "NBA",
    source: MarketSource = MarketSource.POLYMARKET,
    time: datetime | None = None,
) -> PredictionMarket:
    return PredictionMarket(
        source=source,
        market_id="pm1",
        event_title="Lakers vs Celtics",
        outcome=outcome,
        yes_price=0.52,
        league=league,
        start_time=time or datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc),
    )


class TestMatchMarkets:
    def test_exact_match(self):
        cl = _make_consensus()
        pm = _make_pm()
        matches, unmatched = match_markets([cl], [pm])
        assert len(matches) == 1
        assert matches[0].matched_side == "home"
        assert matches[0].confidence >= 92

    def test_fuzzy_match(self):
        cl = _make_consensus()
        pm = _make_pm(outcome="LA Lakers")
        matches, unmatched = match_markets([cl], [pm])
        assert len(matches) == 1
        assert matches[0].matched_side == "home"

    def test_away_team_match(self):
        cl = _make_consensus()
        pm = _make_pm(outcome="Boston Celtics")
        matches, _ = match_markets([cl], [pm])
        assert len(matches) == 1
        assert matches[0].matched_side == "away"

    def test_wrong_league_no_match(self):
        cl = _make_consensus(league="NBA")
        pm = _make_pm(league="MLB")
        matches, unmatched = match_markets([cl], [pm])
        assert len(matches) == 0
        assert len(unmatched) == 1

    def test_time_outside_window(self):
        t1 = datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(hours=8)
        cl = _make_consensus(time=t1)
        pm = _make_pm(time=t2)
        matches, unmatched = match_markets([cl], [pm])
        assert len(matches) == 0

    def test_multiple_markets(self):
        cl = _make_consensus()
        pm1 = _make_pm(outcome="Los Angeles Lakers")
        pm2 = _make_pm(outcome="Boston Celtics")
        pm2.market_id = "pm2"
        matches, _ = match_markets([cl], [pm1, pm2])
        assert len(matches) == 2

    def test_kalshi_match(self):
        cl = _make_consensus()
        pm = _make_pm(source=MarketSource.KALSHI)
        matches, _ = match_markets([cl], [pm])
        assert len(matches) == 1

    def test_no_consensus_no_match(self):
        pm = _make_pm()
        matches, unmatched = match_markets([], [pm])
        assert len(matches) == 0
        assert len(unmatched) == 1
