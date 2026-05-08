import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import type React from "react";
import { useSynapse } from "@nimblebrain/synapse/react";
import { useStyleTokens } from "../tokens";
import { usePanelHeader } from "./DetailPanel";
import type { PanelStackController } from "./DetailPanel";
import type { Deal } from "../hooks/useDeals";
import type { Contact } from "../hooks/useContacts";
import { STAGES, STAGE_LABELS, STAGE_COLORS } from "../hooks/useDeals";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

interface DealViewProps {
  /** Existing deal id for view/edit; null for create. */
  dealId: string | null;
  mode: "view" | "edit" | "create";
  controller: PanelStackController;
  /** Called after a successful create or update so the parent can refresh. */
  onChanged: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/** Find the `belongs_to` target id, if any, on a deal's relationships. */
function belongsToTarget(deal: Deal | null): string | null {
  if (!deal?.relationships) return null;
  const edge = deal.relationships.find((r) => r.rel === "belongs_to");
  return edge?.target ?? null;
}

/** Coerce empty strings → undefined so we don't overwrite stored values. */
function trimToUndef(s: string): string | undefined {
  const t = s.trim();
  return t === "" ? undefined : t;
}

/** Parse a numeric string back into a number, or undefined if blank/invalid. */
function parseNumber(s: string): number | undefined {
  if (s.trim() === "") return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

// ---------------------------------------------------------------------------
// DealView
// ---------------------------------------------------------------------------

export function DealView({
  dealId,
  mode,
  controller,
  onChanged,
}: DealViewProps): React.ReactElement {
  const synapse = useSynapse();
  const tokens = useStyleTokens();

  // Fetched deal (used in view/edit). Null while loading or in create mode.
  const [deal, setDeal] = useState<Deal | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(mode !== "create");
  const [stageMoving, setStageMoving] = useState(false);

  // Edit/create form state. Strings — coerced at submit time.
  const [title, setTitle] = useState("");
  const [valueStr, setValueStr] = useState("");
  const [probabilityStr, setProbabilityStr] = useState("");
  const [closeDate, setCloseDate] = useState("");

  // Create-mode-only contact picker state. We use a datalist of contact names
  // and resolve the typed name back to a contact id at submit time. The
  // captured `contactId` lets us still wire `belongs_to` if the user picks
  // exactly one of the suggestions.
  const [contactName, setContactName] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const datalistId = useId();

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // Fetch deal (view/edit modes)
  // -------------------------------------------------------------------------

  const loadDeal = useCallback(async () => {
    if (!dealId) return;
    setLoading(true);
    setFetchError(null);
    try {
      const result = await synapse.callTool<
        { deal_id: string },
        Deal
      >("get_deal", { deal_id: dealId });
      if (result.isError) {
        setFetchError(String(result.data));
        setDeal(null);
        return;
      }
      const fetched = result.data as Deal | null;
      setDeal(fetched ?? null);
      if (fetched) {
        setTitle(fetched.title ?? "");
        setValueStr(fetched.value != null ? String(fetched.value) : "");
        setProbabilityStr(
          fetched.probability != null ? String(fetched.probability) : "",
        );
        setCloseDate(fetched.close_date ?? "");
      }
    } catch (err) {
      setFetchError(
        err instanceof Error ? err.message : "Failed to load deal",
      );
      setDeal(null);
    } finally {
      setLoading(false);
    }
  }, [synapse, dealId]);

  useEffect(() => {
    if (mode === "create") {
      // Reset create-mode form when (re-)entering create mode.
      setTitle("");
      setValueStr("");
      setProbabilityStr("");
      setCloseDate("");
      setContactName("");
      setSubmitError(null);
      setLoading(false);
      return;
    }
    synapse.ready.then(() => loadDeal());
  }, [synapse, mode, loadDeal]);

  // -------------------------------------------------------------------------
  // Fetch contacts list (create mode only — for the datalist picker)
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (mode !== "create") return;
    let cancelled = false;
    synapse.ready.then(async () => {
      try {
        const result = await synapse.callTool<
          Record<string, unknown>,
          { entities?: Contact[] } | Contact[]
        >("list_contacts");
        if (cancelled || result.isError) return;
        const raw = result.data;
        const list = Array.isArray(raw) ? raw : (raw?.entities ?? []);
        setContacts(list);
      } catch {
        // non-critical — datalist just won't have suggestions
      }
    });
    return () => {
      cancelled = true;
    };
  }, [synapse, mode]);

