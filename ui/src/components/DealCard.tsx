import type { Deal } from "../hooks/useDeals";
import { STAGE_COLORS } from "../hooks/useDeals";
import { useStyleTokens } from "../tokens";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function daysInStage(updatedAt: string): number {
  const updated = new Date(updatedAt);
  const now = new Date();
  return Math.floor((now.getTime() - updated.getTime()) / (1000 * 60 * 60 * 24));
}

export function DealCard({
  deal,
  onClick,
}: {
  deal: Deal;
  onClick: () => void;
}) {
  const tokens = useStyleTokens();
  const days = daysInStage(deal.updated_at);
  const stageColor = STAGE_COLORS[deal.stage] || "#6B7280";

  return (
    <div
      onClick={onClick}
      style={{
        padding: "0.75rem",
        borderRadius: "8px",
        border: `1px solid ${tokens.borderStrong}`,
        borderLeft: `3px solid ${stageColor}`,
        background: tokens.bgRaised,
        cursor: "pointer",
        transition: "box-shadow 0.15s",
      }}
      onMouseEnter={(e) => {
        // Hover shadow uses raw rgba — shadows are not theme-tokenable today.
        (e.currentTarget as HTMLDivElement).style.boxShadow =
          "0 2px 8px rgba(0,0,0,0.2)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.35rem" }}>
        {deal.title}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "0.9rem", fontWeight: 700, color: stageColor }}>
          {deal.value ? formatCurrency(deal.value) : "--"}
        </span>
        <span style={{ fontSize: "0.7rem", color: tokens.fgMuted }}>
          {days}d in stage
        </span>
      </div>
      {deal.contact_name && (
        <div style={{ fontSize: "0.75rem", color: tokens.fgMuted, marginTop: "0.25rem" }}>
          {deal.contact_name}
        </div>
      )}
    </div>
  );
}
