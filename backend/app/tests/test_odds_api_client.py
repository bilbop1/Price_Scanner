"""Unit tests for the odds-api.io client parsing and mapping logic."""

import pytest
from datetime import datetime, timezone

from app.clients.odds_api import (
    LEAGUE_DISPLAY,
    LEAGUE_TO_SPORT_KEY,
    SPORT_DISPLAY,
    _build_odds_map,
    _parse_bookmaker_odds,
    _parse_event,
    _parse_value_bet,
    _parse_arbitrage_bet,
    _safe_decimal,
    _sport_slug_matches,
)
from app.models.schemas import ArbitrageLeg


class TestSafeDecimal:
    def test_float_value(self):
        assert _safe_decimal(2.10) == 2.10

    def test_string_decimal(self):
        assert _safe_decimal("1.85") == 1.85

    def test_int_value(self):
        assert _safe_decimal(3) == 3.0

    def test_none(self):
        assert _safe_decimal(None) is None

    def test_invalid_string(self):
        assert _safe_decimal("abc") is None

    def test_empty_string(self):
        assert _safe_decimal("") is None


class TestSportSlugMatches:
    def test_american_football_nfl(self):
        assert _sport_slug_matches("americanfootball_nfl", "american-football")

    def test_american_football_ncaaf(self):
        assert _sport_slug_matches("americanfootball_ncaaf", "american-football")

    def test_basketball_nba(self):
        assert _sport_slug_matches("basketball_nba", "basketball")

    def test_basketball_ncaab(self):
        assert _sport_slug_matches("basketball_ncaab", "basketball")

    def test_baseball_mlb(self):
        assert _sport_slug_matches("baseball_mlb", "baseball")

    def test_ice_hockey_nhl(self):
        assert _sport_slug_matches("icehockey_nhl", "ice-hockey")

    def test_soccer_mls(self):
        assert _sport_slug_matches("soccer_usa_mls", "football")

    def test_mismatch(self):
        assert not _sport_slug_matches("basketball_nba", "american-football")

    def test_unknown_slug(self):
        assert not _sport_slug_matches("basketball_nba", "cricket")


class TestLeagueMappings:
    def test_league_display_nfl(self):
        assert LEAGUE_DISPLAY["NFL"] == "NFL"

    def test_league_display_ncaa_football(self):
        assert LEAGUE_DISPLAY["NCAA Football"] == "NCAAF"

    def test_league_to_sport_key(self):
        assert LEAGUE_TO_SPORT_KEY["NBA"] == "basketball_nba"
        assert LEAGUE_TO_SPORT_KEY["NHL"] == "icehockey_nhl"

    def test_sport_display(self):
        assert SPORT_DISPLAY["americanfootball_nfl"] == "NFL"
        assert SPORT_DISPLAY["basketball_nba"] == "NBA"


class TestBuildOddsMap:
    def test_dict_response(self):
        data = {
            "12345": {"bookmakers": {"Bet365": {"markets": []}}},
            "67890": {"bookmakers": {"Unibet": {"markets": []}}},
        }
        result = _build_odds_map(data)
        assert "12345" in result
        assert "67890" in result

    def test_list_response(self):
        data = [
            {"id": "12345", "bookmakers": {"Bet365": {"markets": []}}},
            {"id": "67890", "bookmakers": {"Unibet": {"markets": []}}},
        ]
        result = _build_odds_map(data)
        assert "12345" in result
        assert "67890" in result

    def test_empty_dict(self):
        assert _build_odds_map({}) == {}

    def test_empty_list(self):
        assert _build_odds_map([]) == {}

    def test_list_item_without_id(self):
        data = [{"bookmakers": {}}]
        result = _build_odds_map(data)
        assert len(result) == 0

    def test_dict_with_non_dict_value(self):
        data = {"12345": "not_a_dict"}
        result = _build_odds_map(data)
        assert len(result) == 0


