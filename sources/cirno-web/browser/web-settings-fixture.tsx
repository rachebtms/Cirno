import { useMemo, useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import { ClientProvider } from "@/providers/ClientProvider";
import { SettingsView } from "@/features/settings/SettingsView";
import { settings } from "@/dev/gallery/settings";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";

export function WebSettingsFixture() {
  const { preference, setTheme } = useTheme();
  const [saved, setSaved] = useState("");
  const fixture = useMemo(() => {
    let snapshot: SettingsPayload = { ...settings,
      runtime_config: { ...settings.runtime_config, "tools.web.enable": true, "network.proxy": "http://localhost:7890" },
      web_search: { ...settings.web_search, provider: "duckduckgo", api_key_hint: null, timeout: 30, providers: [
        { name: "duckduckgo", label: "DuckDuckGo", credential: "none" },
        { name: "brave", label: "Brave Search", credential: "api_key" },
      ] },
    };
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), location.href);
      if (url.origin !== location.origin || !url.pathname.startsWith("/v0/")) return original(input, init);
      if (url.pathname === "/v0/settings") return Response.json(snapshot);
      if (url.pathname === "/v0/settings/cirno-features") return Response.json({ features: [], installed_count: 0 });
      if (url.pathname === "/v0/settings/cli-apps") return Response.json({ apps: [], installed_count: 0 });
      if (url.pathname === "/v0/settings/mcp-presets") return Response.json({ presets: [], installed_count: 0 });
      return Response.json({ error: `No fixture response for ${url.pathname}` }, { status: 404 });
    };
    const client = { status: "open", onStatus: (handler: (status: string) => void) => { handler("open"); return () => {}; }, requestMutation: async (action: string, args: Record<string, unknown>) => {
      if (action !== "settings.web_search.update") throw new Error(`No fixture mutation for ${action}`);
      snapshot = { ...snapshot, web_search: { ...snapshot.web_search, provider: String(args.provider), max_results: Number(args.max_results), timeout: Number(args.timeout), api_key_hint: args.api_key ? "configured-search-key" : snapshot.web_search.api_key_hint },
        web: { ...snapshot.web, fetch: { ...snapshot.web.fetch, use_jina_reader: Boolean(args.use_jina_reader) } } };
      setSaved(JSON.stringify(args));
      return snapshot;
    } } as unknown as CirnoClient;
    return { client, settings: snapshot };
  }, []);
  return <main style={{ height: "100dvh", display: "flex" }}><ClientProvider client={fixture.client} token="fixture-web-settings">
    <SettingsView initialSettings={fixture.settings} initialSection="capabilities" themePreference={preference} onChangeTheme={setTheme} onBackToChat={() => {}} onModelNameChange={() => {}} />
  </ClientProvider><output hidden aria-label="Saved web settings">{saved}</output></main>;
}
