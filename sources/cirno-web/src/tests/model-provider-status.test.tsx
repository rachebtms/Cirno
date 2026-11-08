import { fireEvent, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { autoDynamicProviderPayload, togglePresetEditor } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("uses the resolved provider row for auto dynamic providers without api keys", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderSettingsView({
      initialSection: "models",
      initialSettings: autoDynamicProviderPayload({
        configured: true,
        hasApiKey: false,
        apiBase: "https://proxy.example.test/v1",
        apiKeyHint: null,
      }),
    });

    expect(screen.queryByText("Provider setup required")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manage providers" }));
    expect(screen.getByRole("button", { name: "Company Proxy" })).toBeInTheDocument();
  });

  it("does not treat auto dynamic provider api keys as configured without apiBase", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderSettingsView({
      initialSection: "models",
      initialSettings: autoDynamicProviderPayload({
        configured: false,
        hasApiKey: true,
        apiBase: null,
        apiKeyHint: "sk-...",
      }),
    });

    expect(screen.getByText("Provider setup required")).toBeInTheDocument();
  });

  it("marks the current model as unconfigured when its provider needs setup", async () => {
    const payload: SettingsPayload = {
      ...settingsPayload(),
      agent: {
        ...settingsPayload().agent,
        model: "openai-codex/gpt-5.1-codex",
        provider: "openai_codex",
        resolved_provider: "openai_codex",
        has_api_key: false,
      },
      model_presets: [
        {
          ...settingsPayload().model_presets[0],
          model: "openai-codex/gpt-5.1-codex",
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

    expect(await screen.findByText("Provider setup required")).toBeInTheDocument();
    await togglePresetEditor();
    expect(screen.getByText(/Sign in before saving/)).toBeVisible();
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});
