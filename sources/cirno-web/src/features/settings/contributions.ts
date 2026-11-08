import type { SettingsSectionKey } from "@/features/settings/contracts";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";

export interface SettingsPanelProps {
  client: CirnoClient;
  settings: SettingsPayload;
  onRestart: () => void;
  selectSection: (key: SettingsSectionKey) => void;
}
export interface SettingsContribution {
  key: SettingsSectionKey;
  icon: LucideIcon;
  fallback: string;
  group: string;
  Panel?: ComponentType<SettingsPanelProps>;
}
