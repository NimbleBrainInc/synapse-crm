import { useEffect, useState } from "react";
import { useTheme, useVisibleState } from "@nimblebrain/synapse/react";
import { useDeals } from "./hooks/useDeals";
import { useContacts } from "./hooks/useContacts";
import { usePipelineSummary } from "./hooks/usePipelineSummary";
import type { Deal } from "./hooks/useDeals";
import type { Contact } from "./hooks/useContacts";
import { PipelineSummaryBar } from "./components/PipelineSummaryBar";
import { PipelineView } from "./views/PipelineView";
import { ContactListView } from "./views/ContactListView";
import { RelationshipMap } from "./views/RelationshipMap";
import { DealDetail } from "./components/DealDetail";
import { ContactDetail } from "./components/ContactDetail";

// ---------------------------------------------------------------------------
// Responsive styles
// ---------------------------------------------------------------------------

const RESPONSIVE_STYLES = `
@media (max-width: 640px) {
  .crm-pipeline {
    flex-direction: column !important;
  }
  .crm-pipeline > div {
    flex: none !important;
    width: 100% !important;
    min-width: 0 !important;
    max-width: none !important;
  }
  .crm-dialog-panel {
    width: 100vw !important;
    max-width: 100vw !important;
    border-radius: 0 !important;
  }
}
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  stylesInjected = true;
  const el = document.createElement("style");
  el.textContent = RESPONSIVE_STYLES;
  document.head.appendChild(el);
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

type ViewMode = "pipeline" | "contacts" | "map";

export default function App() {
  const theme = useTheme();
  const { deals, dealsByStage, refresh: refreshDeals } = useDeals();
  const { contacts, refresh: refreshContacts } = useContacts();
  const { summary } = usePipelineSummary();

  const [activeView, setActiveView] = useState<ViewMode>("pipeline");
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);

  const isDark = theme.mode === "dark";
  const accentColor = theme.tokens["--color-text-accent"] || "#2563eb";

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme.mode);
  }, [theme.mode]);

  useEffect(() => {
    injectStyles();
  }, []);

  // Push visible state to the agent
  const pushState = useVisibleState();
  useEffect(() => {
    const activeDeals = deals.filter((d) => d.status === "active" && !d.stage.startsWith("closed_"));
    pushState(
      {
        view: activeView,
        activeDealCount: activeDeals.length,
        contactCount: contacts.filter((c) => c.status === "active").length,
        pipelineValue: summary?.totals.active_value ?? 0,
      },
      `CRM: ${activeView} view, ${activeDeals.length} active deals`,
    );
  }, [activeView, deals, contacts, summary, pushState]);

  const handleRefresh = () => {
    refreshDeals();
    refreshContacts();
  };

  const border = isDark ? "#2d2d44" : "#e0e0e0";

  const buttonBase: React.CSSProperties = {
    padding: "0.4rem 1rem",
    fontSize: "0.8rem",
    border: `1px solid ${isDark ? "#3d3d5c" : "#ccc"}`,
    cursor: "pointer",
    color: isDark ? "#e0e0e0" : "#1a1a2e",
  };

  return (
    <div
      style={{
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        minHeight: "100vh",
        background: isDark ? "#1a1a2e" : "#f8f9fa",
        color: isDark ? "#e0e0e0" : "#1a1a2e",
      }}
    >
      {/* Pipeline Summary Bar */}
      <PipelineSummaryBar summary={summary} isDark={isDark} />

      {/* Header with view toggle */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.6rem 1rem",
          borderBottom: `1px solid ${border}`,
          background: isDark ? "#16162a" : "#ffffff",
        }}
      >
        <div style={{ display: "flex", gap: 0 }}>
          {(["pipeline", "contacts", "map"] as const).map((view, i, arr) => (
            <button
              key={view}
              onClick={() => setActiveView(view)}
              style={{
                ...buttonBase,
                fontWeight: activeView === view ? 600 : 400,
                borderRadius:
                  i === 0 ? "6px 0 0 6px" :
                  i === arr.length - 1 ? "0 6px 6px 0" : "0",
                background: activeView === view
                  ? (isDark ? "#2d2d44" : "#e8e8f0")
                  : (isDark ? "#1a1a2e" : "#fff"),
                textTransform: "capitalize",
                marginLeft: i > 0 ? "-1px" : 0,
              }}
            >
              {view === "pipeline" ? "Pipeline" : view === "contacts" ? "Contacts" : "Map"}
            </button>
          ))}
        </div>
      </header>

      {/* Main content */}
      <main>
        {activeView === "pipeline" ? (
          <PipelineView
            dealsByStage={dealsByStage}
            isDark={isDark}
            onDealClick={(deal) => setSelectedDeal(deal)}
          />
        ) : activeView === "contacts" ? (
          <ContactListView
            contacts={contacts}
            isDark={isDark}
            onContactClick={(contact) => setSelectedContact(contact)}
          />
        ) : (
          <RelationshipMap
            contacts={contacts}
            deals={deals}
            isDark={isDark}
            onContactClick={(contact) => setSelectedContact(contact)}
            onDealClick={(deal) => setSelectedDeal(deal)}
          />
        )}
      </main>

      {/* Deal detail panel */}
      {selectedDeal && (
        <DealDetail
          deal={selectedDeal}
          isDark={isDark}
          accentColor={accentColor}
          onClose={() => setSelectedDeal(null)}
          onRefresh={handleRefresh}
        />
      )}

      {/* Contact detail panel */}
      {selectedContact && (
        <ContactDetail
          contact={selectedContact}
          isDark={isDark}
          accentColor={accentColor}
          onClose={() => setSelectedContact(null)}
          onRefresh={handleRefresh}
        />
      )}
    </div>
  );
}