class TestParseBookmakerOdds:
    def test_valid_ml_market(self):
        bm_info = {
            "markets": [
                {
                    "name": "ML",
                    "updatedAt": "2025-01-15T10:30:00Z",
                    "odds": [{"home": "1.85", "away": "2.10"}],
                }
            ]
        }
        result = _parse_bookmaker_odds("Bet365", bm_info, "Team A", "Team B")
        assert result is not None
        assert result.bookmaker == "Bet365"
        assert result.home.price == 1.85
        assert result.away.price == 2.10
        assert result.home.name == "Team A"
        assert result.away.name == "Team B"

    def test_h2h_market_name(self):
        bm_info = {
            "markets": [
                {
                    "name": "H2H",
                    "odds": [{"home": "1.50", "away": "2.80"}],
                }
            ]
        }
        result = _parse_bookmaker_odds("FanDuel", bm_info, "Home", "Away")
        assert result is not None
        assert result.home.price == 1.50
        assert result.away.price == 2.80

    def test_match_result_market_name(self):
        bm_info = {
            "markets": [
                {
                    "name": "Match Result",
                    "odds": [{"home": "1.90", "away": "1.95"}],
                }
            ]
        }
        result = _parse_bookmaker_odds("DK", bm_info, "Home", "Away")
        assert result is not None

    def test_missing_markets(self):
        result = _parse_bookmaker_odds("Bet365", {}, "Home", "Away")
        assert result is None

    def test_empty_markets_list(self):
        result = _parse_bookmaker_odds("Bet365", {"markets": []}, "Home", "Away")
        assert result is None

    def test_missing_odds(self):
        bm_info = {"markets": [{"name": "ML", "odds": []}]}
        result = _parse_bookmaker_odds("Bet365", bm_info, "Home", "Away")
        assert result is None

    def test_invalid_price_below_one(self):
        bm_info = {
            "markets": [
                {"name": "ML", "odds": [{"home": "0.5", "away": "2.10"}]}
            ]
        }
        result = _parse_bookmaker_odds("Bet365", bm_info, "Home", "Away")
        assert result is None

    def test_fallback_to_first_market(self):
        bm_info = {
            "markets": [
                {
                    "name": "Spread",
                    "odds": [{"home": "1.85", "away": "2.10"}],
                }
            ]
        }
        result = _parse_bookmaker_odds("Bet365", bm_info, "Home", "Away")
        assert result is not None

    def test_last_update_parsed(self):
        bm_info = {
            "markets": [
                {
                    "name": "ML",
                    "updatedAt": "2025-06-15T10:30:00Z",
                    "odds": [{"home": "1.85", "away": "2.10"}],
                }
            ]
        }
        result = _parse_bookmaker_odds("Bet365", bm_info, "Home", "Away")
        assert result is not None
        assert result.last_update is not None


class TestParseEvent:
    def _sample_odds(self):
        return {
            "bookmakers": {
                "Bet365": {
                    "markets": [
                        {
                            "name": "ML",
                            "odds": [{"home": "1.85", "away": "2.10"}],
                        }
                    ]
                },
                "Unibet": {
                    "markets": [
                        {
                            "name": "ML",
                            "odds": [{"home": "1.90", "away": "2.05"}],
                        }
                    ]
                },
            }
        }

    def test_valid_event(self):
        raw = {
            "id": "12345",
            "home": "Los Angeles Lakers",
            "away": "Boston Celtics",
            "league": "NBA",
            "date": "2025-01-15T20:00:00Z",
        }
        result = _parse_event(raw, self._sample_odds(), "basketball")
        assert result is not None
        assert result.event_id == "12345"
        assert result.home_team == "Los Angeles Lakers"
        assert result.away_team == "Boston Celtics"
        assert result.league == "NBA"
        assert result.sport_key == "basketball_nba"
        assert len(result.bookmakers) == 2

    def test_missing_home_team(self):
        raw = {"id": "12345", "away": "Team B", "league": "NBA"}
        result = _parse_event(raw, self._sample_odds(), "basketball")
        assert result is None

    def test_missing_away_team(self):
        raw = {"id": "12345", "home": "Team A", "league": "NBA"}
        result = _parse_event(raw, self._sample_odds(), "basketball")
        assert result is None

    def test_unknown_league(self):
        raw = {
            "id": "12345",
            "home": "Team A",
            "away": "Team B",
            "league": "SuperLeague",
            "date": "2025-01-15T20:00:00Z",
        }
        result = _parse_event(raw, self._sample_odds(), "basketball")
        assert result is not None
        assert result.league == "SuperLeague"

    def test_bookmakers_as_list(self):
        raw = {
            "id": "12345",
            "home": "Team A",
            "away": "Team B",
            "league": "NBA",
            "date": "2025-01-15T20:00:00Z",
        }
        odds = {
            "bookmakers": [
                {
                    "key": "bet365",
                    "markets": [
                        {"name": "ML", "odds": [{"home": "1.85", "away": "2.10"}]}
                    ],
                }
            ]
        }
        result = _parse_event(raw, odds, "basketball")
        assert result is not None
        assert len(result.bookmakers) == 1

    def test_no_bookmakers_still_returns_event(self):
        raw = {
            "id": "12345",
            "home": "Team A",
            "away": "Team B",
            "league": "NBA",
            "date": "2025-01-15T20:00:00Z",
        }
        result = _parse_event(raw, {"bookmakers": {}}, "basketball")
        assert result is not None
        assert len(result.bookmakers) == 0


