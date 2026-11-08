import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  openPopover,
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
  it.each(["legacy", "declaration"])(
    "saves and restores a preset API declaration, then returns to automatic (%s host)",
    async (host) => {
      let payload = settingsPayload();
      const provider: SettingsPayload["providers"][number] = {
        id: "openai",
        name: "OpenAI",
        configured: true,
      };
      if (host === "legacy") provider.model_api_configurable = true;
      else provider.request_apis = ["chat_completions", "responses"];
      payload.providers = [provider];
      payload.model_presets[0].provider = "openai";
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => jsonResponse(payload)),
      );
      requestMutationMock.mockImplementation(async (action, args) => {
        expect(action).toBe("settings.model_configuration.update");
        payload = {
          ...payload,
          model_presets: payload.model_presets.map((preset) => ({ ...preset, api: args.api })),
        };
        return payload;
      });
      renderSettingsView({ initialSection: "models" });
      await togglePresetEditor();
      expect(screen.queryByRole("combobox", { name: "API connection" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      await openPopover(screen.getByLabelText("API connection"));
      expect(screen.getAllByRole("option")).toHaveLength(3);
      fireEvent.click(screen.getByRole("option", { name: "Responses" }));
      expect(
        screen.getByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
      ).not.toBeChecked();
      await returnToPresetEditor();
      fireEvent.click(presetSaveButton());
      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenLastCalledWith(
          "settings.model_configuration.update",
          { id: "primary", api: { supported_apis: ["responses"], preferred_api: "responses" } },
          20_000,
        ),
      );
      await waitFor(() => expect(presetSaveButton()).toBeDisabled());
      await openPopover(screen.getByRole("button", { name: "Close" }));
      await openPresetAdvancedOptions();
      expect(screen.getByLabelText("API connection")).toHaveTextContent("Responses");
      fireEvent.click(
        screen.getByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
      );
      await returnToPresetEditor();
      fireEvent.click(presetSaveButton());
      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenLastCalledWith(
          "settings.model_configuration.update",
          {
            id: "primary",
            api: { supported_apis: ["responses", "chat_completions"], preferred_api: "responses" },
          },
          20_000,
        ),
      );
      await waitFor(() => expect(presetSaveButton()).toBeDisabled());
      await openPopover(screen.getByRole("button", { name: "Close" }));
      await openPresetAdvancedOptions();
      expect(
        screen.getByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
      ).toBeChecked();
      await openPopover(screen.getByLabelText("API connection"));
      fireEvent.click(screen.getByRole("option", { name: "Responses" }));
      expect(
        screen.getByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
      ).toBeChecked();
      expect(presetSaveButton()).toBeDisabled();
      await openPopover(screen.getByLabelText("API connection"));
      fireEvent.click(screen.getByRole("option", { name: "Auto" }));
      expect(
        screen.queryByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
      ).not.toBeInTheDocument();
      await returnToPresetEditor();
      fireEvent.click(presetSaveButton());
      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenLastCalledWith(
          "settings.model_configuration.update",
          { id: "primary", api: null },
          20_000,
        ),
      );
      expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/model-api?"))).toBe(
        false,
      );
    },
  );

  it("saves and restores Anthropic Messages for a custom gateway", async () => {
    let payload = settingsPayload();
    payload.providers = [
      {
        id: "tenant",
        name: "Tenant",
        configured: true,
        request_apis: ["chat_completions", "responses", "anthropic_messages"],
      },
    ];
    payload.model_presets[0].provider = "tenant";
    payload.model_presets[0].resolved_provider = "tenant";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(payload)),
    );
    requestMutationMock.mockImplementation(async (action, args) => {
      expect(action).toBe("settings.model_configuration.update");
      payload = {
        ...payload,
        model_presets: payload.model_presets.map((preset) => ({ ...preset, api: args.api })),
      };
      return payload;
    });
    renderSettingsView({ initialSection: "models" });
    await openPresetAdvancedOptions();
    await openPopover(screen.getByLabelText("API connection"));
    expect(screen.getAllByRole("option")).toHaveLength(4);
    fireEvent.click(screen.getByRole("option", { name: "Anthropic Messages" }));
    expect(
      screen.queryByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
    ).not.toBeInTheDocument();
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenLastCalledWith(
        "settings.model_configuration.update",
        {
          id: "primary",
          api: { supported_apis: ["anthropic_messages"], preferred_api: "anthropic_messages" },
        },
        20_000,
      ),
    );
    await waitFor(() => expect(presetSaveButton()).toBeDisabled());
    await openPopover(screen.getByRole("button", { name: "Close" }));
    await openPresetAdvancedOptions();
    expect(screen.getByLabelText("API connection")).toHaveTextContent("Anthropic Messages");
    expect(presetSaveButton()).toBeDisabled();
    await openPopover(screen.getByLabelText("API connection"));
    fireEvent.click(screen.getByRole("option", { name: "Responses" }));
    expect(
      screen.getByRole("switch", { name: "Try Chat Completions if Responses is unsupported" }),
    ).not.toBeChecked();
  });
});
