export function pct(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function signedPct(value: number, decimals = 1): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${(value * 100).toFixed(decimals)}%`;
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

export function edgeColor(edge: number): string {
  if (edge >= 0.05) return "#16a34a";
  if (edge >= 0.02) return "#ca8a04";
  if (edge > 0) return "#6b7280";
  return "#dc2626";
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 98) return "#16a34a";
  if (confidence >= 95) return "#ca8a04";
  return "#6b7280";
}

export function sourceLabel(source: string): string {
  switch (source) {
    case "polymarket":
      return "Polymarket";
    case "kalshi":
      return "Kalshi";
    default:
      return source;
  }
}
