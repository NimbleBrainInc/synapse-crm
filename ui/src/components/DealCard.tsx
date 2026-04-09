import type { Deal } from "../hooks/useDeals";
import { STAGE_COLORS } from "../hooks/useDeals";

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
  isDark,
  onClick,
}: {
  deal: Deal;
  isDark: boolean;
  onClick: () => void;
}) {
  const days = daysInStage(deal.updated_at);
  const stageColor = STAGE_COLORS[deal.stage] || "#6B7280";
  const bg = isDark ? "#1e1e36" : "#ffffff";
  const border = isDark ? "#3d3d5c" : "#e0e0e0";
  const muted = isDark ? "#888" : "#999";

  return (
    <div
      onClick={onClick}
      style={{
        padding: "0.75rem",
        borderRadius: "8px",
        border: `1px solid ${border}`,
        borderLeft: `3px solid ${stageColor}`,
        background: bg,
        cursor: "pointer",
        transition: "box-shadow 0.15s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = isDark
          ? "0 2px 8px rgba(0,0,0,0.4)"
          : "0 2px 8px rgba(0,0,0,0.1)";
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
        <span style={{ fontSize: "0.7rem", color: muted }}>
          {days}d in stage
        </span>
      </div>
      {deal.contact_name && (
        <div style={{ fontSize: "0.75rem", color: muted, marginTop: "0.25rem" }}>
          {deal.contact_name}
        </div>
      )}
    </div>
  );
}
