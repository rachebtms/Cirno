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
  it("recognizes and removes versioned web search tools without losing raw settings", async () => {
    const base = settingsPayload();
    const payload: SettingsPayload = {
      ...base,
      providers: [
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
          extra_body: {
            metadata: { owner: "legacy-config" },
            tools: [
              { type: "web_search_preview", search_context_size: "medium" },
              { type: "file_search", vector_store_ids: ["vs_legacy"] },
            ],
          },
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
    requestMutationMock.mockResolvedValueOnce(payload);

    renderProviderManager({ initialSection: "models", initialSettings: payload });

    fireEvent.click(await screen.findByRole("button", { name: "OpenAI" }));
    const searchSwitch = screen.getByRole("switch", { name: "OpenAI web search" });
    expect(searchSwitch).toBeChecked();
    fireEvent.click(searchSwitch);
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));

    await waitFor(() => {
      const updateCall = requestMutationMock.mock.calls.find(
        ([action]) => action === "settings.provider.update",
      );
      expect(updateCall).toBeTruthy();
      const values = updateCall?.[1] as { extraBody: string };
      expect(JSON.parse(values.extraBody)).toEqual({
        metadata: { owner: "legacy-config" },
        tools: [{ type: "file_search", vector_store_ids: ["vs_legacy"] }],
      });
    });
  });
});
