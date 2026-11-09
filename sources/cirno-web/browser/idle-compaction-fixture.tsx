import { useState } from "react";

import { SettingsView } from "@/features/settings/SettingsView";
import { RUNTIME_CONFIG_FIELDS } from "@/features/settings/system/runtime-config-fields";
import { settings } from "@/dev/gallery/settings";
import { CirnoClient } from "@/lib/cirno-client";
import type { RuntimeConfigValue, SettingsPayload } from "@/lib/contracts/settings";
import { ClientProvider } from "@/providers/ClientProvider";

const path = "agents.defaults.idle_compact_after_minutes";
const storageKey = "fixture.idle-compaction-minutes";
const client = new CirnoClient({ url: "ws://127.0.0.1:1", reconnect: false });
let failNext = false;
const initial: SettingsPayload = {
  ...settings,
  runtime_config: Object.fromEntries(RUNTIME_CONFIG_FIELDS.map((field) => [field.path,
    field.kind === "boolean" ? false : field.kind === "toggle" ? field.options?.[0] ?? ""
      : field.kind === "list" ? [] : field.kind === "number" ? 20 : field.kind === "duration" ? 60 : "",
  ])),
};
initial.runtime_config![path] = Number(localStorage.getItem(storageKey) ?? 720);
const section = new URLSearchParams(location.search).get("section");
if (section === "models") {
  initial.model_presets = [{ id: "primary", name: "primary", is_default: false, model: "gpt-5.4", provider: "openai", resolved_provider: "openai", active: true, max_tokens: 8192, temperature: 0.1, reasoning_effort: "low", reasoning_history: "auto", context_window_tokens: 200_000 }];
  initial.model_call_order = ["primary"];
}
if (section === "memory-search") Object.assign(initial.runtime_config!, {
  "agents.defaults.memory.embedding_enabled": true,
  "agents.defaults.memory.embedding_provider": "api",
  "agents.defaults.memory.embedding_api_base": "https://embedding.example/v1",
  "agents.defaults.memory.embedding_api_model": "research-embedding",
  "agents.defaults.memory.embedding_api_key": "••••••••",
  "agents.defaults.memory.embedding_api_chunk_chars": 768,
});
Object.assign(initial.runtime_config!, {
  "agents.defaults.compaction.output_reserve_percent": 5,
  "agents.defaults.compaction.max_tokens": 8192,
  "agents.defaults.compaction.reasoning_effort": "low",
  "agents.defaults.compaction.checkpoint_reminder_percent": 85,
});
let persisted = initial;

client.requestMutation = async <T,>(action: string, payload?: Record<string, unknown>): Promise<T> => {
  if (action !== "settings.runtime_config.update") throw new Error(`Unexpected mutation: ${action}`);
  if (failNext) {
    failNext = false;
    throw new Error("Fixture save failed");
  }
  const values = payload?.values as Record<string, RuntimeConfigValue>;
  if (path in values) localStorage.setItem(storageKey, String(values[path]));
  persisted = { ...persisted, runtime_config: { ...persisted.runtime_config, ...values }, requires_restart: true,
    restart_required_sections: ["runtime"] };
  return persisted as T;
};

export function installIdleCompactionApi() {
  const fetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/v0/")) return fetch(input, init);
    const bodies: Record<string, unknown> = {
      "/v0/settings": persisted,
      "/v0/settings/cirno-features": { features: [], enabled_count: 0, requires_restart: false },
      "/v0/settings/api-service": { installed: false, running: false, managed: false, host: "127.0.0.1",
        port: 8900, timeout: 120, endpoint: "http://127.0.0.1:8900/v1", command: "cirno serve" },
    };
    return Response.json(bodies[url.pathname] ?? {});
  };
}

export function IdleCompactionFixture() {
  const [snapshot, setSnapshot] = useState(initial);
  return <ClientProvider client={client} token="fixture">
    <div className="flex min-h-screen flex-col">
      <div className="flex gap-3 p-2 text-xs">
        <button onClick={() => { failNext = true; }}>Fail next save</button>
        <output aria-label="Persisted minutes">{String(snapshot.runtime_config?.[path])}</output>
      </div>
      <SettingsView themePreference="light" initialSection={section === "memory-search" ? "memory-search" : section === "models" ? "models" : "context"} initialSettings={initial}
        onSettingsChange={setSnapshot} onChangeTheme={() => {}} onBackToChat={() => {}}
        onModelNameChange={() => {}} onRestart={() => {}} />
    </div>
  </ClientProvider>;
}
