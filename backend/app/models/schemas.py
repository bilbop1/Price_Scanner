"""Pydantic schemas for the entire data pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MarketSource(str, Enum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


# ── Sportsbook layer ──────────────────────────────────────────────

class BookmakerOutcome(BaseModel):
    name: str
    price: float  # decimal odds


class BookmakerOdds(BaseModel):
    bookmaker: str
    home: BookmakerOutcome
    away: BookmakerOutcome
    last_update: Optional[datetime] = None


class SportsEvent(BaseModel):
    event_id: str
    sport_key: str
    sport_title: str
    league: str = ""
    home_team: str
    away_team: str
    commence_time: datetime
    bookmakers: list[BookmakerOdds] = Field(default_factory=list)


# ── De-vigged probabilities ──────────────────────────────────────

class DeViggedBook(BaseModel):
    bookmaker: str
    home_prob: float
    away_prob: float


class ConsensusLine(BaseModel):
    event_id: str
    home_team: str
    away_team: str
    league: str
    commence_time: datetime
    books: list[DeViggedBook]
    consensus_home: float
    consensus_away: float
    median_home: float
    median_away: float
    num_books: int


# ── Prediction-market layer ──────────────────────────────────────

class PredictionMarket(BaseModel):
    source: MarketSource
    market_id: str
    event_title: str
    outcome: str  # team / side name
    yes_price: float  # implied probability
    no_price: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    last_trade: Optional[float] = None
    volume: Optional[float] = None
    league: str = ""
    start_time: Optional[datetime] = None
    raw_tags: list[str] = Field(default_factory=list)


# ── Matching ─────────────────────────────────────────────────────

class MatchResult(BaseModel):
    consensus: ConsensusLine
    prediction_market: PredictionMarket
    matched_side: str  # "home" or "away"
    confidence: float  # 0-100


# ── Edge / Opportunity ───────────────────────────────────────────

class Opportunity(BaseModel):
    id: str = ""
    league: str
    commence_time: datetime
    home_team: str
    away_team: str
    matched_side: str
    consensus_prob: float
    median_prob: float
    market_source: MarketSource
    market_price: float
    edge: float
    ev_proxy: float
    num_books: int
    confidence: float
    bookmaker_details: list[DeViggedBook] = Field(default_factory=list)
    market_bid: Optional[float] = None
    market_ask: Optional[float] = None
    market_mid: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Health / self-test ───────────────────────────────────────────

class SubsystemStatus(BaseModel):
    name: str
    ok: bool
    message: str = ""


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "error"
    subsystems: list[SubsystemStatus]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
