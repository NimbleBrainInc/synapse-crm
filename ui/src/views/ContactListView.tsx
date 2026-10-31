import {
  type Column,
  EmptyState,
  ListRow,
  SearchField,
  Stack,
  Table,
  Text,
  tokens,
  useBreakpoint,
} from "@nimblebrain/synapse/ui";
import { useMemo, useState } from "react";
import type { Contact } from "../hooks/useContacts";

const SOURCE_LABELS: Record<string, string> = {
  referral: "Referral",
  inbound: "Inbound",
  outbound: "Outbound",
  event: "Event",
  other: "Other",
};

const CURRENCY = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

type DealsByContact = Map<string, { count: number; activeValue: number }>;

function Dash() {
  return (
    <Text size="sm" tone="faint">
      —
    </Text>
  );
}

/** Deals summary: 0 / active>0 (count · value) / all-closed (count · closed). */
function DealsCell({ count, activeValue }: { count: number; activeValue: number }) {
  if (count === 0) return <Dash />;
  if (activeValue > 0) {
    return (
      <Text size="sm">
        {count} ·{" "}
        <span style={{ color: tokens.accent, fontWeight: 600 }}>
          {CURRENCY.format(activeValue)}
        </span>
      </Text>
    );
  }
  return (
    <Text size="sm" tone="faint">
      {count} · closed
    </Text>
  );
}

export function ContactListView({
  contacts,
  dealsByContact,
  onContactClick,
}: {
  contacts: Contact[];
  dealsByContact: DealsByContact;
  onContactClick: (contact: Contact) => void;
}) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const filtered = useMemo(() => {
    const active = contacts.filter((c) => c.status === "active");
    if (!q) return active;
    return active.filter(
      (c) =>
        (c.name || "").toLowerCase().includes(q) ||
        (c.company || "").toLowerCase().includes(q) ||
        (c.email || "").toLowerCase().includes(q),
    );
  }, [contacts, q]);

  const columns: Column<Contact>[] = [
    {
      key: "name",
      header: "Name",
      render: (c) => (
        <Text size="sm" weight="medium">
          {c.name}
        </Text>
      ),
    },
    { key: "company", header: "Company", render: (c) => c.company || <Dash /> },
    { key: "role", header: "Role", render: (c) => c.role || <Dash /> },
    {
      key: "deals",
      header: "Deals",
      align: "right",
      render: (c) => {
        const d = dealsByContact.get(c.id);
        return <DealsCell count={d?.count ?? 0} activeValue={d?.activeValue ?? 0} />;
      },
    },
    { key: "email", header: "Email", render: (c) => c.email || <Dash /> },
    {
      key: "source",
      header: "Source",
      render: (c) => (c.lead_source ? (SOURCE_LABELS[c.lead_source] ?? <Dash />) : <Dash />),
    },
  ];

  // Container-width breakpoint (not viewport): the app renders in an iframe pane
  // the host sizes, so a 6-column table would horizontally-scroll on a phone.
  // Below 640px we fall back to a stacked card list with comfortable tap targets.
  const { ref, isNarrow } = useBreakpoint<HTMLDivElement>(640);

  const emptyState = (
    <EmptyState
      title={q ? "No matches" : "No contacts"}
      description={q ? `No contacts match "${query}".` : "Contacts will appear here."}
    />
  );

  return (
    <div
      ref={ref}
      style={{
        padding: `1rem ${tokens.gutter}`,
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        height: "100%",
        minHeight: 0,
      }}
    >
      <SearchField
        variant="boxed"
        placeholder="Search by name, company, or email…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ maxWidth: 420 }}
      />
      {isNarrow ? (
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
          {filtered.length === 0 ? (
            emptyState
          ) : (
            <Stack gap="0.5rem">
              {filtered.map((c) => {
                const d = dealsByContact.get(c.id);
                const parts = [c.company, c.role].filter(
                  (p): p is string => !!p && p.trim() !== "",
                );
                return (
                  <ListRow
                    key={c.id}
                    interactive
                    onClick={() => onContactClick(c)}
                    title={
                      <Text size="sm" weight="medium">
                        {c.name}
                      </Text>
                    }
                    meta={
                      <Stack gap="0.1rem">
                        <Text size="sm" tone={parts.length ? "muted" : "faint"}>
                          {parts.length ? parts.join(" · ") : "—"}
                        </Text>
                        <Text size="sm" tone="muted">
                          {c.email || "—"}
                        </Text>
                      </Stack>
                    }
                    trailing={
                      <DealsCell count={d?.count ?? 0} activeValue={d?.activeValue ?? 0} />
                    }
                    style={{
                      minHeight: 44,
                      border: `1px solid ${tokens.border}`,
                      borderRadius: tokens.radiusMd,
                      background: tokens.bgRaised,
                    }}
                  />
                );
              })}
            </Stack>
          )}
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            border: `1px solid ${tokens.border}`,
            borderRadius: tokens.radiusMd,
          }}
        >
          <Table
            data={filtered}
            columns={columns}
            rowKey={(c) => c.id}
            onRowClick={onContactClick}
            empty={emptyState}
          />
        </div>
      )}
    </div>
  );
}
