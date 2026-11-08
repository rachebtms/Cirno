import { Alert, Button, Spinner, Tabs } from "@heroui/react";
import { ArrowRight, Check } from "lucide-react";
import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { TabSurface } from "@/ui/layout/TabSurface";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { useModelSetup } from "./model/useModelSetup";
import "./entry.css";

const SettingsView = lazy(() => import("@/features/settings/SettingsView").then(module => ({ default: module.SettingsView })));
export function ModelSetup({ onComplete, onModelNameChange, onBack }: { onComplete: () => void; onModelNameChange: (name: string | null) => void; onBack?: () => void }) {
  const { t } = useTranslation();
  const { theme, preference, setTheme } = useTheme();
  const state = useModelSetup(onComplete);
  return <ThemeProvider theme={theme}><TabSurface as="main" className="model-setup">
    <header className="model-setup-header"><div className="model-setup-heading">
      <div><p className="model-setup-step"><Check aria-hidden size={16} />{t("setup.step", { current: 3, total: 3 })}</p><LanguageSwitcher /></div>
      <h1>{t("setup.modelTitle")}</h1><p>{t("setup.modelDescription")}</p>
    </div></header>
    <Tabs align="start" className="model-setup-content" selectedKey={state.section} onSelectionChange={key => state.selectSection(String(key) as SettingsSectionKey)}>
      <div className="model-setup-nav"><Tabs.ListContainer><Tabs.List aria-label={t("setup.modelTitle")}>
        {(["providers", "models"] as const).map(id => <Tabs.Tab key={id} id={id}>{t(`settings.nav.${id}`)}<Tabs.Indicator /></Tabs.Tab>)}
      </Tabs.List></Tabs.ListContainer></div>
      <Tabs.Panel id={state.section} className="model-setup-panel"><Suspense fallback={<div className="entry-loading"><Spinner aria-label={t("app.loading.boot")} /></div>}>
        <SettingsView registerExitGuard={state.registerGuard} initialSection={state.section} onSectionChange={state.setSection} showSidebar={false} hideHeader
          themePreference={preference} onChangeTheme={setTheme} onBackToChat={() => state.complete(false)} onModelNameChange={onModelNameChange} onSettingsChange={state.settingsChanged} />
      </Suspense></Tabs.Panel>
    </Tabs>
    <footer className="model-setup-footer"><div className="model-setup-actions">
      {state.error && <Alert status="danger" role="alert"><Alert.Description>{state.error}</Alert.Description></Alert>}
      {onBack && <Button variant="ghost" isDisabled={state.saving} onPress={() => state.afterEdits(onBack)}>{t("setup.back")}</Button>}
      <Button variant="ghost" isDisabled={state.saving} onPress={() => state.complete(false)}>{t("setup.configureLater")}</Button>
      <Button isDisabled={!state.configured} isPending={state.saving} onPress={() => state.complete(true)}>{t("setup.startChatting")}<ArrowRight aria-hidden size={16} /></Button>
    </div></footer>
  </TabSurface></ThemeProvider>;
}
