import { useCallback, useRef, useState } from "react";
import type { SettingsExitGuard, SettingsSectionKey } from "@/features/settings/contracts";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { accountRequest } from "@/lib/account";
import { ROUTER_SESSION_KEY } from "@/lib/conversation-role";
import { useTranslation } from "react-i18next";

export function useModelSetup(onComplete: () => void) {
  const { i18n } = useTranslation();
  const [configured, setConfigured] = useState(false);
  const [section, setSection] = useState<SettingsSectionKey>("providers");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exitGuard = useRef<SettingsExitGuard | null>(null);
  const pending = useRef(false);
  const registerGuard = useCallback((guard: SettingsExitGuard | null) => { exitGuard.current = guard; }, []);
  const afterEdits = (action: () => void) => {
    if (exitGuard.current) exitGuard.current(action, { promptRestart: false });
    else action();
  };
  const settingsChanged = useCallback((settings: SettingsPayload) => {
    setConfigured(settings.model_presets.some(preset => settings.model_call_order.includes(preset.id)
      && settings.providers.some(provider => provider.id === (preset.resolved_provider ?? preset.provider) && provider.configured)));
  }, []);
  async function finish(wake: boolean) {
    if (pending.current) return;
    pending.current = true; setSaving(true); setError(null);
    try {
      await accountRequest("complete", { wake, language: i18n.resolvedLanguage ?? i18n.language });
      window.location.hash = `/chat/${encodeURIComponent(ROUTER_SESSION_KEY)}`;
      onComplete();
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { pending.current = false; setSaving(false); }
  }
  return { section, setSection, saving, error, configured, registerGuard, settingsChanged, afterEdits,
    selectSection: (section: SettingsSectionKey) => afterEdits(() => setSection(section)),
    complete: (wake: boolean) => afterEdits(() => { void finish(wake); }) };
}
