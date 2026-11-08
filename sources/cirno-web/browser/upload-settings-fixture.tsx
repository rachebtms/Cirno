import { useMemo, useState } from "react";
import { RuntimeConfiguration } from "@/features/settings/runtime/RuntimeConfiguration";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload, RuntimeConfigValue } from "@/lib/contracts/settings";

export function UploadSettingsFixture() {
  const [settings, setSettings] = useState(() => ({
    model_presets: [], advanced: { exec_max_runtime_limit: 86400 },
    runtime_config: {
      "server.health_host": "127.0.0.1", "server.health_port": 18790, "server.restart_mode": "auto",
      "server.uploads.max_file_mb": 6, "server.uploads.max_video_mb": 20, "server.uploads.max_total_mb": 24,
    },
  } as unknown as SettingsPayload));
  const [saved, setSaved] = useState("");
  const client = useMemo(() => new CirnoClient({ url: "ws://localhost:1", reconnect: false }), []);
  client.requestMutation = async <T,>(_method: string, args: unknown): Promise<T> => {
    const values = (args as { values: Record<string, RuntimeConfigValue> }).values;
    setSaved(JSON.stringify(values));
    return { ...settings, runtime_config: { ...settings.runtime_config, ...values }, requires_restart: true } as T;
  };
  const state = useRuntimeConfigSettings(settings, client, payload => setSettings(payload));
  return <main className="mx-auto max-w-3xl px-4 py-6" style={{ containerType: "inline-size" }}>
    <RuntimeConfiguration page="runtime" settings={settings} state={state} isRestarting={false} onRestart={() => {}} />
    <output aria-label="Saved settings" className="sr-only">{saved}</output>
  </main>;
}
