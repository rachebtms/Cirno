import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, vi } from "vitest";
import type { Window as HappyWindow } from "happy-dom";
import i18n from "@/i18n";
import {
  clearOwnerPreferences,
  readOwnerPreferences,
  readThemes,
} from "@/features/preferences/store";
import { useSessions } from "@/hooks/useSessions";
import type { RunState } from "@/lib/cirno-client";
import { clearReloadCache } from "@/lib/reload-cache";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { ConnectionStatus } from "@/lib/contracts/transport";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { SidebarStatePayload } from "@/lib/contracts/conversation-preferences";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { deriveWsUrl, fetchBootstrap } from "@/lib/bootstrap";

export const appTest = {
  sessions: [] as ChatSummary[],
  defaultChatId: null as string | null,
  restoreBrowserFocus: undefined as (() => void) | undefined,
};
(window as unknown as HappyWindow).happyDOM.settings.disableIframePageLoading =
  true;
export const connectSpy = vi.fn();
export const refreshSpy = vi.fn();
export const createChatSpy = vi.fn().mockResolvedValue("chat-1");
export const deleteChatSpy = vi.fn();
export const getSessionAutomationsSpy =
  vi.fn<(key: string) => Promise<SessionAutomationJob[]>>();
export const toggleThemeSpy = vi.fn();
export const updateUrlSpy = vi.fn();
export const attachSpy = vi.fn();
export const setSidebarStateSpy = vi.fn();
export const requestMutationSpy = vi.fn();
export const discardTemporaryChatSpy = vi.fn();
export const newTemporaryChatSpy = vi.fn<() => Promise<string>>();
export const sendMessageSpy = vi.fn();
export const sendSystemCommandSpy = vi.fn().mockResolvedValue(undefined);
export const statusHandlers = new Set<(status: ConnectionStatus) => void>();
export const runStatusHandlers = new Set<
  (chatId: string, state: RunState) => void
>();
export const runState = (startedAt: number | null): RunState => ({
  active: startedAt !== null,
  startedAt,
  latestTurnId: null,
  generation: 0,
  unsettled: false,
});
export const sessionUpdateHandlers = new Set<
  (
    chatId: string,
    scope?: string,
    workspaceScope?: WorkspaceScopePayload,
  ) => void
>();
export const sidebarStateUpdateHandlers = new Set<
  (state: SidebarStatePayload) => void
>();
export const readyHandlers = new Set<() => void>();
export const HERO_GREETING_PATTERN =
  /What should we work on\?|Where should we start\?|What are we building today\?|What should we tackle together\?/;
