import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { settingsPayloadWithBackup, mockPresetRowLayout } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("keeps repeated fallback preset rows stable when changing the primary preset", async () => {
    const { payload, backupPreset } = settingsPayloadWithBackup();
    const initialPayload: SettingsPayload = {
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
      })),
      model_call_order: ["backup", "primary", "backup"],
    };
    const updatedPayload: SettingsPayload = {
      ...initialPayload,
      agent: {
        ...payload.agent,
        model_preset: "primary",
      },
      model_presets: payload.model_presets.map((preset) => ({
        ...preset,
        active: preset.id === "primary",
      })),
      model_call_order: ["primary", "backup", "backup"],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(initialPayload);
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({ apps: [], installed_count: 0 });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce(updatedPayload);

    renderSettingsView({ initialSection: "models", initialSettings: initialPayload });

    const primaryRow = screen.getByTestId("model-call-order-row-primary");
    const backupRows = screen.getAllByTestId("model-call-order-row-backup");
    const secondBackupRow = backupRows[1];
    const secondBackupTrigger = secondBackupRow.querySelector<HTMLButtonElement>(
      'button[aria-haspopup="dialog"]',
    )!;
    fireEvent.click(secondBackupTrigger);
    expect(document.querySelectorAll(".model-preset-dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog", { name: "backup" })).toContainElement(
      document.querySelector<HTMLElement>(".model-preset-dialog")!,
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    const centers = mockPresetRowLayout();
    fireEvent.pointerDown(within(primaryRow).getByRole("button", { name: /Drag to reorder/ }), {
      button: 0,
      clientY: centers[1],
      pointerId: 1,
    });
    fireEvent.pointerMove(primaryRow, { clientY: centers[0], pointerId: 1, buttons: 1 });
    fireEvent.pointerUp(primaryRow, { pointerId: 1 });

    await waitFor(() =>
      expect(
        screen
          .getAllByTestId(/^model-call-order-row-/)
          .map((row) => row.getAttribute("data-testid")),
      ).toEqual([
        "model-call-order-row-primary",
        "model-call-order-row-backup",
        "model-call-order-row-backup",
      ]),
    );
  });
});
