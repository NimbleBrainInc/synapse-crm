import type { PipelineSummaryData } from "../hooks/usePipelineSummary";
import { useStyleTokens } from "../tokens";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function PipelineSummaryBar({
  summary,
}: {
  summary: PipelineSummaryData | null;
}) {
  const tokens = useStyleTokens();
  if (!summary) return null;

  const { totals } = summary;

  const metrics = [
    { label: "Active Deals", value: String(totals.active_deals) },
    { label: "Pipeline Value", value: formatCurrency(totals.active_value) },
    { label: "Weighted", value: formatCurrency(totals.weighted_value) },
    {
      label: "Win Rate",
      value: totals.win_rate_pct !== null ? `${totals.win_rate_pct}%` : "--",
    },
  ];

  return (
    <div
      style={{
        display: "flex",
        gap: "1.5rem",
        padding: `0.75rem ${tokens.gutter}`,
        background: tokens.bgRaised,
        borderBottom: `1px solid ${tokens.border}`,
        flexWrap: "wrap",
      }}
    >
      {metrics.map((m) => (
        <div key={m.label} style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
          <span style={{ fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "0.05em", color: tokens.fgMuted }}>
            {m.label}
          </span>
          <span style={{ fontSize: "1.1rem", fontWeight: 700, color: tokens.accent }}>
            {m.value}
          </span>
        </div>
      ))}
    </div>
  );
}