export function setNavigatorPlatform(platform: string): void {
  Object.defineProperty(window.navigator, "platform", {
    configurable: true,
    value: platform,
  });
}
export function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}
export function mockFetchRoutes(routes: Record<string, unknown>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const route =
        routes[String(input)] ??
        (String(input) === "/v0/webui/sidebar-state" ? {} : undefined) ??
        (String(input) === "/v0/workspaces"
          ? {
              schema_version: 1,
              default_access_mode: "default",
              default_scope: {
                project_path: "/tmp/workspace",
                project_name: "workspace",
                access_mode: "restricted",
                restrict_to_workspace: true,
              },
              controls: { can_change_project: false },
            }
          : undefined) ??
        (/^\/v0\/sessions\/[^/]+\/subagents$/.test(String(input))
          ? { tasks: [] }
          : undefined);
      const body =
        typeof route === "function"
          ? await (route as () => unknown | Promise<unknown>)()
          : route;
      return body === undefined
        ? ({ ok: false, status: 404, json: async () => ({}) } as Response)
        : jsonResponse(body);
    }),
  );
}
export function currentMonthTimestamp(
  day: number,
  hour = 10,
  minute = 0,
): number {
  const now = new Date();
  return new Date(
    now.getFullYear(),
    now.getMonth(),
    day,
    hour,
    minute,
  ).getTime();
}
export function baseSettingsPayload() {
  return {
    agent: {
      model: "openai/gpt-4o",
      provider: "auto",
      resolved_provider: "openai",
      has_api_key: true,
      model_preset: "default",
      max_tokens: 8192,
      context_window_tokens: 65536,
      temperature: 0.1,
      reasoning_effort: null,
      timezone: "UTC",
      tool_status_summary_max_chars: 40,
    },
    model_presets: [
      {
        id: "default",
        name: "default",

        active: true,
        is_default: true,
        model: "openai/gpt-4o",
        provider: "auto",
        max_tokens: 8192,
        context_window_tokens: 65536,
        temperature: 0.1,
        reasoning_effort: null,
      },
    ],
    model_call_order: [],
    model_call_order_editable: false,
    providers: [],
    web_search: {
      provider: "duckduckgo",
      api_key_hint: null,
      base_url: null,
      max_results: 5,
      timeout: 30,
      providers: [
        { name: "duckduckgo", label: "DuckDuckGo", credential: "none" },
      ],
    },
    web: {
      enable: true,
      use_proxy: false,
      user_agent: null,
      search: { max_results: 5, timeout: 30 },
      fetch: { use_jina_reader: true },
    },
    runtime: {
      config_path: "/tmp/config.json",
      workspace_path: "/tmp/workspace",
      health_host: "127.0.0.1",
      health_port: 18790,
      heartbeat: {
        enabled: true,
        interval_s: 1800,
      },
      dream: {
        schedule: "every 2h",
      },
    },
    advanced: {
      restrict_to_workspace: false,
      webui_allow_local_service_access: true,
      webui_default_access_mode: "default",
      private_service_protection_enabled: true,
      ssrf_whitelist_count: 0,
      mcp_server_count: 0,
      exec_enabled: true,
      exec_sandbox: null,
      exec_path_prepend_set: false,
      exec_path_append_set: false,
    },
    requires_restart: false,
  };
}
vi.mock("@/hooks/useSessions", async (importOriginal) => {
  const React = await import("react");
  const actual = await importOriginal<typeof import("@/hooks/useSessions")>();
  return {
    ...actual,
    useSessions: vi.fn(function useMockSessions() {
      const [sessions, setSessions] = React.useState(appTest.sessions);
      return {
        sessions,
        loading: false,
        error: null,
        refresh: refreshSpy,
        createChat: async (scope?: WorkspaceScopePayload | null) => {
          const chatId = await createChatSpy(scope);
          const now = new Date().toISOString();
          setSessions((prev: ChatSummary[]) => [
            {
              key: `websocket:${chatId}`,
              channel: "websocket",
              chatId,
              createdAt: now,
              updatedAt: now,
              title: "",
              preview: "",
              workspaceScope: scope ?? null,
            },
            ...prev.filter((session) => session.chatId !== chatId),
          ]);
          return chatId;
        },
        forkChat: async () => "fork-chat",
        getSessionAutomations: getSessionAutomationsSpy,
        deleteChat: async (
          key: string,
          options?: { deleteAutomations?: boolean },
        ) => {
          if (options === undefined) await deleteChatSpy(key);
          else await deleteChatSpy(key, options);
          setSessions((prev: ChatSummary[]) =>
            prev.filter((s) => s.key !== key),
          );
          return { deleted: true };
        },
      };
    }),
  };
});
vi.mock("@/hooks/useTheme", async () => {
  const React = await import("react");
  return {
    ThemeProvider: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useTheme: () => ({
      theme: "light" as const,
      preference: "light" as const,
      setTheme: vi.fn(),
      toggle: toggleThemeSpy,
    }),
    useThemeValue: () => "light" as const,
  };
});
vi.mock("@/lib/bootstrap", () => ({
  BootstrapAuthRequiredError: class BootstrapAuthRequiredError extends Error {
    constructor(message = "bootstrap authentication required") {
      super(message);
      this.name = "BootstrapAuthRequiredError";
    }
  },
  fetchBootstrap: vi.fn().mockResolvedValue({
    token: "tok",
    api_token: "api-tok",
    ws_path: "/",
    expires_in: 300,
  }),
  deriveWsUrl: vi.fn(() => "ws://test"),
  consumeUrlBootstrapSecret: vi.fn(() => ""),
  loadSavedSecret: vi.fn(() => ""),
  saveSecret: vi.fn(),
  clearSavedSecret: vi.fn(),
}));
vi.mock("@/lib/cirno-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/cirno-client")>();
  class MockClient {
    onTaskNotice = () => () => {};
    status: ConnectionStatus = "idle";
    private receiveStatus = (status: ConnectionStatus) => { this.status = status; };
    constructor() { statusHandlers.add(this.receiveStatus); }
    defaultChatId = appTest.defaultChatId;
    sendSystemCommand = sendSystemCommandSpy;
    connect = connectSpy;
    resumeFromBackground = async () => undefined;
    onStatus = (handler: (status: ConnectionStatus) => void) => {
      const listener = (status: ConnectionStatus) => { this.status = status; handler(status); };
      statusHandlers.add(listener);
      handler(this.status);
      return () => statusHandlers.delete(listener);
    };
    onRuntimeModelUpdate = () => () => {};
    onPreferencesUpdate = () => () => {};
    onReady = (handler: () => void) => {
      readyHandlers.add(handler);
      return () => readyHandlers.delete(handler);
    };
    onError = () => () => {};
    onChat = () => () => {};
    onTranscript = () => () => {};
    onSessionUpdate = (
      handler: (
        chatId: string,
        scope?: string,
        workspaceScope?: WorkspaceScopePayload,
      ) => void,
    ) => {
      sessionUpdateHandlers.add(handler);
      return () => sessionUpdateHandlers.delete(handler);
    };
    onSidebarStateUpdate = (handler: (state: SidebarStatePayload) => void) => {
      sidebarStateUpdateHandlers.add(handler);
      return () => sidebarStateUpdateHandlers.delete(handler);
    };
    onRunStatus = (handler: (chatId: string, state: RunState) => void) => {
      runStatusHandlers.add(handler);
      return () => runStatusHandlers.delete(handler);
    };
    onRunCompletion = () => () => {};
    getRunState = () => runState(null);
    restorePendingRun = vi.fn();
    getRunStartedAt = () => null;
    getRunTurnId = () => null;
    getUnsettledRunChatIds = () => [];
    getRunGeneration = () => 0;
    hasUnsettledRun = () => false;
    canReconcileCanonicalCompletion = () => true;
    reconcileCanonicalCompletion = () => true;
    fenceCanonicalCompletedTurns = vi.fn();
    getGoalState = () => undefined;
    sendMessage = sendMessageSpy;
    sendTextMessage = async (
      chatId: string,
      content: string,
      options?: unknown,
    ) => {
      sendMessageSpy(chatId, content, undefined, options);
    };
    newChat = vi.fn();
    newTemporaryChat = newTemporaryChatSpy;
    attach = attachSpy;
    setSidebarState = setSidebarStateSpy;
    requestMutation = (...args: unknown[]) => {
      if (args[0] === "preferences.read") {
        return Promise.resolve({
          revision: 0,
          values: readOwnerPreferences(),
          themes: readThemes(),
        });
      }
      if (args[0] === "preferences.update") {
        return Promise.resolve({
          revision: 1,
          values: {
            ...readOwnerPreferences(),
            ...(args[1] as { patch: object }).patch,
          },
          themes: readThemes(),
        });
      }
      // Background inbox reads are independent of the mutation under test.
      if (
        args[0] === "instance.action" &&
        (args[1] as { action?: string })?.action === "inbox.list"
      ) {
        return Promise.resolve({
          items: [],
          unread: { operations: 0, conversations: 0, system: 0 },
          latest_seq: 0,
          next_before: null,
        });
      }
      return requestMutationSpy(...args);
    };
    discardTemporaryChat = discardTemporaryChatSpy;
    close = vi.fn(() => { statusHandlers.delete(this.receiveStatus); });
    updateUrl = updateUrlSpy;
    updateMaxFrameBytes = vi.fn();
  }

  return { ...actual, CirnoClient: MockClient };
});
const defaultUseSessions = vi.mocked(useSessions).getMockImplementation()!;

