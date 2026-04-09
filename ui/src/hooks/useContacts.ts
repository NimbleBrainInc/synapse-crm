import { useCallback, useEffect, useRef, useState } from "react";
import { useSynapse, useDataSync } from "@nimblebrain/synapse/react";

export interface Contact {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  role?: string;
  notes?: string;
  lead_source?: "referral" | "inbound" | "outbound" | "event" | "other";
  status: string;
  created_at: string;
  updated_at: string;
  relationships?: Array<{ rel: string; target: string }>;
}

export function useContacts() {
  const synapse = useSynapse();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const callId = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++callId.current;
    setError(null);
    try {
      const result = await synapse.callTool<Record<string, unknown>, Contact[]>(
        "list_contacts",
      );
      if (id !== callId.current) return;
      if (result.isError) {
        setError(String(result.data));
        return;
      }
      const raw = result.data as { entities?: Contact[] } | Contact[];
      const list = Array.isArray(raw) ? raw : (raw?.entities ?? []);
      setContacts(list);
    } catch (err) {
      if (id !== callId.current) return;
      setError(err instanceof Error ? err.message : "Failed to fetch contacts");
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

  return { contacts, loading, error, refresh } as const;
}
