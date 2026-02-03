# Market Edge Scanner

Compares US sportsbook consensus odds against prediction market prices (Polymarket + Kalshi) to surface statistically significant mispricings.

## Architecture

```
backend/          Python FastAPI server
  app/
    api/          REST endpoints
    clients/      API clients (Odds API, Polymarket, Kalshi)
    core/         Calculations, matching, scanner, self-tests
    fixtures/     Synthetic test data
    models/       Pydantic schemas
    tests/        Unit + integration tests

frontend/         React + Vite + TypeScript dashboard
  src/
    components/   UI components
    hooks/        Data-fetching hooks
    types/        TypeScript interfaces
    utils/        Formatting helpers
```

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and add your THE_ODDS_API_KEY
```

The app runs without API keys using synthetic data for testing. Add `THE_ODDS_API_KEY` from [the-odds-api.com](https://the-odds-api.com/) for live data. Polymarket and Kalshi use public endpoints (no key needed).

### 2. Start backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On startup the server will:
- Run 8 self-tests validating odds conversion, de-vig, consensus, matching, and schema logic
- Perform an initial scan (live or synthetic depending on API key)
- Start polling every 60 seconds

### 3. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### 4. Run tests

```bash
cd backend
python -m pytest app/tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health + self-test results |
| GET | `/odds/sportsbooks` | Consensus lines from sportsbooks |
| GET | `/markets/polymarket` | Polymarket listings |
| GET | `/markets/kalshi` | Kalshi listings |
| GET | `/opportunities` | Ranked edge opportunities (supports filters) |
| GET | `/unmatched` | Prediction markets that didn't match any sportsbook event |
| POST | `/refresh` | Trigger immediate rescan |

### Opportunity Filters (query params)

- `league` — NFL, NBA, MLB, NHL, NCAAF, NCAAB, MLS
- `min_edge` — minimum absolute edge (e.g., 0.02)
- `min_books` — minimum number of bookmakers
- `min_confidence` — minimum match confidence score
- `ev_positive_only` — boolean, filter to EV > 0

## Core Calculations

**Odds to implied probability:**
```
p = 1 / decimal_odds
```

**De-vig (two-outcome):**
```
p1 = p1_raw / (p1_raw + p2_raw)
p2 = p2_raw / (p1_raw + p2_raw)
```

**Consensus:** Mean of de-vigged probabilities across all bookmakers.

**Edge:**
```
edge = consensus_prob - market_price
ev_proxy = edge - fee_buffer (default 0.03)
```

## Matching Engine

1. Normalize team names via alias table + pattern stripping
2. Enforce same-league constraint
3. Require start times within ±6 hours
4. Exact match first, then fuzzy match (rapidfuzz token_sort_ratio >= 92)
5. Store match confidence score per pair

## Data Sources

- **The Odds API** — US sportsbook odds (h2h markets, decimal format)
- **Polymarket** — Gamma API for event listings, CLOB API for bid/ask/mid pricing
- **Kalshi** — Public market data endpoints for events, markets, and orderbook

## Assumptions

- All odds are two-outcome moneyline (h2h) markets
- Fee buffer of 3% approximates prediction market transaction costs
- Polymarket: use midpoint if bid-ask spread <= $0.10, otherwise last trade
- Kalshi: prices may be in cents (0-100) and are normalized to probability (0-1)
- Matching is conservative (>=92 confidence) to minimize false positives
- No automated trading — display and analysis only
- Respects all API terms of service and rate limits
