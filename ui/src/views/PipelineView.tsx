import { STAGES, STAGE_LABELS, STAGE_COLORS } from "../hooks/useDeals";
import type { DealsByStage, Deal } from "../hooks/useDeals";
import { DealCard } from "../components/DealCard";

export function PipelineView({
  dealsByStage,
  isDark,
  onDealClick,
}: {
  dealsByStage: DealsByStage;
  isDark: boolean;
  onDealClick: (deal: Deal) => void;
}) {
  const colBg = isDark ? "#16162a" : "#f3f4f6";
  const headerColor = isDark ? "#ccc" : "#374151";

  return (
    <div
      className="crm-pipeline"
      style={{
        display: "flex",
        gap: "0.75rem",
        padding: "1rem",
        overflowX: "auto",
        minHeight: "calc(100vh - 140px)",
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
              background: colBg,
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
                    color: headerColor,
                  }}
                >
                  {STAGE_LABELS[stage]}
                </span>
              </div>
              <span
                style={{
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  color: isDark ? "#666" : "#9ca3af",
                  background: isDark ? "#2d2d44" : "#e5e7eb",
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
                isDark={isDark}
                onClick={() => onDealClick(deal)}
              />
            ))}

            {deals.length === 0 && (
              <div
                style={{
                  padding: "1.5rem 0.75rem",
                  textAlign: "center",
                  fontSize: "0.75rem",
                  color: isDark ? "#555" : "#9ca3af",
                }}
              >
                No deals
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
