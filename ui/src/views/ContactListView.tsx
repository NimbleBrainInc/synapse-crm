import {
  type Column,
  EmptyState,
  SearchField,
  Table,
  Text,
  tokens,
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
      render: (c) => SOURCE_LABELS[c.lead_source ?? "other"] ?? "—",
    },
  ];

  return (
    <div
      style={{
        padding: "1rem",
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
          empty={
            <EmptyState
              title={q ? "No matches" : "No contacts"}
              description={q ? "Try a different search." : "Contacts will appear here."}
            />
          }
        />
      </div>
    </div>
  );
}