  // Resolve a typed contact name back to a contact id (exact match, case-insensitive)
  const resolvedContactId = useMemo<string | null>(() => {
    if (mode !== "create") return null;
    const needle = contactName.trim().toLowerCase();
    if (!needle) return null;
    const hit = contacts.find((c) => c.name.toLowerCase() === needle);
    return hit?.id ?? null;
  }, [contactName, contacts, mode]);

  // -------------------------------------------------------------------------
  // Dirty check (edit mode)
  // -------------------------------------------------------------------------

  const isDirty = useMemo<boolean>(() => {
    if (mode !== "edit" || !deal) return false;
    if (title !== (deal.title ?? "")) return true;
    if (valueStr !== (deal.value != null ? String(deal.value) : "")) return true;
    if (
      probabilityStr !==
      (deal.probability != null ? String(deal.probability) : "")
    ) {
      return true;
    }
    if (closeDate !== (deal.close_date ?? "")) return true;
    return false;
  }, [mode, deal, title, valueStr, probabilityStr, closeDate]);

  // -------------------------------------------------------------------------
  // Stage-move handler (view mode)
  // -------------------------------------------------------------------------

  const handleMoveStage = useCallback(
    async (newStage: string) => {
      if (!deal || newStage === deal.stage) return;
      setStageMoving(true);
      setFetchError(null);
      try {
        const result = await synapse.callTool("move_deal_stage", {
          deal_id: deal.id,
          stage: newStage,
        });
        if (result.isError) {
          setFetchError(String(result.data));
          return;
        }
        onChanged();
        await loadDeal();
      } catch (err) {
        setFetchError(
          err instanceof Error ? err.message : "Failed to move deal",
        );
      } finally {
        setStageMoving(false);
      }
    },
    [synapse, deal, onChanged, loadDeal],
  );

  // -------------------------------------------------------------------------
  // Save / Create handlers (edit + create)
  // -------------------------------------------------------------------------

