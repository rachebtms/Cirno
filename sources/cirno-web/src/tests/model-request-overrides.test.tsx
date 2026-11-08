import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { returnToPresetEditor, openPresetAdvancedOptions } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("saves model compaction percentages when no other field changes", async () => {
    const payload = settingsPayload();
    payload.providers = [{ id: "openai", name: "OpenAI", configured: true }];
    payload.model_presets[0].provider = "openai";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(payload)),
    );
    requestMutationMock.mockResolvedValue(payload);
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await openPresetAdvancedOptions();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Idle compaction trigger (%)" }), {
      target: { value: "35" },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Recent context retention (%)" }), {
      target: { value: "8" },
    });
    await returnToPresetEditor();
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        { id: "primary", idle_compact_percent: 35, idle_compact_keep_percent: 8 },
        20_000,
      ),
    );
  });

  it("saves request overrides in a preset and restores inheritance when cleared", async () => {
    const payload = settingsPayload();
    payload.model_request_overrides_supported = true;
    payload.providers = [
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        advanced_fields: ["extra_headers", "extra_body", "extra_query"],
      },
    ];
    payload.model_presets[0].provider = "openai";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(payload)),
    );
    requestMutationMock.mockImplementation(async (_action, args) => {
      if (args.extra_headers !== undefined)
        payload.model_presets[0].extra_headers = args.extra_headers
          ? JSON.parse(args.extra_headers)
          : null;
      return structuredClone(payload);
    });
    requestMutationMock.mockRejectedValueOnce(new Error("Could not save. Try again."));
    renderSettingsView({ initialSection: "models" });
    await openPresetAdvancedOptions();
    const editor = screen.getByRole("group", { name: "Headers" });
    fireEvent.change(within(editor).getByRole("textbox", { name: "Headers" }), {
      target: { value: '{"X-Route":"preset"}' },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Save" }));
    expect(await within(editor).findByRole("alert")).toHaveTextContent(
      "Could not save. Try again.",
    );
    expect(within(editor).getByRole("textbox")).toHaveValue('{"X-Route":"preset"}');
    fireEvent.click(within(editor).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.model_configuration.update",
        { id: "primary", extra_headers: '{"X-Route":"preset"}' },
        20_000,
      ),
    );
    await waitFor(() =>
      expect(within(editor).getByRole("textbox", { name: "Headers" })).toBeEnabled(),
    );
    fireEvent.change(within(editor).getByRole("textbox", { name: "Headers" }), {
      target: { value: "" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenLastCalledWith(
        "settings.model_configuration.update",
        { id: "primary", extra_headers: "" },
        20_000,
      ),
    );
    await waitFor(() => expect(within(editor).getByText("Use provider settings")).toBeVisible());
  });
});
