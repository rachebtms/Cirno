import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  togglePresetEditor,
  openModelPicker,
  returnToPresetEditor,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("loads provider models and lets users choose one without typing the id manually", async () => {
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
      if (url === "/v0/settings/provider-models?provider=deepseek") {
        return jsonResponse({
          provider: "deepseek",
          label: "DeepSeek",
          status: "available",
          catalog_kind: "official",
          models: [
            { id: "deepseek-chat", owned_by: "deepseek", context_window: 65536 },
            { id: "deepseek-reasoner", owned_by: "deepseek", context_window: 65536 },
          ],
          model_count: 2,
          fetched_at: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    let current = payload;
    requestMutationMock.mockImplementation(async (_action, args) => {
      current = { ...current, model_presets: current.model_presets.map(row => row.id === args.id ? { ...row, ...args } : row) };
      return structuredClone(current);
    });

    renderSettingsView({ initialSection: "models" });

    await togglePresetEditor();
    await openModelPicker();
    await screen.findByText("deepseek-reasoner");
    fireEvent.click(screen.getAllByText("deepseek-reasoner")[0]);
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    fireEvent.change(screen.getByLabelText("Temperature"), {
      target: { value: "0.4" },
    });
    await returnToPresetEditor();
    fireEvent.change(screen.getByRole("combobox", { name: "Reasoning effort" }), {
      target: { value: "provider-native-mode" },
    });
    fireEvent.blur(screen.getByRole("combobox", { name: "Reasoning effort" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/v0/settings/provider-models?provider=deepseek",
        expect.objectContaining({
          headers: { Authorization: "Bearer tok" },
        }),
      ),
    );
    await waitFor(() => {
      const saveCall = requestMutationMock.mock.calls.find(
        ([action]) => action === "settings.model_configuration.update",
      );
      expect(saveCall).toBeDefined();
      expect(saveCall?.[1]).toEqual({ id: "primary", model: "deepseek-reasoner" });
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        expect.objectContaining({ reasoning_effort: "provider-native-mode" }),
        20_000,
      );
    });
  });
});
