import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import { AppearanceSettingsView } from "@/features/settings/overview/AppearanceSettingsView";
import { useReadingTypography } from "@/hooks/useReadingTypography";
import { usePreferences } from "@/hooks/usePreferences";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import { readPreferences, writePreferences, type DisplayPreferences } from "@/features/preferences/store";

/** Actual appearance controls in a browser-local harness, without a gateway. */
export function AppearanceFixture() {
  const { t } = useTranslation();
  const { theme, preference, setTheme } = useTheme();
  const preferences = usePreferences();
  const setPreferences: Dispatch<SetStateAction<DisplayPreferences>> = (update) => {
    writePreferences(typeof update === "function" ? update(readPreferences()) : update);
  };
  useReadingTypography();
  return <ThemeProvider theme={theme}>
    <main className="h-full overflow-y-auto bg-background" data-appearance-fixture>
      <header className="flex items-center gap-2 text-caption text-muted-foreground" style={{ maxWidth: 800, margin: "0 auto", padding: "28px 32px" }}>
        <img src="/brand/cirno_mark.svg" className="h-5 w-5" alt="" />
        <span className="font-medium text-foreground">cirno</span><span aria-hidden>/</span><span>{t("settings.nav.appearance")}</span>
      </header>
      <div style={{ containerType: "inline-size", maxWidth: 800, margin: "0 auto", padding: "0 16px 64px" }}>
        <div className="settings-grid" style={{ margin: 0, width: "100%", maxWidth: "none" }}>
          <h1 className="font-semibold tracking-tight" style={{ fontSize: 28, marginBottom: 20, paddingInline: "var(--settings-inset, 16px)" }}>{t("settings.nav.appearance")}</h1>
          <AppearanceSettingsView themePreference={preference} onChangeTheme={setTheme}
            displayPreferences={preferences} onChangePreferences={setPreferences} />
        </div>
      </div>
    </main>
  </ThemeProvider>;
}
