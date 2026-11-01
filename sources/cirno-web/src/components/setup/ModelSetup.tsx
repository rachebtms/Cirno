import { lazy, Suspense, useCallback, useState } from "react";
import { ArrowRight, Check, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Button } from "@/components/ui/button";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import { accountRequest } from "@/lib/account";
import type { SettingsPayload } from "@/lib/types";

const SettingsView = lazy(() => import("@/components/settings/SettingsView").then((module) => ({ default: module.SettingsView })));

export function ModelSetup({ onComplete, onModelNameChange }: { onComplete: () => void; onModelNameChange: (name: string | null) => void }) {
  const { t } = useTranslation();
  const { theme, preference, setTheme } = useTheme();
  const [configured, setConfigured] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  const settingsChanged = useCallback((settings: SettingsPayload) => {
    setConfigured(settings.model_presets.some((preset) => settings.model_call_order.includes(preset.name)
      && settings.providers.some((provider) => provider.name === (preset.resolved_provider ?? preset.provider) && provider.configured)));
  }, []);

  async function finish() {
    setSaving(true);
    setError(false);
    try {
      await accountRequest("complete");
      onComplete();
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  }

  return <ThemeProvider theme={theme}>
    <main className="flex h-full min-w-0 flex-col bg-settings-canvas">
      <header className="shrink-0 border-b border-foreground/10 px-5 py-5 sm:px-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground"><Check className="h-3.5 w-3.5" aria-hidden />{t("setup.step", { current: 2, total: 2 })}</p>
            <LanguageSwitcher className="h-8 shrink-0 text-xs" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">{t("setup.modelTitle")}</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("setup.modelDescription")}</p>
        </div>
      </header>
      <Suspense fallback={<div className="flex flex-1 items-center justify-center"><LoaderCircle className="h-5 w-5 animate-spin text-muted-foreground" aria-label={t("app.loading.boot")} /></div>}>
        <SettingsView initialSection="models" showSidebar={false} hideHeader themePreference={preference} onChangeTheme={setTheme} onBackToChat={() => { void finish(); }} onModelNameChange={onModelNameChange} onSettingsChange={settingsChanged} />
      </Suspense>
      <footer className="shrink-0 border-t border-foreground/10 bg-settings-canvas px-5 py-4 sm:px-8">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-end gap-3">
          {error && <p role="alert" className="mr-auto text-sm text-destructive">{t("setup.errors.connection_failed")}</p>}
          <Button variant="ghost" disabled={saving} onClick={() => { void finish(); }} className="rounded-full text-muted-foreground">{t("setup.configureLater")}</Button>
          <Button disabled={!configured || saving} onClick={() => { void finish(); }} className="gap-2 rounded-full">{t("setup.startChatting")}{saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}</Button>
        </div>
      </footer>
    </main>
  </ThemeProvider>;
}
