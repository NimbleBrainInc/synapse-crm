import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { useApp, useDataSync } from "@nimblebrain/synapse/react";
import { tokens } from "@nimblebrain/synapse/ui";

export interface Deal {
  id: string;
  title: string;
  value?: number;
  stage: "lead" | "qualified" | "proposal" | "negotiation" | "closed_won" | "closed_lost";
  close_date?: string;
  probability?: number;
  contact_name?: string;
  status: string;
  created_at: string;
  updated_at: string;
  relationships?: Array<{ rel: string; target: string }>;
}

export const STAGES = [
  "lead",
  "qualified",
  "proposal",
  "negotiation",
  "closed_won",
  "closed_lost",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  lead: "Lead",
  qualified: "Qualified",
  proposal: "Proposal",
  negotiation: "Negotiation",
  closed_won: "Closed Won",
  closed_lost: "Closed Lost",
};

export const STAGE_COLORS: Record<string, string> = {
  lead: tokens.fgMuted,
  qualified: tokens.accent,
  proposal: tokens.processing,
  negotiation: tokens.warning,
  closed_won: tokens.success,
  closed_lost: tokens.danger,
};

export type DealsByStage = Record<string, Deal[]>;

export function useDeals() {
  const app = useApp();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const callId = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++callId.current;
    setError(null);
    try {
      const result = await app.callTool<Deal[] | { entities: Deal[] }>(
        "list_deals",
        { limit: null },
      );
      if (id !== callId.current) return;
      if (result.isError) {
        setError(String(result.data));
        return;
      }
      const raw = result.data as { entities?: Deal[] } | Deal[];
      const list = Array.isArray(raw) ? raw : (raw?.entities ?? []);
      setDeals(list);
    } catch (err) {
      if (id !== callId.current) return;
      setError(err instanceof Error ? err.message : "Failed to fetch deals");
    } finally {
      if (id === callId.current) setLoading(false);
    }
  }, [app]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useDataSync(refresh);

  const dealsByStage = useMemo<DealsByStage>(() => {
    const grouped: DealsByStage = {};
    for (const stage of STAGES) {
      grouped[stage] = [];
    }
    for (const deal of deals) {
      if (deal.status !== "active") continue;
      const stage = deal.stage || "lead";
      if (grouped[stage]) {
        grouped[stage].push(deal);
      }
    }
    // Sort by value descending within each stage
    for (const stage of Object.keys(grouped)) {
      grouped[stage].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    }
    return grouped;
  }, [deals]);

  return { deals, dealsByStage, loading, error, refresh } as const;
}
