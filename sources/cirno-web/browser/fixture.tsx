import { KeyboardViewportFixture } from "./keyboard-viewport-fixture";
import { PreviewLifetimeFixture } from "./preview-lifetime-fixture";
import { DraftPersistenceFixture, installDraftPersistenceFailure } from "./draft-persistence-fixture";
import { MessageDeliveryFixture } from "./message-delivery-fixture";
import { OperationNotices } from "@/ui/feedback/OperationNotices";
import { ConversationsFixture } from "./conversations-fixture";
import { ChannelInstancesFixture } from "./channel-instances-fixture";
import { ChannelFieldsFixture } from "./channel-fields-fixture";
import { ChannelsFixture } from "./channels-fixture";
import { TelegramFixture } from "./telegram-fixture";
import { SkillsFixture, installSkillsFixtureApi } from "./skills-fixture";
import { MemoryFixture } from "./memory-fixture";
import { AutomationsFixture } from "./automations-fixture";
import { AutomationCatalogFixture } from "./automation-catalog-fixture";
import { NotificationsFixture } from "./notifications-fixture";
import { NodesFixture } from "./nodes-fixture";
import { TraceFixture } from "./trace-fixture";
import { EntryFixture } from "./entry-fixture";
import { WebSettingsFixture } from "./web-settings-fixture";
import type { AppsKindFilter } from "@/features/settings/apps/model/contracts";
import { McpSettingsFixture } from "./mcp-settings-fixture";
import { ProviderModelFixture } from "./provider-model-fixture";
import { InterfaceProvider } from "@/providers/InterfaceProvider";
import { InboxFixture } from "./inbox-fixture";
import { readOwnerPreferences } from "@/features/preferences/store";
import { installPreviewPreferences } from "./preview-preferences";
import { WorkspaceFixture } from "./workspace-fixture";
import { UserQuestionsFixture } from "./user-questions-fixture";
import { UsageChartFixture } from "./usage-chart-fixture";
import { UploadSettingsFixture } from "./upload-settings-fixture";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { MessageBubble } from "@/features/messages";
import { AppsCatalogSettings, DEFAULT_CUSTOM_MCP_FORM } from "@/features/settings/apps/AppsCatalogSettings";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { PromptNavigator } from "@/components/thread/PromptNavigator";
import type { ThreadViewportHandle } from "@/components/thread/viewport/contracts";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { TabSurface } from "@/ui/layout/TabSurface";
import { useTheme } from "@/hooks/useTheme";
import { usePromptHistory } from "@/hooks/usePromptHistory";
import { ClientProvider } from "@/providers/ClientProvider";
import { CirnoClient } from "@/lib/cirno-client";
import { fetchWebuiThread } from "@/lib/api";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { TooltipProvider } from "@/components/ui/tooltip";
import { initializeI18n, setAppLanguage } from "@/i18n";
import { normalizeLocale } from "@/i18n/config";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { UIMessage } from "@/lib/contracts/messages";
import { SettingsRebuildFixture } from "./settings-rebuild-fixture";
import { SkeletonFixture } from "./skeleton-fixture";
import { installSkeletonPreviewApi, SkeletonAdditionsFixture } from "./skeleton-additions-fixture";
import { NewChatSkeletonFixture } from "./new-chat-skeleton-fixture";
import "../src/globals.css";
import { DiagramFixture } from "./diagram-fixture";
import { TypographyFixture } from "./typography-fixture";
import { CodeWrappingFixture } from "./code-wrapping-fixture";
import { InlineReferencesFixture } from "./inline-references-fixture";
import { HistoryBoundaryFixture } from "./history-boundary-fixture";
import { ChatFailureFixture } from "./chat-failure-fixture";
import { ThreadLoadingFixture } from "./thread-loading-fixture";
import { AnswerOrderFixture } from "./answer-order-fixture";
import { CatalogActivityFixture } from "./catalog-activity-fixture";
import { ActivityLogosFixture } from "./activity-logos-fixture";
import { HistoryHydrationFixture } from "./history-hydration-fixture";
import { IdleCompactionFixture, installIdleCompactionApi } from "./idle-compaction-fixture";
import { FileEditPathFixture } from "./file-edit-path-fixture";
import { QueuedGuidanceFixture } from "./queued-guidance-fixture";
import { WorkspaceAlignmentFixture } from "./workspace-alignment-fixture";
import { ComposerActionFixture } from "./composer-action-fixture";
import { MobileChatLayoutFixture } from "./mobile-chat-layout-fixture";
import { ThemeToggleFixture } from "./theme-toggle-fixture";
import { DisplayMathFixture } from "./display-math-fixture";
import { AttachmentLayoutFixture } from "./attachment-layout-fixture";
import { LoadedSessionSearchFixture } from "./loaded-session-search-fixture";
import { MessageActionsFixture } from "./message-actions-fixture";
import { MessagePresentationFixture } from "./message-presentation-fixture";
import { BackupFixture } from "./backup-fixture";
import { AppearanceFixture } from "./appearance-fixture";
import { installSubagentDockApi, SubagentDockFixture } from "./subagent-dock-fixture";

