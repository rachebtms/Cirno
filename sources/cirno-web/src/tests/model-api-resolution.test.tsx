import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  openPopover,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  openModelPicker,
  returnToPresetEditor,
  presetSaveButton,
  openPresetAdvancedOptions,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("saves an explicit API after an Auto provider resolves the changed model to a new connection", async () => {
    const payload = settingsPayload();
    payload.model_api_resolution_supported = true;
    payload.model_presets[0] = {
      ...payload.model_presets[0],
      provider: "auto",
      model: "anthropic/claude-sonnet-4",
      resolved_provider: "anthropic",
    };
    payload.providers = [
      {
        id: "anthropic",
        name: "Anthropic",
        configured: true,
        request_apis: ["anthropic_messages"],
      },
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        request_apis: ["chat_completions", "responses"],
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost");
        if (url.pathname === "/v0/settings/provider-models")
          return jsonResponse({
            provider: url.searchParams.get("provider"),
            status: "available",
            catalog_kind: "official",
            models: [],
            model_count: 0,
          });
        if (url.pathname !== "/v0/settings/model-api") return jsonResponse(payload);
        return jsonResponse(
          url.searchParams.get("model")?.startsWith("gpt")
            ? { provider: "openai", api: "chat_completions" }
            : { provider: "anthropic", api: "anthropic_messages" },
        );
      }),
    );
    requestMutationMock.mockImplementation(async (_action, args) => {
      payload.model_presets = payload.model_presets.map((preset) =>
        preset.id !== args.id
          ? preset
          : {
              ...preset,
              model: args.model ?? preset.model,
              api: args.api ?? preset.api,
            },
      );
      return { ...payload };
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await openPresetAdvancedOptions();
    await returnToPresetEditor();
    const search = await openModelPicker();
    const user = userEvent.setup();
    await user.clear(search);
    await user.type(search, "gpt-4o");
    await user.keyboard("{Enter}");
    await openPopover(await screen.findByRole("button", { name: /Advanced options/ }));
    await waitFor(() =>
      expect(screen.getByLabelText("API connection")).toHaveTextContent("Auto (Chat Completions)"),
    );
    await openPopover(screen.getByLabelText("API connection"));
    fireEvent.click(screen.getByRole("option", { name: "Responses" }));
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        {
          id: "primary",
          model: "gpt-4o",
          api: { supported_apis: ["responses"], preferred_api: "responses" },
        },
        20_000,
      ),
    );
  });

  it("shows the host's automatic API and discards an older reasoning resolution", async () => {
    const payload = settingsPayload();
    payload.model_api_resolution_supported = true;
    payload.model_presets[0].provider = "openai";
    payload.providers = [
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        request_apis: ["chat_completions", "responses"],
      },
    ];
    let finishHigh!: (response: Response) => void;
    const highResponse = new Promise<Response>((resolve) => {
      finishHigh = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname !== "/v0/settings/model-api") return jsonResponse(payload);
      if (url.searchParams.get("reasoning_effort") === "high") return highResponse;
      return jsonResponse({ provider: "openai", api: "chat_completions" });
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockImplementation(async (_action, args) => {
      payload.model_presets = payload.model_presets.map((preset) => ({
        ...preset,
        reasoning_effort: args.reasoning_effort ?? preset.reasoning_effort,
      }));
      return { ...payload };
    });
    renderSettingsView({ initialSection: "models" });
    await openPresetAdvancedOptions();
    await waitFor(() =>
      expect(screen.getByLabelText("API connection")).toHaveTextContent("Auto (Chat Completions)"),
    );
    expect(presetSaveButton()).toBeDisabled();
    await openPopover(screen.getByLabelText("API connection"));
    expect(screen.getByRole("option", { name: "Auto (Chat Completions)" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("option", { name: "Auto (Chat Completions)" }));
    await returnToPresetEditor();
    fireEvent.change(screen.getByRole("combobox", { name: "Reasoning effort" }), {
      target: { value: "high" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("reasoning_effort=high")),
      ).toBe(true),
    );
    await returnToPresetEditor();
    fireEvent.change(screen.getByRole("combobox", { name: "Reasoning effort" }), {
      target: { value: "none" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("reasoning_effort=none")),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("API connection")).toHaveTextContent("Auto (Chat Completions)"),
    );
    await act(async () => {
      finishHigh(jsonResponse({ provider: "openai", api: "responses" }));
    });
    expect(screen.getByLabelText("API connection")).toHaveTextContent("Auto (Chat Completions)");
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.model_configuration.update",
      { id: "primary", reasoning_effort: "high" },
      20_000,
    );
  });
});
