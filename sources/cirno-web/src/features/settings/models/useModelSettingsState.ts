import { useRef, useState } from "react";

import {
  DEFAULT_AGENT_SETTINGS_DRAFT,
  agentDraftFromPayload,
  selectedModelId,
  type AgentSettingsDraft,
} from "@/features/settings/models/modelDraft";
import type { ProviderForm } from "@/features/settings/providers/providerForm";
import type { ProviderOperation } from "../providers/model/operations";
import type { SettingsPayload } from "@/lib/contracts/settings";

export function useModelSettingsState(initialSettings: SettingsPayload | null) {
  const initialForm = initialSettings
    ? agentDraftFromPayload(initialSettings)
    : DEFAULT_AGENT_SETTINGS_DRAFT;
  const [saving, setSaving] = useState(false);
  const [modelPresetCreating, setModelPresetCreating] = useState(false);
  const [modelPresetNameError, setModelPresetNameError] = useState<string | null>(null);
  const [modelConfigurationSaving, setModelConfigurationSaving] = useState(false);
  const [modelCallOrderSaving, setModelCallOrderSaving] = useState(false);
  const [modelPresetPendingDelete, setModelPresetPendingDelete] = useState<
    SettingsPayload["model_presets"][number] | null
  >(null);
  const modelPresetBeforeCreateRef = useRef<string | null>(null);
  const [providerOperation, setProviderOperation] = useState<ProviderOperation | null>(null);
  const providerSaving = providerOperation?.provider ?? null;
  const [providerForms, setProviderForms] = useState<Record<string, ProviderForm>>({});
  const [visibleProviderKeys, setVisibleProviderKeys] = useState<Record<string, boolean>>({});
  const [editingProviderKeys, setEditingProviderKeys] = useState<Record<string, boolean>>({});
  const [form, setForm] = useState<AgentSettingsDraft>(initialForm);
  const [modelPresetEditingId, setModelPresetEditingId] = useState(
    initialSettings ? selectedModelId(initialSettings) : "",
  );
  const [modelCallOrder, setModelCallOrder] = useState<string[]>(
    () => initialSettings?.model_call_order ?? [],
  );

  return {
    editingProviderKeys,
    form,
    modelCallOrder,
    modelCallOrderSaving,
    modelConfigurationSaving,
    modelPresetBeforeCreateRef,
    modelPresetCreating,
    modelPresetEditingId,
    modelPresetNameError,
    modelPresetPendingDelete,
    providerForms,
    providerSaving,
    providerOperation,
    saving,
    setEditingProviderKeys,
    setForm,
    setModelCallOrder,
    setModelCallOrderSaving,
    setModelConfigurationSaving,
    setModelPresetCreating,
    setModelPresetEditingId,
    setModelPresetNameError,
    setModelPresetPendingDelete,
    setProviderForms,
    setProviderOperation,
    setSaving,
    setVisibleProviderKeys,
    visibleProviderKeys,
  };
}

export type ModelSettingsState = ReturnType<typeof useModelSettingsState>;