const history: UIMessage[] = [
  { id: "question", role: "user", content: "Earlier question", createdAt: 1_700_000_000_000 },
  { id: "answer", role: "assistant", content: "Earlier answer", createdAt: 1_700_000_001_000 },
];
const trace: UIMessage = {
  id: "trace", role: "tool", kind: "trace", content: "Earlier tool call", createdAt: 1_700_000_002_000,
};

function HistoryFixture() {
  const [open, setOpen] = useState(false);
  return <main>
    <button onClick={() => setOpen(!open)}>{open ? "Close history" : "Reopen history"}</button>
    <section aria-label="Persisted history">
      {open && <>
        <ThreadMessages messages={history} isStreaming={false} />
        <MessageBubble message={trace} />
      </>}
    </section>
  </main>;
}

function TallDialogFixture({ placement }: { placement: "center" | "bottom" }) {
  return <main aria-label="Background content" style={{ height: 240, overflowY: "auto" }}>
    <div style={{ minHeight: 1800 }}><Dialog>
      <DialogTrigger asChild><button>Open tall dialog</button></DialogTrigger>
      <DialogContent placement={placement}>
        <DialogTitle>Tall dialog</DialogTitle>
        <DialogDescription>All controls must remain reachable in a short viewport.</DialogDescription>
        {Array.from({ length: 30 }, (_, index) => <label key={index}>
          Field {index + 1}<input aria-label={`Field ${index + 1}`} style={{ display: "block", height: 40 }} />
        </label>)}
        <DialogClose asChild><button>Save tall dialog</button></DialogClose>
      </DialogContent>
    </Dialog></div>
  </main>;
}

function SessionMessagesFixture() {
  const messages: UIMessage[] = [
    { id: "own-input", role: "user", content: "Please review the update.", createdAt: 1 },
    {
      id: "session-message:short", role: "user", content: "Looks good.", createdAt: 2,
      sessionMessage: { message_id: "short", session: { id: "handle_0123456789abcdef0123456789abcdef", name: "mira" } },
    },
    {
      id: "session-message:long", role: "user", createdAt: 3,
      content: "**Review notes**\n\n- Keep the layout left-aligned.\n- Preserve Markdown and links.\n\n```ts\nconst message = \"" + "long-path/".repeat(30) + "\";\n```\n\n[Release notes](https://example.com/release-notes)",
      sessionMessage: { message_id: "long", session: { id: "handle_fedcba9876543210fedcba9876543210", name: "nori" } },
    },
    { id: "reply", role: "assistant", content: "Thanks, I will keep those details.", createdAt: 4 },
  ];
  return <main className="mx-auto max-w-3xl px-6 py-8" aria-label="Session messages">
    <ThreadMessages messages={messages} isStreaming={false} />
  </main>;
}

