import { useId } from "react";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ThemePreference } from "@/hooks/useTheme";
import { SettingsSectionTitle } from "@/features/settings/shared/SettingsControls";
import "@/features/settings/overview/appearance-settings.css";

export function ThemeModePicker({ preference, onChange }: {
  preference: ThemePreference; onChange: (mode: ThemePreference) => void;
}) {
  const { t } = useTranslation(), themeId = useId();
  const themes = [
    { value: "system", label: t("settings.appearance.system"), icon: Monitor },
    { value: "light", label: t("settings.values.light"), icon: Sun },
    { value: "dark", label: t("settings.values.dark"), icon: Moon },
  ] as const;
  return <section>
      <SettingsSectionTitle>{t("settings.rows.theme")}</SettingsSectionTitle>
      <fieldset>
        <legend className="sr-only">{t("settings.rows.theme")}</legend>
        <div className="appearance-theme-grid">
          {themes.map(({ value, label, icon: Icon }) => <label key={value} className="appearance-theme-option">
            <input className="appearance-theme-input" type="radio" name={themeId} value={value}
              checked={preference === value} onChange={() => onChange(value)} />
            <span className="appearance-theme-card">
              <span className="appearance-theme-miniature" data-mode={value} aria-hidden>
                <span className="appearance-mini-sidebar"><span /><span /><span /></span>
                <span className="appearance-mini-main"><span /><span /><span /><span /></span>
              </span>
              <span className="appearance-theme-label text-ui-label">
                <span className="flex min-w-0 items-center gap-1.5"><Icon className="h-3.5 w-3.5 shrink-0" aria-hidden /><span>{label}</span></span>
                <Check className="appearance-theme-check h-3.5 w-3.5 shrink-0" aria-hidden />
              </span>
            </span>
          </label>)}
        </div>
      </fieldset>
    </section>;
}
