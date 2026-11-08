import type { SettingsPayload } from "@/lib/contracts/settings";
export { formatContextWindow, formatModelContextWindow } from "@/lib/model-context-format";

export function normalizeContextWindowTokens(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 200_000;
}

export function parseContextWindowTokens(value: string): number {
  const match = /^(\d+(?:\.\d+)?)\s*([km]?)$/i.exec(value.trim());
  if (!match) return NaN;
  const exponent = { k: 3, m: 6 }[match[2].toLowerCase()] ?? 0;
  const tokens = Number(`${match[1]}e${exponent}`);
  return Number.isSafeInteger(tokens) && tokens > 0 ? tokens : NaN;
}

export function formatContextWindowInput(tokens: number): string {
  if (!Number.isFinite(tokens)) return "";
  if (tokens % 1_000_000 === 0) return `${tokens / 1_000_000}m`;
  if (tokens % 1_000 === 0) return `${tokens / 1_000}k`;
  return String(tokens);
}

export function settingsProviderRow(
  payload: SettingsPayload,
  provider: string | null | undefined,
): SettingsPayload["providers"][number] | null {
  if (!provider) return null;
  return payload.providers.find((row) => row.id === provider) ?? null;
}

export function settingsProviderConfigured(
  payload: SettingsPayload,
  provider: string | null | undefined,
  resolvedProvider?: string | null,
): boolean {
  const concreteProvider = provider === "auto"
    ? resolvedProvider ?? payload.agent.resolved_provider ?? payload.agent.provider
    : provider;
  return settingsProviderRow(payload, concreteProvider)?.configured ?? false;
}
