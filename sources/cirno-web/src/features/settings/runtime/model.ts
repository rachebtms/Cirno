import type { TFunction } from "i18next";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { RUNTIME_CONFIG_FIELDS, RUNTIME_CONFIG_GROUPS, type RuntimeConfigField, type RuntimeConfigPage } from "../system/runtime-config-fields";

export function configurationGroups(page: RuntimeConfigPage) {
  return RUNTIME_CONFIG_GROUPS.filter(group => group.page === page)
    .map(group => ({ ...group, fields: RUNTIME_CONFIG_FIELDS.filter(field => field.group === group.id) }))
    .filter(group => group.fields.length || group.id === "chat");
}

export function configurationOptions(field: RuntimeConfigField, settings: SettingsPayload, current: string, t: TFunction) {
  const tr = (key: string) => t(`settings.runtimeConfig.${key}`);
  const values = field.kind === "preset"
    ? [...new Set(["", "default", ...settings.model_presets.map(preset => preset.id), ...(current ? [current] : [])])]
    : field.options ?? [];
  return values.map(value => ({
    id: value || ":none",
    value,
    name: !value ? tr(field.kind === "preset" ? "activeModel" : "none")
      : field.kind === "preset" ? settings.model_presets.find(preset => preset.id === value)?.name ?? value
      : field.path.endsWith("consolidation.reasoning_effort") ? tr(`compactionEffortOptions.${value}`)
      : field.path.endsWith("memory.embedding_provider") ? tr(`embeddingProviders.${value}`)
      : ["auto", "manual", "standard", "persistent", "idle", "interval", "report", "terminate"].includes(value) ? tr(value) : value,
  }));
}
