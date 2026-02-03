export interface DeViggedBook {
  bookmaker: string;
  home_prob: number;
  away_prob: number;
}

export interface Opportunity {
  id: string;
  league: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  matched_side: string;
  consensus_prob: number;
  median_prob: number;
  market_source: "polymarket" | "kalshi";
  market_price: number;
  edge: number;
  ev_proxy: number;
  num_books: number;
  confidence: number;
  bookmaker_details: DeViggedBook[];
  market_bid: number | null;
  market_ask: number | null;
  market_mid: number | null;
  timestamp: string;
}

export interface OpportunitiesResponse {
  source: "live" | "synthetic";
  count: number;
  data: Opportunity[];
}

export interface SubsystemStatus {
  name: string;
  ok: boolean;
  message: string;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  subsystems: SubsystemStatus[];
  timestamp: string;
}

export interface RefreshResponse {
  status: string;
  sportsbook_events: number;
  consensus_lines: number;
  polymarket_markets: number;
  kalshi_markets: number;
  opportunities: number;
  errors: string[];
}

export interface Filters {
  league: string;
  minEdge: number;
  minBooks: number;
  minConfidence: number;
  evPositiveOnly: boolean;
}
