import type { Filters as FiltersType } from "../types/api";

interface Props {
  filters: FiltersType;
  onChange: (f: FiltersType) => void;
  onRefresh: () => void;
  refreshing: boolean;
}

const LEAGUES = ["", "NFL", "NBA", "MLB", "NHL", "NCAAF", "NCAAB", "MLS"];

export function FiltersBar({ filters, onChange, onRefresh, refreshing }: Props) {
  const set = (patch: Partial<FiltersType>) => onChange({ ...filters, ...patch });

  return (
    <div style={styles.bar}>
      <label style={styles.label}>
        League
        <select
          value={filters.league}
          onChange={(e) => set({ league: e.target.value })}
          style={styles.select}
        >
          {LEAGUES.map((l) => (
            <option key={l} value={l}>
              {l || "All"}
            </option>
          ))}
        </select>
      </label>

      <label style={styles.label}>
        Min Edge
        <input
          type="number"
          step="0.01"
          min="0"
          value={filters.minEdge}
          onChange={(e) => set({ minEdge: parseFloat(e.target.value) || 0 })}
          style={styles.input}
        />
      </label>

      <label style={styles.label}>
        Min Books
        <input
          type="number"
          min="0"
          value={filters.minBooks}
          onChange={(e) => set({ minBooks: parseInt(e.target.value) || 0 })}
          style={styles.input}
        />
      </label>

      <label style={styles.label}>
        Min Confidence
        <input
          type="number"
          min="0"
          max="100"
          value={filters.minConfidence}
          onChange={(e) => set({ minConfidence: parseFloat(e.target.value) || 0 })}
          style={styles.input}
        />
      </label>

      <label style={styles.checkLabel}>
        <input
          type="checkbox"
          checked={filters.evPositiveOnly}
          onChange={(e) => set({ evPositiveOnly: e.target.checked })}
        />
        EV &gt; 0 only
      </label>

      <button onClick={onRefresh} disabled={refreshing} style={styles.btn}>
        {refreshing ? "Scanning..." : "Refresh"}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 16,
    alignItems: "flex-end",
    marginBottom: 20,
    padding: "14px 18px",
    background: "#1e1e2e",
    borderRadius: 8,
    border: "1px solid #313244",
  },
  label: {
    display: "flex",
    flexDirection: "column",
    fontSize: 12,
    color: "#a6adc8",
    gap: 4,
  },
  checkLabel: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 13,
    color: "#cdd6f4",
    cursor: "pointer",
  },
  select: {
    background: "#313244",
    color: "#cdd6f4",
    border: "1px solid #45475a",
    borderRadius: 4,
    padding: "6px 10px",
    fontSize: 13,
  },
  input: {
    background: "#313244",
    color: "#cdd6f4",
    border: "1px solid #45475a",
    borderRadius: 4,
    padding: "6px 10px",
    fontSize: 13,
    width: 70,
  },
  btn: {
    background: "#89b4fa",
    color: "#1e1e2e",
    border: "none",
    borderRadius: 6,
    padding: "8px 20px",
    fontWeight: 600,
    fontSize: 13,
    cursor: "pointer",
    marginLeft: "auto",
  },
};
