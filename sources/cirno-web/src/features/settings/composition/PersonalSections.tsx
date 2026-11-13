import { ProfileFiles } from "@/features/profile/ProfileFiles";
import { MemorySettings } from "@/features/memory/MemorySettings";
import { FixedSkillsSettings } from "../runtime/FixedSkillsSettings";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import { NotificationSettings } from "../notifications/NotificationSettings";
import { AppearanceSettings, OverviewSettings } from "../overview/OverviewSettings";
import { TelegramSettings } from "@/features/telegram/TelegramSettings";
import type { SectionRenderer, SectionRenderers } from "./contracts";
import type { SettingsComposition } from "./useSettingsComposition";

export function createPersonalSections(bindings: SettingsComposition): SectionRenderers {
  const { controller, themePreference, onChangeTheme, skills, skillsLoading, skillsError, displayPreferences, setDisplayPreferences, settings, selectSection, runtimeConfiguration } = bindings;
  const renderOverview: SectionRenderer = () => {
    return settings && (
      <OverviewSettings
        settings={settings}
        showBrandLogos={displayPreferences.brandLogos}
        onSelectSection={selectSection}
      />
    );
  };

  const renderMemory: SectionRenderer = () => {
    return <div className="settings-stack">{runtimeConfiguration("memory")}<ProfileFiles client={controller.client} section="memory" /><MemorySettings client={controller.client} /></div>;
  };

  const renderPersonality: SectionRenderer = () => {
    return <div className="settings-stack">{runtimeConfiguration("personality")}<ProfileFiles client={controller.client} section="personality" /></div>;
  };

  const renderNotifications: SectionRenderer = () => {
    return <NotificationSettings displayPreferences={displayPreferences} onChangePreferences={setDisplayPreferences} />;
  };

  const renderTelegram: SectionRenderer = () => {
    return <TelegramSettings client={controller.client} onConfigure={() => selectSection("channels")} />;
  };

  const renderAppearance: SectionRenderer = () => {
    return <AppearanceSettings section="appearance" themePreference={themePreference} onChangeTheme={onChangeTheme}
      displayPreferences={displayPreferences} onChangePreferences={setDisplayPreferences} />;
  };

  const renderReading: SectionRenderer = () => {
    return <AppearanceSettings section="reading" themePreference={themePreference} onChangeTheme={onChangeTheme}
      displayPreferences={displayPreferences} onChangePreferences={setDisplayPreferences} />;
  };

  const renderActivity: SectionRenderer = () => {
    return <div className="settings-stack"><AppearanceSettings section="activity" themePreference={themePreference} onChangeTheme={onChangeTheme}
      displayPreferences={displayPreferences} onChangePreferences={setDisplayPreferences} />{runtimeConfiguration("activity")}</div>;
  };

  const renderSkills: SectionRenderer = () => {
    return <div className="settings-stack">{settings?.runtime_config && <FixedSkillsSettings skills={skills} state={controller.runtimeConfigState} loading={skillsLoading} />}<SkillsLibrary skills={skills} loading={skillsLoading} error={skillsError} /></div>;
  };

  return {
    "overview": renderOverview,
    "memory": renderMemory,
    "personality": renderPersonality,
    "notifications": renderNotifications,
    "telegram": renderTelegram,
    "appearance": renderAppearance,
    "reading": renderReading,
    "activity": renderActivity,
    "skills": renderSkills,
  };
}
