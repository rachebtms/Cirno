import { Button } from "@heroui/react";
import { releaseAuthorization } from "@/features/settings/providers/oauth/releaseAuthorization";
import { ModelSetup } from "@/features/entry/ModelSetup";
import { useMemo, useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import { ClientProvider } from "@/providers/ClientProvider";
import { SettingsView } from "@/features/settings/SettingsView";
import { settings } from "@/dev/gallery/settings";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";

export function ProviderModelFixture() {
  const { preference, setTheme } = useTheme();
  const [complete, setComplete] = useState(false);
  const [modelWrites, setModelWrites] = useState(0);
  const [modelUpdates, setModelUpdates] = useState<Record<string, string>[]>([]);
  const fixture = useMemo(() => {
    const flags = new URLSearchParams(location.search);
    let snapshot: SettingsPayload = { ...settings, model_api_resolution_supported: flags.has("apiPreviewFailure"),
      providers: [{ id: "openai", name: "OpenAI", configured: true, api_key_hint: "configured", api_base: "https://api.openai.com/v1", model_catalog: "official",
        advanced_fields: ["extra_headers", "extra_query", "extra_body", "use_proxy"], provider_api_configurable: true, model_api_configurable: true },
        { id: "deepseek", name: "DeepSeek", configured: false },
        ...(flags.has("oauth") ? [{ id: "github_copilot", name: "GitHub Copilot", configured: false, auth_type: "oauth" as const, api_key_required: false, oauth_login_supported: true, model_catalog: "hybrid" as const }] : [])],
      model_presets: [{ id: "research", name: "Research", model: "research-model", provider: "openai", active: true, is_default: false,
        max_tokens: 8192, context_window_tokens: 128000, temperature: .1, reasoning_effort: null }], model_call_order: ["research"] };
    let catalogRequests = 0;
    let modelRequests = 0;
    let previewRequests = 0;
    let authorizationPolls = 0, cancellations = 0;
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), location.href);
      if (url.origin !== location.origin || !url.pathname.startsWith("/v0/")) return original(input, init);
      if (url.pathname === "/v0/auth/complete") return Response.json({ ok: true });
      if (url.pathname === "/v0/settings") return Response.json(snapshot);
      if (url.pathname === "/v0/settings/model-api") {
        if (flags.has("apiPreviewFailure") && previewRequests++ === 0) return Response.json({ error: "API preview unavailable" }, { status: 503 });
        return Response.json({ provider: "openai", api: "responses" });
      }
      if (url.pathname === "/v0/settings/provider-models" && new URLSearchParams(location.search).has("catalogFailure") && catalogRequests++ === 0) return Response.json({
        provider: "openai", label: "OpenAI", status: "available", catalog_kind: "hybrid", source: "stale", error_kind: "unavailable",
        message: "Provider temporarily unavailable (request research-42)", models: [{ id: "analysis-model", label: "Analysis model", context_window: 256000 }], model_count: 1,
      });
      if (url.pathname === "/v0/settings/provider-models") return Response.json({ provider: "openai", label: "OpenAI", status: "available", catalog_kind: "official",
        models: [{ id: "research-model", context_window: 128000, reasoning_efforts: ["low", "high"] }, { id: "analysis-model", context_window: 256000 }], model_count: 2 });
      if (url.pathname === "/v0/settings/usage") return Response.json(snapshot.usage ?? {});
      return Response.json({ error: `No fixture response for ${url.pathname}` }, { status: 404 });
    };
    const client = { status: "open", onStatus: (handler: (status: string) => void) => { handler("open"); return () => {}; }, requestMutation: async (action: string, args: Record<string, string>) => {
      if (action === "settings.provider.oauth_login") return { status: "authorization_required", provider: args.provider,
        flow_id: "fixture-authorization", authorization_url: "https://github.com/login/device", user_code: "FIXT-URE1", completion_input: "device_code", expires_in: 600 };
      if (action === "settings.provider.oauth_complete") {
        if (args.cancel) {
          if ((flags.has("oauthCancelFailure") || flags.has("oauthReleaseFailure")) && cancellations++ === 0) throw new Error("Authorization cancellation unavailable");
          return { status: "cancelled" };
        }
        if (flags.has("oauthPollFailure")) {
          if (++authorizationPolls === 1) throw new Error("Authorization service unavailable");
          snapshot = { ...snapshot, providers: snapshot.providers.map(provider => provider.id === args.provider ? { ...provider, configured: true } : provider) };
          return snapshot;
        }
        return { status: "pending", provider: args.provider, flow_id: args.flow_id };
      }
      if (action === "settings.provider.update") {
        if (new URLSearchParams(location.search).has("saveFailure")) throw new Error("Provider save failed");
        snapshot = { ...snapshot, providers: snapshot.providers.map(provider => provider.id === args.provider ? { ...provider, configured: true, api_base: args.apiBase } : provider) };
        return snapshot;
      }
      if (action === "settings.model_configuration.update") {
        setModelUpdates(updates => [...updates, args]);
        setModelWrites(++modelRequests);
        if (flags.has("modelSaveFailure") && modelRequests === 1) throw new Error("Model save failed");
        snapshot = { ...snapshot, model_presets: snapshot.model_presets.map(preset => preset.id === args.id ? {
          ...preset, ...args,
          reasoning_effort: args.reasoning_effort === undefined ? preset.reasoning_effort : args.reasoning_effort || null,
        } : preset) };
        return snapshot;
      }
      throw new Error(`No fixture mutation for ${action}`);
    } } as unknown as CirnoClient;
    return { client, settings: snapshot };
  }, []);
  if (complete) return <h1>Model setup complete</h1>;
  if (new URLSearchParams(location.search).has("oauthReleaseFailure")) return <main><Button onPress={() => void releaseAuthorization(fixture.client, {
    status: "authorization_required", provider: "github_copilot", flow_id: "released-flow", authorization_url: "https://github.com/login/device", expires_in: 600,
  })}>Release inactive sign-in</Button></main>;
  return <main style={{ height: "100dvh", display: "flex" }}><ClientProvider client={fixture.client} token="fixture-provider-model">
    <output aria-label="Model saves" className="sr-only">{modelWrites}</output>
    <output aria-label="Model updates" className="sr-only">{JSON.stringify(modelUpdates)}</output>
    {new URLSearchParams(location.search).has("setup") ? <ModelSetup onComplete={() => setComplete(true)} onModelNameChange={() => {}} /> : <SettingsView initialSettings={fixture.settings} initialSection="models" themePreference={preference} onChangeTheme={setTheme} onBackToChat={() => {}} onModelNameChange={() => {}} />}
  </ClientProvider></main>;
}