export function installAppTestLifecycle() {
  beforeAll(async () => {
    // These tests exercise app state and navigation. First-load paint and lazy
    // bundle delivery are covered by the browser startup/layout suites.
    await Promise.all([
      import("@/components/thread/ThreadShell"),
      import("@/features/settings/SettingsView"),
      import("@/features/conversations/ConversationsPage"),
    ]);
  });
  beforeEach(async () => {
    clearOwnerPreferences();
    await i18n.changeLanguage("en");
    appTest.sessions = [];
    vi.mocked(useSessions).mockImplementation(defaultUseSessions);
    clearReloadCache();
    connectSpy.mockClear();
    updateUrlSpy.mockClear();
    refreshSpy.mockReset();
    createChatSpy.mockClear();
    deleteChatSpy.mockReset();
    getSessionAutomationsSpy.mockReset().mockResolvedValue([]);
    toggleThemeSpy.mockReset();
    attachSpy.mockReset();
    setSidebarStateSpy
      .mockReset()
      .mockImplementation(async (state: SidebarStatePayload) => state);
    requestMutationSpy.mockReset().mockResolvedValue({ projects: [] });
    discardTemporaryChatSpy.mockReset();
    let temporaryChatCounter = 0;
    newTemporaryChatSpy.mockImplementation(
      async () =>
        `00000000-0000-4000-8000-${String(++temporaryChatCounter).padStart(12, "0")}`,
    );
    sendMessageSpy.mockReset();
    sendSystemCommandSpy.mockReset().mockResolvedValue(undefined);
    appTest.defaultChatId = null;
    statusHandlers.clear();
    runStatusHandlers.clear();
    sessionUpdateHandlers.clear();
    sidebarStateUpdateHandlers.clear();
    readyHandlers.clear();
    window.history.replaceState(null, "", "/");
    sessionStorage.removeItem("cirno.remote-instance");
    setNavigatorPlatform("Linux x86_64");
    localStorage.setItem("cirno-webui.library", "1");
    localStorage.removeItem("cirno-webui.workspace-tabs.v1");
    localStorage.removeItem("cirno-webui.sidebar.width");
    localStorage.removeItem("cirno-webui.sidebar.completed-runs.v1");
    localStorage.removeItem("cirno-webui.sidebar.session-updates.v1");
    localStorage.removeItem("cirno-webui.collapsed-pane-groups.v1");
    localStorage.removeItem("cirno-webui.restartStartedAt");
    localStorage.removeItem("cirno-webui.restartRoute");
    vi.mocked(fetchBootstrap).mockReset().mockResolvedValue({
      token: "tok",
      api_token: "api-tok",
      ws_path: "/",
      expires_in: 300,
    });
    vi.mocked(deriveWsUrl).mockReset().mockReturnValue("ws://test");
    mockFetchRoutes({});
  });
  afterEach(() => {
    cleanup();
    appTest.restoreBrowserFocus?.();
    appTest.restoreBrowserFocus = undefined;
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
}
