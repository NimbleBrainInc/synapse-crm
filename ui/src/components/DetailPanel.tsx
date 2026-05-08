import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_STACK_DEPTH = 8;
const STYLE_TAG_ID = "crm-detail-panel-styles";

const PANEL_STYLES = `
.crm-detail-panel-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  z-index: 1000;
}
.crm-detail-panel {
  width: 480px;
  max-width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transform: translateX(100%);
  transition: transform 200ms ease-out;
  outline: none;
}
.crm-detail-panel[data-mounted="true"] {
  transform: translateX(0);
}
@media (max-width: 640px) {
  .crm-detail-panel-overlay {
    align-items: flex-end;
    justify-content: stretch;
  }
  .crm-detail-panel {
    width: 100vw;
    max-width: 100vw;
    height: 100vh;
    border-radius: 0;
    transform: translateY(100%);
  }
  .crm-detail-panel[data-mounted="true"] {
    transform: translateY(0);
  }
}
`;

// Ref-counted style-tag injection so concurrent panels share one <style> node
// without clobbering each other on unmount.
let styleRefCount = 0;
function acquireStyleTag() {
  if (typeof document === "undefined") return;
  if (styleRefCount === 0 && !document.getElementById(STYLE_TAG_ID)) {
    const el = document.createElement("style");
    el.id = STYLE_TAG_ID;
    el.textContent = PANEL_STYLES;
    document.head.appendChild(el);
  }
  styleRefCount += 1;
}
function releaseStyleTag() {
  if (typeof document === "undefined") return;
  styleRefCount = Math.max(0, styleRefCount - 1);
  if (styleRefCount === 0) {
    const el = document.getElementById(STYLE_TAG_ID);
    if (el) el.remove();
  }
}

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
 *
 * The chrome's title/actions slots stay empty until this hook fires its
 * effect, so a freshly-pushed entry shows blank header for one frame and
 * then fills in — preferable to a stale-title flash from the previous body.
 *
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
// Focus-trap helper
// ---------------------------------------------------------------------------

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((el) => !el.hasAttribute("disabled") && el.tabIndex !== -1);
}

// ---------------------------------------------------------------------------
// DetailPanel — chrome (overlay, slide, header, body); body is render-prop
// ---------------------------------------------------------------------------

