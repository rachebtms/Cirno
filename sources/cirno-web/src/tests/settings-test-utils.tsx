import { cleanup, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";
import { SettingsView } from "@/components/settings/SettingsView";
import { ClientProvider } from "@/providers/ClientProvider";
import type { SettingsPayload } from "@/lib/types";
import type { CirnoClient } from "@/lib/cirno-client";

export { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

export const requestMutationMock = vi.fn();

export function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

export function settingsPayload(): SettingsPayload {
  return {
    agent: {
      model: "openai/gpt-4o",
      provider: "auto",
      resolved_provider: "openai",
      has_api_key: true,
      model_preset: "primary",
      max_tokens: 8192,
      context_window_tokens: 200000,
      temperature: 0.1,
      reasoning_effort: null,
      timezone: "UTC",
      tool_hint_max_length: 40,
    },
    model_presets: [{
      name: "primary",
      label: "Primary",
      active: true,
      is_default: false,
      model: "openai/gpt-4o",
      provider: "auto",
      resolved_provider: "openai",
      max_tokens: 8192,
      context_window_tokens: 200000,
      temperature: 0.1,
      reasoning_effort: null,
    }],
    model_call_order: ["primary"],
    model_call_order_editable: true,
    providers: [],
    web_search: {
      provider: "duckduckgo",
      api_key_hint: null,
      base_url: null,
      max_results: 5,
      timeout: 30,
      providers: [{ name: "duckduckgo", label: "DuckDuckGo", credential: "none" }],
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
      gateway_host: "127.0.0.1",
      gateway_port: 18790,
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
    version: {
      current: "0.2.2",
    },
    docs: {
      version: "0.2.2",
      base_url: "https://github.com/rachebtms/Cirno/tree/main/documents/docs/0.2.2",
      chat_apps_url: "https://github.com/rachebtms/Cirno/blob/main/documents/configuration.md",
      latest_url: "https://github.com/rachebtms/Cirno/tree/main/documents",
    },
  };
}

type SettingsViewTestOptions = Partial<Pick<
  React.ComponentProps<typeof SettingsView>,
  | "initialSection"
  | "initialSettings"
  | "themePreference"
  | "onChangeTheme"
  | "skills"
  | "skillsLoading"
  | "showSidebar"
  | "mainNavigationExpanded"
  | "onBackToChat"
  | "onSettingsChange"
  | "onStartAutomationChat"
  | "onNativeEngineRestart"
  | "onRestart"
>> & { client?: CirnoClient };

export function renderSettingsView(options: SettingsViewTestOptions = {}) {
  render(
    <ClientProvider client={options.client ?? {
      requestMutation: (action: string, args: {action?: string; name?: string}, timeout?: number) => {
        if (action === 'instance.action' && args.action === 'memory.list') return Promise.resolve({memories: [], has_more: false, next_offset: 0});
        if (action === 'instance.action' && args.action === 'memory.status') return Promise.resolve({counts: {}, pending: 0, failed: 0, index_bytes: 0, last_dream: null});
        if (action === 'settings.profile.read') return Promise.resolve({name: args.name, file: args.name, content: '', revision: 'test'});
        return requestMutationMock(action, args, timeout);
      },
      status: "open",
      onStatus: (handler: (status: "open") => void) => {
        handler("open");
        return () => {};
      },
    } as never} token="tok">
      <SettingsView
        themePreference={options.themePreference ?? "light"}
        initialSection={options.initialSection ?? "apps"}
        initialSettings={options.initialSettings}
        skills={options.skills}
        skillsLoading={options.skillsLoading}
        showSidebar={options.showSidebar}
        mainNavigationExpanded={options.mainNavigationExpanded}
        onChangeTheme={options.onChangeTheme ?? (() => {})}
        onBackToChat={options.onBackToChat ?? (() => {})}
        onModelNameChange={() => {}}
        onSettingsChange={options.onSettingsChange}
        onStartAutomationChat={options.onStartAutomationChat}
        onNativeEngineRestart={options.onNativeEngineRestart}
        onRestart={options.onRestart}
      />
    </ClientProvider>,
  );
}

export async function openPopover(trigger: HTMLElement) {
  await userEvent.setup().click(trigger);
}

export function installSettingsViewTestHooks() {
  beforeEach(() => {
    requestMutationMock.mockReset().mockResolvedValue(settingsPayload());
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query === "(min-width: 1280px)",
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
  });

  afterEach(() => {
    cleanup();
    localStorage.removeItem("cirno-webui.settings-preferences");
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
}
