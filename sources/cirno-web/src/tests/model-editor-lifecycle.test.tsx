import { screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  installSettingsViewTestHooks,
  jsonResponse,
  renderSettingsView,
  requestMutationMock,
} from "./settings-test-utils";
import { providerModelSettings } from "./helpers/provider-model-settings";

describe("model editor save and preview lifecycle", () => {
  installSettingsViewTestHooks();
  it("does not save partial model IDs while typing, then saves the completed ID on blur", async () => {
    const value = providerModelSettings();
    requestMutationMock.mockImplementation(async (_action, args) => ({
      ...value,
      model_presets: value.model_presets.map((row) => ({ ...row, model: args.model ?? row.model })),
    }));
    const user = userEvent.setup();
    renderSettingsView({ initialSection: "models", initialSettings: value });
    await user.click(
      screen
        .getByTestId("model-call-order-row-primary")
        .querySelector('button[aria-haspopup="dialog"]')!,
    );
    const dialog = await screen.findByRole("dialog", { name: "primary" });
    const input = within(dialog).getByRole("combobox", { name: "Model" });
    await user.clear(input);
    await user.type(input, "private-research-model");
    expect(input).toHaveValue("private-research-model");
    expect(requestMutationMock).not.toHaveBeenCalled();
    await user.tab();
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
    expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.model_configuration.update",
      { id: "primary", model: "private-research-model" },
      20_000,
    );
    expect(input).toHaveValue("private-research-model");
  });
  it("shows an API resolution failure inside the model editor and can retry it", async () => {
    const value = providerModelSettings();
    value.model_api_resolution_supported = true;
    let requests = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/settings/model-api?")) {
          if (++requests === 1) throw new Error("API preview unavailable");
          return jsonResponse({ provider: "openai", api: "responses" });
        }
        return jsonResponse(value);
      }),
    );
    const user = userEvent.setup();
    renderSettingsView({ initialSection: "models", initialSettings: value });
    await user.click(
      screen
        .getByTestId("model-call-order-row-primary")
        .querySelector('button[aria-haspopup="dialog"]')!,
    );
    const dialog = await screen.findByRole("dialog", { name: "primary" });
    await user.click(within(dialog).getByRole("button", { name: "Advanced options" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("API preview unavailable");
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument());
    expect(requests).toBe(2);
    expect(requestMutationMock).not.toHaveBeenCalled();
  });
  it("retains advanced edits after a failed save and collapses only after successful retry", async () => {
    const value = providerModelSettings();
    requestMutationMock.mockRejectedValueOnce(new Error("Model save failed"));
    requestMutationMock.mockResolvedValueOnce({
      ...value,
      model_presets: value.model_presets.map((row) => ({
        ...row,
        idle_compact_percent: 35,
      })),
    });
    const user = userEvent.setup();
    renderSettingsView({ initialSection: "models", initialSettings: value });
    await user.click(
      screen
        .getByTestId("model-call-order-row-primary")
        .querySelector('button[aria-haspopup="dialog"]')!,
    );
    const dialog = await screen.findByRole("dialog", { name: "primary" });
    const advanced = within(dialog).getByRole("button", {
      name: "Advanced options",
    });
    await user.click(advanced);
    fireEvent.change(
      within(dialog).getByRole("spinbutton", {
        name: "Idle consolidation trigger (%)",
      }),
      { target: { value: "35" } },
    );
    await user.click(advanced);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Model save failed");
    expect(advanced).toHaveAttribute("aria-expanded", "true");
    expect(
      within(dialog).getByRole("spinbutton", {
        name: "Idle consolidation trigger (%)",
      }),
    ).toHaveValue(35);
    await user.click(advanced);
    await waitFor(() => expect(advanced).toHaveAttribute("aria-expanded", "false"));
    expect(requestMutationMock).toHaveBeenCalledTimes(2);
    expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.model_configuration.update",
      { id: "primary", idle_compact_percent: 35 },
      20_000,
    );
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
