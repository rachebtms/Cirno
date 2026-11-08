import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ProviderModelsPayload } from "@/lib/contracts/models";
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
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("offers catalog reasoning levels including max and none, distinct from Default, and retains manual values", async () => {
    const payload = settingsPayload();
    payload.model_presets[0].provider = "deepseek";
    payload.model_presets[0].resolved_provider = "deepseek";
    payload.model_presets[0].model = "deepseek-flash";
    payload.model_presets[0].reasoning_effort = "high";
    payload.model_presets[0].reasoning_effort_values = ["", "low", "medium", "high"];
    payload.providers = [{ id: "deepseek", name: "DeepSeek", configured: true }];
    const catalog: ProviderModelsPayload = {
      provider: "deepseek",
      label: "DeepSeek",
      status: "available",
      catalog_kind: "official",
      models: [
        {
          id: payload.model_presets[0].model,
          max_output_tokens: 393_216,
          input_modalities: ["text", "image"],
          output_modalities: ["text"],
          reasoning_efforts: ["none", "low", "high", "max"],
          default_reasoning_effort: "high",
        },
        { id: "another-model", reasoning_efforts: ["ultra"] },
      ],
      model_count: 2,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/provider-models?") ? jsonResponse(catalog) : jsonResponse(payload),
      ),
    );
    requestMutationMock.mockImplementation(async (_action, args) => {
      payload.model_presets = payload.model_presets.map((preset) => ({
        ...preset,
        reasoning_effort: args.reasoning_effort ?? null,
      }));
      return structuredClone(payload);
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor();
    const input = screen.getByRole("combobox", { name: "Reasoning effort" });
    await openPopover(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
    await openPopover(await screen.findByRole("option", { name: "max" }));
    await waitFor(() => expect(input).toHaveValue("max"));
    await openPopover(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
    expect(screen.queryByRole("option", { name: "ultra" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "medium" })).not.toBeInTheDocument();
    await openPopover(screen.getByRole("option", { name: "none" }));
    await waitFor(() => expect(input).toHaveValue("none"));
    await openPopover(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
    await openPopover(screen.getByRole("option", { name: "Default" }));
    await waitFor(() => expect(input).toHaveValue("Default"));
    fireEvent.click(input);
    fireEvent.change(input, { target: { value: "provider-native-mode" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        expect.objectContaining({ reasoning_effort: "provider-native-mode" }),
        expect.any(Number),
      ),
    );
  });
});
