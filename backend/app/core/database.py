"""SQLite persistence for snapshot history."""

from __future__ import annotations

import json
import aiosqlite
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.models.schemas import Opportunity


_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    league TEXT,
    commence_time TEXT,
    home_team TEXT,
    away_team TEXT,
    matched_side TEXT,
    consensus_prob REAL,
    median_prob REAL,
    market_source TEXT,
    market_price REAL,
    edge REAL,
    ev_proxy REAL,
    num_books INTEGER,
    confidence REAL,
    bookmaker_details TEXT,
    market_bid REAL,
    market_ask REAL,
    market_mid REAL,
    snapshot_time TEXT
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    num_sportsbook_events INTEGER,
    num_polymarket_markets INTEGER,
    num_kalshi_markets INTEGER,
    num_matches INTEGER,
    num_opportunities INTEGER,
    errors TEXT
);
"""


async def get_db() -> aiosqlite.Connection:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.DB_PATH)
    await db.executescript(_CREATE_TABLES)
    return db


async def save_opportunities(opps: list[Opportunity]) -> None:
    db = await get_db()
    try:
        now = datetime.utcnow().isoformat()
        for opp in opps:
            await db.execute(
                """INSERT OR REPLACE INTO opportunities
                   (id, league, commence_time, home_team, away_team,
                    matched_side, consensus_prob, median_prob,
                    market_source, market_price, edge, ev_proxy,
                    num_books, confidence, bookmaker_details,
                    market_bid, market_ask, market_mid, snapshot_time)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    opp.id,
                    opp.league,
                    opp.commence_time.isoformat(),
                    opp.home_team,
                    opp.away_team,
                    opp.matched_side,
                    opp.consensus_prob,
                    opp.median_prob,
                    opp.market_source.value,
                    opp.market_price,
                    opp.edge,
                    opp.ev_proxy,
                    opp.num_books,
                    opp.confidence,
                    json.dumps([b.model_dump() for b in opp.bookmaker_details]),
                    opp.market_bid,
                    opp.market_ask,
                    opp.market_mid,
                    now,
                ),
            )
        await db.commit()
    finally:
        await db.close()


async def save_scan_log(
    num_sportsbook: int,
    num_poly: int,
    num_kalshi: int,
    num_matches: int,
    num_opps: int,
    errors: list[str],
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO scan_log
               (timestamp, num_sportsbook_events, num_polymarket_markets,
                num_kalshi_markets, num_matches, num_opportunities, errors)
               VALUES (?,?,?,?,?,?,?)""",
            (
                datetime.utcnow().isoformat(),
                num_sportsbook,
                num_poly,
                num_kalshi,
                num_matches,
                num_opps,
                json.dumps(errors),
            ),
        )
        await db.commit()
    finally:
        await db.close()
