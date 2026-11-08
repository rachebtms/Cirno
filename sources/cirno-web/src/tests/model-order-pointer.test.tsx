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
  togglePresetEditor,
  mockPresetRowLayout,
  returnToPresetEditor,
  presetSaveButton,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it.each([
    ["backup", 1, 0],
    ["primary", 0, 1],
  ] as const)(
    "drags %s across different row heights and saves the model call order immediately",
    async (name, from, to) => {
      const { payload, backupPreset } = settingsPayloadWithBackup();
      const updatedPayload: SettingsPayload = {
        ...payload,
        agent: {
          ...payload.agent,
          model: backupPreset.model,
          provider: backupPreset.provider,
          resolved_provider: backupPreset.resolved_provider,
          model_preset: backupPreset.id,
        },
        model_presets: payload.model_presets.map((preset) => ({
          ...preset,
          active: preset.id === backupPreset.id,
          temperature: preset.id === "primary" ? 0.4 : preset.temperature,
        })),
        model_call_order: ["backup", "primary"],
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
      requestMutationMock
        .mockResolvedValueOnce({
          ...payload,
          model_presets: payload.model_presets.map((preset) =>
            preset.id === "primary" ? { ...preset, temperature: 0.4 } : preset,
          ),
        })
        .mockResolvedValueOnce(updatedPayload);

      renderSettingsView({ initialSection: "models", initialSettings: payload });

      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          "/v0/settings",
          expect.objectContaining({
            headers: { Authorization: "Bearer tok" },
          }),
        ),
      );
      await togglePresetEditor();
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      fireEvent.change(screen.getByLabelText("Temperature"), {
        target: { value: "0.4" },
      });
      await returnToPresetEditor();
      fireEvent.click(screen.getByRole("button", { name: "Close" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      requestMutationMock.mockClear();
      const centers = mockPresetRowLayout();
      const draggedRow = screen.getByTestId(`model-call-order-row-${name}`);
      fireEvent.pointerDown(within(draggedRow).getByRole("button", { name: /Drag to reorder/ }), {
        button: 0,
        clientY: centers[from],
        pointerId: 1,
      });
      fireEvent.pointerMove(draggedRow, {
        clientY: centers[to] + (to > from ? 1 : -1),
        pointerId: 1,
        buttons: 1,
      });
      expect(
        within(screen.getByTestId("model-call-order-row-backup")).getByText("Primary"),
      ).toBeInTheDocument();
      expect(requestMutationMock).not.toHaveBeenCalled();
      fireEvent.pointerUp(draggedRow, { pointerId: 1 });
      fireEvent.click(draggedRow);

      await waitFor(() => {
        expect(requestMutationMock).toHaveBeenCalledWith(
          "settings.model_call_order.update",
          { order: ["backup", "primary"] },
          20_000,
        );
      });

      const newPrimary = screen.getByTestId("model-call-order-row-backup");
      expect(within(newPrimary).getByText("Primary")).toBeInTheDocument();
      expect(within(newPrimary).getByText(backupPreset.model)).toBeInTheDocument();
      expect(within(newPrimary).getByText("200K")).toBeInTheDocument();
      await togglePresetEditor("primary");
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      expect(screen.getByLabelText("Temperature")).toHaveValue(0.4);
      expect(presetSaveButton()).toBeDisabled();
    },
  );

  it("allows the next switch click when a drag ends without a click event", async () => {
    const { payload } = settingsPayloadWithBackup();
    requestMutationMock
      .mockResolvedValueOnce({ ...payload, model_call_order: ["backup", "primary"] })
      .mockResolvedValueOnce({ ...payload, model_call_order: ["backup"] });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    const centers = mockPresetRowLayout();
    const backupRow = screen.getByTestId("model-call-order-row-backup");
    fireEvent.pointerDown(within(backupRow).getByRole("button", { name: /Drag to reorder/ }), {
      button: 0,
      clientY: centers[1],
      pointerId: 1,
    });
    fireEvent.pointerMove(backupRow, { clientY: centers[0], pointerId: 1, buttons: 1 });
    fireEvent.pointerUp(backupRow, { pointerId: 1 });
    await waitFor(() => expect(within(backupRow).getByText("Primary")).toBeInTheDocument());

    const toggle = within(screen.getByTestId("model-call-order-row-primary")).getByRole("switch");
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.pointerDown(toggle, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(toggle, { pointerId: 1 });
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenLastCalledWith(
        "settings.model_call_order.update",
        { order: ["backup"] },
        20_000,
      ),
    );
  });

  it("restores the primary preview without saving when a pointer drag is cancelled", async () => {
    const { payload } = settingsPayloadWithBackup();
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    const centers = mockPresetRowLayout();
    const backupRow = screen.getByTestId("model-call-order-row-backup");
    fireEvent.pointerDown(within(backupRow).getByRole("button", { name: /Drag to reorder/ }), {
      button: 0,
      clientY: centers[1],
      pointerId: 1,
    });
    fireEvent.pointerMove(backupRow, { clientY: centers[0] - 1, pointerId: 1, buttons: 1 });
    expect(within(backupRow).getByText("Primary")).toBeInTheDocument();
    fireEvent.pointerCancel(backupRow, { pointerId: 1 });
    expect(
      within(screen.getByTestId("model-call-order-row-primary")).getByText("Primary"),
    ).toBeInTheDocument();
    expect(requestMutationMock).not.toHaveBeenCalled();
  });
});
