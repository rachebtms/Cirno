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
  it("opens generation parameters in the preset accordion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/v0/settings") return jsonResponse(settingsPayload());
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
    const advanced = await screen.findByRole("button", { name: /Advanced options/ });

    fireEvent.click(advanced);

    expect(within(screen.getByRole("dialog")).getByText("Context window")).toBeInTheDocument();
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Context window" })).toHaveValue("200k");
    await returnToPresetEditor();
    const reasoningEffort = screen.getByRole("combobox", { name: "Reasoning effort" });
    expect(reasoningEffort).toHaveProperty("type", "text");
    fireEvent.change(reasoningEffort, { target: { value: "provider-native-mode" } });
    expect(reasoningEffort).toHaveValue("provider-native-mode");
  });

  it.each([
    ["128000", 128000],
    ["131072", 131072],
    ["272k", 272000],
    ["256K", 256000],
    ["1.5m", 1500000],
    ["1.001k", 1001],
  ] as const)("saves a custom context budget (%s)", async (input, tokens) => {
    const payload = settingsPayload();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    requestMutationMock.mockResolvedValue({
      ...payload,
      model_presets: payload.model_presets.map((preset) => ({
        ...preset,
        context_window_tokens: tokens,
      })),
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor();
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Context window" }), {
      target: { value: input },
    });
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        expect.objectContaining({ context_window_tokens: tokens }),
        expect.any(Number),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    expect(screen.getByRole("textbox", { name: "Context window" })).toHaveValue(input);
  });

  it.each(["", "0", "-1", "1.5", "abc", "2ki", "0.0001k", "9007199254740992"])(
    "keeps invalid context input unsaved (%s)",
    async (value) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(() => new Promise<Response>(() => {})),
      );
      renderSettingsView({ initialSection: "models", initialSettings: settingsPayload() });
      await togglePresetEditor();
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      const input = screen.getByRole("textbox", { name: "Context window" });
      vi.useFakeTimers();
      fireEvent.change(input, { target: { value } });
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(input).toHaveAccessibleDescription(
        "Enter a positive token count, such as 200k, 1m, or 131072.",
      );
      await act(() => vi.advanceTimersByTimeAsync(750));
      vi.useRealTimers();
      expect(requestMutationMock).not.toHaveBeenCalled();
      expect(input).toHaveValue(value);
      fireEvent.click(screen.getByRole("button", { name: "Close" }));
      await act(async () => {});
      expect(screen.getByRole("dialog")).toContainElement(input);
      expect(presetSaveButton()).toBeDisabled();
    },
  );

  it("saves abbreviated output budgets as integers and keeps an incomplete input unsaved", async () => {
    let payload = settingsPayload();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    requestMutationMock.mockImplementation(async (_action, args) => {
      payload = {
        ...payload,
        model_presets: payload.model_presets.map((preset) => ({
          ...preset,
          max_tokens: args.max_tokens,
        })),
      };
      return payload;
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await openPresetAdvancedOptions();
    let input = screen.getByRole("textbox", { name: "Max output tokens" });
    fireEvent.change(input, { target: { value: "32K" } });
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenLastCalledWith(
        "settings.model_configuration.update",
        expect.objectContaining({ max_tokens: 32000 }),
        expect.any(Number),
      ),
    );
    await waitFor(() => expect(presetSaveButton()).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    input = screen.getByRole("textbox", { name: "Max output tokens" });
    expect(input).toHaveValue("32K");
    requestMutationMock.mockClear();
    vi.useFakeTimers();
    fireEvent.change(input, { target: { value: "" } });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(presetSaveButton()).toBeDisabled();
    await act(() => vi.advanceTimersByTimeAsync(750));
    vi.useRealTimers();
    expect(requestMutationMock).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "8.192k" } });
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenLastCalledWith(
        "settings.model_configuration.update",
        expect.objectContaining({ max_tokens: 8192 }),
        expect.any(Number),
      ),
    );
  });
});
