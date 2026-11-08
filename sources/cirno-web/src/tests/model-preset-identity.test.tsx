import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  togglePresetEditor,
  returnToPresetEditor,
  presetSaveButton,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("edits the display name independently of the stable model ID", async () => {
    const payload = settingsPayload();
    payload.model_presets[0] = {
      ...payload.model_presets[0],
      id: "model-123",
      name: "Research model",
    };
    payload.model_call_order = ["model-123"];
    payload.agent.model_preset = "model-123";
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor("model-123");
    expect(screen.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Research model");
  });

  it("renames an existing preset without losing the editor selection", async () => {
    const payload = settingsPayload();
    const renamedPayload: SettingsPayload = {
      ...payload,
      agent: { ...payload.agent, model_preset: "primary" },
      model_presets: payload.model_presets.map((preset) => ({
        ...preset,
        name: "Codex",
      })),
      model_call_order: ["primary"],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    requestMutationMock.mockResolvedValueOnce(renamedPayload);

    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor();

    const nameInput = screen.getByRole("textbox", { name: /^Preset name/ });
    fireEvent.change(nameInput, { target: { value: "Codex" } });
    fireEvent.blur(nameInput);
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());

    await waitFor(() => {
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        { id: "primary", name: "Codex" },
        20_000,
      );
    });
    expect(await screen.findByTestId("model-call-order-row-primary")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Codex");
  });

  it("maps a server-side name conflict back to the preset name field", async () => {
    const payload = settingsPayload();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    requestMutationMock.mockRejectedValueOnce(new ApiError(409, "Duplicate model name"));

    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor();

    const nameInput = screen.getByRole("textbox", { name: /^Preset name/ });
    fireEvent.change(nameInput, { target: { value: "Codex" } });
    fireEvent.blur(nameInput);
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A preset with this name already exists.",
    );
    expect(nameInput).toHaveAttribute("aria-invalid", "true");
    expect(nameInput).toHaveFocus();
  });
});
