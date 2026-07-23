import { tokens as ui } from "@nimblebrain/synapse/ui";

/**
 * CRM token shape, now backed by the shared `@nimblebrain/synapse/ui` token
 * contract instead of a per-app fallback table. `useStyleTokens()` keeps its
 * old signature so the rest of the app is unchanged — but every value is now a
 * `var(--token, neutral-fallback)` from the library, so the host's injected
 * brand theme drives the whole app and light/dark resolve via CSS.
 */
export interface ResolvedTokens {
  bg: string;
  bgRaised: string;
  bgSubtle: string;
  bgHover: string;
  fg: string;
  fgMuted: string;
  fgFaint: string;
  border: string;
  borderStrong: string;
  accent: string;
  accentSoft: string;
  accentText: string;
  fontFamily: string;
  fontMono: string;
  danger: string;
  dangerSoft: string;
  success: string;
}

// Static var()-based mapping. No `useTheme` needed — the host swaps the CSS
// variables and every `var()` re-resolves without a React re-render.
const RESOLVED: ResolvedTokens = {
  bg: ui.bg,
  bgRaised: ui.bgRaised,
  bgSubtle: ui.bgSubtle,
  bgHover: ui.bgSubtle,
  fg: ui.fg,
  fgMuted: ui.fgMuted,
  fgFaint: ui.fgFaint,
  border: ui.border,
  borderStrong: ui.borderStrong,
  accent: ui.accent,
  accentSoft: ui.infoLight,
  accentText: ui.accentFg,
  fontFamily: ui.fontSans,
  fontMono: ui.fontMono,
  danger: ui.danger,
  dangerSoft: `color-mix(in oklab, ${ui.danger} 14%, transparent)`,
  success: ui.success,
};

export function useStyleTokens(): ResolvedTokens {
  return RESOLVED;
}
