import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  togglePresetEditor,
  returnToPresetEditor,
  presetSaveButton,
  openPresetAdvancedOptions,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("updates the Auto label from a valid host result without changing the preset declaration", async () => {
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost");
        if (url.pathname !== "/v0/settings/model-api") return jsonResponse(payload);
        return jsonResponse({
          provider: "openai",
          api:
            url.searchParams.get("reasoning_effort") === "high" ? "responses" : "chat_completions",
        });
      }),
    );
    requestMutationMock.mockResolvedValue({ ...payload,
      model_presets: payload.model_presets.map(row => ({ ...row, reasoning_effort: "high" })) });
    renderSettingsView({ initialSection: "models" });
    await openPresetAdvancedOptions();
    await waitFor(() =>
      expect(screen.getByLabelText("API connection")).toHaveTextContent("Auto (Chat Completions)"),
    );
    await returnToPresetEditor();
    fireEvent.change(screen.getByRole("combobox", { name: "Reasoning effort" }), {
      target: { value: "high" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    await waitFor(() =>
      expect(screen.getByLabelText("API connection")).toHaveTextContent("Auto (Responses)"),
    );
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        { id: "primary", reasoning_effort: "high" },
        20_000,
      ),
    );
  });

  it.each(["future_api", null])(
    "leaves the automatic API unconfirmed for an unsupported host result (%s)",
    async (api) => {
      const payload = settingsPayload();
      payload.model_api_resolution_supported = true;
      payload.providers = [
        {
          id: "openai",
          name: "OpenAI",
          configured: true,
          request_apis: ["chat_completions", "responses"],
        },
      ];
      const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/model-api?")
          ? jsonResponse({ provider: "openai", api })
          : jsonResponse(payload),
      );
      vi.stubGlobal("fetch", fetchMock);
      renderSettingsView({ initialSection: "models" });
      await openPresetAdvancedOptions();
      await waitFor(() =>
        expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/model-api?"))).toBe(
          true,
        ),
      );
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByLabelText("API connection")).toHaveTextContent(/^Auto$/);
      expect(presetSaveButton()).toBeDisabled();
    },
  );

  it.each([undefined, ["future_api"], ["future_api", "future_api_v2"], "responses"])(
    "hides API controls when host support is unconfirmed (%s)",
    async (requestAPIs) => {
      const payload = settingsPayload();
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          jsonResponse({
            ...payload,
            providers: [
              { id: "openai", name: "OpenAI", configured: true, request_apis: requestAPIs },
            ],
          }),
        ),
      );
      renderSettingsView({ initialSection: "models" });
      await openPresetAdvancedOptions();
      expect(screen.queryByRole("combobox", { name: "API connection" })).not.toBeInTheDocument();
    },
  );

  it("uses the host's API declaration and preserves an existing Chat preference when renaming", async () => {
    const payload = settingsPayload();
    payload.providers = [
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        request_apis: ["chat_completions", "responses"],
      },
    ];
    payload.model_presets[0].api = {
      supported_apis: ["chat_completions", "responses"],
      preferred_api: "chat_completions",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(payload)),
    );
    requestMutationMock.mockResolvedValue(payload);
    renderSettingsView({ initialSection: "models" });
    await togglePresetEditor();
    expect(screen.queryByRole("combobox", { name: "API connection" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Advanced options/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(presetSaveButton()).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Preset name"), { target: { value: "Renamed" } });
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        { id: "primary", name: "Renamed" },
        20_000,
      ),
    );
  });

  it.each([
    ["openai_codex", "OpenAI Codex", "responses", "Responses"],
    ["anthropic", "Anthropic", "anthropic_messages", "Anthropic Messages"],
    ["bedrock", "AWS Bedrock", "bedrock_converse", "Bedrock Converse"],
  ] as const)("shows the fixed connection for %s", async (provider, label, api, apiLabel) => {
    const payload = settingsPayload();
    payload.providers = [{ id: provider, name: label, configured: true, request_apis: [api] }];
    payload.model_presets[0].provider = provider;
    payload.model_presets[0].resolved_provider = provider;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(payload)),
    );
    renderSettingsView({ initialSection: "models" });
    await openPresetAdvancedOptions();
    expect(screen.getByText(apiLabel, { exact: true })).toBeVisible();
    expect(screen.queryByRole("combobox", { name: "API connection" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).queryByRole("switch")).not.toBeInTheDocument();
    expect(presetSaveButton()).toBeDisabled();
  });
});
