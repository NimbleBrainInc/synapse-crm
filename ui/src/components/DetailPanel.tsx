import { Drawer } from "@nimblebrain/synapse/ui";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import { useStyleTokens } from "../tokens";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type PanelEntry =
  | { kind: "deal"; id: string; mode: "view" | "edit" }
  | { kind: "deal-create" }
  | { kind: "contact"; id: string; mode: "view" | "edit" }
  | { kind: "contact-create" };

export interface PanelStackController {
  push(entry: PanelEntry): void;
  pop(): void;
  /** swap mode/identity at the top of the stack without changing depth */
  replaceTop(entry: PanelEntry): void;
  close(): void;
  stack: PanelEntry[];
}

/**
 * Body render-prop. Returns the body React node directly. Title and actions
 * are registered by the body via {@link usePanelHeader} (helmet-style), so
 * they can depend on data the body fetches/owns without violating the Rules
 * of Hooks at the call site.
 */
export type RenderEntryFn = (
  entry: PanelEntry,
  controller: PanelStackController,
) => React.ReactNode;

/** Header content registered by a body component. */
export interface PanelHeader {
  title?: string;
  actions?: React.ReactNode;
}

interface DetailPanelProps {
  controller: PanelStackController;
  renderEntry: RenderEntryFn;
}

const MAX_STACK_DEPTH = 8;

// ---------------------------------------------------------------------------
// usePanelStack — hook owning the stack state + stable controller identity
// ---------------------------------------------------------------------------

function entriesEqual(a: PanelEntry, b: PanelEntry): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "deal" && b.kind === "deal") {
    return a.id === b.id && a.mode === b.mode;
  }
  if (a.kind === "contact" && b.kind === "contact") {
    return a.id === b.id && a.mode === b.mode;
  }
  // deal-create / contact-create are singletons by kind
  return true;
}

export function usePanelStack(): PanelStackController {
  const [stack, setStack] = useState<PanelEntry[]>([]);

  const push = useCallback((entry: PanelEntry) => {
    setStack((prev) => {
      const top = prev[prev.length - 1];
      // Dedupe consecutive identical pushes (e.g. accidental double-click)
      if (top && entriesEqual(top, entry)) return prev;
      // Cap depth — beyond MAX_STACK_DEPTH, treat as replaceTop so the user
      // never gets trapped in a runaway stack.
      if (prev.length >= MAX_STACK_DEPTH) {
        return [...prev.slice(0, MAX_STACK_DEPTH - 1), entry];
      }
      return [...prev, entry];
    });
  }, []);

  const pop = useCallback(() => {
    setStack((prev) => (prev.length === 0 ? prev : prev.slice(0, -1)));
  }, []);

  const replaceTop = useCallback((entry: PanelEntry) => {
    setStack((prev) => {
      if (prev.length === 0) return [entry];
      return [...prev.slice(0, -1), entry];
    });
  }, []);

  const close = useCallback(() => {
    setStack((prev) => (prev.length === 0 ? prev : []));
  }, []);

  // Stable controller identity. Functions are stable via useCallback;
  // `stack` is the only thing that changes, and consumers expect that.
  return useMemo<PanelStackController>(
    () => ({ push, pop, replaceTop, close, stack }),
    [push, pop, replaceTop, close, stack],
  );
}

// ---------------------------------------------------------------------------
// Header context — body components register title/actions via usePanelHeader
// ---------------------------------------------------------------------------

interface PanelHeaderContextValue {
  setHeader: (header: PanelHeader) => void;
  clearHeader: () => void;
}

const PanelHeaderContext = createContext<PanelHeaderContextValue | null>(null);

/**
 * Register header content (title, actions) for the enclosing DetailPanel.
 * Call from inside a body component rendered by {@link RenderEntryFn}.
 * If used outside a DetailPanel, this hook is a no-op.
 */
export function usePanelHeader(header: PanelHeader): void {
  const ctx = useContext(PanelHeaderContext);
  const { title, actions } = header;
  useEffect(() => {
    if (!ctx) return;
    ctx.setHeader({ title, actions });
    return () => {
      ctx.clearHeader();
    };
  }, [ctx, title, actions]);
}

// ---------------------------------------------------------------------------
// DetailPanel — now a thin shell over the shared Drawer. The panel *stack*
// (push/pop, depth) and helmet-style header registration stay here; the
// overlay chrome, slide animation, scrim, focus-trap, focus restore, and
// scroll-lock are all provided by Drawer. Escape pops one level (then closes)
// via Drawer's onEscape; the scrim and the close button fully close.
// ---------------------------------------------------------------------------

export function DetailPanel({
  controller,
  renderEntry,
}: DetailPanelProps): React.ReactElement | null {
  const tokens = useStyleTokens();
  const { stack } = controller;
  const isOpen = stack.length > 0;
  const top = stack[stack.length - 1];

  // Header state populated by body components via usePanelHeader.
  const [header, setHeaderState] = useState<PanelHeader>({});
  const setHeader = useCallback((next: PanelHeader) => setHeaderState(next), []);
  const clearHeader = useCallback(() => setHeaderState({}), []);
  const headerCtx = useMemo<PanelHeaderContextValue>(
    () => ({ setHeader, clearHeader }),
    [setHeader, clearHeader],
  );

  // The body owns the header: its usePanelHeader effect sets title/actions on
  // mount and clears on unmount. (We deliberately don't clear here on entry
  // change — a parent clear effect runs AFTER the child's set effect and would
  // clobber the freshly-registered title, blanking the header.)

  // Move focus to the panel content on open and whenever the top entry changes
  // (nested push/pop). The Drawer handles focus on open/close, but a nested
  // push (deal → contact) keeps the same dialog open, so we re-focus here to
  // carry keyboard users to the new panel — parity with the pre-Drawer panel.
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bodyRef.current?.focus();
  }, [stack.length]);

  if (!isOpen || !top) return null;

  const body = renderEntry(top, controller);
  const depth = stack.length;
  const headerTitle = header.title ?? "";

  return (
    <Drawer
      open
      onClose={() => controller.close()}
      onEscape={() => (controller.stack.length > 1 ? controller.pop() : controller.close())}
      side="right"
      width={480}
      aria-label={headerTitle}
    >
      <Drawer.Header onClose={() => controller.close()}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
          {depth > 1 && (
            <button
              type="button"
              aria-label="Back"
              onClick={() => controller.pop()}
              style={{
                flexShrink: 0,
                background: "none",
                border: `1px solid ${tokens.border}`,
                borderRadius: "4px",
                width: 28,
                height: 28,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                color: tokens.fgMuted,
                fontFamily: tokens.fontFamily,
                fontSize: "1rem",
                lineHeight: 1,
              }}
            >
              {"‹"}
            </button>
          )}
          <span
            style={{
              flex: 1,
              minWidth: 0,
              fontWeight: 600,
              color: tokens.fg,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={headerTitle}
          >
            {headerTitle}
          </span>
          {header.actions && (
            <div
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexShrink: 0 }}
            >
              {header.actions}
            </div>
          )}
        </div>
      </Drawer.Header>
      <Drawer.Body>
        <div ref={bodyRef} tabIndex={-1} style={{ outline: "none" }}>
          <PanelHeaderContext.Provider value={headerCtx}>{body}</PanelHeaderContext.Provider>
        </div>
      </Drawer.Body>
    </Drawer>
  );
}
