import type { ModelPresetOption } from "@/features/model-selection/contracts";
import { inferProviderFromModelName, providerDisplayLabel } from "@/lib/provider-brand";
import type { SettingsPayload } from "@/lib/contracts/settings";

function compactModelName(modelName: string | null): string | null {
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  return leaf || trimmed;
}

export interface ModelBadgeInfo {
  label: string | null;
  model: string | null;
  provider: string | null;
  providerLabel: string | null;
  needsSetup: boolean;
}

function modelPresetForBadge(
  settings: SettingsPayload | null,
  scopedPreset: string | null,
): SettingsPayload["model_presets"][number] | null {
  if (!settings) return null;
  const presets = settings.model_presets ?? [];
  if (scopedPreset) {
    return presets.find((preset) => preset.id === scopedPreset) ?? null;
  }
  const configured = settings.agent.model_preset || "default";
  return (
    presets.find((preset) => preset.id === configured)
    ?? presets.find((preset) => preset.active)
    ?? null
  );
}

export function toModelBadgeInfo(
  modelName: string | null,
  settings: SettingsPayload | null,
  modelPreset: string | null = null,
): ModelBadgeInfo {
  const scopedPreset = modelPreset?.trim() || null;
  const preset = modelPresetForBadge(settings, scopedPreset);
  const model = scopedPreset
    ? preset?.model || null
    : settings?.agent.model || modelName || null;
  const label = preset
    ? preset.is_default
      ? "Default"
      : preset.name.trim()
    : scopedPreset || compactModelName(model);
  const rawProvider = preset?.provider
    || (!scopedPreset ? settings?.agent.provider : null)
    || null;
  const provider = rawProvider === "auto"
    ? preset?.resolved_provider
      || (!scopedPreset ? settings?.agent.resolved_provider : null)
      || null
    : rawProvider || inferProviderFromModelName(model);
  const providerRow = provider
    ? settings?.providers?.find((item) => item.id === provider)
    : null;
  const needsSetup = Boolean(
    settings && (!model || !provider || !providerRow || !providerRow.configured),
  );
  return {
    label,
    model: compactModelName(model),
    provider,
    providerLabel: provider ? providerDisplayLabel(settings?.providers ?? [], provider) : null,
    needsSetup,
  };
}

export function modelPresetOptionsFromSettings(
  settings: SettingsPayload | null,
): ModelPresetOption[] {
  if (!settings) return [];
  const order = new Map(
    (settings.model_call_order ?? []).map((name, index) => [name.trim(), index]),
  );
  return (settings.model_presets ?? [])
    .filter((preset) => !preset.is_default && preset.id.trim())
    .sort((a, b) => (
      (order.get(a.id.trim()) ?? Number.POSITIVE_INFINITY)
      - (order.get(b.id.trim()) ?? Number.POSITIVE_INFINITY)
    ))
    .map((preset) => {
      const id = preset.id.trim();
      return {
        id,
        name: preset.name,
        model: preset.model,
        contextWindowTokens: preset.context_window_tokens,
        reasoningEffort: preset.reasoning_effort,
        provider: preset.resolved_provider || preset.provider,
      };
    });
}

/** Commands accept a stable ID or an unambiguous display name. */
export function resolveModelPresetSelection(settings: SettingsPayload | null, value: string): string | null {
  if (value.toLowerCase() === "default") return "default";
  const normalized = value.trim().toLowerCase();
  const presets = settings?.model_presets ?? [];
  const identity = presets.find(preset => preset.id.toLowerCase() === normalized);
  if (identity) return identity.id;
  const matches = presets.filter(preset => preset.name.toLowerCase() === normalized);
  return matches.length === 1 ? matches[0].id : null;
}
