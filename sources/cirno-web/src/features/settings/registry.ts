import type { SettingsSectionKey } from "@/features/settings/contracts";
import type { SettingsContribution } from "./contributions";

export function createSettingsRegistry(contributions: readonly SettingsContribution[]) {
  const entries = new Map<SettingsSectionKey, SettingsContribution>();
  for (const contribution of contributions) {
    if (entries.has(contribution.key)) throw new Error(`Settings section '${contribution.key}' is registered twice`);
    entries.set(contribution.key, Object.freeze({ ...contribution }));
  }
  return Object.freeze({
    navigation: Object.freeze([...entries.values()]),
    has: (key: string): key is SettingsSectionKey => entries.has(key as SettingsSectionKey),
    get: (key: SettingsSectionKey) => entries.get(key),
  });
}
