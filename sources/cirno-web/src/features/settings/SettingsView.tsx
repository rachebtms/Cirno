import { SettingsPage } from "@/features/settings/SettingsPage";
import type { SettingsExitGuard, SettingsSectionKey } from "@/features/settings/contracts";
import { useSettingsController } from "@/features/settings/useSettingsController";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import type { ThemePreference } from "@/hooks/useTheme";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { SkillSummary } from "@/lib/contracts/skills";

export type { SettingsSectionKey } from "@/features/settings/contracts";

interface SettingsViewProps {
  registerExitGuard?: (guard: SettingsExitGuard | null) => void;
  themePreference: ThemePreference;
  initialSection?: SettingsSectionKey;
  initialSettings?: SettingsPayload | null;
  showSidebar?: boolean;
  hideHeader?: boolean;
  onChangeTheme: (value: ThemePreference) => void;
  onBackToChat: () => void;
  onModelNameChange: (modelName: string | null) => void;
  onSettingsChange?: (payload: SettingsPayload) => void;
  skills?: SkillSummary[];
  skillsLoading?: boolean;
  skillsError?: boolean;
  onStartAutomationChat?: (
    content: string,
    images?: SendAttachment[],
    options?: SendOptions,
    modelPreset?: string | null,
  ) => boolean | void | Promise<boolean | void>;
  titleOverrides?: Record<string, string>;
  sessions?: ChatSummary[];
  onSectionChange?: (section: SettingsSectionKey) => void;
  onLogout?: () => void;
  onRestart?: () => void;

  isRestarting?: boolean;

}

export function SettingsView({
  registerExitGuard,
  themePreference,
  initialSection = "overview",
  initialSettings = null,
  showSidebar = true,
  hideHeader = false,
  onChangeTheme,
  onBackToChat,
  onModelNameChange,
  onSettingsChange,
  skills = [],
  skillsLoading = false,
  skillsError = false,
  onStartAutomationChat,
  titleOverrides,
  sessions,
  onSectionChange,
  onLogout,
  onRestart,

  isRestarting = false,

}: SettingsViewProps) {
  const controller = useSettingsController({
    initialSection,
    initialSettings,
    onModelNameChange,
    onSettingsChange,
    onSectionChange,
    onRestart,

  });

  return (
    <SettingsPage
      registerExitGuard={registerExitGuard}
      controller={controller}
      themePreference={themePreference}
      showSidebar={showSidebar}
      hideHeader={hideHeader}
      onChangeTheme={onChangeTheme}
      onBackToChat={onBackToChat}
      skills={skills}
      skillsLoading={skillsLoading}
      skillsError={skillsError}
      onStartAutomationChat={onStartAutomationChat}
      titleOverrides={titleOverrides}
      sessions={sessions}
      onLogout={onLogout}
      isRestarting={isRestarting}

    />
  );
}
