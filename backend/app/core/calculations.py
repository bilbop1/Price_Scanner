"""Core math: odds conversion, de-vig, consensus, edge."""

from __future__ import annotations

import hashlib
import statistics
from datetime import datetime

from app.core.config import settings
from app.models.schemas import (
    BookmakerOdds,
    ConsensusLine,
    DeViggedBook,
    MatchResult,
    Opportunity,
    SportsEvent,
)


# ── Odds → implied probability ──────────────────────────────────

def decimal_to_implied(decimal_odds: float) -> float:
    """Convert decimal odds to raw implied probability."""
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


# ── De-vig (two-outcome normalization) ───────────────────────────

def devig_two_outcome(p1_raw: float, p2_raw: float) -> tuple[float, float]:
    """Remove vig from a two-outcome market.

    p1 = p1_raw / (p1_raw + p2_raw)
    p2 = p2_raw / (p1_raw + p2_raw)
    """
    total = p1_raw + p2_raw
    if total == 0:
        return 0.5, 0.5
    return p1_raw / total, p2_raw / total


def devig_bookmaker(bm: BookmakerOdds) -> DeViggedBook:
    """De-vig a single bookmaker's odds."""
    p_home_raw = decimal_to_implied(bm.home.price)
    p_away_raw = decimal_to_implied(bm.away.price)
    p_home, p_away = devig_two_outcome(p_home_raw, p_away_raw)
    return DeViggedBook(bookmaker=bm.bookmaker, home_prob=p_home, away_prob=p_away)


# ── Consensus ────────────────────────────────────────────────────

def compute_consensus(event: SportsEvent) -> ConsensusLine | None:
    """Compute consensus probabilities across all bookmakers for an event."""
    if not event.bookmakers:
        return None

    books: list[DeViggedBook] = []
    for bm in event.bookmakers:
        books.append(devig_bookmaker(bm))

    home_probs = [b.home_prob for b in books]
    away_probs = [b.away_prob for b in books]

    return ConsensusLine(
        event_id=event.event_id,
        home_team=event.home_team,
        away_team=event.away_team,
        league=event.league or event.sport_title,
        commence_time=event.commence_time,
        books=books,
        consensus_home=statistics.mean(home_probs),
        consensus_away=statistics.mean(away_probs),
        median_home=statistics.median(home_probs),
        median_away=statistics.median(away_probs),
        num_books=len(books),
    )


# ── Edge calculation ─────────────────────────────────────────────

def compute_edge(
    consensus_prob: float,
    market_price: float,
    fee_buffer: float | None = None,
) -> tuple[float, float]:
    """Return (edge, ev_proxy).

    edge = consensus_prob − market_price
    ev_proxy = edge − fee_buffer
    """
    if fee_buffer is None:
        fee_buffer = settings.FEE_BUFFER
    edge = consensus_prob - market_price
    ev_proxy = edge - fee_buffer
    return round(edge, 6), round(ev_proxy, 6)


# ── Build opportunity from match ─────────────────────────────────

def build_opportunity(match: MatchResult) -> Opportunity:
    """Create an Opportunity from a MatchResult."""
    c = match.consensus
    pm = match.prediction_market

    if match.matched_side == "home":
        consensus_prob = c.consensus_home
        median_prob = c.median_home
    else:
        consensus_prob = c.consensus_away
        median_prob = c.median_away

    market_price = pm.mid if pm.mid is not None else pm.yes_price
    edge, ev_proxy = compute_edge(consensus_prob, market_price)

    opp_id = hashlib.md5(
        f"{c.event_id}:{pm.source.value}:{pm.market_id}:{match.matched_side}".encode()
    ).hexdigest()[:12]

    return Opportunity(
        id=opp_id,
        league=c.league,
        commence_time=c.commence_time,
        home_team=c.home_team,
        away_team=c.away_team,
        matched_side=match.matched_side,
        consensus_prob=round(consensus_prob, 4),
        median_prob=round(median_prob, 4),
        market_source=pm.source,
        market_price=round(market_price, 4),
        edge=edge,
        ev_proxy=ev_proxy,
        num_books=c.num_books,
        confidence=match.confidence,
        bookmaker_details=c.books,
        market_bid=pm.bid,
        market_ask=pm.ask,
        market_mid=pm.mid,
        timestamp=datetime.utcnow(),
    )
