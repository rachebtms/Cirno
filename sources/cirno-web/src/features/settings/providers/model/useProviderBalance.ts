import { useState } from "react";
import { fetchProviderBalance, updateProviderSettings } from "@/lib/api";
import type { ProviderBalanceConfig, ProviderBalancePayload } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { useClient } from "@/providers/ClientProvider";
export function useProviderBalance(provider: SettingsPayload["providers"][number], onSaved: (settings: SettingsPayload) => void) {
  const { client, getToken } = useClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ProviderBalanceConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ signature: string; payload: ProviderBalancePayload } | null>(null);
  const signature = JSON.stringify(provider.balance ?? null);
  const refresh = async () => {
    setLoading(true); setError("");
    try { setResult({ signature, payload: await fetchProviderBalance(getToken(), provider.id) }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  };
  const save = async () => {
    setSaving(true); setError("");
    try { onSaved(await updateProviderSettings(client, { provider: provider.id, balance: draft })); setOpen(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  };
  return { open, setOpen, draft, setDraft, saving, loading, error, refresh, save,
    balances: result?.signature === signature ? result.payload.balances : [],
    edit: () => { setDraft(provider.balance ?? null); setError(""); setOpen(true); },
  };
}
