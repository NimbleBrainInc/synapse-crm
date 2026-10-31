import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type React from "react";
import { useApp, useDataSync } from "@nimblebrain/synapse/react";
import { useStyleTokens } from "../tokens";
import { usePanelHeader, type PanelStackController } from "./DetailPanel";
import type { Contact } from "../hooks/useContacts";
import { FULL_LIST_LIMIT } from "../limits";
import { STAGE_LABELS, STAGE_COLORS } from "../hooks/useDeals";
import type { Deal } from "../hooks/useDeals";

// ---------------------------------------------------------------------------
// Local types
// ---------------------------------------------------------------------------

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

type LeadSource = NonNullable<Contact["lead_source"]>;

const LEAD_SOURCES: ReadonlyArray<LeadSource> = [
  "referral",
  "inbound",
  "outbound",
  "event",
  "other",
];

// Domain palette for interaction icons — kept inline; not a platform token.
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

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Coerce a tool-call error envelope into a readable string. Servers may
 * return structured errors ({error}, {message}, etc.); avoid the
 * "[object Object]" fallback that String(...) on an object would produce.
 */
function formatToolError(data: unknown, fallback = "Request failed"): string {
  if (data == null) return fallback;
  if (typeof data === "string") return data;
  if (typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.error === "string") return obj.error;
    if (typeof obj.message === "string") return obj.message;
    if (typeof obj.detail === "string") return obj.detail;
    try {
      return JSON.stringify(data);
    } catch {
      return fallback;
    }
  }
  return String(data);
}

// ---------------------------------------------------------------------------
// Edit form state
// ---------------------------------------------------------------------------

interface EditableFields {
  name: string;
  email: string;
  phone: string;
  company: string;
  role: string;
  notes: string;
  lead_source: string; // "" means unset
}

const EMPTY_FIELDS: EditableFields = {
  name: "",
  email: "",
  phone: "",
  company: "",
  role: "",
  notes: "",
  lead_source: "",
};

function fieldsFromContact(contact: Contact): EditableFields {
  return {
    name: contact.name ?? "",
    email: contact.email ?? "",
    phone: contact.phone ?? "",
    company: contact.company ?? "",
    role: contact.role ?? "",
    notes: contact.notes ?? "",
    lead_source: contact.lead_source ?? "",
  };
}

function fieldsEqual(a: EditableFields, b: EditableFields): boolean {
  return (
    a.name === b.name &&
    a.email === b.email &&
    a.phone === b.phone &&
    a.company === b.company &&
    a.role === b.role &&
    a.notes === b.notes &&
    a.lead_source === b.lead_source
  );
}

// ---------------------------------------------------------------------------
// ContactView
// ---------------------------------------------------------------------------