class TestParseValueBet:
    def test_valid_value_bet(self):
        raw = {
            "id": "vb123",
            "eventId": "ev456",
            "bookmaker": "Bet365",
            "market": "ML",
            "betSide": "home",
            "expectedValue": 0.08,
            "bookmakerOdds": "2.15",
            "event": {
                "home": "Team A",
                "away": "Team B",
                "league": "NBA",
                "sport": "basketball",
                "date": "2025-01-15T20:00:00Z",
            },
        }
        result = _parse_value_bet(raw)
        assert result is not None
        assert result.id == "vb123"
        assert result.bookmaker == "Bet365"
        assert result.expected_value == 0.08
        assert result.bookmaker_odds == 2.15
        assert result.home_team == "Team A"
        assert result.league == "NBA"

    def test_missing_event(self):
        raw = {
            "id": "vb123",
            "eventId": "ev456",
            "bookmaker": "Bet365",
            "market": "ML",
            "betSide": "home",
            "expectedValue": 0.08,
            "bookmakerOdds": "2.15",
        }
        result = _parse_value_bet(raw)
        assert result is not None
        assert result.home_team == ""

    def test_invalid_data(self):
        result = _parse_value_bet({"invalid": "data"})
        # Should return None or a ValueBet with defaults
        # depending on what fields are required


class TestParseArbitrageBet:
    def test_valid_arb_bet(self):
        raw = {
            "id": "arb123",
            "eventId": "ev456",
            "market": "ML",
            "profitMargin": 0.025,
            "impliedProbability": 0.975,
            "totalStake": 100,
            "legs": [
                {"bookmaker": "Bet365", "betSide": "home", "odds": "2.10"},
                {"bookmaker": "Unibet", "betSide": "away", "odds": "2.05"},
            ],
            "optimalStakes": [51.2, 48.8],
            "event": {
                "home": "Team A",
                "away": "Team B",
                "league": "NFL",
                "sport": "american-football",
                "date": "2025-01-20T18:00:00Z",
            },
        }
        result = _parse_arbitrage_bet(raw)
        assert result is not None
        assert result.id == "arb123"
        assert result.profit_margin == 0.025
        assert len(result.legs) == 2
        assert result.legs[0].bookmaker == "Bet365"
        assert result.legs[1].odds == 2.05
        assert result.optimal_stakes == [51.2, 48.8]
        assert result.home_team == "Team A"

    def test_empty_legs(self):
        raw = {
            "id": "arb1",
            "eventId": "ev1",
            "market": "ML",
            "profitMargin": 0.01,
            "impliedProbability": 0.99,
            "totalStake": 100,
            "legs": [],
            "optimalStakes": [],
            "event": {},
        }
        result = _parse_arbitrage_bet(raw)
        assert result is not None
        assert len(result.legs) == 0
