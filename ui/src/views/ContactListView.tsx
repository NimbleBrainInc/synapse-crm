import { useEffect, useState, type ReactNode } from "react";
import type { Contact } from "../hooks/useContacts";
import { useStyleTokens } from "../tokens";

const SOURCE_LABELS: Record<string, string> = {
  referral: "Referral",
  inbound: "Inbound",
  outbound: "Outbound",
  event: "Event",
  other: "Other",
};

// Inline currency formatter — matches existing `formatCurrency` patterns used
// in sibling views (no decimals; "$" prefix). Local to this view; lift to a
// shared util if a third caller appears.
const CURRENCY_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function formatCurrency(value: number): string {
  return CURRENCY_FORMATTER.format(value);
}

// Inline mobile detection. matchMedia + listener; only ContactListView uses
// this today. Promote to a shared hook if a second view picks it up.
function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(max-width: 640px)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(max-width: 640px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    // Sync once in case viewport changed between render and effect.
    setIsMobile(mql.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return isMobile;
}

// Shared three-state deals rendering: 0 / active>0 / all-closed.
function renderDealsCell(
  count: number,
  activeValue: number,
  tokens: ReturnType<typeof useStyleTokens>,
): ReactNode {
  if (count === 0) {
    return <span style={{ color: tokens.fgFaint }}>—</span>;
  }
  if (activeValue > 0) {
    return (
      <span>
        {count}
        {" · "}
        <span style={{ color: tokens.accent, fontWeight: 600 }}>
          {formatCurrency(activeValue)}
        </span>
      </span>
    );
  }
  return (
    <span style={{ color: tokens.fgFaint }}>
      {count}
      {" · closed"}
    </span>
  );
}

export function ContactListView({
  contacts,
  dealsByContact,
  onContactClick,
}: {
  contacts: Contact[];
  dealsByContact: Map<string, { count: number; activeValue: number }>;
  onContactClick: (contact: Contact) => void;
}) {
  const tokens = useStyleTokens();
  const isMobile = useIsMobile();
  const [query, setQuery] = useState<string>("");

  const activeContacts = contacts.filter((c) => c.status === "active");

  // Case-insensitive substring match across name/company/email. Empty query
  // returns the full list (existing behavior preserved).
  const trimmedQuery = query.trim().toLowerCase();
  const filteredContacts = trimmedQuery
    ? activeContacts.filter((c) => {
        const name = (c.name || "").toLowerCase();
        const company = (c.company || "").toLowerCase();
        const email = (c.email || "").toLowerCase();
        return (
          name.includes(trimmedQuery) ||
          company.includes(trimmedQuery) ||
          email.includes(trimmedQuery)
        );
      })
    : activeContacts;

  // Header order: Name, Company, Role, Deals, Email, Source. "Deals" is
  // numeric and right-aligned.
  const HEADERS: { label: string; align: "left" | "right" }[] = [
    { label: "Name", align: "left" },
    { label: "Company", align: "left" },
    { label: "Role", align: "left" },
    { label: "Deals", align: "right" },
    { label: "Email", align: "left" },
    { label: "Source", align: "left" },
  ];

  const noMatches = trimmedQuery && filteredContacts.length === 0;

  return (
    <div style={{ padding: "1rem", overflowX: "auto" }}>
      <div
        style={{
          position: "relative",
          width: "100%",
          maxWidth: "420px",
          marginBottom: "0.75rem",
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, company, or email…"
          style={{
            width: "100%",
            padding: "0.5rem 2rem 0.5rem 0.75rem",
            fontSize: "0.85rem",
            background: tokens.bg,
            color: tokens.fg,
            border: `1px solid ${tokens.border}`,
            borderRadius: "6px",
            outline: "none",
            boxSizing: "border-box",
          }}
        />
        {query && (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => setQuery("")}
            style={{
              position: "absolute",
              right: "0.4rem",
              top: "50%",
              transform: "translateY(-50%)",
              width: "1.5rem",
              height: "1.5rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: tokens.fgMuted,
              fontSize: "1rem",
              lineHeight: 1,
              padding: 0,
              borderRadius: "4px",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                tokens.bgHover;
              (e.currentTarget as HTMLButtonElement).style.color = tokens.fg;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "none";
              (e.currentTarget as HTMLButtonElement).style.color =
                tokens.fgMuted;
            }}
          >
            {"×"}
          </button>
        )}
      </div>
      {isMobile ? (
        <CardList
          contacts={filteredContacts}
          dealsByContact={dealsByContact}
          onContactClick={onContactClick}
          tokens={tokens}
          query={trimmedQuery}
          noMatches={!!noMatches}
        />
      ) : (
        <TableView
          contacts={filteredContacts}
          dealsByContact={dealsByContact}
          onContactClick={onContactClick}
          tokens={tokens}
          headers={HEADERS}
          query={trimmedQuery}
          noMatches={!!noMatches}
        />
      )}
    </div>
  );
}

function TableView({
  contacts,
  dealsByContact,
  onContactClick,
  tokens,
  headers,
  query,
  noMatches,
}: {
  contacts: Contact[];
  dealsByContact: Map<string, { count: number; activeValue: number }>;
  onContactClick: (contact: Contact) => void;
  tokens: ReturnType<typeof useStyleTokens>;
  headers: { label: string; align: "left" | "right" }[];
  query: string;
  noMatches: boolean;
}) {
  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "0.85rem",
      }}
    >
      <thead>
        <tr style={{ background: tokens.bgRaised }}>
          {headers.map((h) => (
            <th
              key={h.label}
              style={{
                textAlign: h.align,
                padding: "0.6rem 0.75rem",
                borderBottom: `2px solid ${tokens.border}`,
                fontSize: "0.7rem",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                color: tokens.fgMuted,
              }}
            >
              {h.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {contacts.map((contact) => {
          const dealAgg = dealsByContact.get(contact.id);
          const count = dealAgg?.count ?? 0;
          const activeValue = dealAgg?.activeValue ?? 0;
          return (
            <tr
              key={contact.id}
              onClick={() => onContactClick(contact)}
              style={{ cursor: "pointer" }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.background =
                  tokens.bgHover;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.background =
                  "transparent";
              }}
            >
              <td
                style={{
                  padding: "0.6rem 0.75rem",
                  borderBottom: `1px solid ${tokens.border}`,
                  fontWeight: 600,
                }}
              >
                {contact.name}
              </td>
              <td
                style={{
                  padding: "0.6rem 0.75rem",
                  borderBottom: `1px solid ${tokens.border}`,
                }}
              >
                {contact.company || "--"}
              </td>
              <td
                style={{
                  padding: "0.6rem 0.75rem",
                  borderBottom: `1px solid ${tokens.border}`,
                }}
              >
                {contact.role || "--"}
              </td>
              <td
                style={{
                  padding: "0.6rem 0.75rem",
                  borderBottom: `1px solid ${tokens.border}`,
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {renderDealsCell(count, activeValue, tokens)}
              </td>
              <td
                style={{
                  padding: "0.6rem 0.75rem",
                  borderBottom: `1px solid ${tokens.border}`,
                  color: tokens.fgMuted,
                }}
              >
                {contact.email || "--"}
              </td>
              <td
                style={{
                  padding: "0.6rem 0.75rem",
                  borderBottom: `1px solid ${tokens.border}`,
                }}
              >
                {contact.lead_source ? (
                  <span
                    style={{
                      fontSize: "0.7rem",
                      padding: "0.15rem 0.5rem",
                      borderRadius: "10px",
                      background: tokens.bgSubtle,
                      color: tokens.fgMuted,
                    }}
                  >
                    {SOURCE_LABELS[contact.lead_source] || contact.lead_source}
                  </span>
                ) : (
                  "--"
                )}
              </td>
            </tr>
          );
        })}
        {contacts.length === 0 && (
          <tr>
            <td
              colSpan={headers.length}
              style={{
                padding: "2rem",
                textAlign: "center",
                color: tokens.fgMuted,
              }}
            >
              {noMatches ? `No contacts match "${query}"` : "No contacts yet"}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function CardList({
  contacts,
  dealsByContact,
  onContactClick,
  tokens,
  query,
  noMatches,
}: {
  contacts: Contact[];
  dealsByContact: Map<string, { count: number; activeValue: number }>;
  onContactClick: (contact: Contact) => void;
  tokens: ReturnType<typeof useStyleTokens>;
  query: string;
  noMatches: boolean;
}) {
  if (contacts.length === 0) {
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: tokens.fgMuted,
          border: `1px solid ${tokens.border}`,
          borderRadius: "8px",
          background: tokens.bgRaised,
        }}
      >
        {noMatches ? `No contacts match "${query}"` : "No contacts yet"}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {contacts.map((contact) => {
        const dealAgg = dealsByContact.get(contact.id);
        const count = dealAgg?.count ?? 0;
        const activeValue = dealAgg?.activeValue ?? 0;

        // Second-row composition: company · role with separator handling.
        const parts = [contact.company, contact.role].filter(
          (p): p is string => !!p && p.trim() !== "",
        );
        const hasSubline = parts.length > 0;

        return (
          <button
            key={contact.id}
            type="button"
            className="crm-touch-target"
            onClick={() => onContactClick(contact)}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                tokens.bgHover;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                tokens.bgRaised;
            }}
            onFocus={(e) => {
              (e.currentTarget as HTMLButtonElement).style.outline =
                `2px solid ${tokens.accent}`;
            }}
            onBlur={(e) => {
              (e.currentTarget as HTMLButtonElement).style.outline = "none";
            }}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.25rem",
              width: "100%",
              textAlign: "left",
              padding: "0.75rem",
              border: `1px solid ${tokens.border}`,
              borderRadius: "8px",
              background: tokens.bgRaised,
              color: tokens.fg,
              cursor: "pointer",
              font: "inherit",
              outline: "none",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "0.5rem",
              }}
            >
              <span
                style={{
                  fontWeight: 600,
                  fontSize: "0.95rem",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {contact.name}
              </span>
              <span
                style={{
                  fontSize: "0.8rem",
                  fontVariantNumeric: "tabular-nums",
                  flexShrink: 0,
                }}
              >
                {renderDealsCell(count, activeValue, tokens)}
              </span>
            </div>
            <div
              style={{
                fontSize: "0.8rem",
                color: hasSubline ? tokens.fgMuted : tokens.fgFaint,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {hasSubline ? parts.join(" · ") : "—"}
            </div>
            <div
              style={{
                fontSize: "0.8rem",
                color: tokens.fgMuted,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {contact.email || "—"}
            </div>
          </button>
        );
      })}
    </div>
  );
}
