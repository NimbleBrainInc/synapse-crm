import { useTheme } from "@nimblebrain/synapse/react";

export interface ResolvedTokens {
  // Backgrounds
  bg: string;          // page background
  bgRaised: string;    // card/panel background
  bgSubtle: string;    // input / muted area
  bgHover: string;     // hover row / button hover
  // Foreground
  fg: string;          // primary text
  fgMuted: string;     // labels, secondary text
  fgFaint: string;     // disabled / placeholder
  // Border
  border: string;
  borderStrong: string;
  // Brand
  accent: string;        // primary action / focused state
  accentSoft: string;    // 10% accent for subtle backgrounds
  accentText: string;    // text/icon over accent fills
  // Stage palette (kept domain-specific for now — not platform tokens)
  // — STAGE_COLORS continues to live in useDeals.ts
  // Typography
  fontFamily: string;
  fontMono: string;
  // Status
  danger: string;
  dangerSoft: string;
  success: string;
}

export function useStyleTokens(): ResolvedTokens {
  const theme = useTheme();
  const isDark = theme.mode === "dark";
  const t = theme.tokens;
  // Keys are the canonical platform tokens. Fallbacks chosen to match
  // the host's actual light/dark themes (not arbitrary hex).
  return {
    bg:           t["--color-background-primary"]   ?? (isDark ? "#0f1117" : "#ffffff"),
    bgRaised:     t["--color-background-secondary"] ?? (isDark ? "#1a1d27" : "#fafafa"),
    bgSubtle:     t["--color-background-tertiary"]  ?? (isDark ? "#22262f" : "#f3f4f6"),
    bgHover:      t["--color-background-hover"]     ?? (isDark ? "#22262f" : "#f3f4f6"),
    fg:           t["--color-text-primary"]         ?? (isDark ? "#e5e7eb" : "#111827"),
    fgMuted:      t["--color-text-secondary"]       ?? (isDark ? "#9ca3af" : "#6b7280"),
    fgFaint:      t["--color-text-tertiary"]        ?? (isDark ? "#6b7280" : "#9ca3af"),
    border:       t["--color-border-primary"]       ?? (isDark ? "#2d3340" : "#e5e7eb"),
    borderStrong: t["--color-border-secondary"]     ?? (isDark ? "#3f4754" : "#d1d5db"),
    accent:       t["--color-text-accent"]          ?? "#2563eb",
    accentSoft:   t["--color-background-accent"]    ?? (isDark ? "rgba(37,99,235,0.18)" : "rgba(37,99,235,0.10)"),
    accentText:   t["--color-text-on-accent"]       ?? "#ffffff",
    fontFamily:   t["--font-sans"]                  ?? "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    fontMono:     t["--font-mono"]                  ?? "ui-monospace, SFMono-Regular, Menlo, monospace",
    danger:       t["--color-text-danger"]          ?? "#dc2626",
    dangerSoft:   t["--color-background-danger"]    ?? (isDark ? "rgba(220,38,38,0.18)" : "rgba(220,38,38,0.10)"),
    success:      t["--color-text-success"]         ?? "#10b981",
  };
}
