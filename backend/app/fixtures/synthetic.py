"""Synthetic fixture data for running when no API keys are configured.

These fixtures exercise the full pipeline: parsing, de-vig, consensus,
matching, and edge computation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import (
    BookmakerOdds,
    BookmakerOutcome,
    MarketSource,
    PredictionMarket,
    SportsEvent,
)


def synthetic_sportsbook_events() -> list[SportsEvent]:
    """Return realistic synthetic sportsbook events."""
    return [
        SportsEvent(
            event_id="synth_nba_001",
            sport_key="basketball_nba",
            sport_title="NBA",
            league="NBA",
            home_team="Los Angeles Lakers",
            away_team="Boston Celtics",
            commence_time=datetime(2025, 2, 10, 0, 30, tzinfo=timezone.utc),
            bookmakers=[
                BookmakerOdds(
                    bookmaker="fanduel",
                    home=BookmakerOutcome(name="Los Angeles Lakers", price=1.87),
                    away=BookmakerOutcome(name="Boston Celtics", price=1.95),
                ),
                BookmakerOdds(
                    bookmaker="draftkings",
                    home=BookmakerOutcome(name="Los Angeles Lakers", price=1.83),
                    away=BookmakerOutcome(name="Boston Celtics", price=2.00),
                ),
                BookmakerOdds(
                    bookmaker="betmgm",
                    home=BookmakerOutcome(name="Los Angeles Lakers", price=1.85),
                    away=BookmakerOutcome(name="Boston Celtics", price=1.97),
                ),
                BookmakerOdds(
                    bookmaker="caesars",
                    home=BookmakerOutcome(name="Los Angeles Lakers", price=1.89),
                    away=BookmakerOutcome(name="Boston Celtics", price=1.93),
                ),
            ],
        ),
        SportsEvent(
            event_id="synth_nfl_001",
            sport_key="americanfootball_nfl",
            sport_title="NFL",
            league="NFL",
            home_team="Kansas City Chiefs",
            away_team="Philadelphia Eagles",
            commence_time=datetime(2025, 2, 9, 23, 30, tzinfo=timezone.utc),
            bookmakers=[
                BookmakerOdds(
                    bookmaker="fanduel",
                    home=BookmakerOutcome(name="Kansas City Chiefs", price=1.55),
                    away=BookmakerOutcome(name="Philadelphia Eagles", price=2.50),
                ),
                BookmakerOdds(
                    bookmaker="draftkings",
                    home=BookmakerOutcome(name="Kansas City Chiefs", price=1.57),
                    away=BookmakerOutcome(name="Philadelphia Eagles", price=2.45),
                ),
                BookmakerOdds(
                    bookmaker="betmgm",
                    home=BookmakerOutcome(name="Kansas City Chiefs", price=1.53),
                    away=BookmakerOutcome(name="Philadelphia Eagles", price=2.55),
                ),
            ],
        ),
        SportsEvent(
            event_id="synth_mlb_001",
            sport_key="baseball_mlb",
            sport_title="MLB",
            league="MLB",
            home_team="New York Yankees",
            away_team="Houston Astros",
            commence_time=datetime(2025, 4, 15, 23, 5, tzinfo=timezone.utc),
            bookmakers=[
                BookmakerOdds(
                    bookmaker="fanduel",
                    home=BookmakerOutcome(name="New York Yankees", price=1.72),
                    away=BookmakerOutcome(name="Houston Astros", price=2.14),
                ),
                BookmakerOdds(
                    bookmaker="draftkings",
                    home=BookmakerOutcome(name="New York Yankees", price=1.70),
                    away=BookmakerOutcome(name="Houston Astros", price=2.18),
                ),
            ],
        ),
        SportsEvent(
            event_id="synth_nhl_001",
            sport_key="icehockey_nhl",
            sport_title="NHL",
            league="NHL",
            home_team="Edmonton Oilers",
            away_team="Florida Panthers",
            commence_time=datetime(2025, 3, 5, 1, 0, tzinfo=timezone.utc),
            bookmakers=[
                BookmakerOdds(
                    bookmaker="fanduel",
                    home=BookmakerOutcome(name="Edmonton Oilers", price=2.05),
                    away=BookmakerOutcome(name="Florida Panthers", price=1.80),
                ),
                BookmakerOdds(
                    bookmaker="betmgm",
                    home=BookmakerOutcome(name="Edmonton Oilers", price=2.10),
                    away=BookmakerOutcome(name="Florida Panthers", price=1.77),
                ),
            ],
        ),
    ]


def synthetic_polymarket_markets() -> list[PredictionMarket]:
    """Return synthetic Polymarket listings that partially match the sportsbook events."""
    return [
        PredictionMarket(
            source=MarketSource.POLYMARKET,
            market_id="poly_synth_001",
            event_title="Lakers vs Celtics – NBA",
            outcome="Los Angeles Lakers",
            yes_price=0.50,
            bid=0.49,
            ask=0.51,
            mid=0.50,
            league="NBA",
            start_time=datetime(2025, 2, 10, 0, 30, tzinfo=timezone.utc),
        ),
        PredictionMarket(
            source=MarketSource.POLYMARKET,
            market_id="poly_synth_002",
            event_title="Chiefs vs Eagles – Super Bowl",
            outcome="Kansas City Chiefs",
            yes_price=0.58,
            bid=0.57,
            ask=0.60,
            mid=0.585,
            league="NFL",
            start_time=datetime(2025, 2, 9, 23, 30, tzinfo=timezone.utc),
        ),
        PredictionMarket(
            source=MarketSource.POLYMARKET,
            market_id="poly_synth_003",
            event_title="Will the Oilers win the Stanley Cup?",
            outcome="Edmonton Oilers",
            yes_price=0.42,
            bid=0.40,
            ask=0.44,
            mid=0.42,
            league="NHL",
            start_time=datetime(2025, 3, 5, 1, 0, tzinfo=timezone.utc),
        ),
    ]


def synthetic_kalshi_markets() -> list[PredictionMarket]:
    """Return synthetic Kalshi listings."""
    return [
        PredictionMarket(
            source=MarketSource.KALSHI,
            market_id="kalshi_synth_001",
            event_title="NBA: Lakers vs Celtics",
            outcome="LA Lakers",
            yes_price=0.48,
            bid=0.47,
            ask=0.50,
            mid=0.485,
            league="NBA",
            start_time=datetime(2025, 2, 10, 0, 30, tzinfo=timezone.utc),
        ),
        PredictionMarket(
            source=MarketSource.KALSHI,
            market_id="kalshi_synth_002",
            event_title="NFL Championship: KC Chiefs vs Philly Eagles",
            outcome="KC Chiefs",
            yes_price=0.60,
            bid=0.59,
            ask=0.62,
            mid=0.605,
            league="NFL",
            start_time=datetime(2025, 2, 9, 23, 30, tzinfo=timezone.utc),
        ),
        PredictionMarket(
            source=MarketSource.KALSHI,
            market_id="kalshi_synth_003",
            event_title="Yankees vs Astros – MLB Winner",
            outcome="New York Yankees",
            yes_price=0.53,
            bid=0.52,
            ask=0.55,
            mid=0.535,
            league="MLB",
            start_time=datetime(2025, 4, 15, 23, 5, tzinfo=timezone.utc),
        ),
    ]
