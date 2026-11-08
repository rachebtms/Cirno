import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ProviderCreationUpdate } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager, providerDialog } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("creates a custom provider with folded advanced request settings", async () => {
    const base = settingsPayload();
    let payload: SettingsPayload = {
      ...base,
      providers: [
        {
          id: "deepseek",
          name: "DeepSeek",
          configured: true,
          api_key_required: true,
          api_key_hint: "deep••••test",
          api_base: "https://api.deepseek.com",
        },
        {
          id: "openrouter",
          name: "OpenRouter",
          configured: false,
          api_key_required: true,
          api_key_hint: null,
          api_base: null,
          default_api_base: "https://openrouter.ai/api/v1",
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
      if (url === "/v0/settings/cirno-features") return jsonResponse({ features: [] });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockImplementationOnce(
      async (_action: string, values: ProviderCreationUpdate) => {
        payload = {
          ...payload,
          created_provider: "custom-company-gateway",
          providers: [
            ...payload.providers,
            {
              id: "custom-company-gateway",
              name: values.name,
              is_custom: true,
              configured: true,
              api_key_required: false,
              api_key_hint: "sk-c••••pany",
              api_base: values.apiBase,
              default_api_base: null,
              advanced_fields: [
                "extra_headers",
                "extra_body",
                "extra_query",
                "use_proxy",
                "thinking_style",
              ],
              extra_headers: JSON.parse(values.extraHeaders ?? "{}"),
              extra_body: JSON.parse(values.extraBody ?? "{}"),
              extra_query: JSON.parse(values.extraQuery ?? "{}"),
              use_proxy: values.use_proxy,
              thinking_style: values.thinkingStyle,
            },
          ],
        };
        return payload;
      },
    );

    renderProviderManager({ initialSection: "models", initialSettings: payload });

    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    const customOption = await screen.findByRole("button", { name: "Custom" });
    const openRouterOption = screen.getByRole("option", { name: "OpenRouter" });
    expect(customOption.querySelector("svg, img")).not.toBeNull();
    expect(openRouterOption.querySelector("svg, img")).not.toBeNull();
    fireEvent.click(customOption);

    fireEvent.change(screen.getByPlaceholderText("My model provider"), {
      target: { value: "Company Gateway" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://api.example.com/v1"), {
      target: { value: "https://gateway.example/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter API key"), {
      target: { value: "sk-company" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    for (const [title, value] of [
      ["Headers", '{"X-Tenant":"engineering"}'],
      ["Body parameters", '{"service_tier":"priority"}'],
      ["Query parameters", '{"api-version":"2026-01-01"}'],
    ]) {
      fireEvent.change(screen.getByRole("textbox", { name: title }), { target: { value } });
    }
    fireEvent.click(screen.getByRole("switch", { name: "Use proxy" }));
    await userEvent.setup().click(screen.getByRole("button", { name: /Reasoning format/ }));
    fireEvent.click(await screen.findByRole("option", { name: "enable_thinking" }));
    fireEvent.click(within(providerDialog()).getByRole("button", { name: "Add provider" }));

    await waitFor(() => {
      const createCall = requestMutationMock.mock.calls.find(
        ([action]) => action === "settings.provider.create",
      );
      expect(createCall).toBeTruthy();
      expect(createCall?.[1]).toEqual({
        name: "Company Gateway",
        apiKey: "sk-company",
        apiBase: "https://gateway.example/v1",
        use_proxy: true,
        extraHeaders: '{"X-Tenant":"engineering"}',
        extraBody: '{"service_tier":"priority"}',
        extraQuery: '{"api-version":"2026-01-01"}',
        thinkingStyle: "enable_thinking",
      });
    });
    expect(await screen.findByRole("button", { name: /^Company Gateway$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add provider" })).toBeInTheDocument();
  });
});
