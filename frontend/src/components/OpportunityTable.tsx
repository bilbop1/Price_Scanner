import { useState } from "react";
import type { Opportunity } from "../types/api";
import {
  pct,
  signedPct,
  formatTime,
  edgeColor,
  confidenceColor,
  sourceLabel,
} from "../utils/format";
import { OpportunityDetail } from "./OpportunityDetail";

interface Props {
  opportunities: Opportunity[];
  source: string;
}

type SortKey = "edge" | "confidence" | "commence_time" | "consensus_prob" | "league";
type SortDir = "asc" | "desc";

export function OpportunityTable({ opportunities, source }: Props) {
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("edge");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = [...opportunities].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "edge":
        cmp = Math.abs(a.edge) - Math.abs(b.edge);
        break;
      case "confidence":
        cmp = a.confidence - b.confidence;
        break;
      case "commence_time":
        cmp =
          new Date(a.commence_time).getTime() -
          new Date(b.commence_time).getTime();
        break;
      case "consensus_prob":
        cmp = a.consensus_prob - b.consensus_prob;
        break;
      case "league":
        cmp = a.league.localeCompare(b.league);
        break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ^" : " v") : "";

  return (
    <>
      {source === "synthetic" && (
        <div style={styles.syntheticTag}>
          Showing synthetic data &mdash; configure API keys for live results
        </div>
      )}

      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              <Th onClick={() => handleSort("league")}>
                League{arrow("league")}
              </Th>
              <Th onClick={() => handleSort("commence_time")}>
                Start{arrow("commence_time")}
              </Th>
              <Th>Game</Th>
              <Th onClick={() => handleSort("consensus_prob")}>
                Consensus{arrow("consensus_prob")}
              </Th>
              <Th>Polymarket</Th>
              <Th>Kalshi</Th>
              <Th onClick={() => handleSort("edge")}>
                Edge{arrow("edge")}
              </Th>
              <Th>Books</Th>
              <Th onClick={() => handleSort("confidence")}>
                Conf{arrow("confidence")}
              </Th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={9} style={styles.empty}>
                  No opportunities found with current filters
                </td>
              </tr>
            ) : (
              sorted.map((opp) => (
                <tr
                  key={opp.id}
                  style={styles.row}
                  onClick={() => setSelected(opp)}
                >
                  <td style={styles.td}>
                    <span style={styles.leagueBadge}>{opp.league}</span>
                  </td>
                  <td style={styles.td}>{formatTime(opp.commence_time)}</td>
                  <td style={styles.td}>
                    <span style={styles.team}>
                      {opp.matched_side === "home" ? (
                        <strong>{opp.home_team}</strong>
                      ) : (
                        opp.home_team
                      )}
                      {" vs "}
                      {opp.matched_side === "away" ? (
                        <strong>{opp.away_team}</strong>
                      ) : (
                        opp.away_team
                      )}
                    </span>
                  </td>
                  <td style={{ ...styles.td, fontFamily: "monospace" }}>
                    {pct(opp.consensus_prob)}
                  </td>
                  <td style={{ ...styles.td, fontFamily: "monospace" }}>
                    {opp.market_source === "polymarket"
                      ? pct(opp.market_price)
                      : "—"}
                  </td>
                  <td style={{ ...styles.td, fontFamily: "monospace" }}>
                    {opp.market_source === "kalshi"
                      ? pct(opp.market_price)
                      : "—"}
                  </td>
                  <td
                    style={{
                      ...styles.td,
                      color: edgeColor(opp.edge),
                      fontWeight: 700,
                      fontFamily: "monospace",
                    }}
                  >
                    {signedPct(opp.edge)}
                  </td>
                  <td style={{ ...styles.td, textAlign: "center" }}>
                    {opp.num_books}
                  </td>
                  <td
                    style={{
                      ...styles.td,
                      color: confidenceColor(opp.confidence),
                      fontFamily: "monospace",
                    }}
                  >
                    {opp.confidence.toFixed(0)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <OpportunityDetail
          opportunity={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

function Th({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <th
      style={{
        ...styles.th,
        cursor: onClick ? "pointer" : "default",
        userSelect: onClick ? "none" : "auto",
      }}
      onClick={onClick}
    >
      {children}
    </th>
  );
}

const styles: Record<string, React.CSSProperties> = {
  tableWrap: {
    overflowX: "auto",
    borderRadius: 8,
    border: "1px solid #313244",
  },
  syntheticTag: {
    fontSize: 12,
    color: "#f9e2af",
    marginBottom: 8,
    fontStyle: "italic",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    textAlign: "left",
    padding: "10px 12px",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    color: "#6c7086",
    background: "#181825",
    borderBottom: "2px solid #313244",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "10px 12px",
    borderBottom: "1px solid #313244",
    color: "#cdd6f4",
    whiteSpace: "nowrap",
  },
  row: {
    cursor: "pointer",
    transition: "background 0.15s",
  },
  empty: {
    padding: 40,
    textAlign: "center",
    color: "#6c7086",
  },
  leagueBadge: {
    background: "#313244",
    padding: "2px 8px",
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 600,
  },
  team: { fontSize: 13 },
};
