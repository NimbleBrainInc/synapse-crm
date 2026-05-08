import { useEffect, useMemo, useState } from "react";
import type React from "react";
import { useTheme, useVisibleState } from "@nimblebrain/synapse/react";
import { useDeals } from "./hooks/useDeals";
import { useContacts } from "./hooks/useContacts";
import { usePipelineSummary } from "./hooks/usePipelineSummary";
import { useStyleTokens } from "./tokens";
import { PipelineSummaryBar } from "./components/PipelineSummaryBar";
import { PipelineView } from "./views/PipelineView";
import { ContactListView } from "./views/ContactListView";
import {
  DetailPanel,
  usePanelStack,
  type PanelEntry,
} from "./components/DetailPanel";
import { DealView } from "./components/DealView";
import { ContactView } from "./components/ContactView";

// ---------------------------------------------------------------------------
// Responsive styles
// ---------------------------------------------------------------------------
//
// Two responsive concerns live here:
//   1. Pipeline column stacking on narrow viewports.
//   2. 44px minimum hit-target sizing on mobile (Apple HIG / Material).
//      Applied via `.crm-touch-target` to interactive elements scattered
//      across App / DetailPanel / DealView / ContactView. Desktop layout
//      is unaffected — the rule only fires below 640px.
//
// DetailPanel owns the rest of its own responsive chrome.

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
  .crm-touch-target {
    min-height: 44px !important;
    padding-top: 0.6rem !important;
    padding-bottom: 0.6rem !important;
  }
  .crm-touch-target.crm-touch-icon {
    min-width: 44px !important;
    width: auto !important;
    height: auto !important;
    padding: 0 !important;
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
// Visible-state summary
// ---------------------------------------------------------------------------

type ViewMode = "pipeline" | "contacts";

function summarize(
  view: ViewMode,
  activeDealCount: number,
  top: PanelEntry | null,
): string {
  const base = `CRM: ${view} view, ${activeDealCount} active deals`;
  if (!top) return base;
  switch (top.kind) {
    case "deal":
      return `${base}, viewing deal id ${top.id} (mode: ${top.mode})`;
    case "deal-create":
      return `${base}, creating new deal`;
    case "contact":
      return `${base}, viewing contact id ${top.id} (mode: ${top.mode})`;
    case "contact-create":
      return `${base}, creating new contact`;
  }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const theme = useTheme();
  const tokens = useStyleTokens();
  const { deals, dealsByStage, refresh: refreshDeals } = useDeals();
  const { contacts, refresh: refreshContacts } = useContacts();
  const { summary } = usePipelineSummary();

  const [activeView, setActiveView] = useState<ViewMode>("pipeline");
  const panel = usePanelStack();

  // Per-contact deal aggregates for the contacts table. O(deals) once, O(1)
  // per row at render time. A deal contributes to count for every
  // `belongs_to` relationship it has; it contributes its `value` to
  // `activeValue` only if the deal itself is active and not in a closed_*
  // stage.
  const dealsByContact = useMemo(() => {
    const map = new Map<string, { count: number; activeValue: number }>();
    for (const deal of deals) {
      const isActive =
        deal.status === "active" && !deal.stage.startsWith("closed_");
      const value = deal.value ?? 0;
      for (const rel of deal.relationships ?? []) {
        if (rel.rel !== "belongs_to") continue;
        const entry = map.get(rel.target) ?? { count: 0, activeValue: 0 };
        entry.count += 1;
        if (isActive) entry.activeValue += value;
        map.set(rel.target, entry);
      }
    }
    return map;
  }, [deals]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme.mode);
  }, [theme.mode]);

  useEffect(() => {
    injectStyles();
  }, []);

  // Push visible state to the agent. IDs only — agent fetches the rest via
  // tools. Avoid leaking notes / titles / freeform text here.
  const pushState = useVisibleState();
  useEffect(() => {
    const activeDealCount = deals.filter(
      (d) => d.status === "active" && !d.stage.startsWith("closed_"),
    ).length;
    const contactCount = contacts.filter((c) => c.status === "active").length;
    const pipelineValue = summary?.totals.active_value ?? 0;
    const top = panel.stack[panel.stack.length - 1] ?? null;
    pushState(
      {
        view: activeView,
        activeDealCount,
        contactCount,
        pipelineValue,
        openPanel: top,
        panelDepth: panel.stack.length,
      },
      summarize(activeView, activeDealCount, top),
    );
  }, [activeView, deals, contacts, summary, panel.stack, pushState]);

  const handleRefresh = () => {
    refreshDeals();
    refreshContacts();
  };

  // Shared base for the view-toggle buttons. Active state uses
  // `tokens.accentSoft` to read as a brand-tinted highlight.
  const buttonBase: React.CSSProperties = {
    padding: "0.4rem 1rem",
    fontSize: "0.8rem",
    border: `1px solid ${tokens.border}`,
    cursor: "pointer",
    color: tokens.fg,
    fontFamily: tokens.fontFamily,
  };

  return (
    <div
      style={{
        fontFamily: tokens.fontFamily,
        minHeight: "100vh",
        background: tokens.bg,
        color: tokens.fg,
      }}
    >
      <PipelineSummaryBar summary={summary} />

      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.6rem 1rem",
          borderBottom: `1px solid ${tokens.border}`,
          background: tokens.bgRaised,
        }}
      >
        <div style={{ display: "flex", gap: 0 }}>
          {(["pipeline", "contacts"] as const).map((view, i, arr) => {
            const isActive = activeView === view;
            return (
              <button
                key={view}
                type="button"
                className="crm-touch-target"
                onClick={() => setActiveView(view)}
                style={{
                  ...buttonBase,
                  fontWeight: isActive ? 600 : 400,
                  borderRadius:
                    i === 0
                      ? "6px 0 0 6px"
                      : i === arr.length - 1
                        ? "0 6px 6px 0"
                        : "0",
                  background: isActive ? tokens.accentSoft : tokens.bg,
                  color: isActive ? tokens.accent : tokens.fg,
                  borderColor: isActive ? tokens.accent : tokens.border,
                  textTransform: "capitalize",
                  marginLeft: i > 0 ? "-1px" : 0,
                  zIndex: isActive ? 1 : 0,
                  position: "relative",
                }}
              >
                {view === "pipeline" ? "Pipeline" : "Contacts"}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          className="crm-touch-target"
          onClick={() =>
            panel.push({
              kind: activeView === "pipeline" ? "deal-create" : "contact-create",
            })
          }
          style={{
            fontFamily: tokens.fontFamily,
            fontSize: "0.85rem",
            fontWeight: 600,
            padding: "0.4rem 0.85rem",
            borderRadius: "6px",
            cursor: "pointer",
            lineHeight: 1.2,
            border: `1px solid ${tokens.accent}`,
            background: "transparent",
            color: tokens.accent,
          }}
        >
          {activeView === "pipeline" ? "+ New Deal" : "+ New Contact"}
        </button>
      </header>

      <main>
        {activeView === "pipeline" ? (
          <PipelineView
            dealsByStage={dealsByStage}
            onDealClick={(deal) =>
              panel.push({ kind: "deal", id: deal.id, mode: "view" })
            }
          />
        ) : (
          <ContactListView
            contacts={contacts}
            dealsByContact={dealsByContact}
            onContactClick={(contact) =>
              panel.push({ kind: "contact", id: contact.id, mode: "view" })
            }
          />
        )}
      </main>

      <DetailPanel
        controller={panel}
        renderEntry={(entry, ctrl) => {
          switch (entry.kind) {
            case "deal":
              return (
                <DealView
                  dealId={entry.id}
                  mode={entry.mode}
                  controller={ctrl}
                  onChanged={handleRefresh}
                />
              );
            case "deal-create":
              return (
                <DealView
                  dealId={null}
                  mode="create"
                  controller={ctrl}
                  onChanged={handleRefresh}
                />
              );
            case "contact":
              return (
                <ContactView
                  contactId={entry.id}
                  mode={entry.mode}
                  controller={ctrl}
                  onChanged={handleRefresh}
                />
              );
            case "contact-create":
              return (
                <ContactView
                  contactId={null}
                  mode="create"
                  controller={ctrl}
                  onChanged={handleRefresh}
                />
              );
            default: {
              // Exhaustiveness check — adding a new PanelEntry kind without
              // wiring a case here is a TypeScript compile error.
              const _exhaustive: never = entry;
              return _exhaustive;
            }
          }
        }}
      />
    </div>
  );
}
