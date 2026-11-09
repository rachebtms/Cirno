import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAutomaticModelAPI } from "../useAutomaticModelAPI";
import { useModelPresetDrag } from "../useModelPresetDrag";
import { uniqueProviders } from "../modelCatalog";
import { settingsProviderConfigured } from "../modelValues";
import { agentDraftFromPayload } from "../modelDraft";
import { modelPresetRows } from "./presetRows";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { ModelsSettingsProps } from "./contracts";
export function useModelSettings({
  editCompletion: edits,
  token,
  form,
  setForm,
  editingPresetId,
  presetNameError,
  settings,
  creating,
  callOrder,
  saving,
  orderSaving,
  providerSaving,
  onChangeCallOrder,
  onSelectConfiguration,
}: ModelsSettingsProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => t(key, { defaultValue: fallback });
  const [editorOpen, setEditorOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const automaticAPI = useAutomaticModelAPI({
    token,
    provider: form.provider,
    model: form.model,
    reasoningEffort: form.reasoningEffort,
    providers: settings.providers,
    supported: settings.model_api_resolution_supported === true,
    editorOpen: editorOpen && advancedOpen,
  });
  const editorTriggerRef = useRef<HTMLElement | null>(null);
  const presetNameInputRef = useRef<HTMLInputElement>(null);
  const suggestedPresetNameRef = useRef<string | null>(null);
  const presetContextInitializedRef = useRef(false);
  const [editorRowKey, setEditorRowKey] = useState<string | null>(null);

  useEffect(() => {
    if (presetNameError) presetNameInputRef.current?.focus();
  }, [presetNameError]);
  useEffect(() => {
    if (!creating) {
      suggestedPresetNameRef.current = null;
      presetContextInitializedRef.current = false;
    }
  }, [creating]);
  const presetRows = modelPresetRows(settings.model_presets, callOrder);
  const selectedPreset =
    settings.model_presets.find((preset) => !preset.is_default && preset.id === editingPresetId) ??
    null;
  const activeEditorRowKey =
    editorRowKey ?? presetRows.find((row) => row.name === selectedPreset?.id)?.key ?? null;
  useEffect(() => {
    setAdvancedOpen(false);
  }, [editorOpen, edits.identity]);

  const configuredProviders = settings.providers.filter((provider) => provider.configured);
  const selectedProvider = settings.providers.find((provider) => provider.id === form.provider);
  const selectableProviders = uniqueProviders([
    ...configuredProviders,
    ...(selectedProvider ? [selectedProvider] : []),
  ]);
  const showAutoProvider = selectedPreset?.provider === "auto" || form.provider === "auto";
  const providerOptions = showAutoProvider
    ? [{ id: "auto", name: tx("settings.values.auto", "Auto") }, ...selectableProviders]
    : selectableProviders;
  const providerValue = providerOptions.some((provider) => provider.id === form.provider)
    ? form.provider
    : "";
  const selectProvider = (provider: string) => {
    edits.complete();
    const clearSuggestedName =
      creating &&
      provider !== form.provider &&
      suggestedPresetNameRef.current !== null &&
      form.presetName === suggestedPresetNameRef.current;
    if (clearSuggestedName) suggestedPresetNameRef.current = null;
    setForm((prev) => ({
      ...prev,
      provider,
      model: provider === prev.provider ? prev.model : "",
      api: provider === prev.provider ? prev.api : null,
      imageInput: provider === prev.provider ? prev.imageInput : null,
      videoInput: provider === prev.provider ? prev.videoInput : null,
      extraHeaders: provider === prev.provider ? prev.extraHeaders : "",
      extraQuery: provider === prev.provider ? prev.extraQuery : "",
      extraBody: provider === prev.provider ? prev.extraBody : "",
      presetName: clearSuggestedName ? "" : prev.presetName,
    }));
  };
  const selectedProviderNeedsSignIn =
    selectedProvider?.auth_type === "oauth" && !selectedProvider.configured;
  const selectedProviderSigningIn = providerSaving === selectedProvider?.id;
  const selectedProviderConfigured = settingsProviderConfigured(
    settings,
    form.provider,
    selectedPreset?.resolved_provider,
  );
  const modelFieldsMissing =
    !form.model.trim() ||
    !form.provider.trim() ||
    !form.presetName.trim() ||
    !Number.isSafeInteger(form.maxTokens) ||
    form.maxTokens <= 0 ||
    !Number.isSafeInteger(form.contextWindowTokens) ||
    form.contextWindowTokens <= 0 ||
    !Number.isFinite(form.temperature) ||
    form.temperature < 0 ||
    form.temperature > 2;
  const selectedPresetReferenced = Boolean(selectedPreset && callOrder[0] === selectedPreset.id);
  const callOrderBusy = orderSaving || saving;
  const presetDrag = useModelPresetDrag({
    keys: presetRows.filter((row) => row.orderIndex >= 0).map((row) => row.key),
    disabled: callOrderBusy,
    onReorder: (keys) =>
      onChangeCallOrder(keys.map((key) => presetRows.find((row) => row.key === key)!.name)),
  });
  const selectPreset = async (preset: SettingsPayload["model_presets"][number], rowKey: string) => {
    editorTriggerRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const toggleCurrentPreset =
      !creating && selectedPreset?.id === preset.id && activeEditorRowKey === rowKey;
    if (edits.needsCompletion() && !(await edits.commit())) return;
    onSelectConfiguration(preset.id);
    if (toggleCurrentPreset) {
      setEditorOpen((open) => !open);
      return;
    }
    setForm(agentDraftFromPayload(settings, preset.id));
    setEditorRowKey(rowKey);
    setEditorOpen(true);
  };

  const moveCallOrderItem = (index: number, offset: -1 | 1) => {
    if (callOrderBusy) return;
    const nextIndex = index + offset;
    if (nextIndex < 0 || nextIndex >= callOrder.length) return;
    const next = [...callOrder];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    onChangeCallOrder(next);
  };

  const removeCallOrderItem = (index: number) => {
    if (callOrderBusy || callOrder.length <= 1) return;
    onChangeCallOrder(callOrder.filter((_, itemIndex) => itemIndex !== index));
  };

  const changeAdvanced = async (open: boolean) => {
    if (!open && !creating && edits.needsCompletion() && !(await edits.commit())) return;
    setAdvancedOpen(open);
  };
  return {
    editorOpen,
    setEditorOpen,
    advancedOpen,
    setAdvancedOpen,
    changeAdvanced,
    automaticAPI,
    resolvedAutomaticAPI: automaticAPI.result,
    editorTriggerRef,
    presetNameInputRef,
    suggestedPresetNameRef,
    presetContextInitializedRef,
    presetRows,
    selectedPreset,
    activeEditorRowKey,
    setEditorRowKey,
    selectedProvider,
    providerOptions,
    providerValue,
    selectProvider,
    selectedProviderNeedsSignIn,
    selectedProviderSigningIn,
    selectedProviderConfigured,
    modelFieldsMissing,
    selectedPresetReferenced,
    callOrderBusy,
    presetDrag,
    selectPreset,
    moveCallOrderItem,
    removeCallOrderItem,
  };
}
export type ModelSettings = ReturnType<typeof useModelSettings>;
