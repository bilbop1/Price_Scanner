"""Unit tests for the Telegram notification module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.core.telegram import (
    _track_notified,
    _notified_ids,
    clear_notified_cache,
    send_opportunity_alert,
    send_value_bet_alert,
    send_arbitrage_alert,
)
from app.models.schemas import (
    ArbitrageBet,
    ArbitrageLeg,
    MarketSource,
    Opportunity,
    ValueBet,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear notified cache before each test."""
    clear_notified_cache()
    yield
    clear_notified_cache()


class TestTrackNotified:
    def test_adds_id(self):
        _track_notified("test1")
        assert "test1" in _notified_ids

    def test_evicts_when_full(self):
        # Fill up the cache
        for i in range(6000):
            _track_notified(f"item_{i}")
        # Should have evicted some
        assert len(_notified_ids) <= 5001

    def test_clear_cache(self):
        _track_notified("test1")
        _track_notified("test2")
        clear_notified_cache()
        assert len(_notified_ids) == 0


class TestSendOpportunityAlert:
    def _make_opp(self, edge: float = 0.10, opp_id: str = "opp1") -> Opportunity:
        return Opportunity(
            id=opp_id,
            league="NBA",
            commence_time=datetime(2025, 2, 10, 20, 0, tzinfo=timezone.utc),
            home_team="Los Angeles Lakers",
            away_team="Boston Celtics",
            matched_side="home",
            consensus_prob=0.60,
            median_prob=0.61,
            market_source=MarketSource.POLYMARKET,
            market_price=0.50,
            edge=edge,
            ev_proxy=edge - 0.03,
            num_books=5,
            confidence=98.0,
            market_bid=0.49,
            market_ask=0.51,
            market_mid=0.50,
        )

    @pytest.mark.asyncio
    async def test_skips_when_telegram_disabled(self):
        with patch("app.core.telegram.settings") as mock_settings:
            mock_settings.has_telegram = False
            result = await send_opportunity_alert(self._make_opp())
            assert result is False

    @pytest.mark.asyncio
    async def test_skips_below_threshold(self):
        with patch("app.core.telegram.settings") as mock_settings:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            result = await send_opportunity_alert(self._make_opp(edge=0.05))
            assert result is False

    @pytest.mark.asyncio
    async def test_skips_duplicate(self):
        _track_notified("opp1")
        with patch("app.core.telegram.settings") as mock_settings:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            result = await send_opportunity_alert(self._make_opp(edge=0.10))
            assert result is False

    @pytest.mark.asyncio
    async def test_sends_when_above_threshold(self):
        with patch("app.core.telegram.settings") as mock_settings, \
             patch("app.core.telegram._send_message", new_callable=AsyncMock) as mock_send:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            mock_send.return_value = True

            result = await send_opportunity_alert(self._make_opp(edge=0.10, opp_id="new_opp"))
            assert result is True
            mock_send.assert_called_once()

            # Verify message content
            msg = mock_send.call_args[0][0]
            assert "HIGH EDGE ALERT" in msg
            assert "NBA" in msg
            assert "Lakers" in msg
            assert "10.0%" in msg

    @pytest.mark.asyncio
    async def test_tracks_notified_after_send(self):
        with patch("app.core.telegram.settings") as mock_settings, \
             patch("app.core.telegram._send_message", new_callable=AsyncMock) as mock_send:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            mock_send.return_value = True

            await send_opportunity_alert(self._make_opp(edge=0.10, opp_id="tracked_opp"))
            assert "tracked_opp" in _notified_ids


class TestSendValueBetAlert:
    def _make_vb(self, ev: float = 0.10, vb_id: str = "vb1") -> ValueBet:
        return ValueBet(
            id=vb_id,
            event_id="ev1",
            bookmaker="Bet365",
            market="ML",
            bet_side="home",
            expected_value=ev,
            bookmaker_odds=2.15,
            home_team="Team A",
            away_team="Team B",
            league="NBA",
            commence_time=datetime(2025, 2, 10, 20, 0, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_skips_below_threshold(self):
        with patch("app.core.telegram.settings") as mock_settings:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            result = await send_value_bet_alert(self._make_vb(ev=0.03))
            assert result is False

    @pytest.mark.asyncio
    async def test_sends_above_threshold(self):
        with patch("app.core.telegram.settings") as mock_settings, \
             patch("app.core.telegram._send_message", new_callable=AsyncMock) as mock_send:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            mock_send.return_value = True

            result = await send_value_bet_alert(self._make_vb(ev=0.10, vb_id="new_vb"))
            assert result is True
            msg = mock_send.call_args[0][0]
            assert "VALUE BET FOUND" in msg
            assert "Bet365" in msg

    @pytest.mark.asyncio
    async def test_skips_duplicate(self):
        _track_notified("vb_vb1")
        with patch("app.core.telegram.settings") as mock_settings:
            mock_settings.has_telegram = True
            mock_settings.TELEGRAM_ALERT_EDGE = 0.07
            result = await send_value_bet_alert(self._make_vb(ev=0.10))
            assert result is False


class TestSendArbitrageAlert:
    def _make_arb(self, arb_id: str = "arb1") -> ArbitrageBet:
        return ArbitrageBet(
            id=arb_id,
            event_id="ev1",
            market="ML",
            profit_margin=0.02,
            implied_probability=0.98,
            total_stake=100,
            legs=[
                ArbitrageLeg(bookmaker="Bet365", bet_side="home", odds=2.10),
                ArbitrageLeg(bookmaker="Unibet", bet_side="away", odds=2.05),
            ],
            optimal_stakes=[52.0, 48.0],
            home_team="Team A",
            away_team="Team B",
            league="NFL",
            commence_time=datetime(2025, 1, 20, 18, 0, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_sends_arb_alert(self):
        with patch("app.core.telegram.settings") as mock_settings, \
             patch("app.core.telegram._send_message", new_callable=AsyncMock) as mock_send:
            mock_settings.has_telegram = True
            mock_send.return_value = True

            result = await send_arbitrage_alert(self._make_arb(arb_id="new_arb"))
            assert result is True
            msg = mock_send.call_args[0][0]
            assert "ARBITRAGE OPPORTUNITY" in msg
            assert "Bet365" in msg
            assert "2.00%" in msg

    @pytest.mark.asyncio
    async def test_skips_duplicate_arb(self):
        _track_notified("arb_arb1")
        with patch("app.core.telegram.settings") as mock_settings:
            mock_settings.has_telegram = True
            result = await send_arbitrage_alert(self._make_arb())
            assert result is False
