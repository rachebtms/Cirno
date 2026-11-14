import { useLayoutEffect, useState } from "react";

import { ConversationCatalogPreview } from "@/dev/fixtures/ConversationCatalogPreview";
import { SettingsPage } from "@/features/settings/SettingsPage";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import { AutomationsPage } from "@/features/automations";
import { RUNTIME_CONFIG_FIELDS } from "@/features/settings/system/runtime-config-fields";
import { useSettingsController } from "@/features/settings/useSettingsController";
import { SessionAutomationsDialog } from "@/features/automations/session/SessionAutomationsDialog";
import { settings } from "@/dev/gallery/settings";
import { setAppLanguage } from "@/i18n";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { SkillDetail } from "@/lib/contracts/skills";

const noop = () => {};
const now = Date.now();
const names = ["Project summary", "Review changes", "Release checklist", "Documentation"];
const jobs: SessionAutomationJob[] = names.slice(0, 3).map((name, index) => ({
  id: `preview-${index}`, name, enabled: true, schedule: { kind: "every", every_ms: 3_600_000 },
  payload: { message: "Summarize the project." }, state: { next_run_at_ms: now + index * 86_400_000 + 3_600_000 },
}));
const sessions: ChatSummary[] = names.map((title, index) => ({
  key: `websocket:preview-${index}`, chatId: `preview-${index}`, channel: "websocket", title, preview: "",
  handle: { id: `preview-${index}`, name: `topic${index}` },
  createdAt: new Date(now).toISOString(), updatedAt: new Date(now).toISOString(),
}));
const skill: SkillDetail = {
  name: "project-review", description: "Review the repository and summarize actionable changes.", source: "builtin", available: true, enabled: true,
  requirements: { bins: [], env: [], missing_bins: [], missing_env: [] }, raw_markdown: "# Project review\n\nRead the repository instructions before reviewing changes.",
};
const previewSettings: SettingsPayload = {
  ...settings,
  version: { current: "0.2.17", commit: null },
  advanced: { ...settings.advanced, exec_max_runtime_limit: 86400 },
  model_presets: [{ id: "primary", name: "primary", model: "openai-codex/gpt-6.1-sol", provider: "openai", resolved_provider: "openai", active: true, is_default: false,
    max_tokens: 8192, context_window_tokens: 500_000, temperature: 0.1, reasoning_effort: "max" }],
  model_call_order: ["primary"],
  runtime_config: Object.fromEntries(RUNTIME_CONFIG_FIELDS.map((field) => [field.path,
    field.kind === "boolean" ? true : field.kind === "toggle" ? field.options?.[1] ?? "" : field.kind === "list" ? [] : field.kind === "number" ? 20 : field.kind === "duration" ? 3600 : field.kind === "idle-compaction" ? 15 : "",
  ])),
};
let detailState = "loaded";

export function installSkeletonPreviewApi() {
  // Windows headless Chromium can report denied even after a context permission grant.
  if (new URLSearchParams(location.search).get("notificationPermission") === "granted") {
    Object.defineProperty(Notification, "permission", { configurable: true, value: "granted" });
  }
  const fetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/v0/")) return fetch(input, init);
    if ((init?.method ?? "GET") !== "GET") return Response.json({ error: "Read-only preview" }, { status: 403 });
    if (url.pathname.startsWith("/v0/webui/skills/")) {
      if (detailState === "loading") await new Promise<void>(() => {});
      return detailState === "error" ? Response.json({ error: "Preview read failed" }, { status: 503 }) : Response.json(skill);
    }
    const bodies: Record<string, unknown> = {
      "/v0/settings": previewSettings, "/v0/settings/usage": { usage: null },
      "/v0/webui/automations": { jobs }, "/v0/settings/cirno-features": { features: [], enabled_count: 0, requires_restart: false },
      "/v0/settings/cli-apps": { apps: [], installed_count: 0 }, "/v0/settings/mcp-presets": { presets: [], installed_count: 0 },
      "/v0/settings/api-service": { installed: false, running: false, managed: false, host: "127.0.0.1", port: 8900, timeout: 120, endpoint: "http://127.0.0.1:8900/v1", command: "cirno serve" },
    };
    return Response.json(bodies[url.pathname] ?? {});
  };
}

export function SkeletonAdditionsFixture() {
  return new URLSearchParams(location.search).has("preview") ? <SkeletonPreview /> : <SkeletonSurface />;
}

