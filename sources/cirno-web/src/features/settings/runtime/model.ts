import type { TFunction } from "i18next";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { RUNTIME_CONFIG_FIELDS, RUNTIME_CONFIG_GROUPS, type RuntimeConfigField, type RuntimeConfigPage } from "../system/runtime-config-fields";

export function configurationGroups(page: RuntimeConfigPage) {
  const memoryPage = ["memory", "context", "dream", "memory-search"].includes(page);
  const includes = (field: RuntimeConfigField) => {
    if (!memoryPage || page === "memory") return true;
    if (page === "dream") return field.path.includes(".dream.");
    const context = field.path.includes(".compaction.") || field.path.includes("_compact_")
      || field.path.endsWith("idle_compact_after_minutes") || field.path.endsWith("checkpoint_tokens")
      || field.path.endsWith("release_archived_runtime");
    return page === "context" ? context : !context && !field.path.includes(".dream.");
  };
  return RUNTIME_CONFIG_GROUPS.filter(group => group.page === page || (memoryPage && group.id === "memory"))
    .map(group => ({ ...group, fields: RUNTIME_CONFIG_FIELDS.filter(field => field.group === group.id && includes(field)) }))
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
      : field.path.endsWith("compaction.reasoning_effort") ? tr(`compactionEffortOptions.${value}`)
      : field.path.endsWith("memory.embedding_provider") ? tr(`embeddingProviders.${value}`)
      : ["auto", "manual", "standard", "persistent", "idle", "interval", "report", "terminate"].includes(value) ? tr(value) : value,
  }));
}
