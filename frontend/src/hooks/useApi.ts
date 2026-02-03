import { useState, useEffect, useCallback, useRef } from "react";
import type {
  HealthResponse,
  OpportunitiesResponse,
  Filters,
  RefreshResponse,
} from "../types/api";

const API_BASE = "http://localhost:8000";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function useHealth(pollMs = 15000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchJson<HealthResponse>(`${API_BASE}/health`);
      setHealth(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Health check failed");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
  }, [load, pollMs]);

  return { health, error, reload: load };
}

export function useOpportunities(filters: Filters, pollMs = 10000) {
  const [data, setData] = useState<OpportunitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const load = useCallback(async () => {
    try {
      const f = filtersRef.current;
      const params = new URLSearchParams();
      if (f.league) params.set("league", f.league);
      if (f.minEdge > 0) params.set("min_edge", String(f.minEdge));
      if (f.minBooks > 0) params.set("min_books", String(f.minBooks));
      if (f.minConfidence > 0) params.set("min_confidence", String(f.minConfidence));
      if (f.evPositiveOnly) params.set("ev_positive_only", "true");
      const qs = params.toString();
      const url = `${API_BASE}/opportunities${qs ? `?${qs}` : ""}`;
      const resp = await fetchJson<OpportunitiesResponse>(url);
      setData(resp);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
  }, [load, pollMs, filters]);

  return { data, loading, error, reload: load };
}

export async function triggerRefresh(): Promise<RefreshResponse> {
  const res = await fetch(`${API_BASE}/refresh`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}