export function ContactView({
  contactId,
  mode,
  controller,
  onChanged,
}: {
  contactId: string | null;
  mode: "view" | "edit" | "create";
  controller: PanelStackController;
  onChanged: () => void;
}): React.ReactElement {
  const tokens = useStyleTokens();
  const app = useApp();

  // -------------------------------------------------------------------------
  // Data state — fetched in view & edit modes
  // -------------------------------------------------------------------------

  const [contact, setContact] = useState<Contact | null>(null);
  const [contactError, setContactError] = useState<string | null>(null);
  const [loadingContact, setLoadingContact] = useState<boolean>(
    mode !== "create",
  );

  const [deals, setDeals] = useState<Deal[]>([]);
  const [loadingDeals, setLoadingDeals] = useState<boolean>(mode === "view");
  const [dealsError, setDealsError] = useState<string | null>(null);

  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [loadingTimeline, setLoadingTimeline] = useState<boolean>(
    mode === "view",
  );
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const contextSeqRef = useRef(0);

  // Per-load seq counters. Each load guards against its own out-of-order
  // resolution: if the panel switches contactId mid-flight, the earlier
  // call's seq mismatches the current and the result is dropped. We use
  // separate counters (not one shared) so that three concurrent loads of
  // the *same* contact don't invalidate each other.
  const contactSeqRef = useRef(0);
  const dealsSeqRef = useRef(0);
  const timelineSeqRef = useRef(0);

  const loadContact = useCallback(async () => {
    if (!contactId) return;
    const seq = ++contactSeqRef.current;
    const context = contextSeqRef.current;
    setLoadingContact(true);
    setContactError(null);
    try {
      const result = await app.callTool<Contact>("get_contact", {
        contact_id: contactId,
      });
      if (seq !== contactSeqRef.current || context !== contextSeqRef.current) return;
      if (result.isError) {
        setContactError(formatToolError(result.data, "Failed to load contact"));
      } else {
        if (result.data?.id !== contactId) {
          setContactError("Server did not return this contact");
          return;
        }
        setContact(result.data);
        if (mode === "edit") {
          const next = fieldsFromContact(result.data);
          setFields(next);
          setOriginalFields(next);
        }
      }
    } catch (err) {
      if (seq !== contactSeqRef.current || context !== contextSeqRef.current) return;
      setContactError(
        err instanceof Error ? err.message : "Failed to load contact",
      );
    } finally {
      if (seq === contactSeqRef.current && context === contextSeqRef.current) setLoadingContact(false);
    }
  }, [app, contactId, mode]);

  const loadDeals = useCallback(async () => {
    if (!contactId) return;
    const seq = ++dealsSeqRef.current;
    setLoadingDeals(true);
    setDealsError(null);
    try {
      const result = await app.callTool("query_deals_by_relationship", {
        rel: "belongs_to",
        target_id: contactId,
        limit: FULL_LIST_LIMIT,
      });
      if (seq !== dealsSeqRef.current) return;
      if (result.isError) {
        setDealsError(formatToolError(result.data, "Failed to load deals"));
        setDeals([]);
        return;
      }
      const raw = result.data as { entities?: Deal[] } | Deal[];
      setDeals(Array.isArray(raw) ? raw : (raw?.entities ?? []));
    } catch (err) {
      if (seq !== dealsSeqRef.current) return;
      setDealsError(
        err instanceof Error ? err.message : "Failed to load deals",
      );
      setDeals([]);
    } finally {
      if (seq === dealsSeqRef.current) setLoadingDeals(false);
    }
  }, [app, contactId]);

  const loadTimeline = useCallback(async () => {
    if (!contactId) return;
    const seq = ++timelineSeqRef.current;
    setLoadingTimeline(true);
    setTimelineError(null);
    try {
      const result = await app.callTool("contact_timeline", {
        contact_id: contactId,
      });
      if (seq !== timelineSeqRef.current) return;
      if (result.isError) {
        setTimelineError(
          formatToolError(result.data, "Failed to load timeline"),
        );
        setTimeline(null);
        return;
      }
      setTimeline(result.data as TimelineData);
    } catch (err) {
      if (seq !== timelineSeqRef.current) return;
      setTimelineError(
        err instanceof Error ? err.message : "Failed to load timeline",
      );
      setTimeline(null);
    } finally {
      if (seq === timelineSeqRef.current) setLoadingTimeline(false);
    }
  }, [app, contactId]);

  // Reset before paint so cached fields cannot be edited during the entry read.
  useLayoutEffect(() => {
    setContact((prev) => prev?.id === contactId ? prev : null);
    setSaving(false);
    setSaveError(null);
    if (mode === "edit") {
      setFields(EMPTY_FIELDS);
      setOriginalFields(EMPTY_FIELDS);
    }
    if (mode !== "create" && contactId) loadContact();
    return () => { contextSeqRef.current += 1; };
  }, [mode, contactId, loadContact]);

  // Fetch deals + timeline only in view mode (edit hides those sections).
  useEffect(() => {
    if (mode !== "view" || !contactId) return;
    loadDeals();
    loadTimeline();
  }, [mode, contactId, loadDeals, loadTimeline]);

  // Refresh when the server announces a change (only relevant in view mode
  // where we display deals + timeline).
  useDataSync(() => {
    if (mode !== "view" || !contactId) return;
    return Promise.all([loadContact(), loadDeals(), loadTimeline()]);
  });

  // -------------------------------------------------------------------------
  // Edit / create form state
  // -------------------------------------------------------------------------

  const [fields, setFields] = useState<EditableFields>(EMPTY_FIELDS);
  const [originalFields, setOriginalFields] =
    useState<EditableFields>(EMPTY_FIELDS);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Reset form to empty when entering create mode.
  useEffect(() => {
    if (mode === "create") {
      setFields(EMPTY_FIELDS);
      setOriginalFields(EMPTY_FIELDS);
      setSaveError(null);
    }
  }, [mode]);

  const isDirty = useMemo(
    () => !fieldsEqual(fields, originalFields),
    [fields, originalFields],
  );

  const updateField = useCallback(
    <K extends keyof EditableFields>(key: K, value: EditableFields[K]) => {
      setFields((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // -------------------------------------------------------------------------
  // Save handlers
  // -------------------------------------------------------------------------

  const editReady = !loadingContact && !contactError && contact?.id === contactId;

  const handleSaveEdit = useCallback(async () => {
    if (mode !== "edit" || !editReady || !contactId || !contact) return;
    const context = contextSeqRef.current;
    if (!fields.name.trim()) {
      setSaveError("Name is required");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      // Only send fields that changed; undefined omits a field.
      const payload: Record<string, unknown> = { contact_id: contactId };
      const sendIfChanged = (key: keyof EditableFields) => {
        if (fields[key] !== originalFields[key]) {
          payload[key] = fields[key];
        }
      };
      sendIfChanged("name");
      sendIfChanged("email");
      sendIfChanged("phone");
      sendIfChanged("company");
      sendIfChanged("role");
      sendIfChanged("notes");
      sendIfChanged("lead_source");

      const result = await app.callTool<Contact>("update_contact", payload);
      if (result.isError) {
        if (context !== contextSeqRef.current) return;
        setSaveError(formatToolError(result.data, "Failed to update contact"));
        return;
      }
      onChanged();
      if (context !== contextSeqRef.current) return;
      if (result.data?.id === contactId) setContact(result.data);
      controller.replaceTop({ kind: "contact", id: contactId, mode: "view" });
    } catch (err) {
      if (context !== contextSeqRef.current) return;
      setSaveError(
        err instanceof Error ? err.message : "Failed to update contact",
      );
    } finally {
      if (context === contextSeqRef.current) setSaving(false);
    }
  }, [mode, editReady, contactId, contact, fields, originalFields, app, onChanged, controller]);

  const handleCreate = useCallback(async () => {
    const context = contextSeqRef.current;
    if (!fields.name.trim()) {
      setSaveError("Name is required");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const payload: Record<string, unknown> = { name: fields.name.trim() };
      if (fields.email) payload.email = fields.email;
      if (fields.phone) payload.phone = fields.phone;
      if (fields.company) payload.company = fields.company;
      if (fields.role) payload.role = fields.role;
      if (fields.notes) payload.notes = fields.notes;
      if (fields.lead_source) payload.lead_source = fields.lead_source;

      const result = await app.callTool(
        "find_or_create_contact",
        payload,
      );
      if (result.isError) {
        if (context !== contextSeqRef.current) return;
        setSaveError(formatToolError(result.data, "Failed to create contact"));
        return;
      }
      const created = result.data as { contact?: Contact; error?: unknown } | null;
      if (created?.error) {
        if (context !== contextSeqRef.current) return;
        setSaveError(formatToolError(created, "Failed to create contact"));
        return;
      }
      const newId = created?.contact?.id;
      if (!newId) {
        if (context !== contextSeqRef.current) return;
        setSaveError("Server did not return a contact id");
        return;
      }
      onChanged();
      if (context !== contextSeqRef.current) return;
      controller.replaceTop({ kind: "contact", id: newId, mode: "view" });
    } catch (err) {
      if (context !== contextSeqRef.current) return;
      setSaveError(
        err instanceof Error ? err.message : "Failed to create contact",
      );
    } finally {
      if (context === contextSeqRef.current) setSaving(false);
    }
  }, [fields, app, onChanged, controller]);

  const handleCancel = useCallback(() => {
    if (isDirty) {
      const ok = window.confirm("Discard your changes?");
      if (!ok) return;
    }
    if (mode === "create") {
      controller.close();
    } else if (contactId) {
      controller.replaceTop({ kind: "contact", id: contactId, mode: "view" });
    } else {
      controller.close();
    }
  }, [isDirty, mode, contactId, controller]);

  // -------------------------------------------------------------------------
  // Log Interaction form (view mode)
  // -------------------------------------------------------------------------

  const [showLogForm, setShowLogForm] = useState(false);
  const [logType, setLogType] = useState("meeting");
  const [logSummary, setLogSummary] = useState("");
  const [logDetails, setLogDetails] = useState("");
  const [logFollowUp, setLogFollowUp] = useState("");
  const [logSaving, setLogSaving] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);
  const logContextSeqRef = useRef(0);

  // Reset the log form when the contact identity changes — prevents leaking
  // half-typed input from one contact to another if the panel is reused.
  useEffect(() => {
    setShowLogForm(false);
    setLogSummary("");
    setLogDetails("");
    setLogFollowUp("");
    setLogType("meeting");
    setLogSaving(false);
    setLogError(null);
    return () => { logContextSeqRef.current += 1; };
  }, [contactId]);

  const handleLogInteraction = useCallback(async () => {
    if (!contactId || !logSummary.trim()) return;
    const context = logContextSeqRef.current;
    setLogSaving(true);
    setLogError(null);
    try {
      const result = await app.callTool("log_interaction", {
        contact_id: contactId,
        interaction_type: logType,
        summary: logSummary.trim(),
        details: logDetails.trim(),
        follow_up_date: logFollowUp,
      });
      const data = result.data;
      const domainError = data !== null && typeof data === "object" &&
        !Array.isArray(data) && "error" in data &&
        Object.keys(data).every((key) => key === "error" || key === "diagnostics");
      if (result.isError || domainError) {
        if (context !== logContextSeqRef.current) return;
        setLogError(formatToolError(result.data, "Failed to log interaction"));
      } else {
        onChanged();
        if (context !== logContextSeqRef.current) return;
        setShowLogForm(false);
        setLogSummary("");
        setLogDetails("");
        setLogFollowUp("");
        loadTimeline();
      }
    } catch (err) {
      if (context !== logContextSeqRef.current) return;
      setLogError(
        err instanceof Error ? err.message : "Failed to log interaction",
      );
    } finally {
      if (context === logContextSeqRef.current) setLogSaving(false);
    }
  }, [
    contactId,
    logType,
    logSummary,
    logDetails,
    logFollowUp,
    app,
    loadTimeline,
    onChanged,
  ]);

  // -------------------------------------------------------------------------
  // Header (title + actions)
  // -------------------------------------------------------------------------

  const headerTitle =
    mode === "create"
      ? "New Contact"
      : (contact?.name ?? (loadingContact ? "Loading…" : "Contact"));

  const headerActions = useMemo<React.ReactNode>(() => {
    const btnBase: React.CSSProperties = {
      padding: "0.3rem 0.7rem",
      borderRadius: "6px",
      fontSize: "0.75rem",
      fontWeight: 600,
      cursor: "pointer",
      fontFamily: tokens.fontFamily,
    };
    if (mode === "view" && contactId) {
      return (
        <button
          type="button"
          className="crm-touch-target"
          onClick={() =>
            controller.replaceTop({
              kind: "contact",
              id: contactId,
              mode: "edit",
            })
          }
          style={{
            ...btnBase,
            background: tokens.bgSubtle,
            color: tokens.fg,
            border: `1px solid ${tokens.border}`,
          }}
        >
          Edit
        </button>
      );
    }
    if (mode === "edit") {
      return (
        <>
          <button
            type="button"
            className="crm-touch-target"
            onClick={handleCancel}
            disabled={saving}
            style={{
              ...btnBase,
              background: "transparent",
              color: tokens.fg,
              border: `1px solid ${tokens.border}`,
              cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.6 : 1,
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            className="crm-touch-target"
            onClick={handleSaveEdit}
            disabled={saving || !editReady || !fields.name.trim()}
            style={{
              ...btnBase,
              background:
                saving || !editReady || !fields.name.trim() ? tokens.bgSubtle : tokens.accent,
              color:
                saving || !editReady || !fields.name.trim()
                  ? tokens.fgMuted
                  : tokens.accentText,
              border: "none",
              cursor:
                saving || !editReady || !fields.name.trim() ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      );
    }
    if (mode === "create") {
      return (
        <>
          <button
            type="button"
            className="crm-touch-target"
            onClick={handleCancel}
            disabled={saving}
            style={{
              ...btnBase,
              background: "transparent",
              color: tokens.fg,
              border: `1px solid ${tokens.border}`,
              cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.6 : 1,
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            className="crm-touch-target"
            onClick={handleCreate}
            disabled={saving || !fields.name.trim()}
            style={{
              ...btnBase,
              background:
                saving || !fields.name.trim() ? tokens.bgSubtle : tokens.accent,
              color:
                saving || !fields.name.trim()
                  ? tokens.fgMuted
                  : tokens.accentText,
              border: "none",
              cursor:
                saving || !fields.name.trim() ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Creating…" : "Create"}
          </button>
        </>
      );
    }
    return null;
  }, [
    mode,
    contactId,
    controller,
    tokens,
    handleCancel,
    handleSaveEdit,
    editReady,
    handleCreate,
    saving,
    fields.name,
  ]);

  usePanelHeader({ title: headerTitle, actions: headerActions });

  // -------------------------------------------------------------------------
  // Shared style helpers (driven entirely by tokens)
  // -------------------------------------------------------------------------

  const labelStyle: React.CSSProperties = {
    fontSize: "0.65rem",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: tokens.fgMuted,
    marginBottom: "0.25rem",
    fontFamily: tokens.fontFamily,
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem",
    borderRadius: "4px",
    border: `1px solid ${tokens.border}`,
    background: tokens.bgSubtle,
    color: tokens.fg,
    fontSize: "0.85rem",
    fontFamily: tokens.fontFamily,
    boxSizing: "border-box",
  };

  const sectionDivider: React.CSSProperties = {
    borderTop: `1px solid ${tokens.border}`,
    margin: "1rem -1.25rem",
  };

  // -------------------------------------------------------------------------
  // Render — dispatch by mode
  // -------------------------------------------------------------------------

  if (mode === "create") {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.85rem",
          color: tokens.fg,
          fontFamily: tokens.fontFamily,
        }}
      >
        <ContactFormFields
          fields={fields}
          onChange={updateField}
          tokens={tokens}
          labelStyle={labelStyle}
          inputStyle={inputStyle}
        />
        {saveError && (
          <ErrorBanner message={saveError} tokens={tokens} />
        )}
      </div>
    );
  }

  if (mode === "edit") {
    if (contactError) {
      return (
        <div>
          <ErrorBanner message={contactError} tokens={tokens} />
          <button type="button" className="crm-touch-target" onClick={loadContact}>
            Retry
          </button>
        </div>
      );
    }
    if (!editReady) return <LoadingState tokens={tokens} />;
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.85rem",
          color: tokens.fg,
          fontFamily: tokens.fontFamily,
        }}
      >
        <ContactFormFields
          fields={fields}
          onChange={updateField}
          tokens={tokens}
          labelStyle={labelStyle}
          inputStyle={inputStyle}
        />
        {saveError && (
          <ErrorBanner message={saveError} tokens={tokens} />
        )}
      </div>
    );
  }

  // mode === "view"
  if (loadingContact && !contact) {
    return <LoadingState tokens={tokens} />;
  }
  if (contactError && !contact) {
    return <ErrorBanner message={contactError} tokens={tokens} />;
  }
  if (!contact) {
    return <LoadingState tokens={tokens} />;
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        color: tokens.fg,
        fontFamily: tokens.fontFamily,
      }}
    >
      {/* Contact info grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
        }}
      >
        <Field label="Company" value={contact.company} tokens={tokens} />
        <Field label="Role" value={contact.role} tokens={tokens} />
        <Field label="Email" value={contact.email} tokens={tokens} />
        <Field label="Phone" value={contact.phone} tokens={tokens} />
      </div>
      {contact.notes && (
        <div style={{ marginTop: "0.85rem" }}>
          <div style={labelStyle}>Notes</div>
          <div
            style={{
              fontSize: "0.8rem",
              color: tokens.fgMuted,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
            }}
          >
            {contact.notes}
          </div>
        </div>
      )}

      <div style={sectionDivider} />

      {/* Deals section */}
      <div>
        <div style={{ ...labelStyle, marginBottom: "0.5rem" }}>
          Deals ({deals.length})
        </div>
        {loadingDeals ? (
          <div style={{ fontSize: "0.8rem", color: tokens.fgMuted }}>
            Loading…
          </div>
        ) : dealsError ? (
          <InlineError message={dealsError} tokens={tokens} />
        ) : deals.length === 0 ? (
          <div style={{ fontSize: "0.8rem", color: tokens.fgMuted }}>
            No deals yet
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.4rem",
            }}
          >
            {deals.map((deal) => (
              <DealRow
                key={deal.id}
                deal={deal}
                tokens={tokens}
                onClick={() =>
                  controller.push({
                    kind: "deal",
                    id: deal.id,
                    mode: "view",
                  })
                }
              />
            ))}
          </div>
        )}
      </div>

      <div style={sectionDivider} />

      {/* Interactions header + Log toggle */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            color: tokens.fgMuted,
          }}
        >
          Interactions ({timeline?.total ?? 0})
        </span>
        <button
          type="button"
          className="crm-touch-target"
          onClick={() => setShowLogForm((v) => !v)}
          style={{
            padding: "0.3rem 0.75rem",
            borderRadius: "6px",
            border: "none",
            background: tokens.accent,
            color: tokens.accentText,
            fontSize: "0.7rem",
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: tokens.fontFamily,
          }}
        >
          {showLogForm ? "Cancel" : "+ Log Interaction"}
        </button>
      </div>

      {/* Log Interaction form */}
      {showLogForm && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
            marginTop: "0.75rem",
            padding: "0.75rem",
            borderRadius: "6px",
            border: `1px solid ${tokens.border}`,
            background: tokens.bgSubtle,
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "0.75rem",
            }}
          >
            <div>
              <div style={labelStyle}>Type</div>
              <select
                value={logType}
                onChange={(e) => setLogType(e.target.value)}
                style={inputStyle}
              >
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
                value={logFollowUp}
                onChange={(e) => setLogFollowUp(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>
          <div>
            <div style={labelStyle}>Summary *</div>
            <input
              type="text"
              value={logSummary}
              onChange={(e) => setLogSummary(e.target.value)}
              placeholder="Brief summary of the interaction"
              style={inputStyle}
              autoFocus
            />
          </div>
          <div>
            <div style={labelStyle}>Details</div>
            <textarea
              value={logDetails}
              onChange={(e) => setLogDetails(e.target.value)}
              placeholder="Optional detailed notes…"
              rows={3}
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </div>
          {logError && <ErrorBanner message={logError} tokens={tokens} />}
          <button
            type="button"
            onClick={handleLogInteraction}
            disabled={logSaving || !logSummary.trim()}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              border: "none",
              background:
                logSaving || !logSummary.trim()
                  ? tokens.bgSubtle
                  : tokens.accent,
              color:
                logSaving || !logSummary.trim()
                  ? tokens.fgMuted
                  : tokens.accentText,
              fontSize: "0.8rem",
              fontWeight: 600,
              cursor:
                logSaving || !logSummary.trim() ? "not-allowed" : "pointer",
              alignSelf: "flex-end",
              fontFamily: tokens.fontFamily,
            }}
          >
            {logSaving ? "Saving…" : "Log Interaction"}
          </button>
        </div>
      )}

      {/* Timeline list */}
      <div style={{ marginTop: "0.75rem" }}>
        {loadingTimeline ? (
          <div
            style={{
              padding: "1.25rem",
              textAlign: "center",
              color: tokens.fgMuted,
              fontSize: "0.85rem",
            }}
          >
            Loading…
          </div>
        ) : timelineError ? (
          <InlineError message={timelineError} tokens={tokens} />
        ) : !timeline || timeline.interactions.length === 0 ? (
          <div
            style={{
              padding: "1.25rem",
              textAlign: "center",
              color: tokens.fgMuted,
              fontSize: "0.85rem",
            }}
          >
            No interactions yet
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            {timeline.interactions.map((ix) => {
              const typeColor = TYPE_COLORS[ix.type] || tokens.fgFaint;
              return (
                <div
                  key={ix.id}
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                    padding: "0.6rem 0",
                    borderBottom: `1px solid ${tokens.border}`,
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
                    <div style={{ fontSize: "0.8rem", fontWeight: 500 }}>
                      {ix.summary}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        gap: "0.75rem",
                        marginTop: "0.2rem",
                      }}
                    >
                      {ix.occurred_at && (
                        <span
                          style={{
                            fontSize: "0.7rem",
                            color: tokens.fgMuted,
                          }}
                        >
                          {new Date(ix.occurred_at).toLocaleDateString()}
                        </span>
                      )}
                      {ix.follow_up_date && (
                        <span
                          style={{
                            fontSize: "0.7rem",
                            color: TYPE_COLORS.call,
                          }}
                        >
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
  );
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function ContactFormFields({
  fields,
  onChange,
  tokens,
  labelStyle,
  inputStyle,
}: {
  fields: EditableFields;
  onChange: <K extends keyof EditableFields>(
    key: K,
    value: EditableFields[K],
  ) => void;
  tokens: ReturnType<typeof useStyleTokens>;
  labelStyle: React.CSSProperties;
  inputStyle: React.CSSProperties;
}): React.ReactElement {
  return (
    <>
      <div>
        <div style={labelStyle}>Name *</div>
        <input
          type="text"
          value={fields.name}
          onChange={(e) => onChange("name", e.target.value)}
          placeholder="Full name"
          style={inputStyle}
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
          <div style={labelStyle}>Email</div>
          <input
            type="email"
            value={fields.email}
            onChange={(e) => onChange("email", e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <div style={labelStyle}>Phone</div>
          <input
            type="tel"
            value={fields.phone}
            onChange={(e) => onChange("phone", e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <div style={labelStyle}>Company</div>
          <input
            type="text"
            value={fields.company}
            onChange={(e) => onChange("company", e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <div style={labelStyle}>Role</div>
          <input
            type="text"
            value={fields.role}
            onChange={(e) => onChange("role", e.target.value)}
            style={inputStyle}
          />
        </div>
      </div>
      <div>
        <div style={labelStyle}>Lead Source</div>
        <select
          value={fields.lead_source}
          onChange={(e) => onChange("lead_source", e.target.value)}
          style={inputStyle}
        >
          <option value="">--</option>
          {LEAD_SOURCES.map((src) => (
            <option key={src} value={src}>
              {src.charAt(0).toUpperCase() + src.slice(1)}
            </option>
          ))}
        </select>
      </div>
      <div>
        <div style={labelStyle}>Notes</div>
        <textarea
          value={fields.notes}
          onChange={(e) => onChange("notes", e.target.value)}
          rows={4}
          placeholder="Free-form notes about this contact"
          style={{
            ...inputStyle,
            resize: "vertical",
            fontFamily: tokens.fontFamily,
          }}
        />
      </div>
    </>
  );
}

function Field({
  label,
  value,
  tokens,
}: {
  label: string;
  value: string | undefined;
  tokens: ReturnType<typeof useStyleTokens>;
}): React.ReactElement {
  return (
    <div>
      <div
        style={{
          fontSize: "0.65rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: tokens.fgMuted,
          marginBottom: "0.2rem",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: "0.85rem", color: tokens.fg }}>
        {value || "--"}
      </div>
    </div>
  );
}

function DealRow({
  deal,
  tokens,
  onClick,
}: {
  deal: Deal;
  tokens: ReturnType<typeof useStyleTokens>;
  onClick: () => void;
}): React.ReactElement {
  const [hover, setHover] = useState(false);
  const [focused, setFocused] = useState(false);
  const stageColor = STAGE_COLORS[deal.stage] || tokens.fgFaint;
  const active = hover || focused;
  return (
    <button
      type="button"
      className="crm-touch-target"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        textAlign: "left",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.5rem 0.6rem",
        borderRadius: "6px",
        border: `1px solid ${active ? tokens.accent : tokens.border}`,
        background: active ? tokens.bgHover : tokens.bgSubtle,
        cursor: "pointer",
        color: tokens.fg,
        fontFamily: tokens.fontFamily,
        width: "100%",
        outline: "none",
        transition: "background 120ms ease, border-color 120ms ease",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "0.8rem",
            fontWeight: 600,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: tokens.fg,
          }}
        >
          {deal.title}
        </div>
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            alignItems: "center",
            marginTop: "0.15rem",
          }}
        >
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
            <span
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                color: tokens.accent,
              }}
            >
              {formatCurrency(deal.value)}
            </span>
          )}
        </div>
      </div>
      {deal.probability != null && (
        <span
          style={{
            fontSize: "0.7rem",
            color: tokens.fgMuted,
            marginLeft: "0.5rem",
          }}
        >
          {deal.probability}%
        </span>
      )}
    </button>
  );
}

function LoadingState({
  tokens,
}: {
  tokens: ReturnType<typeof useStyleTokens>;
}): React.ReactElement {
  return (
    <div
      style={{
        padding: "1.5rem",
        textAlign: "center",
        color: tokens.fgMuted,
        fontSize: "0.85rem",
        fontFamily: tokens.fontFamily,
      }}
    >
      Loading…
    </div>
  );
}

function ErrorBanner({
  message,
  tokens,
}: {
  message: string;
  tokens: ReturnType<typeof useStyleTokens>;
}): React.ReactElement {
  return (
    <div
      style={{
        padding: "0.5rem 0.75rem",
        borderRadius: "4px",
        background: tokens.dangerSoft,
        color: tokens.danger,
        fontSize: "0.8rem",
        fontFamily: tokens.fontFamily,
      }}
    >
      {message}
    </div>
  );
}

function InlineError({
  message,
  tokens,
}: {
  message: string;
  tokens: ReturnType<typeof useStyleTokens>;
}): React.ReactElement {
  return (
    <div
      style={{
        padding: "0.4rem 0.6rem",
        borderRadius: "4px",
        background: tokens.dangerSoft,
        color: tokens.danger,
        fontSize: "0.75rem",
        fontFamily: tokens.fontFamily,
      }}
    >
      {message}
    </div>
  );
}
