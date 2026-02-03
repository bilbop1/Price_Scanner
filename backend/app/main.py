"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, set_selftest_results
from app.core.config import settings
from app.core.scanner import run_scan
from app.core.selftest import run_all_selftests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Edge Scanner",
    description="Compares sportsbook consensus odds vs prediction market prices",
    version="1.0.0",
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
    logger.info("  Market Edge Scanner – starting up")
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
        logger.info("  All self-tests passed ✓")

    # 2) API key status
    if settings.has_odds_api_key:
        logger.info("THE_ODDS_API_KEY configured – will fetch live data")
    else:
        logger.info(
            "THE_ODDS_API_KEY not set – running with synthetic data. "
            "Set the key in .env to enable live scanning."
        )

    # 3) Initial scan
    logger.info("Running initial scan...")
    await run_scan()

    # 4) Start background polling
    asyncio.create_task(_poll_loop())
    logger.info(
        "Background polling started (interval=%ds)", settings.POLL_INTERVAL_SECONDS
    )
    logger.info("=" * 60)
    logger.info("  Ready – http://localhost:%s/docs", 8000)
    logger.info("=" * 60)


async def _poll_loop():
    """Background poll loop."""
    while True:
        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
        try:
            await run_scan()
        except Exception as e:
            logger.error("Poll scan failed: %s", e)
