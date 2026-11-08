import { screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  openPopover,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { togglePresetEditor, openModelPicker } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("keeps unsigned OAuth providers out of the active provider picker", async () => {
    const payload: SettingsPayload = {
      ...settingsPayload(),
      agent: {
        ...settingsPayload().agent,
        model: "deepseek-chat",
        provider: "deepseek",
        resolved_provider: "deepseek",
      },
      model_presets: [
        {
          ...settingsPayload().model_presets[0],
          model: "deepseek-chat",
          provider: "deepseek",
        },
      ],
      providers: [
        {
          id: "deepseek",
          name: "DeepSeek",
          configured: true,
          auth_type: "api_key",
          api_key_required: true,
          api_key_hint: "sk-...",
          api_base: "https://api.deepseek.com",
          default_api_base: "https://api.deepseek.com",
        },
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          configured: false,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: null,
          oauth_account: null,
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
        {
          id: "github_copilot",
          name: "GitHub Copilot",
          configured: false,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: "https://api.githubcopilot.com",
          oauth_account: null,
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/v0/settings") return jsonResponse(payload);
        if (url === "/v0/settings/cli-apps") {
          return jsonResponse({ apps: [], installed_count: 0 });
        }
        if (url === "/v0/settings/mcp-presets") {
          return jsonResponse({ presets: [], installed_count: 0 });
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );

    renderSettingsView({ initialSection: "models" });

    await togglePresetEditor();
    const providerPicker = await screen.findByRole("button", { name: /^DeepSeek Provider$/ });
    await openPopover(providerPicker);

    expect(await screen.findByRole("option", { name: "DeepSeek" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "OpenAI Codex" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "GitHub Copilot" })).not.toBeInTheDocument();
  });

  it("does not fetch model lists for unsigned OAuth providers", async () => {
    const payload: SettingsPayload = {
      ...settingsPayload(),
      agent: {
        ...settingsPayload().agent,
        model: "",
        provider: "openai_codex",
        resolved_provider: "openai_codex",
      },
      model_presets: [
        {
          ...settingsPayload().model_presets[0],
          model: "",
          provider: "openai_codex",
        },
      ],
      providers: [
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          configured: false,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: null,
          oauth_account: null,
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
        {
          id: "github_copilot",
          name: "GitHub Copilot",
          configured: false,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: "https://api.githubcopilot.com",
          oauth_account: null,
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(payload);
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({ apps: [], installed_count: 0 });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({ initialSection: "models" });

    await togglePresetEditor();
    await openModelPicker();
    expect(
      await screen.findByText("Configure this provider before loading models."),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).startsWith("/v0/settings/provider-models"),
      ),
    ).toBe(false);
  });
});