const parameters = new URLSearchParams(location.search);
const railClient = new CirnoClient({ url: "ws://127.0.0.1:8765", reconnect: false });
const railHistory: UIMessage[] = Array.from({ length: 5 }, (_, index) => [
  { id: `u${1995 + index}`, role: "user" as const, content: `Question ${1995 + index}`, createdAt: index + 1 },
  { id: `a${1995 + index}`, role: "assistant" as const, content: "A synthetic answer.\n\n".repeat(8), createdAt: index + 1 },
]).flat();
function RailFixture() {
  useTheme();
  const viewportRef = useRef<ThreadViewportHandle>(null);
  const [messages, setMessages] = useState(parameters.has("real") ? [] : railHistory);
  const [version, setVersion] = useState(1);
  const [streaming, setStreaming] = useState(false);
  useEffect(() => {
    if (!parameters.has("real")) return;
    const controller = new AbortController();
    void fetchWebuiThread("fixture", "websocket:rail", { limit: 40, signal: controller.signal }).then((page) => {
      if (page && !controller.signal.aborted) setMessages(projectThreadEvents(page.events));
    });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!streaming) return;
    let count = 0;
    const user: UIMessage = { id: "stream-user", role: "user", content: "Streaming question", createdAt: Date.now() };
    const timer = window.setInterval(() => {
      count++;
      setMessages((current) => [...current.filter((message) => message.id !== "stream-user" && message.id !== "stream-answer"), user,
        { id: "stream-answer", role: "assistant", content: "Streaming text. ".repeat(count), createdAt: user.createdAt + 1, isStreaming: count < 120 }]);
      if (count === 120) setStreaming(false);
    }, 16);
    return () => window.clearInterval(timer);
  }, [streaming]);
  const navigation = usePromptHistory(messages.length ? "websocket:rail" : null, version, messages);
  const composer = <div style={{ height: parameters.has("tall-composer") ? 240 : 100, border: "1px solid #ddd", borderRadius: 20, padding: 20 }}>Message cirno</div>;
  const viewport = <ThreadViewport ref={viewportRef}
    messages={messages} isStreaming={streaming} conversationKey="websocket:rail"
    navigation={parameters.has("short") ? undefined : navigation} composer={composer} />;
  return <main style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
    {parameters.has("directory") && <div className="flex h-10 shrink-0 items-center justify-end border-b px-3">
      <PromptNavigator messages={messages} prompts={navigation.prompts} source={navigation.source}
        onJumpToPrompt={(id) => viewportRef.current?.jumpToUserPrompt(id)} />
    </div>}
    {parameters.has("real") && <div>
      <button onClick={() => setVersion((value) => value + 1)}>Refresh index</button>
      <button onClick={() => setStreaming(true)} disabled={streaming}>{streaming ? "Streaming" : "Simulate stream"}</button>
    </div>}
    {parameters.has("workbench")
      ? <TabSurface role="region" aria-label="Workbench" className="workbench-pane">{viewport}</TabSurface>
      : viewport}
  </main>;
}
const unbrandedPlugin: McpPresetInfo = {
  name: "plugin-cirno-workflows", display_name: "Cirno Workflows", category: "Workflow",
  description: "Engineering workflows", docs_url: "", requires: "Project files", note: "", connection_summary: "",
  transport: "stdio", install_supported: false, installed: true, configured: true,
  enabled: true, available: true, status: "enabled", required_fields: [], source: "agent-plugin",
};
function AppsFixture() {
  useTheme();
  const noop = () => {};
  const customEditing = parameters.has("custom-edit");
  const managing = parameters.has("manage") || customEditing;
  const connectionLayout = parameters.has("connection-layout");
  const [filter, setFilter] = useState<AppsKindFilter>(parameters.has("cli") ? "cli" : managing || connectionLayout ? "mcp" : "ready");
  const [query, setQuery] = useState("");
  const [customForm, setCustomForm] = useState(DEFAULT_CUSTOM_MCP_FORM);
  const [customConfig, setCustomConfig] = useState({
    type: "stdio", command: "npx", args: ["-y", "docs-mcp"], env: { API_KEY: "${DOCS_API_KEY}" },
    cwd: "/workspace/docs", toolTimeout: 60, enabledTools: ["search", "read"],
  });
  const [importDraft, setImportDraft] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [actions, setActions] = useState<unknown[]>([]);
  const presets: McpPresetInfo[] = connectionLayout ? [
    {
      name: "linear", display_name: "Linear", category: "productivity", description: "Manage issues and projects",
      docs_url: "", transport: "streamableHttp", auth: "oauth", requires: "Linear account", note: "",
      install_supported: true, installed: parameters.has("runtime"), configured: parameters.has("runtime"),
      available: true, status: parameters.has("runtime") ? "configured" : "not_installed",
      required_fields: [], connection_summary: "", source: "preset",
      brand_color: "#5E6AD2", runtime_status: parameters.has("runtime") ? "connecting" : undefined,
    },
    ...["Notion", "GitHub", "Xmind"].map((name): McpPresetInfo => ({
      name: name.toLowerCase(), display_name: name, category: "productivity", description: `Connect your ${name} workspace`,
      docs_url: "", transport: "streamableHttp", auth: "oauth", requires: "", note: "",
      install_supported: true, installed: false, configured: false, available: true,
      status: "not_installed", required_fields: [], connection_summary: "", source: "preset",
    })),
  ] : customEditing ? [{
    name: "docs", display_name: "Docs MCP", category: "custom", description: "Custom MCP server", docs_url: "",
    transport: "stdio", auth: null, requires: "", note: "", install_supported: true, installed: true,
    configured: true, available: true, status: "configured", required_fields: [],
    connection_summary: `${customConfig.command} ${customConfig.args.join(" ")}`, source: "custom",
  }] : managing ? [{
    name: "design", display_name: "Design MCP", category: "design", description: "Read design context",
    docs_url: "", transport: "streamableHttp", auth: "oauth", requires: "", note: "",
    install_supported: true, installed: false, configured: false, available: true,
    status: "not_installed", required_fields: [], connection_summary: "https://design.example/mcp", source: "preset",
  }] : [
    unbrandedPlugin,
    { ...unbrandedPlugin, name: "test-mcp", display_name: "Test MCP", source: "builtin", logo_url: "/missing-app-icon.svg" },
    { ...unbrandedPlugin, name: "brand-example", display_name: "Brand Example", source: "builtin", brand_color: "#5E6AD2" },
  ];
  return <main className="mx-auto max-w-4xl p-6" style={connectionLayout ? { maxWidth: 800 } : undefined}><AppsCatalogSettings
    cliApps={{ apps: parameters.has("cli") ? [true, false].map(installed => ({ name: installed ? "research-cli" : "docs-cli", display_name: installed ? "Research CLI" : "Document tools", category: "research", description: "Inspect papers, data and project workspaces.", requires: "", source: "catalog", entry_point: installed ? "research" : "docs", install_supported: true, skill_installed: installed, installed, available: installed, status: installed ? "installed" : "not_installed" })) : [], installed_count: parameters.has("cli") ? 1 : 0 }}
    mcpPresets={{ presets, installed_count: connectionLayout ? Number(parameters.has("runtime")) : managing ? 0 : 3 }}
    cliAppsLoading={false} mcpPresetsLoading={false} query={query} filter={filter}
    cliActionKey={null} mcpActionKey={null}
    mcpOAuthFlow={connecting ? { flow_id: "fixture", name: "linear", status: "authorization_required", expires_in: 300 } : null}
    mcpOAuthPopupBlocked={false}
    mcpOAuthCallbackUrl="" mcpOAuthCompleting={false} mcpOAuthCallbackError={null}
    cliMessage={null} cliError={null} cliFocusName={null} mcpMessage={null} mcpError={null}
    mcpFieldValues={{}} customMcpForm={customForm} mcpConfigImport={importDraft}
    showBrandLogos={parameters.get("logos") !== "hidden"} requiresRestartPending={false}
    onQueryChange={setQuery} onFilterChange={setFilter} onCliAction={(action, name) => setActions(previous => [...previous, { action, name }])}
    onMcpAction={(action, name, values) => setActions((prev) => [...prev, { action, name, values }])}
    onMcpOAuthConnect={(name, reset, values) => {
      setActions((prev) => [...prev, { action: "oauth", name, reset, values }]);
      if (connectionLayout) setConnecting(true);
    }}
    onMcpOAuthCancel={() => setConnecting(false)} onMcpOAuthOpen={noop}
    onMcpOAuthCallbackUrlChange={noop} onMcpOAuthComplete={noop} onDismissStatus={noop}
    onBackToChat={noop} onMcpFieldChange={noop} onCustomMcpFormChange={setCustomForm}
    onMcpConfigImportChange={setImportDraft} onSaveCustomMcp={() => setActions(previous => [...previous, { action: "custom", form: customForm }])} onImportMcpConfig={() => setActions(previous => [...previous, { action: "import", config: JSON.parse(importDraft) }])}
    onMcpToolsChange={noop}
    mcpConfigEditor={{
      load: async () => JSON.stringify(customConfig),
      save: async (name, config) => { setCustomConfig(JSON.parse(config)); setActions((prev) => [...prev, { action: "edit", name, config: JSON.parse(config) }]); },
    }}
  />{managing && <output hidden data-testid="mcp-actions">{JSON.stringify(actions)}</output>}</main>;
}
if (parameters.get("case") === "draft-persistence") installDraftPersistenceFailure(parameters);
if (parameters.get("case") === "skills-rebuild") installSkillsFixtureApi();
if (parameters.get("case") === "skeleton-additions") installSkeletonPreviewApi();
if (parameters.get("case") === "idle-compaction") installIdleCompactionApi();
if (parameters.get("case") === "subagent-dock") installSubagentDockApi();
installPreviewPreferences({
  language: normalizeLocale(parameters.get("lang") ?? navigator.language),
  ...(parameters.has("theme") ? { themeMode: parameters.get("theme") === "dark" ? "dark" : "light" } : {}),
  ...(parameters.has("readingSize") ? { readingTextSize: "custom", customReadingTextSize: Number(parameters.get("readingSize")) } : {}),
});
await initializeI18n();
await setAppLanguage(normalizeLocale(parameters.get("lang") ?? readOwnerPreferences().language));
createRoot(document.getElementById("root")!).render(<InterfaceProvider><TabSurface className="h-full w-full"><OperationNotices /><TooltipProvider>
  {parameters.get("case") === "preview-lifetime" ? <PreviewLifetimeFixture />
    : parameters.get("case") === "channel-instances"
    ? <ChannelInstancesFixture />
    : parameters.get("case") === "channel-fields"
    ? <ChannelFieldsFixture />
    : parameters.get("case") === "channels-rebuild"
    ? <ChannelsFixture />
    : parameters.get("case") === "telegram-rebuild"
    ? <TelegramFixture />
    : parameters.get("case") === "skills-rebuild"
    ? <SkillsFixture />
    : parameters.get("case") === "memory-rebuild"
    ? <MemoryFixture />
    : parameters.get("case") === "automation-catalog"
    ? <AutomationCatalogFixture />
    : parameters.get("case") === "automations-rebuild"
    ? <AutomationsFixture />
    : parameters.get("case") === "notifications-rebuild"
    ? <NotificationsFixture />
    : parameters.get("case") === "nodes-rebuild"
    ? <NodesFixture />
    : parameters.get("case") === "trace-rebuild"
    ? <TraceFixture />
    : parameters.get("case") === "keyboard-viewport"
    ? <ClientProvider client={railClient} token="fixture"><KeyboardViewportFixture parameters={parameters} /></ClientProvider>
    : parameters.get("case") === "entry"
    ? <EntryFixture />
    : parameters.get("case") === "web-settings-rebuild"
    ? <WebSettingsFixture />
    : parameters.get("case") === "mcp-settings-rebuild"
    ? <McpSettingsFixture />
    : parameters.get("case") === "provider-model-rebuild"
    ? <ProviderModelFixture />
    : parameters.get("case") === "settings-rebuild"
    ? <SettingsRebuildFixture />
    : parameters.get("case") === "user-questions"
    ? <UserQuestionsFixture />
    : parameters.get("case") === "usage-chart"
    ? <UsageChartFixture />
    : parameters.get("case") === "inbox"
      ? <InboxFixture />
    : parameters.get("case") === "workspace"
    ? <WorkspaceFixture />
    : parameters.get("case") === "upload-settings"
    ? <UploadSettingsFixture />
    : parameters.get("case") === "message-presentation"
    ? <MessagePresentationFixture />
    : parameters.get("case") === "message-actions"
    ? <MessageActionsFixture />
    : parameters.get("case") === "backup"
    ? <BackupFixture />
    : parameters.get("case") === "appearance"
    ? <AppearanceFixture />
    : parameters.get("case") === "loaded-session-search"
    ? <LoadedSessionSearchFixture />
    : parameters.get("case") === "subagent-dock"
    ? <SubagentDockFixture parameters={parameters} />
    : parameters.get("case") === "attachments"
    ? <AttachmentLayoutFixture />
    : parameters.get("case") === "theme-toggle"
    ? <ClientProvider client={railClient} token="fixture"><ThemeToggleFixture /></ClientProvider>
    : parameters.get("case") === "mobile-chat-layout"
    ? <ClientProvider client={railClient} token="fixture"><MobileChatLayoutFixture parameters={parameters} /></ClientProvider>
    : parameters.get("case") === "composer-action"
    ? <ComposerActionFixture parameters={parameters} />
    : parameters.get("case") === "workspace-alignment"
    ? <WorkspaceAlignmentFixture parameters={parameters} />
    : parameters.get("case") === "draft-persistence"
    ? <DraftPersistenceFixture />
    : parameters.get("case") === "queued-guidance"
    ? <QueuedGuidanceFixture />
    : parameters.get("case") === "file-edit-path"
    ? <FileEditPathFixture />
    : parameters.get("case") === "answer-order"
    ? <AnswerOrderFixture />
    : parameters.get("case") === "message-delivery"
    ? <MessageDeliveryFixture />
    : parameters.get("case") === "activity-logos"
    ? <ActivityLogosFixture parameters={parameters} />
    : parameters.get("case") === "conversations"
    ? <ConversationsFixture />
    : parameters.get("case") === "catalog-activity"
    ? <CatalogActivityFixture />
    : parameters.get("case") === "chat-failure"
    ? <ChatFailureFixture parameters={parameters} />
    : parameters.get("case") === "display-math"
    ? <DisplayMathFixture />
    : parameters.get("case") === "code-wrapping"
    ? <CodeWrappingFixture />
    : parameters.get("case") === "typography"
    ? <ClientProvider client={railClient} token="fixture"><TypographyFixture /></ClientProvider>
    : parameters.get("case") === "inline-references"
    ? <ClientProvider client={railClient} token="fixture"><InlineReferencesFixture /></ClientProvider>
    : parameters.get("case") === "idle-compaction"
    ? <IdleCompactionFixture />
    : parameters.get("case") === "history-hydration"
    ? <HistoryHydrationFixture />
    : parameters.get("case") === "history-boundary"
    ? <ClientProvider client={railClient} token="fixture" webuiCapabilities={["webui.prompt-navigation.v1"]}><HistoryBoundaryFixture local={parameters.has("local")} navigate={parameters.has("navigate")} tasks={parameters.has("tasks")} /></ClientProvider>
    : parameters.get("case") === "diagrams"
    ? <DiagramFixture parameters={parameters} />
    : parameters.get("case") === "thread-loading"
    ? <ClientProvider client={railClient} token="fixture"><ThreadLoadingFixture /></ClientProvider>
    : parameters.get("case") === "new-chat-skeleton"
    ? <ClientProvider client={railClient} token="fixture"><NewChatSkeletonFixture /></ClientProvider>
    : parameters.get("case") === "skeleton-additions"
    ? <ClientProvider client={railClient} token="fixture"><SkeletonAdditionsFixture /></ClientProvider>
    : parameters.get("case") === "skeleton"
    ? <ClientProvider client={railClient} token="fixture"><SkeletonFixture surface={parameters.get("surface") ?? "skills"} loading={parameters.has("loading")} /></ClientProvider>
    : parameters.get("case") === "apps"
    ? <ClientProvider client={railClient} token="fixture"><AppsFixture /></ClientProvider>
    : parameters.get("case") === "rail"
    ? <ClientProvider client={railClient} token="fixture" webuiCapabilities={["webui.prompt-navigation.v1"]}><RailFixture /></ClientProvider>
    : parameters.get("case") === "session-messages"
    ? <SessionMessagesFixture />
    : parameters.get("case") === "history"
    ? <HistoryFixture />
    : <TallDialogFixture placement={parameters.get("placement") === "bottom" ? "bottom" : "center"} />}
</TooltipProvider></TabSurface></InterfaceProvider>);
