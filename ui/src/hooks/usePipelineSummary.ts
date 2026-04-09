import { useCallback, useEffect, useRef, useState } from "react";
import { useSynapse, useDataSync } from "@nimblebrain/synapse/react";

export interface StageSummary {
  stage: string;
  count: number;
  total_value: number;
  avg_probability: number;
}

export interface PipelineTotals {
  active_deals: number;
  active_value: number;
  weighted_value: number;
  closed_won: number;
  closed_lost: number;
  win_rate_pct: number | null;
}

export interface PipelineSummaryData {
  stages: StageSummary[];
  totals: PipelineTotals;
  next_step: string;
}

export function usePipelineSummary() {
  const synapse = useSynapse();
  const [summary, setSummary] = useState<PipelineSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const callId = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++callId.current;
    setError(null);
    try {
      const result = await synapse.callTool<
        Record<string, unknown>,
        PipelineSummaryData
      >("pipeline_summary");
      if (id !== callId.current) return;
      if (result.isError) {
        setError(String(result.data));
        return;
      }
      setSummary(result.data as PipelineSummaryData);
    } catch (err) {
      if (id !== callId.current) return;
      setError(err instanceof Error ? err.message : "Failed to fetch pipeline summary");
    } finally {
      if (id === callId.current) setLoading(false);
    }
  }, [synapse]);

  useEffect(() => {
    synapse.ready.then(() => refresh());
  }, [synapse, refresh]);

  useDataSync(() => {
    refresh();
  });

  return { summary, loading, error, refresh } as const;
}
