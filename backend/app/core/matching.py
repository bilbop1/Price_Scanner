"""Matching engine: maps sportsbook consensus lines to prediction-market listings."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz

from app.core.config import settings
from app.models.schemas import ConsensusLine, MatchResult, PredictionMarket

logger = logging.getLogger(__name__)

# ── Team-name normalization ──────────────────────────────────────

# Common aliases / abbreviations → canonical form
_ALIASES: dict[str, str] = {
    # NFL
    "kc chiefs": "kansas city chiefs",
    "kc": "kansas city chiefs",
    "la rams": "los angeles rams",
    "la chargers": "los angeles chargers",
    "lv raiders": "las vegas raiders",
    "ne patriots": "new england patriots",
    "ny giants": "new york giants",
    "ny jets": "new york jets",
    "sf 49ers": "san francisco 49ers",
    "sf": "san francisco 49ers",
    "tb buccaneers": "tampa bay buccaneers",
    "tb bucs": "tampa bay buccaneers",
    "jax jaguars": "jacksonville jaguars",
    "gb packers": "green bay packers",
    # NBA
    "la lakers": "los angeles lakers",
    "la clippers": "los angeles clippers",
    "gs warriors": "golden state warriors",
    "gsw": "golden state warriors",
    "okc thunder": "oklahoma city thunder",
    "okc": "oklahoma city thunder",
    "ny knicks": "new york knicks",
    "sa spurs": "san antonio spurs",
    # MLB
    "ny yankees": "new york yankees",
    "ny mets": "new york mets",
    "la dodgers": "los angeles dodgers",
    "la angels": "los angeles angels",
    "sf giants": "san francisco giants",
    "tb rays": "tampa bay rays",
    "chi cubs": "chicago cubs",
    "chi white sox": "chicago white sox",
    "stl cardinals": "st. louis cardinals",
    # NHL
    "la kings": "los angeles kings",
    "nj devils": "new jersey devils",
    "ny rangers": "new york rangers",
    "ny islanders": "new york islanders",
    "tb lightning": "tampa bay lightning",
    "sj sharks": "san jose sharks",
}

_STRIP_PATTERNS = [
    r"\bfc\b",
    r"\bsc\b",
    r"\bunited\b",
    r"\bcity\b",
    r"\bwin\b",
    r"\bto win\b",
    r"\bvs\.?\b",
    r"\bv\b",
    r"\bover\b",
    r"\bunder\b",
    r"\bmoneyline\b",
    r"\bml\b",
    r"\bwill\b",
    r"\?",
]


def normalize_team(name: str) -> str:
    """Normalize a team name to a canonical lowercase form."""
    s = name.strip().lower()
    # Check alias table
    if s in _ALIASES:
        return _ALIASES[s]
    for alias, canonical in _ALIASES.items():
        if alias in s:
            return canonical
    # Strip noise
    for pat in _STRIP_PATTERNS:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_team_names(text: str) -> list[str]:
    """Try to pull team names from a prediction market title like
    'Lakers vs Celtics' or 'Will the Lakers win?'
    """
    text = text.strip()
    # "Team A vs Team B"
    for sep in [" vs ", " vs. ", " v ", " v. ", " - "]:
        if sep in text.lower():
            parts = re.split(re.escape(sep), text, flags=re.IGNORECASE)
            return [normalize_team(p) for p in parts[:2]]
    # Single team mention – return as-is
    return [normalize_team(text)]


# ── League matching ──────────────────────────────────────────────

_LEAGUE_COMPAT: dict[str, set[str]] = {
    "NFL": {"NFL", "NCAAF", ""},
    "NCAAF": {"NCAAF", "NFL", ""},
    "NBA": {"NBA", "NCAAB", ""},
    "NCAAB": {"NCAAB", "NBA", ""},
    "MLB": {"MLB", ""},
    "NHL": {"NHL", ""},
    "MLS": {"MLS", ""},
}


def _leagues_compatible(league1: str, league2: str) -> bool:
    if not league1 or not league2:
        return True  # unknown league = compatible
    compat = _LEAGUE_COMPAT.get(league1.upper(), {league1.upper(), ""})
    return league2.upper() in compat


# ── Time matching ────────────────────────────────────────────────

def _times_close(t1: datetime | None, t2: datetime | None, hours: int = 6) -> bool:
    if t1 is None or t2 is None:
        return True  # unknown time = allow match
    # Ensure both are timezone-aware for comparison
    if t1.tzinfo is None:
        t1 = t1.replace(tzinfo=timezone.utc)
    if t2.tzinfo is None:
        t2 = t2.replace(tzinfo=timezone.utc)
    return abs(t1 - t2) <= timedelta(hours=hours)


# ── Core matching logic ─────────────────────────────────────────

def match_markets(
    consensus_lines: list[ConsensusLine],
    prediction_markets: list[PredictionMarket],
) -> tuple[list[MatchResult], list[PredictionMarket]]:
    """Match consensus lines to prediction markets.

    Returns (matches, unmatched_markets).
    """
    matches: list[MatchResult] = []
    unmatched: list[PredictionMarket] = []
    matched_market_ids: set[str] = set()

    for pm in prediction_markets:
        best_match: MatchResult | None = None
        best_score: float = 0

        pm_teams = _extract_team_names(pm.outcome)
        if not pm_teams:
            pm_teams = _extract_team_names(pm.event_title)

        for cl in consensus_lines:
            # League filter
            if not _leagues_compatible(cl.league, pm.league):
                continue

            # Time filter
            if not _times_close(cl.commence_time, pm.start_time):
                continue

            # Try matching each extracted team to home/away
            home_norm = normalize_team(cl.home_team)
            away_norm = normalize_team(cl.away_team)

            for pm_team in pm_teams:
                # Exact match
                side, score = _score_team(pm_team, home_norm, away_norm)
                if score > best_score:
                    best_score = score
                    best_match = MatchResult(
                        consensus=cl,
                        prediction_market=pm,
                        matched_side=side,
                        confidence=score,
                    )

        threshold = settings.MATCH_CONFIDENCE_THRESHOLD
        if best_match and best_score >= threshold:
            matches.append(best_match)
            matched_market_ids.add(pm.market_id)
        else:
            unmatched.append(pm)

    return matches, unmatched


def _score_team(
    pm_team: str, home_norm: str, away_norm: str
) -> tuple[str, float]:
    """Score how well pm_team matches home or away.

    Returns (side, confidence_score).
    """
    # Exact
    if pm_team == home_norm:
        return "home", 100.0
    if pm_team == away_norm:
        return "away", 100.0

    # Substring containment
    if home_norm in pm_team or pm_team in home_norm:
        return "home", 97.0
    if away_norm in pm_team or pm_team in away_norm:
        return "away", 97.0

    # Fuzzy
    home_score = fuzz.token_sort_ratio(pm_team, home_norm)
    away_score = fuzz.token_sort_ratio(pm_team, away_norm)

    if home_score >= away_score:
        return "home", home_score
    return "away", away_score
