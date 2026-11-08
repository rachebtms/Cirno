import type { SettingsExitGuard } from "../contracts";
import type { SettingsController } from "../useSettingsController";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import type { ThemePreference } from "@/hooks/useTheme";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SkillSummary } from "@/lib/contracts/skills";
import type { ReactNode } from "react";
import type { SettingsSectionKey } from "../contracts";
export interface SettingsPageProps {
  hideHeader?: boolean;
  registerExitGuard?: (guard: SettingsExitGuard | null) => void;
  controller: SettingsController;
  themePreference: ThemePreference;
  showSidebar: boolean;
  onChangeTheme: (value: ThemePreference) => void;
  onBackToChat: () => void;
  skills: SkillSummary[];
  skillsLoading: boolean;
  skillsError: boolean;
  onStartAutomationChat?: (
    content: string,
    images?: SendAttachment[],
    options?: SendOptions,
    modelPreset?: string | null,
  ) => boolean | void | Promise<boolean | void>;
  titleOverrides?: Record<string, string>;
  sessions?: ChatSummary[];
  onLogout?: () => void;
  isRestarting: boolean;

}

export type SectionRenderer = (options: { embedded: boolean }) => ReactNode;
export type SectionRenderers = Partial<Record<SettingsSectionKey, SectionRenderer>>;
