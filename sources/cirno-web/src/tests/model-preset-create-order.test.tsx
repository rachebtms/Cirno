import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  settingsPayloadWithBackup,
  openModelPicker,
  returnToPresetEditor,
  presetSaveButton,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("appends a new model preset to the call order immediately", async () => {
    const { payload } = settingsPayloadWithBackup();
    const writerPreset = {
      ...payload.model_presets[0],
      id: "Writer",
      name: "Writer",
      active: false,
      model: "openai/gpt-4o-mini",
      provider: "openai",
      resolved_provider: "openai",
    };
    const createdPayload: SettingsPayload = {
      ...payload,
      model_presets: [...payload.model_presets, writerPreset],
      created_model_preset: writerPreset.id,
    };
    const orderedPayload: SettingsPayload = {
      ...createdPayload,
      model_call_order: ["primary", "backup", "Writer"],
      created_model_preset: undefined,
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
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce(createdPayload).mockResolvedValueOnce(orderedPayload);

    renderSettingsView({ initialSection: "models", initialSettings: payload });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/v0/settings",
        expect.objectContaining({
          headers: { Authorization: "Bearer tok" },
        }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "New preset" }));
    expect(screen.getByRole("dialog", { name: "New preset" })).toBeInTheDocument();
    expect(presetSaveButton()).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: /^Preset name/ }), {
      target: { value: "Writer" },
    });
    const modelSearch = await openModelPicker();
    fireEvent.change(modelSearch, {
      target: { value: "openai/gpt-4o-mini" },
    });
    fireEvent.keyDown(modelSearch, { key: "Enter" });
    const saveButton = presetSaveButton();
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(requestMutationMock).toHaveBeenLastCalledWith(
        "settings.model_call_order.update",
        { order: ["primary", "backup", "Writer"] },
        20_000,
      );
    });
    const writerRow = await screen.findByTestId("model-call-order-row-Writer");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(within(writerRow).getByRole("switch", { name: "Disable preset" })).toBeChecked();
    expect(screen.getAllByText("Writer").length).toBeGreaterThan(0);
  });

  it("shows an inline error when a new preset name already exists", async () => {
    const { payload } = settingsPayloadWithBackup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response),
    );

    renderSettingsView({ initialSection: "models", initialSettings: payload });

    fireEvent.click(screen.getByRole("button", { name: "New preset" }));
    const nameInput = screen.getByRole("textbox", { name: /^Preset name/ });
    fireEvent.change(nameInput, { target: { value: "PRIMARY" } });
    const modelSearch = await openModelPicker();
    fireEvent.change(modelSearch, { target: { value: "openai/gpt-4o-mini" } });
    fireEvent.keyDown(modelSearch, { key: "Enter" });
    await returnToPresetEditor();
    fireEvent.click(presetSaveButton());

    expect(requestMutationMock).not.toHaveBeenCalled();
    expect(nameInput).toHaveAttribute("aria-invalid", "true");
    expect(nameInput).toHaveAccessibleDescription(/A preset with this name already exists/);
    expect(screen.getByRole("alert")).toHaveTextContent("A preset with this name already exists.");
    expect(nameInput).toHaveFocus();

    fireEvent.change(nameInput, { target: { value: "Writer" } });
    expect(nameInput).not.toHaveAttribute("aria-invalid", "true");
  });
});
