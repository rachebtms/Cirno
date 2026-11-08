import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  settingsPayloadWithBackup,
  togglePresetEditor,
  returnToPresetEditor,
} from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("opens the preset editor in a dialog and protects the primary preset", async () => {
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

    const row = await screen.findByTestId("model-call-order-row-primary");
    const trigger = within(row).getByRole("button", { name: /^primary openai/ });
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");

    fireEvent.click(trigger);

    const editor = document.querySelector<HTMLElement>(".model-preset-dialog")!;
    expect(screen.getByRole("dialog", { name: "primary" })).toBeVisible();
    expect(row.closest('[role="listitem"]')).toBeInTheDocument();
    expect(row.closest('[role="list"]')).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "primary" })).toContainElement(editor);
    expect(within(editor).getByRole("textbox", { name: /^Preset name/ })).toHaveValue("primary");
    const deleteButton = within(editor).getByRole("button", { name: "Delete" });
    expect(deleteButton).toBeDisabled();
    expect(deleteButton).toHaveAccessibleDescription("Cannot delete the primary model");
    expect(within(editor).getByText("Cannot delete the primary model")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
  });

  it("collapses advanced fields inside the preset editor without losing the draft", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    const payload = settingsPayload();
    requestMutationMock.mockResolvedValue({
      ...payload,
      model_presets: payload.model_presets.map((preset) => ({
        ...preset,
        context_window_tokens: 128000,
      })),
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor();
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    const advanced = screen.getByRole("dialog");
    fireEvent.change(within(advanced).getByLabelText("Context window"), {
      target: { value: "128k" },
    });
    await returnToPresetEditor();
    expect(screen.getByRole("button", { name: "Advanced options" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(document.querySelector<HTMLElement>(".model-preset-dialog")!).toBeVisible();
    expect(requestMutationMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    expect(within(screen.getByRole("dialog")).getByLabelText("Context window")).toHaveValue("128k");
  });

  it.each([true, false])(
    "closes the preset editor only after deletion succeeds (success: %s)",
    async (success) => {
      const { payload } = settingsPayloadWithBackup();
      vi.stubGlobal(
        "fetch",
        vi.fn(() => new Promise<Response>(() => {})),
      );
      if (success)
        requestMutationMock.mockResolvedValueOnce({
          ...payload,
          model_presets: payload.model_presets.filter((preset) => preset.id !== "backup"),
          model_call_order: ["primary"],
        });
      else requestMutationMock.mockRejectedValueOnce(new Error("Delete failed"));
      renderSettingsView({ initialSection: "models", initialSettings: payload });
      await togglePresetEditor("backup");
      fireEvent.click(
        within(document.querySelector<HTMLElement>(".model-preset-dialog")!).getByRole("button", {
          name: "Delete",
        }),
      );
      const confirmation = screen.getByRole("alertdialog", { name: "Delete model preset?" });
      fireEvent.click(within(confirmation).getByRole("button", { name: "Delete" }));
      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenCalledWith(
          "settings.model_configuration.delete",
          { id: "backup" },
          20_000,
        ),
      );
      if (success) {
        await waitFor(() =>
          expect(document.querySelector(".model-preset-dialog")).not.toBeInTheDocument(),
        );
        expect(screen.queryByTestId("model-call-order-row-backup")).not.toBeInTheDocument();
      } else {
        await waitFor(() =>
          expect(within(confirmation).getByRole("button", { name: "Delete" })).toBeEnabled(),
        );
        expect(document.querySelector<HTMLElement>(".model-preset-dialog")!).toBeInTheDocument();
      }
    },
  );
});