export function DetailPanel({
  controller,
  renderEntry,
}: DetailPanelProps): React.ReactElement | null {
  const tokens = useStyleTokens();
  const { stack } = controller;
  const isOpen = stack.length > 0;
  const top = stack[stack.length - 1];

  const panelRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const [mounted, setMounted] = useState(false);

  // Header state populated by body components via usePanelHeader.
  const [header, setHeaderState] = useState<PanelHeader>({});

  // Stable context functions — body effects depend on these via the ctx
  // identity, and we don't want every header update to re-fire the body's
  // own effect.
  const setHeader = useCallback((next: PanelHeader) => {
    setHeaderState(next);
  }, []);
  const clearHeader = useCallback(() => {
    setHeaderState({});
  }, []);
  const headerCtx = useMemo<PanelHeaderContextValue>(
    () => ({ setHeader, clearHeader }),
    [setHeader, clearHeader],
  );

  // Clear header whenever the top entry changes (push / pop / replaceTop /
  // close). The new body's effect runs after this state update and fills the
  // header back in — produces a one-frame blank slot rather than a flash of
  // the previous entry's title.
  // Identity key: kind + (id if present) + (mode if present).
  const topKey = top ? entryKey(top) : null;
  useEffect(() => {
    setHeaderState({});
  }, [topKey]);

  // Ref-counted style-tag injection (cleaned up on unmount)
  useEffect(() => {
    acquireStyleTag();
    return () => releaseStyleTag();
  }, []);

  // Capture the trigger element when the panel opens, restore focus on close.
  useEffect(() => {
    if (!isOpen) return;
    previouslyFocusedRef.current =
      (document.activeElement as HTMLElement | null) ?? null;
    return () => {
      const el = previouslyFocusedRef.current;
      if (el && typeof el.focus === "function" && document.contains(el)) {
        el.focus();
      }
      previouslyFocusedRef.current = null;
    };
  }, [isOpen]);

  // Drive the slide-in animation: render off-screen first, then flip data-mounted.
  useEffect(() => {
    if (!isOpen) {
      setMounted(false);
      return;
    }
    // Two RAFs — first commits the initial off-screen frame, second triggers
    // the transition. One RAF works in most engines but can race.
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setMounted(true));
    });
    return () => {
      cancelAnimationFrame(raf1);
      if (raf2) cancelAnimationFrame(raf2);
    };
  }, [isOpen]);

  // Move focus to the panel itself on open / when the top entry changes.
  useEffect(() => {
    if (!isOpen) return;
    panelRef.current?.focus();
  }, [isOpen, stack.length]);

  // Escape: depth>1 → pop; depth=1 → close. Tab: focus trap.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (controller.stack.length > 1) {
          controller.pop();
        } else {
          controller.close();
        }
        return;
      }
      if (e.key === "Tab" && panelRef.current) {
        const focusable = getFocusable(panelRef.current);
        if (focusable.length === 0) {
          // No focusable children — keep focus on the panel itself
          e.preventDefault();
          panelRef.current.focus();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey) {
          if (active === first || active === panelRef.current) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (active === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, controller]);

  if (!isOpen || !top) return null;

  const body = renderEntry(top, controller);
  const depth = stack.length;
  const overlayBg = "rgba(0,0,0,0.45)";
  const headerTitle = header.title ?? "";

  return (
    <div
      className="crm-detail-panel-overlay"
      style={{ background: overlayBg }}
      onClick={() => controller.close()}
    >
      <div
        ref={panelRef}
        className="crm-detail-panel"
        data-mounted={mounted ? "true" : "false"}
        role="dialog"
        aria-modal="true"
        aria-label={headerTitle}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: tokens.bgRaised,
          color: tokens.fg,
          fontFamily: tokens.fontFamily,
          borderLeft: `1px solid ${tokens.border}`,
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.85rem 1rem",
            borderBottom: `1px solid ${tokens.border}`,
            background: tokens.bgRaised,
            flexShrink: 0,
          }}
        >
          {depth > 1 && (
            <button
              type="button"
              aria-label="Back"
              className="crm-touch-target crm-touch-icon"
              onClick={() => controller.pop()}
              style={{
                background: "none",
                border: `1px solid ${tokens.border}`,
                borderRadius: "4px",
                width: "28px",
                height: "28px",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                color: tokens.fg,
                fontSize: "1rem",
                lineHeight: 1,
                padding: 0,
                fontFamily: tokens.fontFamily,
              }}
            >
              {"←"}
            </button>
          )}
          <h3
            style={{
              margin: 0,
              flex: 1,
              minWidth: 0,
              fontSize: "1rem",
              fontWeight: 600,
              color: tokens.fg,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={headerTitle}
          >
            {headerTitle}
          </h3>
          {header.actions && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
              }}
            >
              {header.actions}
            </div>
          )}
          <button
            type="button"
            aria-label="Close panel"
            className="crm-touch-target crm-touch-icon"
            onClick={() => controller.close()}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: tokens.fgMuted,
              fontSize: "1.4rem",
              lineHeight: 1,
              padding: "0.25rem 0.4rem",
              fontFamily: tokens.fontFamily,
            }}
          >
            {"×"}
          </button>
        </div>

        {/* Body */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "1rem 1.25rem",
            background: tokens.bgRaised,
            color: tokens.fg,
          }}
        >
          <PanelHeaderContext.Provider value={headerCtx}>
            {body}
          </PanelHeaderContext.Provider>
        </div>
      </div>
    </div>
  );
}

// Stable identity key for a stack entry, used as a useEffect dep so we can
// reset header state precisely when the *top* entry changes.
function entryKey(entry: PanelEntry): string {
  switch (entry.kind) {
    case "deal":
      return `deal:${entry.id}:${entry.mode}`;
    case "contact":
      return `contact:${entry.id}:${entry.mode}`;
    case "deal-create":
      return "deal-create";
    case "contact-create":
      return "contact-create";
  }
}
