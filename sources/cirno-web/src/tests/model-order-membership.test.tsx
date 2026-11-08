import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { settingsPayloadWithBackup } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("restores the model call order when immediate persistence fails", async () => {
    const { payload } = settingsPayloadWithBackup();
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
    requestMutationMock.mockRejectedValueOnce(new Error("Order update failed"));

    renderSettingsView({ initialSection: "models", initialSettings: payload });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/v0/settings",
        expect.objectContaining({
          headers: { Authorization: "Bearer tok" },
        }),
      ),
    );
    fireEvent.keyDown(
      within(screen.getByTestId("model-call-order-row-backup")).getByRole("button", {
        name: /Drag to reorder/,
      }),
      {
        key: "ArrowUp",
      },
    );

    expect(await screen.findByText("Order update failed")).toBeInTheDocument();
    expect(
      screen.getAllByTestId(/^model-call-order-row-/).map((row) => row.getAttribute("data-testid")),
    ).toEqual(["model-call-order-row-primary", "model-call-order-row-backup"]);
  });

  it("shows presets outside the call order in the unified list and adds them directly", async () => {
    const { payload } = settingsPayloadWithBackup();
    const codexPreset = {
      ...payload.model_presets[0],
      id: "codex",
      name: "codex",
      active: false,
      model: "openai-codex/gpt-5.5",
      provider: "openai",
      resolved_provider: "openai",
    };
    const payloadWithCodex: SettingsPayload = {
      ...payload,
      model_presets: [...payload.model_presets, codexPreset],
    };
    const orderedPayload: SettingsPayload = {
      ...payloadWithCodex,
      model_call_order: ["primary", "backup", "codex"],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(payloadWithCodex);
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({ apps: [], installed_count: 0 });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce(orderedPayload);

    renderSettingsView({ initialSection: "models", initialSettings: payloadWithCodex });

    const codexRow = await screen.findByTestId("model-call-order-row-codex");
    expect(codexRow).toHaveTextContent("codex");
    expect(within(codexRow).getByRole("button", { name: /Drag to reorder/ })).toBeDisabled();

    const enableSwitch = within(codexRow).getByRole("switch", { name: "Enable preset" });
    expect(enableSwitch).not.toBeChecked();
    fireEvent.click(enableSwitch);

    await waitFor(() => {
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_call_order.update",
        { order: ["primary", "backup", "codex"] },
        20_000,
      );
    });
    const enabledCodexRow = await screen.findByTestId("model-call-order-row-codex");
    expect(within(enabledCodexRow).getByRole("button", { name: /Drag to reorder/ })).toBeEnabled();
    expect(within(enabledCodexRow).getByRole("switch", { name: "Disable preset" })).toBeChecked();
  });

  it("does not allow disabling the last preset", () => {
    renderSettingsView({ initialSection: "models", initialSettings: settingsPayload() });
    const toggle = screen.getByRole("switch", { name: "Disable preset" });
    expect(toggle).toBeChecked();
    expect(toggle).toBeDisabled();
    fireEvent.click(toggle);
    expect(requestMutationMock).not.toHaveBeenCalled();
  });
});
