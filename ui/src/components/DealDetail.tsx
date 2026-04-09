import { useState, useEffect } from "react";
import { useSynapse } from "@nimblebrain/synapse/react";
import type { Deal } from "../hooks/useDeals";
import { STAGES, STAGE_LABELS, STAGE_COLORS } from "../hooks/useDeals";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function DealDetail({
  deal,
  isDark,
  accentColor,
  onClose,
  onRefresh,
}: {
  deal: Deal;
  isDark: boolean;
  accentColor: string;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const synapse = useSynapse();
  const [moving, setMoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleMoveStage = async (newStage: string) => {
    if (newStage === deal.stage) return;
    setMoving(true);
    setError(null);
    try {
      const result = await synapse.callTool("move_deal_stage", {
        deal_id: deal.id,
        stage: newStage,
      });
      if (result.isError) {
        setError(String(result.data));
      } else {
        onRefresh();
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to move deal");
    } finally {
      setMoving(false);
    }
  };

  const overlayBg = isDark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.3)";
  const panelBg = isDark ? "#1e1e36" : "#ffffff";
  const border = isDark ? "#3d3d5c" : "#ddd";
  const muted = isDark ? "#888" : "#666";
  const labelStyle: React.CSSProperties = {
    fontSize: "0.65rem",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: muted,
    marginBottom: "0.2rem",
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: overlayBg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="crm-dialog-panel"
        style={{
          width: "500px",
          maxWidth: "90vw",
          maxHeight: "85vh",
          overflow: "auto",
          background: panelBg,
          borderRadius: "12px",
          border: `1px solid ${border}`,
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1rem 1.25rem",
            borderBottom: `1px solid ${border}`,
          }}
        >
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>{deal.title}</h3>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: "1.25rem",
              cursor: "pointer",
              color: muted,
              padding: "0.25rem",
              lineHeight: 1,
            }}
          >
            x
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Value + Probability row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div>
              <div style={labelStyle}>Value</div>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: accentColor }}>
                {deal.value ? formatCurrency(deal.value) : "--"}
              </div>
            </div>
            <div>
              <div style={labelStyle}>Probability</div>
              <div style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                {deal.probability != null ? `${deal.probability}%` : "--"}
              </div>
            </div>
          </div>

          {/* Contact + Close Date */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div>
              <div style={labelStyle}>Contact</div>
              <div style={{ fontSize: "0.9rem" }}>{deal.contact_name || "--"}</div>
            </div>
            <div>
              <div style={labelStyle}>Close Date</div>
              <div style={{ fontSize: "0.9rem" }}>{deal.close_date || "--"}</div>
            </div>
          </div>

          {/* Stage selector */}
          <div>
            <div style={labelStyle}>Stage</div>
            <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
              {STAGES.map((stage) => {
                const isActive = stage === deal.stage;
                const color = STAGE_COLORS[stage];
                return (
                  <button
                    key={stage}
                    onClick={() => handleMoveStage(stage)}
                    disabled={moving || isActive}
                    style={{
                      padding: "0.35rem 0.65rem",
                      borderRadius: "6px",
                      border: isActive ? `2px solid ${color}` : `1px solid ${border}`,
                      background: isActive ? (isDark ? `${color}22` : `${color}15`) : "transparent",
                      color: isActive ? color : (isDark ? "#aaa" : "#555"),
                      fontSize: "0.7rem",
                      fontWeight: isActive ? 700 : 500,
                      cursor: isActive || moving ? "default" : "pointer",
                      opacity: moving && !isActive ? 0.5 : 1,
                    }}
                  >
                    {STAGE_LABELS[stage]}
                  </button>
                );
              })}
            </div>
          </div>

          {error && (
            <div
              style={{
                padding: "0.5rem 0.75rem",
                borderRadius: "4px",
                background: isDark ? "#3b1a1a" : "#fee",
                color: isDark ? "#f88" : "#c00",
                fontSize: "0.8rem",
              }}
            >
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
