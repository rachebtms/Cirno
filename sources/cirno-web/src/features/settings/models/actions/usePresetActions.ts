import { updateModelConfiguration } from "@/lib/api";
import { agentDraftFromPayload } from "../modelDraft";
import { modelPresetUpdate } from "../model/presetChanges";
import type { RequestParameterDraft } from "../../providers/ProviderParameterFields";
import type { ModelSettingsActionsOptions } from "../../modelOperations";
import { usePresetEditContext } from "./usePresetEditContext";
import { usePresetCreation } from "./usePresetCreation";
export function usePresetActions(options: ModelSettingsActionsOptions) {
  const { state, settings, client, applyPayload, setError, onModelNameChange } = options;
  const {
    form,
    modelCallOrderSaving,
    modelConfigurationSaving,
    modelPresetCreating,
    modelPresetEditingId,
    setSaving,
    setModelPresetNameError,
    setForm,
    setModelPresetEditingId,
  } = state;
  const context = usePresetEditContext(options),
    creation = usePresetCreation(options, context);
  const {
    latestSettings,
    editTarget,
    editTargetRef,
    presetNameConflict,
    showPresetNameConflict,
    handlePresetSaveError,
  } = context;
  const saveModelSettings = async () => {
    if (
      !settings ||
      modelCallOrderSaving ||
      modelConfigurationSaving ||
      !Number.isSafeInteger(form.maxTokens) ||
      form.maxTokens <= 0 ||
      !Number.isSafeInteger(form.contextWindowTokens) ||
      form.contextWindowTokens <= 0 ||
      !Number.isFinite(form.temperature) ||
      form.temperature < 0 ||
      form.temperature > 2
    ) {
      return false;
    }

    if (modelPresetCreating) return creation.saveNewPreset();

    const targetName = editTarget.id;
    const selectedPreset = latestSettings.current?.model_presets.find(
      (preset) => !preset.is_default && preset.id === targetName,
    );
    if (!selectedPreset) return false;
    const nextName = form.presetName.trim();
    const nameChanged = form.presetName !== selectedPreset.name;
    if (nameChanged && presetNameConflict(nextName, selectedPreset.id)) {
      showPresetNameConflict();
      return false;
    }
    const update = modelPresetUpdate(
      form,
      selectedPreset,
      settings.model_request_overrides_supported === true,
    );
    if (Object.keys(update).length === 1) return true;
    setModelPresetNameError(null);
    setSaving(true);
    try {
      const payload = await updateModelConfiguration(client, update);
      latestSettings.current = payload;
      applyPayload(payload, {
        preserveAgentForm: true,
        preserveCapabilityForms: true,
      });
      setForm((current) =>
        current === form ? agentDraftFromPayload(payload, targetName) : current,
      );
      if (editTargetRef.current === editTarget) {
        setModelPresetEditingId(targetName);
      }
      onModelNameChange(payload.agent.model || null);
      setModelPresetNameError(null);
      setError(null);
      return true;
    } catch (err) {
      handlePresetSaveError(err);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveModelRequestSettings = async (values: Partial<RequestParameterDraft>) => {
    setSaving(true);
    try {
      const payload = await updateModelConfiguration(client, {
        id: modelPresetEditingId,
        ...values,
      });
      applyPayload(payload, {
        preserveAgentForm: true,
        preserveCapabilityForms: true,
      });
      setForm((current) =>
        current === form ? agentDraftFromPayload(payload, modelPresetEditingId) : current,
      );
      setError(null);
    } finally {
      setSaving(false);
    }
  };

  return {
    modelEditIdentity: String(editTarget.identity),
    beginModelPresetCreation: creation.beginModelPresetCreation,
    cancelModelPresetCreation: creation.cancelModelPresetCreation,
    saveModelSettings,
    saveModelRequestSettings,
  };
}
