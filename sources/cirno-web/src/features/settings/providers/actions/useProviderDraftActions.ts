import { useCallback } from "react";
import { providerFormFromRow } from "../providerForm";
import type { ModelSettingsActionsOptions } from "../../modelOperations";
export function useProviderDraftActions({ state, settings }: ModelSettingsActionsOptions) {
  const { setProviderForms, setVisibleProviderKeys, setEditingProviderKeys, visibleProviderKeys } =
    state;
  const resetProviderDraft = useCallback(
    (providerName: string) => {
      const provider = settings?.providers.find((item) => item.id === providerName);
      if (!provider) return;
      setProviderForms((prev) => ({
        ...prev,
        [providerName]: providerFormFromRow(provider),
      }));
      setVisibleProviderKeys((prev) => ({ ...prev, [providerName]: false }));
      setEditingProviderKeys((prev) => ({ ...prev, [providerName]: false }));
    },
    [settings],
  );

  const toggleProviderKeyVisibility = (providerName: string) => {
    const isVisible = visibleProviderKeys[providerName];
    setVisibleProviderKeys((prev) => ({ ...prev, [providerName]: !isVisible }));
  };

  const toggleProviderKeyEditing = (providerName: string) => {
    const provider = settings?.providers.find((row) => row.id === providerName);
    if (!provider) return;
    setEditingProviderKeys((prev) => {
      const nextEditing = !prev[providerName];
      if (!nextEditing) {
        setProviderForms((forms) => ({
          ...forms,
          [providerName]: {
            ...(forms[providerName] ?? providerFormFromRow(provider)),
            apiKey: "",
          },
        }));
        setVisibleProviderKeys((visible) => ({
          ...visible,
          [providerName]: false,
        }));
      }
      return { ...prev, [providerName]: nextEditing };
    });
  };

  return {
    resetProviderDraft,
    toggleProviderKeyEditing,
    toggleProviderKeyVisibility,
  };
}
