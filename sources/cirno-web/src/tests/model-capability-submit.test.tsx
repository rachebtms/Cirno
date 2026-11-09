import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { requestMutationMock, jsonResponse, settingsPayload, renderSettingsView, installSettingsViewTestHooks } from "./settings-test-utils";
import { togglePresetEditor } from "./helpers/settings-models";

describe("Model capability probing", () => {
  installSettingsViewTestHooks();
  it("keeps the connection fixed and blocks form submission until the probe completes", async () => {
    const payload = settingsPayload();
    payload.model_capability_testing_supported = true;
    payload.model_presets[0].provider = "openai";
    payload.providers = [{ id: "openai", name: "OpenAI", configured: true }];
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(payload)));
    let complete!: (value: unknown) => void;
    requestMutationMock.mockImplementation((name, args) => name === "instance.action" && args.action === "models.probe"
      ? new Promise(resolve => { complete = resolve; }) : Promise.resolve(payload));
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await togglePresetEditor();
    fireEvent.click(screen.getByRole("button", { name: "Test capabilities" }));
    await waitFor(() => expect(complete).toBeDefined());
    expect(screen.getByLabelText("Preset name")).toBeDisabled();
    fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);
    expect(requestMutationMock.mock.calls.filter(([name]) => name === "settings.model_configuration.update")).toHaveLength(0);
    await act(async () => complete({ image: { supported: true, detail: "Recognized sample" }, video: { supported: false, detail: "Unsupported" } }));
    expect(screen.getByLabelText("Preset name")).toBeEnabled();
    expect(screen.getByText("Recognized sample")).toBeVisible();
  });
});