  const handleSave = useCallback(async () => {
    if (mode !== "edit" || !deal) return;
    if (!title.trim()) {
      setSubmitError("Title is required");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      // Send only fields that actually changed — undefined keys are dropped
      // by the Upjack update tool's merge semantics on the server side, but
      // we strip them client-side too so the request is as small as possible
      // and to keep "no-op save" actually be a no-op on the server.
      const payload: Record<string, unknown> = { deal_id: deal.id };
      if (title !== (deal.title ?? "")) payload.title = title.trim();
      const newValue = parseNumber(valueStr);
      const oldValue = deal.value;
      if (newValue !== oldValue) payload.value = newValue;
      const newProb = parseNumber(probabilityStr);
      const oldProb = deal.probability;
      if (newProb !== oldProb) payload.probability = newProb;
      const newDate = closeDate.trim() === "" ? undefined : closeDate;
      const oldDate = deal.close_date;
      if (newDate !== oldDate) payload.close_date = newDate;

      const result = await synapse.callTool("update_deal", payload);
      if (result.isError) {
        setSubmitError(String(result.data));
        return;
      }
      onChanged();
      controller.replaceTop({ kind: "deal", id: deal.id, mode: "view" });
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to save deal",
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    mode,
    deal,
    title,
    valueStr,
    probabilityStr,
    closeDate,
    synapse,
    onChanged,
    controller,
  ]);

  const handleCreate = useCallback(async () => {
    if (mode !== "create") return;
    if (!title.trim()) {
      setSubmitError("Title is required");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload: Record<string, unknown> = { title: title.trim() };
      const v = parseNumber(valueStr);
      if (v != null) payload.value = v;
      const p = parseNumber(probabilityStr);
      if (p != null) payload.probability = p;
      const d = trimToUndef(closeDate);
      if (d != null) payload.close_date = d;
      const cn = trimToUndef(contactName);
      if (cn != null) payload.contact_name = cn;
      // If the typed name resolved to an exact contact match, wire the
      // belongs_to relationship so the deal shows up under that contact.
      // Otherwise the deal is "loose" — the contact_name is denormalized but
      // not linked. Per the Task 006 spec, a richer picker is out of scope.
      if (resolvedContactId) {
        payload.relationships = [
          { rel: "belongs_to", target: resolvedContactId },
        ];
      }

      const result = await synapse.callTool<typeof payload, Deal>(
        "create_deal",
        payload,
      );
      if (result.isError) {
        setSubmitError(String(result.data));
        return;
      }
      const created = result.data as Deal | null;
      onChanged();
      if (created?.id) {
        controller.replaceTop({
          kind: "deal",
          id: created.id,
          mode: "view",
        });
      } else {
        // Fallback: server didn't return an id — just close the panel.
        controller.close();
      }
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to create deal",
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    mode,
    title,
    valueStr,
    probabilityStr,
    closeDate,
    contactName,
    resolvedContactId,
    synapse,
    onChanged,
    controller,
  ]);

  const handleCancelEdit = useCallback(() => {
    if (!deal) return;
    if (isDirty && !window.confirm("Discard changes?")) return;
    controller.replaceTop({ kind: "deal", id: deal.id, mode: "view" });
  }, [deal, isDirty, controller]);

  const handleCancelCreate = useCallback(() => {
    const anyTyped =
      title.trim() !== "" ||
      valueStr.trim() !== "" ||
      probabilityStr.trim() !== "" ||
      closeDate.trim() !== "" ||
      contactName.trim() !== "";
    if (anyTyped && !window.confirm("Discard new deal?")) return;
    controller.close();
  }, [title, valueStr, probabilityStr, closeDate, contactName, controller]);

  // -------------------------------------------------------------------------
  // Header (title + actions slot) — registered via usePanelHeader (helmet)
  // -------------------------------------------------------------------------

  // Style helpers reused for header buttons + body controls
  const buttonBase: React.CSSProperties = {
    fontFamily: tokens.fontFamily,
    fontSize: "0.75rem",
    fontWeight: 600,
    padding: "0.35rem 0.8rem",
    borderRadius: "6px",
    cursor: "pointer",
    lineHeight: 1.2,
  };
  const primaryBtn: React.CSSProperties = {
    ...buttonBase,
    border: "none",
    background: tokens.accent,
    color: tokens.accentText,
  };
  const secondaryBtn: React.CSSProperties = {
    ...buttonBase,
    border: `1px solid ${tokens.border}`,
    background: "transparent",
    color: tokens.fg,
  };
  const disabledBtn: React.CSSProperties = {
    cursor: "not-allowed",
    opacity: 0.6,
  };

  const headerTitle =
    mode === "create"
      ? "New Deal"
      : (deal?.title ?? (loading ? "Loading…" : "Deal"));

  const headerActions = useMemo<React.ReactNode>(() => {
    if (mode === "view") {
      if (!deal) return null;
      return (
        <button
          type="button"
          className="crm-touch-target"
          style={secondaryBtn}
          onClick={() =>
            controller.replaceTop({
              kind: "deal",
              id: deal.id,
              mode: "edit",
            })
          }
        >
          Edit
        </button>
      );
    }
    if (mode === "edit") {
      const canSave = !submitting && title.trim().length > 0;
      return (
        <>
          <button
            type="button"
            className="crm-touch-target"
            style={secondaryBtn}
            onClick={handleCancelEdit}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="crm-touch-target"
            style={canSave ? primaryBtn : { ...primaryBtn, ...disabledBtn }}
            onClick={handleSave}
            disabled={!canSave}
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </>
      );
    }
    // create
    const canCreate = !submitting && title.trim().length > 0;
    return (
      <>
        <button
          type="button"
          className="crm-touch-target"
          style={secondaryBtn}
          onClick={handleCancelCreate}
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="button"
          className="crm-touch-target"
          style={canCreate ? primaryBtn : { ...primaryBtn, ...disabledBtn }}
          onClick={handleCreate}
          disabled={!canCreate}
        >
          {submitting ? "Creating…" : "Create"}
        </button>
      </>
    );
    // primaryBtn / secondaryBtn / disabledBtn are derived from `tokens` and
    // are recreated each render — depending on `tokens` keeps eslint-react
    // happy without us reaching for useMemo on every button style.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    mode,
    deal,
    submitting,
    title,
    tokens,
    controller,
    handleCancelEdit,
    handleSave,
    handleCancelCreate,
    handleCreate,
  ]);

  usePanelHeader({ title: headerTitle, actions: headerActions });

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  // Shared label/input styles (theme-aware)
  const labelStyle: React.CSSProperties = {
    fontSize: "0.65rem",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: tokens.fgMuted,
    marginBottom: "0.25rem",
    display: "block",
  };
  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem",
    borderRadius: "4px",
    border: `1px solid ${tokens.border}`,
    background: tokens.bgSubtle,
    color: tokens.fg,
    fontFamily: tokens.fontFamily,
    fontSize: "0.875rem",
    boxSizing: "border-box",
  };

  // ---- View-mode body ----
  if (mode === "view") {
    if (loading) {
      return (
        <div style={{ color: tokens.fgMuted, fontSize: "0.85rem" }}>
          Loading deal…
        </div>
      );
    }
    if (fetchError && !deal) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          <div
            style={{
              padding: "0.6rem 0.75rem",
              borderRadius: "4px",
              background: tokens.dangerSoft,
              color: tokens.danger,
              fontSize: "0.8rem",
            }}
          >
            {fetchError}
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" style={secondaryBtn} onClick={loadDeal}>
              Retry
            </button>
            <button
              type="button"
              style={secondaryBtn}
              onClick={() => controller.close()}
            >
              Close
            </button>
          </div>
        </div>
      );
    }
    if (!deal) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          <div style={{ color: tokens.fgMuted, fontSize: "0.85rem" }}>
            This deal no longer exists.
          </div>
          <button
            type="button"
            style={secondaryBtn}
            onClick={() => controller.close()}
          >
            Close
          </button>
        </div>
      );
    }

    const linkedContactId = belongsToTarget(deal);

    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        {/* Value + Probability */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          <div>
            <div style={labelStyle}>Value</div>
            <div
              style={{
                fontSize: "1.25rem",
                fontWeight: 700,
                color: tokens.accent,
              }}
            >
              {deal.value != null ? formatCurrency(deal.value) : "--"}
            </div>
          </div>
          <div>
            <div style={labelStyle}>Probability</div>
            <div
              style={{
                fontSize: "1.25rem",
                fontWeight: 700,
                color: tokens.fg,
              }}
            >
              {deal.probability != null ? `${deal.probability}%` : "--"}
            </div>
          </div>
        </div>

        {/* Contact + Close Date */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          <div>
            <div style={labelStyle}>Contact</div>
            {linkedContactId && deal.contact_name ? (
              <button
                type="button"
                className="crm-touch-target"
                onClick={() =>
                  controller.push({
                    kind: "contact",
                    id: linkedContactId,
                    mode: "view",
                  })
                }
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = tokens.bgHover;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
                onFocus={(e) => {
                  e.currentTarget.style.background = tokens.bgHover;
                  e.currentTarget.style.outline = `2px solid ${tokens.accent}`;
                  e.currentTarget.style.outlineOffset = "1px";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.outline = "none";
                }}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
                  padding: "0.2rem 0.4rem",
                  margin: "-0.2rem -0.4rem",
                  borderRadius: "4px",
                  border: "none",
                  background: "transparent",
                  color: tokens.accent,
                  fontFamily: tokens.fontFamily,
                  fontSize: "0.9rem",
                  fontWeight: 500,
                  cursor: "pointer",
                  textDecoration: "underline",
                  textUnderlineOffset: "2px",
                }}
              >
                {deal.contact_name}
                <span aria-hidden="true" style={{ fontSize: "0.7rem" }}>
                  →
                </span>
              </button>
            ) : (
              <div
                style={{
                  fontSize: "0.9rem",
                  color: deal.contact_name ? tokens.fg : tokens.fgFaint,
                }}
              >
                {deal.contact_name || "--"}
              </div>
            )}
          </div>
          <div>
            <div style={labelStyle}>Close Date</div>
            <div style={{ fontSize: "0.9rem", color: tokens.fg }}>
              {deal.close_date || "--"}
            </div>
          </div>
        </div>

        {/* Stage selector */}
        <div>
          <div style={labelStyle}>Stage</div>
          <div
            style={{
              display: "flex",
              gap: "0.35rem",
              flexWrap: "wrap",
            }}
          >
            {STAGES.map((stage) => {
              const isActive = stage === deal.stage;
              const color = STAGE_COLORS[stage];
              return (
                <button
                  key={stage}
                  type="button"
                  className="crm-touch-target"
                  onClick={() => handleMoveStage(stage)}
                  disabled={stageMoving || isActive}
                  style={{
                    padding: "0.35rem 0.65rem",
                    borderRadius: "6px",
                    border: isActive
                      ? `2px solid ${color}`
                      : `1px solid ${tokens.border}`,
                    background: isActive ? `${color}20` : "transparent",
                    color: isActive ? color : tokens.fgMuted,
                    fontFamily: tokens.fontFamily,
                    fontSize: "0.7rem",
                    fontWeight: isActive ? 700 : 500,
                    cursor: isActive || stageMoving ? "default" : "pointer",
                    opacity: stageMoving && !isActive ? 0.5 : 1,
                  }}
                >
                  {STAGE_LABELS[stage]}
                </button>
              );
            })}
          </div>
        </div>

        {fetchError && (
          <div
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "4px",
              background: tokens.dangerSoft,
              color: tokens.danger,
              fontSize: "0.8rem",
            }}
          >
            {fetchError}
          </div>
        )}
      </div>
    );
  }

  // ---- Edit-mode body ----
  if (mode === "edit") {
    if (loading) {
      return (
        <div style={{ color: tokens.fgMuted, fontSize: "0.85rem" }}>
          Loading deal…
        </div>
      );
    }
    if (!deal) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          <div
            style={{
              padding: "0.6rem 0.75rem",
              borderRadius: "4px",
              background: tokens.dangerSoft,
              color: tokens.danger,
              fontSize: "0.8rem",
            }}
          >
            {fetchError ?? "This deal no longer exists."}
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" style={secondaryBtn} onClick={loadDeal}>
              Retry
            </button>
            <button
              type="button"
              style={secondaryBtn}
              onClick={() => controller.close()}
            >
              Close
            </button>
          </div>
        </div>
      );
    }

    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <div>
          <label style={labelStyle}>Title *</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={inputStyle}
          />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "0.75rem",
          }}
        >
          <div>
            <label style={labelStyle}>Value</label>
            <input
              type="number"
              min={0}
              value={valueStr}
              onChange={(e) => setValueStr(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Probability (%)</label>
            <input
              type="number"
              min={0}
              max={100}
              value={probabilityStr}
              onChange={(e) => setProbabilityStr(e.target.value)}
              style={inputStyle}
            />
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "0.75rem",
          }}
        >
          <div>
            <label style={labelStyle}>Contact</label>
            <div
              style={{
                fontSize: "0.85rem",
                color: tokens.fgMuted,
                padding: "0.5rem 0",
              }}
            >
              {deal.contact_name || "--"}
            </div>
          </div>
          <div>
            <label style={labelStyle}>Close Date</label>
            <input
              type="date"
              value={closeDate}
              onChange={(e) => setCloseDate(e.target.value)}
              style={inputStyle}
            />
          </div>
        </div>

        {submitError && (
          <div
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "4px",
              background: tokens.dangerSoft,
              color: tokens.danger,
              fontSize: "0.8rem",
            }}
          >
            {submitError}
          </div>
        )}
      </div>
    );
  }

  // ---- Create-mode body ----
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <div>
        <label style={labelStyle}>Title *</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Acme Corp — Q3 expansion"
          style={inputStyle}
          // biome-ignore lint/a11y/noAutofocus: panel just opened, this is the primary field
          autoFocus
        />
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
        }}
      >
        <div>
          <label style={labelStyle}>Value</label>
          <input
            type="number"
            min={0}
            value={valueStr}
            onChange={(e) => setValueStr(e.target.value)}
            placeholder="0"
            style={inputStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>Probability (%)</label>
          <input
            type="number"
            min={0}
            max={100}
            value={probabilityStr}
            onChange={(e) => setProbabilityStr(e.target.value)}
            placeholder="0–100"
            style={inputStyle}
          />
        </div>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
        }}
      >
        <div>
          <label style={labelStyle}>Contact</label>
          <input
            type="text"
            list={datalistId}
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
            placeholder="Pick or type a name"
            style={inputStyle}
          />
          <datalist id={datalistId}>
            {contacts.map((c) => (
              <option key={c.id} value={c.name}>
                {c.company ? `${c.company}` : ""}
              </option>
            ))}
          </datalist>
          {contactName.trim() !== "" && !resolvedContactId && (
            <div
              style={{
                fontSize: "0.7rem",
                color: tokens.fgMuted,
                marginTop: "0.25rem",
              }}
            >
              No matching contact — this deal will not be linked.
            </div>
          )}
        </div>
        <div>
          <label style={labelStyle}>Close Date</label>
          <input
            type="date"
            value={closeDate}
            onChange={(e) => setCloseDate(e.target.value)}
            style={inputStyle}
          />
        </div>
      </div>

      <div>
        <div style={labelStyle}>Stage</div>
        <div style={{ fontSize: "0.8rem", color: tokens.fgMuted }}>
          New deals start in <strong>{STAGE_LABELS.lead}</strong>. Move them
          along the pipeline once created.
        </div>
      </div>

      {submitError && (
        <div
          style={{
            padding: "0.5rem 0.75rem",
            borderRadius: "4px",
            background: tokens.dangerSoft,
            color: tokens.danger,
            fontSize: "0.8rem",
          }}
        >
          {submitError}
        </div>
      )}
    </div>
  );
}
