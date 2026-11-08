import type { ModelAPIConfig } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { normalizeContextWindowTokens } from "@/features/settings/models/modelValues";
import { providerJsonValue } from "../providers/providerForm";

export interface AgentSettingsDraft {
  model: string;
  provider: string;
  presetName: string;
  maxTokens: number;
  contextWindowTokens: number;
  idleCompactPercent?: number | null;
  idleCompactKeepPercent?: number | null;
  temperature: number;
  reasoningEffort: string;
  reasoningHistory?: "auto" | "preserve" | "omit";
  api: ModelAPIConfig | null;
  extraHeaders: string;
  extraQuery: string;
  extraBody: string;
  timezone: string;
  toolStatusSummaryMaxChars: number;
}

export function selectedModelId(payload: SettingsPayload): string {
  return (
    payload.model_call_order?.[0] ??
    payload.model_presets.find((preset) => !preset.is_default)?.id ??
    ""
  );
}

export function suggestedPresetName(
  model: string,
  presets: SettingsPayload["model_presets"],
): string {
  const modelName = model.trim().split("/").filter(Boolean).at(-1) ?? "";
  const base = (modelName.toLowerCase() === "default" ? "model" : modelName).slice(0, 48);
  if (!base) return "";

  const existing = new Set(
    presets.filter((preset) => !preset.is_default).map((preset) => preset.name.toLowerCase()),
  );
  if (!existing.has(base.toLowerCase())) return base;

  for (let index = 2; ; index += 1) {
    const suffix = ` ${index}`;
    const candidate = `${base.slice(0, 48 - suffix.length)}${suffix}`;
    if (!existing.has(candidate.toLowerCase())) return candidate;
  }
}

export const DEFAULT_AGENT_SETTINGS_DRAFT: AgentSettingsDraft = {
  model: "",
  provider: "",
  presetName: "",
  maxTokens: 8192,
  contextWindowTokens: 200_000,
  temperature: 0.1,
  reasoningEffort: "",
  reasoningHistory: "auto",
  api: null,
  extraHeaders: "",
  extraQuery: "",
  extraBody: "",
  timezone: "UTC",
  toolStatusSummaryMaxChars: 40,
};

export function agentDraftFromPayload(
  payload: SettingsPayload,
  preferredPresetName?: string,
): AgentSettingsDraft {
  const activePresetName = preferredPresetName ?? selectedModelId(payload);
  const activePreset =
    payload.model_presets.find(
      (preset) => !preset.is_default && preset.id === activePresetName,
    ) ?? null;
  return {
    model: activePreset?.model ?? payload.agent.model,
    provider: activePreset?.provider ?? payload.agent.provider ?? payload.agent.resolved_provider ?? "",
    presetName: activePreset?.name ?? "",
    maxTokens: activePreset?.max_tokens ?? payload.agent.max_tokens,
    contextWindowTokens: normalizeContextWindowTokens(
      activePreset?.context_window_tokens ?? payload.agent.context_window_tokens,
    ),
    idleCompactPercent: activePreset?.idle_compact_percent ?? null,
    idleCompactKeepPercent: activePreset?.idle_compact_keep_percent ?? null,
    temperature: activePreset?.temperature ?? payload.agent.temperature,
    reasoningEffort: activePreset?.reasoning_effort ?? "",
    reasoningHistory: activePreset?.reasoning_history ?? "auto",
    api: activePreset ? activePreset.api ?? null : payload.agent.api ?? null,
    extraHeaders: providerJsonValue(activePreset?.extra_headers),
    extraQuery: providerJsonValue(activePreset?.extra_query),
    extraBody: providerJsonValue(activePreset?.extra_body),
    timezone: payload.agent.timezone,
    toolStatusSummaryMaxChars: payload.agent.tool_status_summary_max_chars,
  };
}
