"""Telegram bot integration for real-time profitable edge alerts."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.core.config import settings
from app.models.schemas import ArbitrageBet, Opportunity, ValueBet

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

# Track already-notified opportunity IDs to avoid duplicate spam
_notified_ids: set[str] = set()
_MAX_NOTIFIED_CACHE = 5000  # prevent unbounded memory growth


async def send_opportunity_alert(opp: Opportunity) -> bool:
    """Send a Telegram alert for a high-edge opportunity.

    Returns True if message was sent successfully.
    """
    if not settings.has_telegram:
        return False

    if opp.id in _notified_ids:
        return False

    if abs(opp.edge) < settings.TELEGRAM_ALERT_EDGE:
        return False

    edge_pct = abs(opp.edge) * 100
    ev_pct = opp.ev_proxy * 100
    consensus_pct = opp.consensus_prob * 100
    market_pct = opp.market_price * 100

    direction = "BUY YES" if opp.edge > 0 else "BUY NO"
    time_str = opp.commence_time.strftime("%b %d, %Y %I:%M %p UTC")

    message = (
        f"HIGH EDGE ALERT\n"
        f"{'=' * 30}\n"
        f"\n"
        f"League: {opp.league}\n"
        f"Game: {opp.home_team} vs {opp.away_team}\n"
        f"Side: {opp.matched_side.upper()} — {direction}\n"
        f"\n"
        f"Edge: {edge_pct:.1f}%\n"
        f"EV Proxy: {ev_pct:+.1f}%\n"
        f"Consensus: {consensus_pct:.1f}%\n"
        f"Market Price: {market_pct:.1f}%\n"
        f"\n"
        f"Books: {opp.num_books} | Confidence: {opp.confidence:.0f}%\n"
        f"Source: {opp.market_source.value}\n"
        f"Game Time: {time_str}\n"
    )

    if opp.market_bid is not None and opp.market_ask is not None:
        message += f"Bid/Ask: {opp.market_bid:.3f} / {opp.market_ask:.3f}\n"

    success = await _send_message(message)
    if success:
        _track_notified(opp.id)
    return success


async def send_value_bet_alert(vb: ValueBet) -> bool:
    """Send a Telegram alert for a value bet from Odds-API.io."""
    if not settings.has_telegram:
        return False

    alert_id = f"vb_{vb.id}"
    if alert_id in _notified_ids:
        return False

    if vb.expected_value < settings.TELEGRAM_ALERT_EDGE:
        return False

    ev_pct = vb.expected_value * 100

    message = (
        f"VALUE BET FOUND\n"
        f"{'=' * 30}\n"
        f"\n"
        f"League: {vb.league}\n"
        f"Game: {vb.home_team} vs {vb.away_team}\n"
        f"Side: {vb.bet_side.upper()}\n"
        f"\n"
        f"Expected Value: {ev_pct:+.1f}%\n"
        f"Bookmaker: {vb.bookmaker}\n"
        f"Odds: {vb.bookmaker_odds:.2f}\n"
        f"Market: {vb.market}\n"
    )

    if vb.commence_time:
        message += f"Game Time: {vb.commence_time.strftime('%b %d, %Y %I:%M %p UTC')}\n"

    success = await _send_message(message)
    if success:
        _track_notified(alert_id)
    return success


async def send_arbitrage_alert(arb: ArbitrageBet) -> bool:
    """Send a Telegram alert for an arbitrage opportunity."""
    if not settings.has_telegram:
        return False

    alert_id = f"arb_{arb.id}"
    if alert_id in _notified_ids:
        return False

    # Alert on any arb opportunity (they're all profitable by definition)
    profit_pct = arb.profit_margin * 100

    legs_str = "\n".join(
        f"  {leg.bookmaker}: {leg.bet_side} @ {leg.odds:.2f}"
        for leg in arb.legs
    )

    message = (
        f"ARBITRAGE OPPORTUNITY\n"
        f"{'=' * 30}\n"
        f"\n"
        f"League: {arb.league}\n"
        f"Game: {arb.home_team} vs {arb.away_team}\n"
        f"\n"
        f"Profit Margin: {profit_pct:.2f}%\n"
        f"Market: {arb.market}\n"
        f"\n"
        f"Legs:\n{legs_str}\n"
    )

    if arb.optimal_stakes:
        stakes_str = " / ".join(f"${s:.2f}" for s in arb.optimal_stakes)
        message += f"Optimal Stakes: {stakes_str}\n"

    if arb.commence_time:
        message += f"Game Time: {arb.commence_time.strftime('%b %d, %Y %I:%M %p UTC')}\n"

    success = await _send_message(message)
    if success:
        _track_notified(alert_id)
    return success


async def send_scan_summary(
    num_opps: int,
    num_value_bets: int,
    num_arb_bets: int,
    top_edge: float | None = None,
) -> bool:
    """Send a periodic scan summary (optional, for monitoring)."""
    if not settings.has_telegram:
        return False

    message = (
        f"Scan Complete\n"
        f"{'=' * 30}\n"
        f"Opportunities: {num_opps}\n"
        f"Value Bets: {num_value_bets}\n"
        f"Arbitrage: {num_arb_bets}\n"
    )
    if top_edge is not None:
        message += f"Top Edge: {top_edge * 100:.1f}%\n"

    message += f"Time: {datetime.utcnow().strftime('%H:%M:%S UTC')}\n"

    return await _send_message(message)


async def _send_message(text: str) -> bool:
    """Send a message via Telegram Bot API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            if resp.status_code == 200:
                logger.info("Telegram alert sent successfully")
                return True
            else:
                logger.warning(
                    "Telegram send failed: HTTP %s – %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return False
    except Exception as e:
        logger.error("Telegram send error: %s", e)
        return False


def _track_notified(alert_id: str) -> None:
    """Track a notified alert ID, with cache eviction."""
    _notified_ids.add(alert_id)
    if len(_notified_ids) > _MAX_NOTIFIED_CACHE:
        # Evict oldest half
        to_remove = list(_notified_ids)[: _MAX_NOTIFIED_CACHE // 2]
        for item in to_remove:
            _notified_ids.discard(item)


def clear_notified_cache() -> None:
    """Clear the notified cache (useful for testing)."""
    _notified_ids.clear()
