import type { SettingsPayload } from "@/lib/types";

export type SettingsExitGuard = (leave: () => void, options?: { promptRestart?: boolean }) => void;

export type SettingsSectionKey =
  | "overview"
  | "about"
  | "appearance"
  | "reading"
  | "activity"
  | "context"
  | "dream"
  | "memory-search"
  | "execution"
  | "shell"
  | "network"
  | "telegram"
  | "notifications"
  | "nodes"
  | "models"
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

type PendingRestartSection = "runtime" | "browser" ;
export type PendingRestartSections = Record<PendingRestartSection, boolean>;

export type RestartAwarePayload = {
  requires_restart?: boolean;
  surface?: SettingsPayload["surface"];
  runtime_surface?: SettingsPayload["runtime_surface"];
  runtime_capabilities?: SettingsPayload["runtime_capabilities"];
};

export type ApplySettingsPayload = (
  payload: SettingsPayload,
  options?: { preserveAgentForm?: boolean; preserveCapabilityForms?: boolean },
) => void;

export type MaybeRestartHostEngine = (payload: RestartAwarePayload) => Promise<void>;
