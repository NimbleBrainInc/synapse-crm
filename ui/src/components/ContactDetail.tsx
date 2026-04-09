import { useState, useEffect, useCallback } from "react";
import { useSynapse } from "@nimblebrain/synapse/react";
import type { Contact } from "../hooks/useContacts";
import { STAGE_LABELS, STAGE_COLORS } from "../hooks/useDeals";
import type { Deal } from "../hooks/useDeals";

interface TimelineEntry {
  id: string;
  type: string;
  summary: string;
  details?: string;
  occurred_at?: string;
  follow_up_date?: string;
}

interface TimelineData {
  contact: { id: string; name: string; company?: string; email?: string };
  interactions: TimelineEntry[];
  total: number;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

const TYPE_ICONS: Record<string, string> = {
  meeting: "M",
  email: "E",
  call: "C",
  note: "N",
};

const TYPE_COLORS: Record<string, string> = {
  meeting: "#8B5CF6",
  email: "#3B82F6",
  call: "#10B981",
  note: "#F59E0B",
};

export function ContactDetail({
  contact,
  isDark,
  accentColor,
  onClose,
  onRefresh,
}: {
  contact: Contact;
  isDark: boolean;
  accentColor: string;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const synapse = useSynapse();
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [loadingTimeline, setLoadingTimeline] = useState(true);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loadingDeals, setLoadingDeals] = useState(true);

  // Log interaction form state
  const [showForm, setShowForm] = useState(false);
  const [formType, setFormType] = useState("meeting");
  const [formSummary, setFormSummary] = useState("");
  const [formDetails, setFormDetails] = useState("");
  const [formFollowUp, setFormFollowUp] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTimeline = useCallback(async () => {
    setLoadingTimeline(true);
    try {
      const result = await synapse.callTool("contact_timeline", {
        contact_id: contact.id,
      });
      if (!result.isError) {
        setTimeline(result.data as TimelineData);
      }
    } catch {
      // non-critical
    } finally {
      setLoadingTimeline(false);
    }
  }, [synapse, contact.id]);

  const loadDeals = useCallback(async () => {
    setLoadingDeals(true);
    try {
      const result = await synapse.callTool("query_deals_by_relationship", {
        rel: "belongs_to",
        target_id: contact.id,
      });
      if (!result.isError) {
        const raw = result.data as { entities?: Deal[] } | Deal[];
        setDeals(Array.isArray(raw) ? raw : (raw?.entities ?? []));
      }
    } catch {
      // non-critical
    } finally {
      setLoadingDeals(false);
    }
  }, [synapse, contact.id]);

  useEffect(() => {
    synapse.ready.then(() => {
      loadTimeline();
      loadDeals();
    });
  }, [synapse, loadTimeline, loadDeals]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleLogInteraction = async () => {
    if (!formSummary.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const result = await synapse.callTool("log_interaction", {
        contact_id: contact.id,
        interaction_type: formType,
        summary: formSummary.trim(),
        details: formDetails.trim(),
        follow_up_date: formFollowUp,
      });
      if (result.isError) {
        setError(String(result.data));
      } else {
        setShowForm(false);
        setFormSummary("");
        setFormDetails("");
        setFormFollowUp("");
        loadTimeline();
        onRefresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to log interaction");
    } finally {
      setSaving(false);
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
  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem",
    borderRadius: "4px",
    border: `1px solid ${border}`,
    background: isDark ? "#16162a" : "#f8f9fa",
    color: isDark ? "#e0e0e0" : "#1a1a2e",
    fontSize: "0.85rem",
    boxSizing: "border-box",
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
          width: "540px",
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
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>{contact.name}</h3>
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

        {/* Contact Info */}
        <div style={{ padding: "1rem 1.25rem", borderBottom: `1px solid ${border}` }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <div style={labelStyle}>Company</div>
              <div style={{ fontSize: "0.85rem" }}>{contact.company || "--"}</div>
            </div>
            <div>
              <div style={labelStyle}>Role</div>
              <div style={{ fontSize: "0.85rem" }}>{contact.role || "--"}</div>
            </div>
            <div>
              <div style={labelStyle}>Email</div>
              <div style={{ fontSize: "0.85rem" }}>{contact.email || "--"}</div>
            </div>
            <div>
              <div style={labelStyle}>Phone</div>
              <div style={{ fontSize: "0.85rem" }}>{contact.phone || "--"}</div>
            </div>
          </div>
          {contact.notes && (
            <div style={{ marginTop: "0.75rem" }}>
              <div style={labelStyle}>Notes</div>
              <div style={{ fontSize: "0.8rem", color: muted, lineHeight: 1.5 }}>
                {contact.notes}
              </div>
            </div>
          )}
        </div>

        {/* Deals section */}
        <div style={{ padding: "0.75rem 1.25rem", borderBottom: `1px solid ${border}` }}>
          <div style={{ ...labelStyle, marginBottom: "0.5rem" }}>
            Deals ({deals.length})
          </div>
          {loadingDeals ? (
            <div style={{ fontSize: "0.8rem", color: muted }}>Loading...</div>
          ) : deals.length === 0 ? (
            <div style={{ fontSize: "0.8rem", color: muted }}>No deals yet</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {deals.map((deal) => {
                const stageColor = STAGE_COLORS[deal.stage] || "#6B7280";
                return (
                  <div
                    key={deal.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.4rem 0.6rem",
                      borderRadius: "6px",
                      border: `1px solid ${isDark ? "#2d2d44" : "#e5e7eb"}`,
                      background: isDark ? "#16162a" : "#f9fafb",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: "0.8rem", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {deal.title}
                      </div>
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.15rem" }}>
                        <span
                          style={{
                            fontSize: "0.6rem",
                            fontWeight: 700,
                            padding: "0.1rem 0.4rem",
                            borderRadius: "8px",
                            background: `${stageColor}20`,
                            color: stageColor,
                          }}
                        >
                          {STAGE_LABELS[deal.stage] || deal.stage}
                        </span>
                        {deal.value != null && (
                          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: accentColor }}>
                            {formatCurrency(deal.value)}
                          </span>
                        )}
                      </div>
                    </div>
                    {deal.probability != null && (
                      <span style={{ fontSize: "0.7rem", color: muted, marginLeft: "0.5rem" }}>
                        {deal.probability}%
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Timeline header + Log button */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0.75rem 1.25rem",
            borderBottom: `1px solid ${border}`,
          }}
        >
          <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: muted }}>
            Interactions ({timeline?.total ?? 0})
          </span>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              padding: "0.3rem 0.75rem",
              borderRadius: "6px",
              border: "none",
              background: accentColor,
              color: "#fff",
              fontSize: "0.7rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {showForm ? "Cancel" : "+ Log Interaction"}
          </button>
        </div>

        {/* Log interaction form */}
        {showForm && (
          <div style={{ padding: "1rem 1.25rem", borderBottom: `1px solid ${border}`, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div>
                <div style={labelStyle}>Type</div>
                <select value={formType} onChange={(e) => setFormType(e.target.value)} style={inputStyle}>
                  <option value="meeting">Meeting</option>
                  <option value="email">Email</option>
                  <option value="call">Call</option>
                  <option value="note">Note</option>
                </select>
              </div>
              <div>
                <div style={labelStyle}>Follow-up Date</div>
                <input
                  type="date"
                  value={formFollowUp}
                  onChange={(e) => setFormFollowUp(e.target.value)}
                  style={inputStyle}
                />
              </div>
            </div>
            <div>
              <div style={labelStyle}>Summary *</div>
              <input
                type="text"
                value={formSummary}
                onChange={(e) => setFormSummary(e.target.value)}
                placeholder="Brief summary of the interaction"
                style={inputStyle}
                autoFocus
              />
            </div>
            <div>
              <div style={labelStyle}>Details</div>
              <textarea
                value={formDetails}
                onChange={(e) => setFormDetails(e.target.value)}
                placeholder="Optional detailed notes..."
                rows={3}
                style={{ ...inputStyle, resize: "vertical" }}
              />
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
            <button
              onClick={handleLogInteraction}
              disabled={saving || !formSummary.trim()}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: saving || !formSummary.trim() ? (isDark ? "#333" : "#ccc") : accentColor,
                color: "#fff",
                fontSize: "0.8rem",
                fontWeight: 600,
                cursor: saving || !formSummary.trim() ? "not-allowed" : "pointer",
                alignSelf: "flex-end",
              }}
            >
              {saving ? "Saving..." : "Log Interaction"}
            </button>
          </div>
        )}

        {/* Timeline */}
        <div style={{ padding: "0.5rem 1.25rem 1.25rem" }}>
          {loadingTimeline ? (
            <div style={{ padding: "1.5rem", textAlign: "center", color: muted, fontSize: "0.85rem" }}>
              Loading...
            </div>
          ) : !timeline || timeline.interactions.length === 0 ? (
            <div style={{ padding: "1.5rem", textAlign: "center", color: muted, fontSize: "0.85rem" }}>
              No interactions yet
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
              {timeline.interactions.map((ix) => {
                const typeColor = TYPE_COLORS[ix.type] || "#6B7280";
                return (
                  <div
                    key={ix.id}
                    style={{
                      display: "flex",
                      gap: "0.75rem",
                      padding: "0.6rem 0",
                      borderBottom: `1px solid ${isDark ? "#2d2d44" : "#f0f0f0"}`,
                    }}
                  >
                    <div
                      style={{
                        width: "28px",
                        height: "28px",
                        borderRadius: "50%",
                        background: `${typeColor}20`,
                        color: typeColor,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "0.65rem",
                        fontWeight: 700,
                        flexShrink: 0,
                      }}
                    >
                      {TYPE_ICONS[ix.type] || "?"}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: "0.8rem", fontWeight: 500 }}>{ix.summary}</div>
                      <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.2rem" }}>
                        {ix.occurred_at && (
                          <span style={{ fontSize: "0.7rem", color: muted }}>
                            {new Date(ix.occurred_at).toLocaleDateString()}
                          </span>
                        )}
                        {ix.follow_up_date && (
                          <span style={{ fontSize: "0.7rem", color: TYPE_COLORS.call }}>
                            Follow up: {ix.follow_up_date}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
