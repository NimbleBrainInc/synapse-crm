import { Card, Inline, Text, tokens } from "@nimblebrain/synapse/ui";
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
  onClick,
}: {
  deal: Deal;
  onClick: () => void;
}) {
  const days = daysInStage(deal.updated_at);
  const stageColor = STAGE_COLORS[deal.stage] || tokens.fgMuted;

  // The library `Card` brings the surface, hairline border, radius, and a real
  // token-driven hover lift (replacing the hand-rolled rgba shadow). The stage
  // accent stripe is a domain detail layered on via `style`.
  return (
    <Card
      interactive
      onClick={onClick}
      padding="0.75rem"
      style={{ borderLeft: `3px solid ${stageColor}` }}
    >
      <Text weight="semibold" size="sm" style={{ display: "block", marginBottom: "0.35rem" }}>
        {deal.title}
      </Text>
      <Inline justify="between">
        <span style={{ fontSize: "0.9rem", fontWeight: 700, color: stageColor }}>
          {deal.value ? formatCurrency(deal.value) : "--"}
        </span>
        <Text size="xs" tone="muted">
          {days}d in stage
        </Text>
      </Inline>
      {deal.contact_name && (
        <Text size="xs" tone="muted" style={{ display: "block", marginTop: "0.25rem" }}>
          {deal.contact_name}
        </Text>
      )}
    </Card>
  );
}
