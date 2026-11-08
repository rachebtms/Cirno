import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("maps provider request switches to raw extraBody fields", async () => {
    const base = settingsPayload();
    const providers: SettingsPayload["providers"] = [
      {
        id: "xai_grok",
        name: "xAI Grok",
        configured: true,
        auth_type: "oauth",
        api_key_required: false,
        oauth_account: "grok@example.com",
        oauth_login_supported: true,
        advanced_fields: ["extra_body", "use_proxy"],
        extra_body: null,
      },
      {
        id: "openai_codex",
        name: "OpenAI Codex",
        configured: true,
        auth_type: "oauth",
        api_key_required: false,
        oauth_account: "codex@example.com",
        oauth_login_supported: true,
        advanced_fields: ["extra_body", "use_proxy"],
        extra_body: null,
      },
      {
        id: "deepseek",
        name: "DeepSeek",
        configured: true,
        api_key_required: true,
        api_key_hint: "deep••••test",
        api_base: "https://api.deepseek.com",
        advanced_fields: ["extra_body"],
        extra_body: null,
      },
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        api_key_required: true,
        api_key_hint: "sk-••••test",
        api_base: "https://api.openai.com/v1",
        provider_api_configurable: true,
        request_apis: ["chat_completions", "responses"],
        advanced_fields: ["extra_body"],
        extra_body: null,
      },
    ];
    let payload: SettingsPayload = { ...base, providers };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(payload);
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({ apps: [], installed_count: 0 });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      if (url === "/v0/settings/cirno-features") return jsonResponse({ features: [] });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockImplementation(async (_action, values) => {
      payload = {
        ...payload,
        providers: payload.providers.map((provider) =>
          provider.id === values.provider
            ? {
                ...provider,
                extra_body: values.extraBody ? JSON.parse(values.extraBody) : null,
                api: values.api ?? provider.api,
              }
            : provider,
        ),
      };
      return payload;
    });

    renderProviderManager({ initialSection: "models", initialSettings: payload });

    fireEvent.click(screen.getByRole("button", { name: "xAI Grok" }));
    const xSearch = screen.getByRole("switch", { name: "X Search" });
    expect(xSearch).toBeChecked();
    fireEvent.click(xSearch);
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        expect.objectContaining({ provider: "xai_grok" }),
        20_000,
      ),
    );
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());

    fireEvent.click(screen.getByRole("button", { name: "OpenAI Codex" }));
    fireEvent.click(screen.getByRole("switch", { name: "Fast mode" }));
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        expect.objectContaining({ provider: "openai_codex" }),
        20_000,
      ),
    );
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());

    fireEvent.click(screen.getByRole("button", { name: /^DeepSeek/ }));
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to providers" }));
    fireEvent.click(screen.getByRole("button", { name: "OpenAI" }));
    fireEvent.click(screen.getByRole("switch", { name: "OpenAI web search" }));
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "OpenAI" })).toBeVisible());

    await waitFor(() => {
      const requestUpdates = requestMutationMock.mock.calls
        .filter(([action]) => action === "settings.provider.update")
        .map(([, values]) => {
          const update = values as {
            provider: string;
            api?: { supported_apis: string[]; preferred_api: string };
            extraBody?: string;
          };
          return [
            update.provider,
            {
              ...(update.api ? { api: update.api } : {}),
              extraBody: JSON.parse(update.extraBody ?? "{}"),
            },
          ] as const;
        });
      expect(requestUpdates).toEqual([
        ["xai_grok", { extraBody: { tools: [] } }],
        ["openai_codex", { extraBody: { service_tier: "priority" } }],
        [
          "openai",
          {
            api: { supported_apis: ["responses"], preferred_api: "responses" },
            extraBody: { tools: [{ type: "web_search" }] },
          },
        ],
      ]);
    });
  });
});