function SkeletonPreview() {
  const params = new URLSearchParams(location.search);
  const [surface, setSurface] = useState(params.get("surface") ?? "chats");
  const [state, setState] = useState(params.get("state") ?? "loaded");
  const [section, setSection] = useState<SettingsSectionKey>((params.get("section") ?? "appearance") as SettingsSectionKey);
  const [density, setDensity] = useState<"compact" | "comfortable">(params.has("compact") ? "compact" : "comfortable");
  const [dark, setDark] = useState(false);
  const [language, setLanguage] = useState(document.documentElement.lang);
  const source = new URLSearchParams({ case: "skeleton-additions", surface, state, section });
  if (density === "compact") source.set("compact", "");
  if (dark) source.set("dark", "");
  const changeLanguage = (next: Parameters<typeof setAppLanguage>[0]) => { void setAppLanguage(next).then(() => setLanguage(next)); };
  return <div style={{ height: "100dvh", display: "flex", flexDirection: "column" }}>
    <nav style={{ position: "sticky", top: 0, zIndex: 100, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "12px 16px" }} className="border-b bg-background text-sm" aria-label="Skeleton preview controls">
      <span className="font-medium">首载骨架验收</span>
      <select aria-label="Surface" value={surface} onChange={(event) => setSurface(event.target.value)} className="rounded border bg-background p-1">
        {["chats", "settings", "automations", "skill-detail", "session-jobs"].map((name) => <option key={name}>{name}</option>)}
      </select>
      <select aria-label="State" value={state} onChange={(event) => setState(event.target.value)} className="rounded border bg-background p-1">
        {["loading", "loaded", "refresh", "error"].map((name) => <option key={name}>{name}</option>)}
      </select>
      {surface === "settings" ? <select aria-label="Section" value={section} onChange={(event) => setSection(event.target.value as SettingsSectionKey)} className="rounded border bg-background p-1">
        {["overview", "appearance", "models", "capabilities", "runtime", "advanced", "about", "channels", "apps", "skills", "automations"].map((name) => <option key={name}>{name}</option>)}
      </select> : null}
      {surface === "chats" ? <button onClick={() => setDensity(density === "compact" ? "comfortable" : "compact")}>{density}</button> : null}
      <button onClick={() => { document.documentElement.classList.toggle("dark", !dark); setDark(!dark); }}>{dark ? "浅色" : "深色"}</button>
      <button onClick={() => changeLanguage("zh-CN")}>中文</button><button onClick={() => changeLanguage("en")}>English</button>
      <span className="text-xs text-muted-foreground">固定展示状态；仅示例数据，无模型调用</span>
    </nav>
    <iframe key={language} title="首载骨架预览" src={`/browser/fixture.html?${source}`} style={{ width: "100%", minHeight: 0, flex: 1, border: 0 }} />
  </div>;
}

function SkeletonSurface() {
  const params = new URLSearchParams(location.search);
  const surface = params.get("surface") ?? "chats";
  const state = params.get("state") ?? "loaded";
  const section = (params.get("section") ?? "appearance") as SettingsSectionKey;
  const dark = params.has("dark");
  useLayoutEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  const controller = useSettingsController({ initialSection: section, initialSettings: previewSettings, onModelNameChange: noop });
  detailState = state;
  const loading = state === "loading" || state === "refresh";
  const empty = state === "loading" || state === "error";
  return <div data-testid="skeleton-additions" className="min-h-[85vh] bg-settings-canvas">
      {surface === "settings" ? <div style={{ minHeight: "85vh" }} className="flex flex-col"><SettingsPage controller={{ ...controller, loading, settings: empty ? null : previewSettings, error: state === "error" ? "Preview read failed" : null,
        systemState: { ...controller.systemState,
          cliApps: empty ? null : { apps: [], installed_count: 0 }, cliAppsLoading: loading,
          mcpPresets: empty ? null : { presets: [], installed_count: 0 }, mcpPresetsLoading: loading,
          cirnoFeatures: empty ? null : { features: [], enabled_count: 0, requires_restart: false }, cirnoFeaturesLoading: loading,
          automations: empty ? null : { jobs }, automationsLoading: loading,
          automationsError: state === "error" ? "Preview read failed" : null,
        },
      }}
        themePreference={dark ? "dark" : "light"} showSidebar onChangeTheme={noop} onBackToChat={noop}
        skills={empty ? [] : [skill]} skillsLoading={loading && empty} skillsError={state === "error"} isRestarting={false} /></div>
        : <main className="settings-grid mx-auto w-full p-4" style={surface === "automations" ? { maxWidth: 960 } : undefined}>
          {surface === "chats" ? <div style={{ height: 620, width: 800, maxWidth: "100%" }} className="border border-border bg-background">
            <ConversationCatalogPreview key={state} sessions={empty ? [] : sessions} loading={loading} />
          </div>
            : surface === "automations" ? <AutomationsPage payload={empty ? null : { jobs }} loading={loading} filter="all" actionKey={null} error={state === "error" ? "Preview read failed" : null}
              onFilterChange={noop} onAction={noop} onRequestEdit={noop} onRequestDelete={noop} />
              : surface === "skill-detail" ? <SkillsLibrary skills={[skill]} />
                : surface === "session-jobs" ? <SessionAutomationsDialog title="Project review" jobs={empty ? [] : jobs} loading={loading} loadError={state === "error" ? "Fixture task discovery failed" : null} now={now}
                  onAction={async () => jobs} onEdit={async () => jobs} />
                  : null}
        </main>}
    </div>;
}
