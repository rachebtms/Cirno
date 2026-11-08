import type { SettingsPayload } from "@/lib/contracts/settings";

export function uniqueProviders(
  providers: SettingsPayload["providers"],
): SettingsPayload["providers"] {
  const seen = new Set<string>();
  return providers.filter((provider) => {
    if (seen.has(provider.id)) return false;
    seen.add(provider.id);
    return true;
  });
}

export function modelPresetProviderKey(
  preset: SettingsPayload["model_presets"][number],
  settings: SettingsPayload,
  options: { draftProvider?: string } = {},
): string {
  const provider = options.draftProvider ?? preset.provider;
  if (provider === "auto") {
    return (
      preset.resolved_provider ||
      settings.agent.resolved_provider ||
      settings.agent.provider ||
      preset.provider
    );
  }
  return provider;
}
