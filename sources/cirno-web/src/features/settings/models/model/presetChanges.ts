import type { ModelConfigurationUpdate } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { AgentSettingsDraft } from "../modelDraft";
import { modelAPISelection } from "../modelAPI";
import { normalizeContextWindowTokens } from "../modelValues";
import { providerJsonValue } from "../../providers/providerForm";

type Preset = SettingsPayload["model_presets"][number];

/** Dirty state and transport patches use the same editable-field comparison. */
export function modelPresetUpdate(
  form: AgentSettingsDraft,
  preset: Preset,
  requestOverrides: boolean,
): ModelConfigurationUpdate {
  const next = {
    name: form.presetName,
    provider: form.provider,
    model: form.model,
    maxTokens: form.maxTokens,
    contextWindowTokens: form.contextWindowTokens,
    idleCompactPercent: form.idleCompactPercent ?? null,
    idleCompactKeepPercent: form.idleCompactKeepPercent ?? null,
    temperature: form.temperature,
    reasoningEffort: form.reasoningEffort || null,
    reasoningHistory: form.reasoningHistory ?? "auto",
    imageInput: form.imageInput ?? null,
    videoInput: form.videoInput ?? null,
    api: form.api,
    ...(requestOverrides
      ? {
          extraHeaders: form.extraHeaders,
          extraQuery: form.extraQuery,
          extraBody: form.extraBody,
        }
      : {}),
  };
  const saved = {
    name: preset.name,
    provider: preset.provider,
    model: preset.model,
    maxTokens: preset.max_tokens,
    contextWindowTokens: normalizeContextWindowTokens(preset.context_window_tokens),
    idleCompactPercent: preset.idle_compact_percent ?? null,
    idleCompactKeepPercent: preset.idle_compact_keep_percent ?? null,
    temperature: preset.temperature,
    reasoningEffort: preset.reasoning_effort ?? null,
    reasoningHistory: preset.reasoning_history ?? "auto",
    imageInput: preset.image_input ?? null,
    videoInput: preset.video_input ?? null,
    api: preset.api,
    extraHeaders: providerJsonValue(preset.extra_headers),
    extraQuery: providerJsonValue(preset.extra_query),
    extraBody: providerJsonValue(preset.extra_body),
  };
  const changes = Object.fromEntries(
    Object.entries(next).filter(([field, value]) =>
      field === "api"
        ? modelAPISelection(next.api) !== modelAPISelection(saved.api)
        : value !== saved[field as keyof typeof saved],
    ),
  ) as Omit<ModelConfigurationUpdate, "id">;
  if (changes.name !== undefined) changes.name = changes.name.trim();
  return { id: preset.id, ...changes };
}
