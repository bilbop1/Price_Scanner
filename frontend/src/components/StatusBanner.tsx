import type { HealthResponse } from "../types/api";

interface Props {
  health: HealthResponse | null;
  error: string | null;
}

export function StatusBanner({ health, error }: Props) {
  if (error) {
    return (
      <div style={styles.banner("#dc2626")}>
        <strong>Backend unreachable</strong> &mdash; {error}. Make sure the
        FastAPI server is running on port 8000.
      </div>
    );
  }

  if (!health) return null;

  const failed = health.subsystems.filter((s) => !s.ok);

  if (health.status === "ok" && failed.length === 0) {
    return null; // all good, no banner
  }

  const noKey = failed.find((s) => s.name === "odds_api_key");

  return (
    <div style={styles.banner("#ca8a04")}>
      <strong>Degraded mode</strong>
      {noKey && (
        <span>
          {" "}&mdash; No Odds API key configured. Displaying synthetic data.
          Set <code>THE_ODDS_API_KEY</code> in <code>.env</code> for live data.
        </span>
      )}
      {failed
        .filter((s) => s.name !== "odds_api_key")
        .map((s) => (
          <span key={s.name}>
            {" "}&mdash; {s.name}: {s.message}
          </span>
        ))}
    </div>
  );
}

const styles = {
  banner: (bg: string): React.CSSProperties => ({
    background: bg,
    color: "#fff",
    padding: "10px 20px",
    fontSize: 14,
    fontWeight: 500,
    borderRadius: 6,
    marginBottom: 16,
  }),
};
