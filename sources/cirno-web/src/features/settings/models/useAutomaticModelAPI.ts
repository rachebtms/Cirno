import { useCallback, useEffect, useMemo } from "react";

import { fetchAutomaticModelAPI } from "@/lib/api";
import type { AutomaticModelAPIPayload } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { useRequest } from "@/ui/resources/useRequest";

export function useAutomaticModelAPI({
  token,
  provider,
  model,
  reasoningEffort,
  providers,
  supported,
  editorOpen,
}: {
  token: string;
  provider: string;
  model: string;
  reasoningEffort: string;
  providers: SettingsPayload["providers"];
  supported: boolean;
  editorOpen: boolean;
}) {
  const owner = useMemo(
    () => ({ token, provider, model, reasoningEffort, providers }),
    [token, provider, model, reasoningEffort, providers],
  );
  const preview = useRequest<AutomaticModelAPIPayload>(owner);
  const enabled = editorOpen && supported && Boolean(model.trim());
  const load = useCallback(
    () => preview.load(() => fetchAutomaticModelAPI(token, provider, model, reasoningEffort)),
    [preview.load, token, provider, model, reasoningEffort],
  );

  useEffect(() => {
    if (!enabled) return;
    const timer = window.setTimeout(() => {
      void load();
    }, 150);
    return () => window.clearTimeout(timer);
  }, [enabled, load]);

  return {
    result: supported ? preview.value : null,
    error: supported ? preview.error : null,
    loading: enabled && preview.loading,
    retry: load,
  };
}
