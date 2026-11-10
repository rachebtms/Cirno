import type { SettingsPayload } from "@/lib/contracts/settings";

export type SettingsExitGuard = (leave: () => void, options?: { promptRestart?: boolean }) => void;

export type SettingsSectionKey =
  | `${string}.${string}`
  | "overview"
  | "account"
  | "backup"
  | "heartbeat"
  | "coordination"
  | "regional"
  | "about"
  | "appearance"
  | "reading"
  | "activity"
  | "consolidation"
  | "memory-search"
  | "approval"
  | "execution"
  | "shell"
  | "network"
  | "telegram"
  | "notifications"
  | "nodes"
  | "models"
  | "providers"
  | "capabilities"

  | "browser"
  | "channels"
  | "mcp"
  | "apps"
  | "automations"
  | "memory"
  | "personality"
  | "skills"
  | "runtime"
  | "advanced";

export function isCapabilitySection(section: SettingsSectionKey): boolean {
  return ["capabilities", "browser"].includes(section);
}

type PendingRestartSection = "runtime" | "browser";
export type PendingRestartSections = Record<PendingRestartSection, boolean>;

export type ApplySettingsPayload = (
  payload: SettingsPayload,
  options?: { preserveAgentForm?: boolean; preserveCapabilityForms?: boolean },
) => void;

/** Migrate saved links without registering duplicate settings pages. */
export function canonicalSettingsSection<T extends string | null>(value: T): T | "consolidation" {
  return value === "context" || value === "dream" ? "consolidation" : value;
}
