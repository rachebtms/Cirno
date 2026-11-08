import { ThemeModePicker } from "@/features/preferences/ThemeModePicker";
import { ThemeSettings } from "@/features/preferences/ThemeSettings";
import { type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { SettingsGroup, SettingsRow, SettingsSectionTitle } from "@/features/settings/shared/SettingsControls";
import { SettingsHint } from "@/features/settings/shared/SettingsHint";
import { ToggleButton } from "@/components/ui/toggle-button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ThemePreference } from "@/hooks/useTheme";
import type { FileEditDisplayMode, ActivityDisplayMode, DisplayPreferences } from "@/features/preferences/store";
import { ReadingSettings } from "./ReadingSettings";
import "./appearance-settings.css";

export function AppearanceSettingsView({ themePreference, onChangeTheme, displayPreferences, onChangePreferences, section = "all" }: {
  section?: "all" | "appearance" | "reading" | "activity";
  themePreference: ThemePreference;
  onChangeTheme: (preference: ThemePreference) => void;
  displayPreferences: DisplayPreferences;
  onChangePreferences: Dispatch<SetStateAction<DisplayPreferences>>;
}) {
  const { t } = useTranslation();
  const editHelp = { summary: "summaryHelp", diff: "diffHelp", collapsed_diff: "collapsedHelp" } as const;

  return <div className="settings-stack appearance-page">
    {(section === "all" || section === "appearance") && <ThemeSettings />}
    {(section === "all" || section === "appearance") && <ThemeModePicker preference={themePreference} onChange={onChangeTheme} />}

    {(section === "all" || section === "reading") && <section>
      <SettingsSectionTitle>{t("settings.appearance.reading")}</SettingsSectionTitle>
      <ReadingSettings preferences={displayPreferences} onChange={onChangePreferences} />
      <div className="mt-2">
        <SettingsGroup>
          <SettingsRow title={t("settings.rows.codeWrap")} description={t("settings.help.codeWrap")}>
            <ToggleButton checked={displayPreferences.codeWrap}
              onChange={(codeWrap) => onChangePreferences((previous) => ({ ...previous, codeWrap }))}
              ariaLabel={t("settings.rows.codeWrap")}
              label={t(displayPreferences.codeWrap ? "settings.values.on" : "settings.values.off")} />
          </SettingsRow>
        </SettingsGroup>
      </div>
    </section>}

    {(section === "all" || section === "activity") && <section>
      <SettingsSectionTitle>
        <SettingsHint description={t("settings.appearance.processHelp")}>{t("settings.appearance.process")}</SettingsHint>
      </SettingsSectionTitle>
      <SettingsGroup>
        <SettingsRow title={t("settings.rows.activityMode")}
          description={t(`settings.appearance.${displayPreferences.activityMode === "auto" ? "autoHelp" : "expandedHelp"}`)}>
          <SegmentedControl<ActivityDisplayMode> value={displayPreferences.activityMode}
            ariaLabel={t("settings.rows.activityMode")}
            options={[{ value: "auto", label: t("settings.values.auto") }, { value: "expanded", label: t("settings.values.expanded") }]}
            onChange={(activityMode) => onChangePreferences((previous) => ({ ...previous, activityMode }))} />
        </SettingsRow>
        {(["reasoningDetailMode", "toolDetailMode"] as const).map((mode) => <div key={mode} className="settings-group-divider">
          <SettingsRow title={t(`settings.rows.${mode}`)}>
            <SegmentedControl<"brief" | "detailed"> value={displayPreferences[mode] ?? "brief"}
              ariaLabel={t(`settings.rows.${mode}`)}
              options={[{ value: "brief", label: t("settings.values.summary") }, { value: "detailed", label: t("settings.values.detailed") }]}
              onChange={(value) => onChangePreferences((previous) => ({ ...previous, [mode]: value }))} />
          </SettingsRow>
        </div>)}
        <div className="settings-group-divider">
          <SettingsRow title={t("settings.rows.fileEditDisplay")}
            description={t(`settings.appearance.${editHelp[displayPreferences.fileEditDisplayMode]}`)}>
            <SegmentedControl<FileEditDisplayMode> value={displayPreferences.fileEditDisplayMode}
              ariaLabel={t("settings.rows.fileEditDisplay")}
              options={[
                { value: "summary", label: t("settings.values.summary") },
                { value: "diff", label: t("settings.values.diff") },
                { value: "collapsed_diff", label: t("settings.values.collapsedDiff") },
              ]}
              onChange={(fileEditDisplayMode) => onChangePreferences((previous) => ({ ...previous, fileEditDisplayMode }))} />
          </SettingsRow>
        </div>
      </SettingsGroup>
    </section>}

    {(section === "all" || section === "appearance") && <section>
      <SettingsSectionTitle>{t("settings.sections.interface")}</SettingsSectionTitle>
      <SettingsGroup>
        <SettingsRow title={t("settings.rows.language")}><LanguageSwitcher /></SettingsRow>
        <SettingsRow title={t("settings.rows.brandLogos")} description={t("settings.legal.thirdPartyBrands")}>
          <ToggleButton checked={displayPreferences.brandLogos}
            onChange={(brandLogos) => onChangePreferences((previous) => ({ ...previous, brandLogos }))}
            ariaLabel={t("settings.rows.brandLogos")}
            label={t(displayPreferences.brandLogos ? "settings.values.on" : "settings.values.off")} />
        </SettingsRow>
      </SettingsGroup>
    </section>}
  </div>;
}
