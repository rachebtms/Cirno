import type { SettingsPayload } from "@/lib/contracts/settings";

/** Each occurrence has its own key: fallback order may repeat a preset. */
export function modelPresetRows(presets: SettingsPayload["model_presets"], order: string[]) {
  const named = presets.filter((preset) => !preset.is_default);
  const byId = new Map(named.map((preset) => [preset.id, preset]));
  const occurrences = new Map<string, number>();
  return [
    ...order.map((name, orderIndex) => {
      const occurrence = occurrences.get(name) ?? 0;
      occurrences.set(name, occurrence + 1);
      return { key: `ordered:${name}:${occurrence}`, name, orderIndex, preset: byId.get(name) };
    }),
    ...named
      .filter((preset) => !order.includes(preset.id))
      .map((preset) => ({
        key: `disabled:${preset.id}`,
        name: preset.id,
        orderIndex: -1,
        preset,
      })),
  ];
}
