import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  it("loads curated models for configured OAuth providers", async () => {
    const base = settingsPayload();
    const payload: SettingsPayload = {
      ...base,
      agent: {
        ...base.agent,
        model: "openai-codex/gpt-5.5",
        provider: "openai_codex",
        resolved_provider: "openai_codex",
      },
      model_presets: [
        {
          ...base.model_presets[0],
          model: "openai-codex/gpt-5.5",
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
          default_api_base: "https://chatgpt.com/backend-api",
          model_catalog: "builtin",
          oauth_account: "acct-test",
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings/provider-models?provider=openai_codex") {
        return jsonResponse({
          provider: "openai_codex",
          label: "OpenAI Codex",
          status: "available",
          catalog_kind: "builtin",
          models: [
            {
              id: "openai-codex/gpt-5.6-sol",
              label: "GPT-5.6-Sol",
              description: "Latest frontier agentic coding model.",
              owned_by: "OpenAI Codex",
              context_window: 372000,
            },
          ],
          model_count: 1,
          fetched_at: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({ initialSection: "models", initialSettings: payload });

    await togglePresetEditor();
    await openModelPicker();

    expect(await screen.findByText("GPT-5.6-Sol")).toBeInTheDocument();
    expect(screen.getByText(/Latest frontier agentic coding model\./)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/v0/settings/provider-models?provider=openai_codex",
      expect.objectContaining({ headers: { Authorization: "Bearer tok" } }),
    );
  });

  it("loads hybrid online models for configured OAuth providers", async () => {
    const base = settingsPayload();
    const payload: SettingsPayload = {
      ...base,
      agent: {
        ...base.agent,
        model: "xai-grok/grok-4.5",
        provider: "xai_grok",
        resolved_provider: "xai_grok",
      },
      model_presets: [
        {
          ...base.model_presets[0],
          model: "xai-grok/grok-4.5",
          provider: "xai_grok",
        },
      ],
      providers: [
        {
          id: "xai_grok",
          name: "xAI Grok",
          configured: true,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: "https://cli-chat-proxy.grok.com/v1",
          model_catalog: "hybrid",
          oauth_account: "acct-test",
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings/provider-models?provider=xai_grok") {
        return jsonResponse({
          provider: "xai_grok",
          label: "xAI Grok",
          status: "available",
          catalog_kind: "hybrid",
          source: "remote",
          models: [
            {
              id: "xai-grok/grok-4.6",
              label: "Grok 4.6",
              description: "Latest frontier model",
              owned_by: "xAI",
              context_window: 500_000,
            },
            {
              id: "xai-grok/grok-4.5",
              label: "Grok 4.5",
              owned_by: "xAI",
              context_window: 500_000,
            },
          ],
          model_count: 2,
          fetched_at: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({ initialSection: "models", initialSettings: payload });

    await togglePresetEditor();
    const modelInput = await openModelPicker();

    expect(await screen.findByText("Grok 4.6")).toBeInTheDocument();
    expect(screen.getByText(/Latest frontier model/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/v0/settings/provider-models?provider=xai_grok",
      expect.objectContaining({ headers: { Authorization: "Bearer tok" } }),
    );
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    await waitFor(() => expect(modelInput).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(
        within(screen.getByTestId("model-call-order-row-primary")).getAllByRole("button")[0],
      ).toBeVisible(),
    );
  });
});
