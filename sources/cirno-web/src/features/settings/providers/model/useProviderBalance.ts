import { useMemo, useRef, type Dispatch, type SetStateAction } from "react";
import { fetchProviderBalance, updateProviderSettings } from "@/lib/api";
import type { ProviderBalanceConfig, ProviderBalancePayload } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { useClient } from "@/providers/ClientProvider";
import { useMutation } from "@/ui/resources/useMutation";
import { useRequest } from "@/ui/resources/useRequest";
import { useResourceScope, type ResourceScope } from "@/ui/resources/useResourceScope";
import { useScopedState } from "@/ui/resources/useScopedState";

export function useProviderBalance(provider: SettingsPayload["providers"][number], onSaved: (settings: SettingsPayload) => void) {
  const { client, getToken, token } = useClient();
  const signature = JSON.stringify(provider.balance ?? null);
  const owner = useMemo(() => ({ client, token, id: provider.id, signature }), [client, token, provider.id, signature]);
  const read = useRequest<ProviderBalancePayload>(owner);
  const write = useMutation(owner);
  const scope = useResourceScope(owner);
  const readFlight = useRef<{ scope: ResourceScope } | null>(null);
  const [editor, setEditor] = useScopedState(scope, () => ({
    open: false, draft: null as ProviderBalanceConfig | null, pendingRead: false,
  }));
  const setOpen: Dispatch<SetStateAction<boolean>> = value => {
    setEditor(current => ({
      ...current, open: typeof value === "function" ? value(current.open) : value,
    }));
  };
  const setDraft: Dispatch<SetStateAction<ProviderBalanceConfig | null>> = value => {
    setEditor(current => ({
      ...current, draft: typeof value === "function" ? value(current.draft) : value,
    }));
  };
  const refresh = async () => {
    if (!scope.isCurrent() || write.busy || readFlight.current?.scope === scope) return;
    const flight = { scope };
    readFlight.current = flight;
    setEditor(current => ({ ...current, pendingRead: true }));
    try { await read.load(() => fetchProviderBalance(getToken(), provider.id)); }
    finally {
      if (readFlight.current === flight) {
        readFlight.current = null;
        setEditor(current => ({ ...current, pendingRead: false }));
      }
    }
  };
  const save = async () => {
    await write.run(
      () => updateProviderSettings(client, { provider: provider.id, balance: editor.draft }),
      payload => {
        // A rotated key may retain the same masked settings signature.
        read.clear();
        setOpen(false);
        onSaved(payload);
      },
    );
  };
  return { open: editor.open, setOpen, draft: editor.draft, setDraft,
    saving: write.busy, loading: editor.pendingRead,
    error: write.error ?? (editor.open ? "" : read.error) ?? "",
    refresh, save,
    balances: read.value?.balances ?? [],
    edit: () => {
      if (!read.isCurrent() || write.busy) return;
      write.clear();
      setEditor(current => ({ ...current, open: true, draft: provider.balance ?? null }));
    },
  };
}
