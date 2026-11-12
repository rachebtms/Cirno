import { TabSurface } from "@/ui/layout/TabSurface";
import { TokenUsageCard } from "@/features/settings/TokenUsageCard";
import { fixtureUsage } from "./usage-chart-fixture";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AccountSettings } from "@/features/settings/account/AccountSettings";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { RuntimeConfiguration } from "@/features/settings/runtime/RuntimeConfiguration";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import type { RuntimeConfigPage } from "@/features/settings/system/runtime-config-fields";
import { SettingsLayout } from "@/features/settings/ui/SettingsLayout";
import { SettingsNavigation } from "@/features/settings/ui/SettingsNavigation";
import { useTheme } from "@/hooks/useTheme";
import type { CirnoClient } from "@/lib/cirno-client";
import type { RuntimeConfigValue, SettingsPayload } from "@/lib/contracts/settings";

export function SettingsRebuildFixture({ embedded = false }: { embedded?: boolean }) {
  useTheme();
  const { t } = useTranslation();
  const [section, setSection] = useState<SettingsSectionKey>(embedded ? "overview" : "consolidation");
  const [saved, setSaved] = useState("");
  const [settings, setSettings] = useState(() => ({
    model_presets: [{ id: "research", name: "Research model" }], advanced: { exec_max_runtime_limit: 86400 },
    runtime_config: {
      "agents.defaults.active_compact_percent": 80, "agents.defaults.idle_compact_percent": 35,
      "agents.defaults.idle_compact_keep_percent": 10, "agents.defaults.idle_compact_after_minutes": 15,
      "agents.defaults.idle_compact_check_interval_seconds": 60, "agents.defaults.memory.checkpoint_tokens": 2000,
      "agents.defaults.consolidation.output_reserve_percent": 5,
      "agents.defaults.memory.release_archived_runtime": true, "agents.defaults.consolidation.max_tokens": 4096,
      "agents.defaults.consolidation.reasoning_effort": "low", "agents.defaults.consolidation.checkpoint_reminder_percent": 60,
      "agents.defaults.workspace": "/workspace", "agents.defaults.max_tool_iterations": 200,
      "agents.defaults.provider_retry_mode": "standard", "agents.defaults.goal_continuation_limit": 0,
      "agents.defaults.max_tool_result_chars": 16000, "agents.defaults.resume.message": "Continue",
      "agents.defaults.resume.show_message": false, "tools.exec.enable": true, "tools.exec.max_runtime": 60,
      "tools.exec.allowed_env_keys": ["TERM"], "tools.exec.sandbox": "", "network.proxy": "http://localhost:8080",
      "agents.defaults.timezone_mode": "manual", "agents.defaults.timezone": "UTC",
    },
  } as unknown as SettingsPayload));
  const client = useMemo(() => ({} as CirnoClient), []);
  client.requestMutation = async <T,>(_method: string, args: unknown) => {
    const values = (args as { values: Record<string, RuntimeConfigValue> }).values;
    setSaved(JSON.stringify(values));
    return { ...settings, runtime_config: { ...settings.runtime_config, ...values } } as T;
  };
  const state = useRuntimeConfigSettings(settings, client, setSettings);
  return <TabSurface style={{ height: embedded ? "100%" : "100dvh", display: "flex", flex: 1 }}>
    <SettingsLayout navigation={<SettingsNavigation activeSection={section} onSelectSection={setSection} />}
      section={section} title={t(`settings.nav.${section}`)}>
      {section === "overview" ? <TokenUsageCard usage={fixtureUsage} timeZone="UTC" /> : section === "account" ? <AccountSettings />
        : <RuntimeConfiguration page={section as RuntimeConfigPage} settings={settings} state={state} isRestarting={false} />}
    </SettingsLayout>
    <output aria-label="Saved settings" hidden>{saved}</output>
  </TabSurface>;
}
