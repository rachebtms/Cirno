import { Alert, Button } from "@heroui/react";
import { ArrowRight, Palette } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ThemeSettings } from "@/features/preferences/ThemeSettings";
import { ThemeModePicker } from "@/features/preferences/ThemeModePicker";
import { usePreferenceStatus } from "@/hooks/usePreferences";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import { ModelSetup } from "./ModelSetup";
import "./entry.css";

export function SetupFlow(props: { onComplete: () => void; onModelNameChange: (name: string | null) => void }) {
  const [step, setStep] = useState<"theme" | "model">("theme");
  const { t } = useTranslation(), theme = useTheme(), status = usePreferenceStatus();
  if (step === "model") return <ModelSetup {...props} onBack={() => setStep("theme")} />;
  return <ThemeProvider theme={theme.theme}><main className="model-setup">
    <header className="model-setup-header"><div className="model-setup-heading">
      <div><p className="model-setup-step"><Palette size={16} aria-hidden />{t("setup.step", { current: 2, total: 3 })}</p><LanguageSwitcher /></div>
      <h1>{t("setup.themeTitle")}</h1><p>{t("themes.syncHint")}</p>
    </div></header>
    <div className="setup-theme-content"><div><ThemeSettings /><ThemeModePicker preference={theme.preference} onChange={theme.setTheme} /></div></div>
    <footer className="model-setup-footer"><div className="model-setup-actions">
      {status.error && <Alert status="danger" role="alert"><Alert.Content>{status.error}</Alert.Content></Alert>}
      <Button isDisabled={status.saving || !!status.error} onPress={() => setStep("model")}>{t("setup.continue")}<ArrowRight size={16} aria-hidden /></Button>
    </div></footer>
  </main></ThemeProvider>;
}
