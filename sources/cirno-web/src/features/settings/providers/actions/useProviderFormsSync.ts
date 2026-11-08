import { useEffect } from "react";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { ModelSettingsState } from "../../models/useModelSettingsState";
import { providerFormFromRow } from "../providerForm";
export function useProviderFormsSync(state: ModelSettingsState, settings: SettingsPayload | null) {
  const { setProviderForms } = state;

  useEffect(() => {
    if (!settings) return;
    setProviderForms((prev) => {
      const next: typeof prev = {};
      for (const provider of settings.providers) {
        next[provider.id] = prev[provider.id] ?? providerFormFromRow(provider);
      }
      return next;
    });
  }, [settings]);
}
