import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";
import {
  requestMutationMock,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { settingsPayloadWithBackup, togglePresetEditor } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it.each([true, false])(
    "shows a saved primary summary inside the shared settings layout (sidebar: %s)",
    async (showSidebar) => {
      const payload = settingsPayload();
      payload.model_presets[0].context_window_tokens = 262_144;
      payload.model_presets[0].max_tokens = 32_768;
      renderSettingsView({ initialSection: "models", initialSettings: payload, showSidebar });

      expect(screen.getByRole("heading", { name: "Models" })).toBeVisible();
      expect(screen.getByRole("region", { name: "Model presets" })).toBeVisible();
      expect(screen.queryByRole("heading", { name: "Fallback presets" })).not.toBeInTheDocument();
      const summary = within(screen.getByTestId("model-call-order-row-primary"));
      expect(summary.getByText(payload.model_presets[0].model)).toBeInTheDocument();
      expect(summary.getByText("256K")).toBeInTheDocument();

      await togglePresetEditor();
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      fireEvent.change(screen.getByLabelText("Context window"), { target: { value: "128k" } });
      expect(summary.getByText("256K")).toBeInTheDocument();
    },
  );

  it("shows each preset's own summary before and after changing the primary", async () => {
    const { payload } = settingsPayloadWithBackup();
    payload.model_presets[0].context_window_tokens = 262_144;
    payload.model_presets[1].context_window_tokens = 128_000;
    payload.model_presets[1].reasoning_effort = "xhigh";
    const disabledPreset = {
      ...payload.model_presets[1],
      id: "disabled",
      name: "disabled",
      model: "openai/other-model",
      context_window_tokens: 1_048_576,
      reasoning_effort: "none",
    };
    payload.model_presets.push(disabledPreset);
    requestMutationMock.mockResolvedValueOnce({
      ...payload,
      model_call_order: ["backup", "primary"],
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });

    const expectSummaries = () => {
      for (const [name, model, settings] of [
        ["primary", payload.model_presets[0].model, "256K Default"],
        ["backup", payload.model_presets[1].model, "128K xhigh"],
        ["disabled", disabledPreset.model, "1M none"],
      ]) {
        const row = within(screen.getByTestId(`model-call-order-row-${name}`));
        expect(row.getByText(model)).toBeInTheDocument();
        const [context, effort] = settings.split(" ");
        expect(row.getByText(context)).toBeInTheDocument();
        if (effort !== "Default") expect(row.getByText(effort)).toBeInTheDocument();
      }
    };
    expectSummaries();
    fireEvent.keyDown(
      within(screen.getByTestId("model-call-order-row-backup")).getByRole("button", {
        name: /Drag to reorder/,
      }),
      { key: "ArrowUp" },
    );
    await waitFor(() =>
      expect(
        within(screen.getByTestId("model-call-order-row-backup")).getByText("Primary"),
      ).toBeInTheDocument(),
    );
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.model_call_order.update",
      { order: ["backup", "primary"] },
      20_000,
    );
    expectSummaries();
  });
});
