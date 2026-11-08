import { useCallback, useRef, useState } from "react";
import type { SettingsExitGuard, SettingsSectionKey } from "@/features/settings/contracts";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { accountRequest } from "@/lib/account";

export function useModelSetup(onComplete: () => void) {
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
  async function finish() {
    if (pending.current) return;
    pending.current = true; setSaving(true); setError(null);
    try { await accountRequest("complete"); onComplete(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { pending.current = false; setSaving(false); }
  }
  return { section, setSection, saving, error, configured, registerGuard, settingsChanged,
    selectSection: (section: SettingsSectionKey) => afterEdits(() => setSection(section)),
    complete: () => afterEdits(() => { void finish(); }) };
}
