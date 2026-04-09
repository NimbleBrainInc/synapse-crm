import type { Contact } from "../hooks/useContacts";

const SOURCE_LABELS: Record<string, string> = {
  referral: "Referral",
  inbound: "Inbound",
  outbound: "Outbound",
  event: "Event",
  other: "Other",
};

export function ContactListView({
  contacts,
  isDark,
  onContactClick,
}: {
  contacts: Contact[];
  isDark: boolean;
  onContactClick: (contact: Contact) => void;
}) {
  const border = isDark ? "#2d2d44" : "#e0e0e0";
  const headerBg = isDark ? "#16162a" : "#f9fafb";
  const rowHover = isDark ? "#1e1e36" : "#f3f4f6";
  const muted = isDark ? "#888" : "#666";

  const activeContacts = contacts.filter((c) => c.status === "active");

  return (
    <div style={{ padding: "1rem", overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.85rem",
        }}
      >
        <thead>
          <tr style={{ background: headerBg }}>
            {["Name", "Company", "Role", "Email", "Source"].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  padding: "0.6rem 0.75rem",
                  borderBottom: `2px solid ${border}`,
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: muted,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {activeContacts.map((contact) => (
            <tr
              key={contact.id}
              onClick={() => onContactClick(contact)}
              style={{ cursor: "pointer" }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.background = rowHover;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.background = "transparent";
              }}
            >
              <td style={{ padding: "0.6rem 0.75rem", borderBottom: `1px solid ${border}`, fontWeight: 600 }}>
                {contact.name}
              </td>
              <td style={{ padding: "0.6rem 0.75rem", borderBottom: `1px solid ${border}` }}>
                {contact.company || "--"}
              </td>
              <td style={{ padding: "0.6rem 0.75rem", borderBottom: `1px solid ${border}` }}>
                {contact.role || "--"}
              </td>
              <td style={{ padding: "0.6rem 0.75rem", borderBottom: `1px solid ${border}`, color: muted }}>
                {contact.email || "--"}
              </td>
              <td style={{ padding: "0.6rem 0.75rem", borderBottom: `1px solid ${border}` }}>
                {contact.lead_source ? (
                  <span
                    style={{
                      fontSize: "0.7rem",
                      padding: "0.15rem 0.5rem",
                      borderRadius: "10px",
                      background: isDark ? "#2d2d44" : "#e5e7eb",
                      color: isDark ? "#aaa" : "#555",
                    }}
                  >
                    {SOURCE_LABELS[contact.lead_source] || contact.lead_source}
                  </span>
                ) : (
                  "--"
                )}
              </td>
            </tr>
          ))}
          {activeContacts.length === 0 && (
            <tr>
              <td
                colSpan={5}
                style={{
                  padding: "2rem",
                  textAlign: "center",
                  color: muted,
                }}
              >
                No contacts yet
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
