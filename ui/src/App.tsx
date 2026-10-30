import { useEffect, useMemo, useState } from "react";
import { useTheme, useModelContext } from "@nimblebrain/synapse/react";
import { AppFrame, Button, Inline, SegmentedControl, tokens as ui } from "@nimblebrain/synapse/ui";
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
//      across App / DealView / ContactView. Desktop layout is unaffected —
//      the rule only fires below 640px.
//
// The detail panel is now the shared `@nimblebrain/synapse/ui` Drawer — a
// full-height right side-sheet (92% width on mobile) that owns its own chrome.
// ContactListView swaps to a stacked card list below 640px via `useBreakpoint`.

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
  const pushState = useModelContext();
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

  return (
    <AppFrame contentWidth="full">
      <AppFrame.Header
        style={{
          padding: 0,
          borderBottom: `1px solid ${tokens.border}`,
          background: tokens.bgRaised,
        }}
      >
        <PipelineSummaryBar summary={summary} />
        <Inline justify="between" wrap style={{ padding: `0.6rem ${ui.gutter}` }}>
          <SegmentedControl
            aria-label="CRM view"
            options={[
              { value: "pipeline" as const, label: "Pipeline" },
              { value: "contacts" as const, label: "Contacts" },
            ]}
            value={activeView}
            onChange={setActiveView}
          />
          <Button
            type="button"
            className="crm-touch-target"
            onClick={() => panel.push({ kind: activeView === "pipeline" ? "deal-create" : "contact-create" })}
          >
            {activeView === "pipeline" ? "New deal" : "New contact"}
          </Button>
        </Inline>
      </AppFrame.Header>

      <AppFrame.Body bleed>
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
      </AppFrame.Body>

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
    </AppFrame>
  );
}
