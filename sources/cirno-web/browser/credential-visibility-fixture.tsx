import { useState } from "react";
import { CredentialsTab } from "@/features/credentials/CredentialsTab";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import { skillInjectionSettings } from "@/features/settings/runtime/skill-injection";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import { RuntimeConfiguration } from "@/features/settings/runtime/RuntimeConfiguration";
import { useTheme } from "@/hooks/useTheme";
import { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { ClientProvider } from "@/providers/ClientProvider";

const client = new CirnoClient({ url: "ws://localhost:1", reconnect: false });
const kind = new URLSearchParams(location.search).get("kind") ?? "token";
const ssh = { host: "lab.example", username: "researcher", port: 22, auth_method: "password", has_password: true,
  identity_file: "", host_key: "", node_enabled: false, working_directory: "", init_script: "", environment: {} };
client.requestMutation = async <T,>(_method: string, args?: unknown): Promise<T> => {
  const payload = args as { action: string; values: unknown };
  if (payload.action === "credentials.list") return { records: [{ id: "example", label: "Research server", kind, agent_visible: true }] } as T;
  if (payload.action === "credentials.describe") return { ssh } as T;
  if (payload.action === "credentials.reveal") return (kind === "ssh" ? { ssh: { ...ssh, password: "example-saved-secret" } } : { value: "example-saved-secret" }) as T;
  return { runtime_config: payload.values } as T;
};

export function CredentialVisibilityFixture() {
  useTheme();
  const [settings, setSettings] = useState({ runtime_config: {
    "agents.defaults.always_skills": ["paper-reading"],
    "agents.defaults.memory.context_files": ["memory/workspace/STANDARDS.md"],
    "agents.defaults.memory.context_files_tokens": 2000,
  } } as unknown as SettingsPayload);
  const state = useRuntimeConfigSettings(settings, client, setSettings);
  return <main className="mx-auto max-w-3xl px-4 py-6" style={{ overflowY: "auto", height: "100%" }}>
    {new URLSearchParams(location.search).has("context") ? <ClientProvider client={client} token="fixture">
      <SkillsLibrary skills={[
        { name: "paper-reading", description: "Read scientific papers", source: "home", available: true },
        { name: "research-review", description: "Review results", source: "home", available: true, always: true },
      ]} injection={skillInjectionSettings(state)} />
      <RuntimeConfiguration page="memory" settings={settings} state={state} isRestarting={false} />
    </ClientProvider> : <CredentialsTab client={client} active />}
  </main>;
}
