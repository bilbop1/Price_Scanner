"""FastAPI application entry point.

Runs 24/7 with aggressive background polling.
Adaptive intervals: faster when live games are happening.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, set_selftest_results
from app.core.config import settings
from app.core.scanner import get_latest_scan, run_scan
from app.core.selftest import run_all_selftests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Edge Scanner",
    description=(
        "24/7 autonomous scanner comparing sportsbook consensus odds "
        "vs prediction market prices. Powered by Odds-API.io with "
        "Telegram alerts for high-edge opportunities."
    ),
    version="2.0.0",
)

# CORS – allow local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ── Startup ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("  Market Edge Scanner v2.0 – starting up")
    logger.info("  Mode: 24/7 Autonomous Scanning")
    logger.info("=" * 60)

    # 1) Run self-tests
    logger.info("Running startup self-tests...")
    results = run_all_selftests()
    set_selftest_results(results)

    passed = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)
    logger.info("Self-tests: %d passed, %d failed", passed, failed)
    if failed:
        for r in results:
            if not r.ok:
                logger.error("  FAIL: %s – %s", r.name, r.message)
    else:
        logger.info("  All self-tests passed")

    # 2) API key status
    if settings.has_odds_api_key:
        logger.info("Odds API key configured – fetching live data from odds-api.io")
    else:
        logger.info(
            "ODDS_API_KEY not set – running with synthetic data. "
            "Set the key in .env to enable live scanning."
        )

    # 3) Telegram status
    if settings.has_telegram:
        logger.info(
            "Telegram alerts ENABLED (edge threshold: %.0f%%)",
            settings.TELEGRAM_ALERT_EDGE * 100,
        )
    else:
        logger.info("Telegram alerts disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")

    # 4) Initial scan
    logger.info("Running initial scan...")
    await run_scan()

    # 5) Start background polling
    asyncio.create_task(_poll_loop())
    logger.info(
        "Background polling started (base=%ds, live=%ds)",
        settings.POLL_INTERVAL_SECONDS,
        settings.LIVE_POLL_INTERVAL_SECONDS,
    )
    logger.info("=" * 60)
    logger.info("  Ready – http://localhost:%s/docs", 8000)
    logger.info("  Running 24/7 – autonomous scanning active")
    logger.info("=" * 60)


async def _poll_loop():
    """Adaptive background poll loop.

    Polls more aggressively when live games are detected.
    Default: every 30s. During live games: every 15s.
    """
    while True:
        # Determine interval based on whether live games are happening
        scan = get_latest_scan()
        has_live = scan.has_live_games if scan else False
        interval = (
            settings.LIVE_POLL_INTERVAL_SECONDS
            if has_live
            else settings.POLL_INTERVAL_SECONDS
        )

        await asyncio.sleep(interval)
        try:
            await run_scan()
        except Exception as e:
            logger.error("Poll scan failed: %s", e)
