import { STAGES, STAGE_LABELS, STAGE_COLORS } from "../hooks/useDeals";
import type { DealsByStage, Deal } from "../hooks/useDeals";
import { DealCard } from "../components/DealCard";
import { useStyleTokens } from "../tokens";
import { tokens as ui } from "@nimblebrain/synapse/ui";

export function PipelineView({
  dealsByStage,
  onDealClick,
}: {
  dealsByStage: DealsByStage;
  onDealClick: (deal: Deal) => void;
}) {
  const tokens = useStyleTokens();

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div
        className="crm-pipeline"
        style={{
          display: "flex",
          gap: "0.75rem",
          padding: `1rem ${ui.gutter}`,
          overflow: "auto",
          flex: 1,
          minHeight: 0,
        }}
      >
        {STAGES.map((stage) => {
          const deals = dealsByStage[stage] || [];
          const stageColor = STAGE_COLORS[stage];
          return (
            <div
              key={stage}
              style={{
                flex: "1 0 200px",
                minWidth: "200px",
                maxWidth: "280px",
                background: tokens.bgSubtle,
                borderRadius: "8px",
                padding: "0.75rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {/* Column header */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "0.25rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: stageColor,
                    }}
                  />
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      color: tokens.fgMuted,
                    }}
                  >
                    {STAGE_LABELS[stage]}
                  </span>
                </div>
                <span
                  style={{
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    color: tokens.fgMuted,
                    background: tokens.bgSubtle,
                    borderRadius: "10px",
                    padding: "0.1rem 0.5rem",
                  }}
                >
                  {deals.length}
                </span>
              </div>

              {/* Deal cards */}
              {deals.map((deal) => (
                <DealCard
                  key={deal.id}
                  deal={deal}
                  onClick={() => onDealClick(deal)}
                />
              ))}

              {deals.length === 0 && (
                <div
                  style={{
                    padding: "1.5rem 0.75rem",
                    textAlign: "center",
                    fontSize: "0.75rem",
                    color: tokens.fgFaint,
                  }}
                >
                  No deals
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
