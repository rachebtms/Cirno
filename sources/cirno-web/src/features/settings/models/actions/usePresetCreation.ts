import { useRef } from "react";
import { probeModelCapabilities } from "../probeModelCapabilities";
import { createModelConfiguration, updateModelCallOrder } from "@/lib/api";
import { agentDraftFromPayload, selectedModelId } from "../modelDraft";
import { normalizeContextWindowTokens } from "../modelValues";
import type { ModelSettingsActionsOptions } from "../../modelOperations";
import type { PresetEditContext } from "./usePresetEditContext";
export function usePresetCreation(
  {
    state,
    settings,
    client,
    t,
    applyPayload,
    setError,
    onModelNameChange,
    configuredModelProviderOptions,
  }: ModelSettingsActionsOptions,
  context: PresetEditContext,
) {
  const {
    form,
    modelCallOrderSaving,
    modelConfigurationSaving,
    saving,
    modelPresetEditingId,
    modelPresetBeforeCreateRef,
    setForm,
    setModelPresetEditingId,
    setModelConfigurationSaving,
    setModelPresetNameError,
    setModelPresetCreating,
  } = state;
  const creationPending = useRef(false);
  const { presetNameConflict, showPresetNameConflict, handlePresetSaveError } = context;
  const saveNewPreset = async () => {
    if (!settings || creationPending.current) return false;
    const name = form.presetName.trim();
    const provider = form.provider.trim();
    const model = form.model.trim();
    if (
      !name ||
      !provider ||
      !model ||
      form.maxTokens <= 0 ||
      form.temperature < 0 ||
      form.temperature > 2
    ) {
      return false;
    }
    if (presetNameConflict(name)) {
      showPresetNameConflict();
      return false;
    }
    creationPending.current = true;
    setModelPresetNameError(null);
    setModelConfigurationSaving(true);
    try {
      const capabilities = settings.model_capability_testing_supported ? await probeModelCapabilities(client, form) : {};
      const payload = await createModelConfiguration(client, {
        imageInput: form.imageInput ?? capabilities.image?.supported ?? null,
        videoInput: form.videoInput ?? capabilities.video?.supported ?? null,
        name,
        provider,
        model,
        idleCompactPercent: form.idleCompactPercent ?? null,
        idleCompactKeepPercent: form.idleCompactKeepPercent ?? null,
        maxTokens: form.maxTokens,
        contextWindowTokens: form.contextWindowTokens,
        temperature: form.temperature,
        reasoningEffort: form.reasoningEffort || null,
        reasoningHistory: form.reasoningHistory ?? "auto",
        api: form.api ?? undefined,
        ...(settings.model_request_overrides_supported
          ? {
              extraHeaders: form.extraHeaders,
              extraQuery: form.extraQuery,
              extraBody: form.extraBody,
            }
          : {}),
      });
      const createdPreset = payload.created_model_preset;
      const savedOrder = payload.model_call_order ?? [];
      const nextOrder = createdPreset && !savedOrder.includes(createdPreset)
        ? [...savedOrder, createdPreset] : null;
      applyPayload(payload, { preserveCapabilityForms: true });
      if (createdPreset) {
        setForm(agentDraftFromPayload(payload, createdPreset));
        setModelPresetEditingId(createdPreset);
      }

      let finalPayload = payload;
      let callOrderError: string | null = null;
      if (nextOrder) {
        try {
          const orderedPayload = await updateModelCallOrder(client, nextOrder);
          applyPayload(orderedPayload, { preserveCapabilityForms: true });
          finalPayload = orderedPayload;
        } catch (reason) {
          // Creation is already committed. An order conflict is not a duplicate name.
          callOrderError = t("settings.models.createdOrderFailed", {
            defaultValue: "Preset created, but its call order update failed. Enable it from the preset list to retry. {{error}}",
            error: reason instanceof Error ? reason.message : "",
          });
        }
      }
      if (createdPreset) {
        setForm(agentDraftFromPayload(finalPayload, createdPreset));
        setModelPresetEditingId(createdPreset);
      }
      modelPresetBeforeCreateRef.current = null;
      onModelNameChange(finalPayload.agent.model || null);
      setModelPresetNameError(null);
      setError(callOrderError);
    } catch (err) {
      handlePresetSaveError(err);
    } finally {
      creationPending.current = false;
      setModelConfigurationSaving(false);
    }
    return false;
  };
  const beginModelPresetCreation = () => {
    if (!settings || creationPending.current || saving || modelCallOrderSaving || modelConfigurationSaving) return;
    const primaryPreset = settings.model_presets.find(
      (preset) => !preset.is_default && preset.id === settings.model_call_order?.[0],
    );
    const currentProvider =
      primaryPreset?.provider === "auto"
        ? (primaryPreset.resolved_provider ?? settings.agent.resolved_provider)
        : (primaryPreset?.provider ?? settings.agent.provider);
    const provider =
      configuredModelProviderOptions.find((option) => option.name === currentProvider)?.name ??
      configuredModelProviderOptions[0]?.name ??
      "";
    modelPresetBeforeCreateRef.current = modelPresetEditingId;
    setModelPresetNameError(null);
    setForm((prev) => ({
      ...prev,
      presetName: "",
      provider,
      model: "",
      api: null,
      imageInput: null,
      videoInput: null,
      extraHeaders: "",
      extraQuery: "",
      extraBody: "",
      maxTokens: primaryPreset?.max_tokens ?? settings.agent.max_tokens,
      contextWindowTokens: normalizeContextWindowTokens(
        primaryPreset?.context_window_tokens ?? settings.agent.context_window_tokens,
      ),
      temperature: primaryPreset?.temperature ?? settings.agent.temperature,
      reasoningEffort: primaryPreset?.reasoning_effort ?? settings.agent.reasoning_effort ?? "",
      reasoningHistory: primaryPreset?.reasoning_history ?? settings.agent.reasoning_history ?? "auto",
      idleCompactPercent: primaryPreset?.idle_compact_percent ?? null,
      idleCompactKeepPercent: primaryPreset?.idle_compact_keep_percent ?? null,
    }));
    setModelPresetCreating(true);
  };

  const cancelModelPresetCreation = () => {
    if (!settings || creationPending.current || modelConfigurationSaving) return;
    const previousPreset = modelPresetBeforeCreateRef.current;
    setModelPresetCreating(false);
    setModelPresetNameError(null);
    setForm(agentDraftFromPayload(settings, previousPreset ?? undefined));
    setModelPresetEditingId(previousPreset ?? selectedModelId(settings));
    modelPresetBeforeCreateRef.current = null;
  };

  return { saveNewPreset, beginModelPresetCreation, cancelModelPresetCreation };
}
