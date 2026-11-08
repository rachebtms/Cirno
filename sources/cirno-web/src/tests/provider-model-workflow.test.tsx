import { screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  installSettingsViewTestHooks,
  renderSettingsView,
  requestMutationMock,
} from "./settings-test-utils";

import { providerModelSettings } from "./helpers/provider-model-settings";

async function createDraft(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "New preset" }));
  const dialog = await screen.findByRole("dialog", { name: "New preset" });
  await user.clear(within(dialog).getByRole("textbox", { name: /^Preset name/ }));
  await user.type(within(dialog).getByRole("textbox", { name: /^Preset name/ }), "Keep this draft");
  const field = within(dialog).getByRole("combobox", { name: "Model" });
  fireEvent.change(field, { target: { value: "gpt-4o-mini" } });
  return dialog;
}
describe("native provider and model workflow", () => {
  installSettingsViewTestHooks();
  it("configures a provider from a model draft and returns without losing that draft", async () => {
    const user = userEvent.setup();
    renderSettingsView({
      initialSection: "models",
      initialSettings: providerModelSettings(),
    });
    const draft = await createDraft(user);
    await user.click(within(draft).getByRole("button", { name: "Configure" }));
    const provider = await screen.findByRole("dialog", { name: "OpenAI" });
    fireEvent.change(within(provider).getByRole("textbox", { name: "API URL" }), {
      target: { value: "https://unsaved.example/v1" },
    });
    await user.click(within(provider).getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "OpenAI" })).not.toBeInTheDocument(),
    );
    expect(within(draft).getByRole("textbox", { name: /^Preset name/ })).toHaveValue(
      "Keep this draft",
    );
    expect(within(draft).getByRole("combobox", { name: "Model" })).toHaveValue("gpt-4o-mini");
    expect(requestMutationMock).not.toHaveBeenCalled();
  });
  it("keeps the provider draft and error visible after a failed save", async () => {
    const user = userEvent.setup();
    requestMutationMock.mockRejectedValueOnce(new Error("Provider save failed"));
    renderSettingsView({
      initialSection: "providers",
      initialSettings: providerModelSettings(),
    });
    await user.click(screen.getByRole("button", { name: "OpenAI" }));
    const dialog = await screen.findByRole("dialog", { name: "OpenAI" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "API URL" }), {
      target: { value: "https://keep.example/v1" },
    });
    await user.click(within(dialog).getByRole("button", { name: "Save provider" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Provider save failed");
    expect(within(dialog).getByRole("textbox", { name: "API URL" })).toHaveValue(
      "https://keep.example/v1",
    );
  });
});
