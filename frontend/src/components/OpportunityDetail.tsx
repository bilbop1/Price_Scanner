import type { Opportunity } from "../types/api";
import { pct, signedPct, sourceLabel } from "../utils/format";

interface Props {
  opportunity: Opportunity;
  onClose: () => void;
}

export function OpportunityDetail({ opportunity: opp, onClose }: Props) {
  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.drawer} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2 style={styles.title}>
            {opp.home_team} vs {opp.away_team}
          </h2>
          <button onClick={onClose} style={styles.close}>
            &times;
          </button>
        </div>

        <div style={styles.meta}>
          <span>{opp.league}</span>
          <span>{new Date(opp.commence_time).toLocaleString()}</span>
          <span>Matched: {opp.matched_side}</span>
          <span>{sourceLabel(opp.market_source)}</span>
        </div>

        <div style={styles.section}>
          <h3 style={styles.sectionTitle}>Edge Analysis</h3>
          <table style={styles.table}>
            <tbody>
              <tr>
                <td style={styles.td}>Consensus Probability</td>
                <td style={styles.tdVal}>{pct(opp.consensus_prob)}</td>
              </tr>
              <tr>
                <td style={styles.td}>Median Probability</td>
                <td style={styles.tdVal}>{pct(opp.median_prob)}</td>
              </tr>
              <tr>
                <td style={styles.td}>Market Price</td>
                <td style={styles.tdVal}>{pct(opp.market_price)}</td>
              </tr>
              <tr>
                <td style={styles.td}>Edge</td>
                <td style={{ ...styles.tdVal, fontWeight: 700 }}>
                  {signedPct(opp.edge)}
                </td>
              </tr>
              <tr>
                <td style={styles.td}>EV Proxy (edge - fees)</td>
                <td style={styles.tdVal}>{signedPct(opp.ev_proxy)}</td>
              </tr>
              <tr>
                <td style={styles.td}>Confidence</td>
                <td style={styles.tdVal}>{opp.confidence.toFixed(0)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div style={styles.section}>
          <h3 style={styles.sectionTitle}>
            {sourceLabel(opp.market_source)} Pricing
          </h3>
          <table style={styles.table}>
            <tbody>
              <tr>
                <td style={styles.td}>Bid</td>
                <td style={styles.tdVal}>
                  {opp.market_bid != null ? pct(opp.market_bid) : "—"}
                </td>
              </tr>
              <tr>
                <td style={styles.td}>Ask</td>
                <td style={styles.tdVal}>
                  {opp.market_ask != null ? pct(opp.market_ask) : "—"}
                </td>
              </tr>
              <tr>
                <td style={styles.td}>Mid</td>
                <td style={styles.tdVal}>
                  {opp.market_mid != null ? pct(opp.market_mid) : "—"}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {opp.bookmaker_details.length > 0 && (
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>
              Bookmaker Probabilities ({opp.num_books} books)
            </h3>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Book</th>
                  <th style={styles.th}>Home</th>
                  <th style={styles.th}>Away</th>
                </tr>
              </thead>
              <tbody>
                {opp.bookmaker_details.map((b) => (
                  <tr key={b.bookmaker}>
                    <td style={styles.td}>{b.bookmaker}</td>
                    <td style={styles.tdVal}>{pct(b.home_prob)}</td>
                    <td style={styles.tdVal}>{pct(b.away_prob)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(0,0,0,0.6)",
    zIndex: 1000,
    display: "flex",
    justifyContent: "flex-end",
  },
  drawer: {
    width: 480,
    maxWidth: "90vw",
    background: "#1e1e2e",
    height: "100%",
    overflowY: "auto",
    padding: "24px 28px",
    boxShadow: "-4px 0 20px rgba(0,0,0,0.5)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 16,
  },
  title: {
    margin: 0,
    fontSize: 18,
    color: "#cdd6f4",
  },
  close: {
    background: "none",
    border: "none",
    color: "#6c7086",
    fontSize: 28,
    cursor: "pointer",
    lineHeight: 1,
  },
  meta: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
    fontSize: 12,
    color: "#a6adc8",
    marginBottom: 24,
    paddingBottom: 16,
    borderBottom: "1px solid #313244",
  },
  section: { marginBottom: 24 },
  sectionTitle: {
    fontSize: 14,
    color: "#89b4fa",
    marginBottom: 8,
    fontWeight: 600,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  th: {
    textAlign: "left",
    fontSize: 11,
    color: "#6c7086",
    padding: "6px 8px",
    borderBottom: "1px solid #313244",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  td: {
    padding: "6px 8px",
    fontSize: 13,
    color: "#bac2de",
    borderBottom: "1px solid #313244",
  },
  tdVal: {
    padding: "6px 8px",
    fontSize: 13,
    color: "#cdd6f4",
    borderBottom: "1px solid #313244",
    textAlign: "right",
    fontFamily: "monospace",
  },
};
