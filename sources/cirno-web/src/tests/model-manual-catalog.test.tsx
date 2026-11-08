import { fireEvent, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { togglePresetEditor, openModelPicker } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("prefills manual model ids for configured OAuth providers", async () => {
    const payload: SettingsPayload = {
      ...settingsPayload(),
      agent: {
        ...settingsPayload().agent,
        model: "open-codex/gpt-5.5",
        provider: "openai_codex",
        resolved_provider: "openai_codex",
      },
      model_presets: [
        {
          ...settingsPayload().model_presets[0],
          model: "open-codex/gpt-5.5",
          provider: "openai_codex",
        },
      ],
      providers: [
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          configured: true,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: null,
          oauth_account: "acct-test",
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
    const input = await openModelPicker();
    expect(input).toHaveValue("open-codex/gpt-5.5");

    fireEvent.change(input, { target: { value: "openai-codex/gpt-5.5" } });
    expect(input).toHaveValue("openai-codex/gpt-5.5");
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).startsWith("/v0/settings/provider-models"),
      ),
    ).toBe(false);
  });

  it("defers the OrcaRouter catalog until the user searches", async () => {
    const base = settingsPayload();
    const payload: SettingsPayload = {
      ...base,
      agent: {
        ...base.agent,
        model: "orcarouter/auto",
        provider: "orcarouter",
        resolved_provider: "orcarouter",
      },
      model_presets: [
        {
          ...base.model_presets[0],
          model: "orcarouter/auto",
          provider: "orcarouter",
          resolved_provider: "orcarouter",
        },
      ],
      providers: [
        {
          id: "orcarouter",
          name: "OrcaRouter",
          configured: true,
          auth_type: "api_key",
          api_key_required: true,
          api_key_hint: "sk-o••••test",
          api_base: null,
          default_api_base: "https://api.orcarouter.ai/v1",
          model_catalog: "catalog",
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
      if (url === "/v0/settings/provider-models?provider=orcarouter") {
        return jsonResponse({
          provider: "orcarouter",
          label: "OrcaRouter",
          status: "available",
          catalog_kind: "catalog",
          models: [
            { id: "orcarouter/auto", owned_by: "orcarouter" },
            { id: "anthropic/claude-sonnet-4.6", owned_by: "anthropic" },
          ],
          model_count: 2,
          fetched_at: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({ initialSection: "models" });

    await togglePresetEditor();
    await openModelPicker();
    expect(await screen.findByText("Search this provider’s model catalog.")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).startsWith("/v0/settings/provider-models"),
      ),
    ).toBe(false);

    fireEvent.change(screen.getByRole("combobox", { name: "Model" }), {
      target: { value: "cl" },
    });

    await screen.findByText("anthropic/claude-sonnet-4.6");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v0/settings/provider-models?provider=orcarouter",
      expect.objectContaining({
        headers: { Authorization: "Bearer tok" },
      }),
    );
  });
});
