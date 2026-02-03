import { useState, useCallback } from "react";
import { StatusBanner } from "./components/StatusBanner";
import { FiltersBar } from "./components/Filters";
import { OpportunityTable } from "./components/OpportunityTable";
import { useHealth, useOpportunities, triggerRefresh } from "./hooks/useApi";
import type { Filters } from "./types/api";

const DEFAULT_FILTERS: Filters = {
  league: "",
  minEdge: 0,
  minBooks: 0,
  minConfidence: 0,
  evPositiveOnly: false,
};

export default function App() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [refreshing, setRefreshing] = useState(false);

  const { health, error: healthErr } = useHealth();
  const { data, reload } = useOpportunities(filters);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await triggerRefresh();
      await reload();
    } catch {
      // error handling via health check
    } finally {
      setRefreshing(false);
    }
  }, [reload]);

  const oppCount = data?.count ?? 0;
  const source = data?.source ?? "synthetic";

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <div>
          <h1 style={styles.h1}>Market Edge Scanner</h1>
          <p style={styles.subtitle}>
            Sportsbook consensus vs prediction market prices
          </p>
        </div>
        <div style={styles.stats}>
          <Stat label="Opportunities" value={String(oppCount)} />
          <Stat
            label="Source"
            value={source === "live" ? "LIVE" : "SYNTHETIC"}
            color={source === "live" ? "#a6e3a1" : "#f9e2af"}
          />
          <Stat
            label="Status"
            value={health?.status?.toUpperCase() ?? "..."}
            color={
              health?.status === "ok"
                ? "#a6e3a1"
                : health?.status === "degraded"
                ? "#f9e2af"
                : "#f38ba8"
            }
          />
        </div>
      </header>

      <StatusBanner health={health} error={healthErr} />

      <FiltersBar
        filters={filters}
        onChange={setFilters}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      <OpportunityTable
        opportunities={data?.data ?? []}
        source={source}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div style={styles.stat}>
      <div style={styles.statLabel}>{label}</div>
      <div style={{ ...styles.statValue, color: color ?? "#cdd6f4" }}>
        {value}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    minHeight: "100vh",
    background: "#11111b",
    color: "#cdd6f4",
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    padding: "20px 32px",
    maxWidth: 1400,
    margin: "0 auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 20,
    paddingBottom: 16,
    borderBottom: "1px solid #313244",
  },
  h1: {
    margin: 0,
    fontSize: 24,
    fontWeight: 700,
    color: "#cdd6f4",
  },
  subtitle: {
    margin: "4px 0 0",
    fontSize: 13,
    color: "#6c7086",
  },
  stats: {
    display: "flex",
    gap: 24,
  },
  stat: { textAlign: "right" as const },
  statLabel: {
    fontSize: 10,
    textTransform: "uppercase" as const,
    letterSpacing: 1,
    color: "#6c7086",
    marginBottom: 2,
  },
  statValue: {
    fontSize: 16,
    fontWeight: 700,
    fontFamily: "monospace",
  },
};
