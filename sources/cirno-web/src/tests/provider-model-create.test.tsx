import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import {
  requestMutationMock,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { providerDialog } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("opens provider setup from the preset picker with the keyboard and returns to the draft on cancel", async () => {
    const user = userEvent.setup();
    const payload = settingsPayload();
    payload.providers = [{ id: "openai", name: "OpenAI", configured: true }];
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await user.click(screen.getByRole("button", { name: "New preset" }));
    const name = screen.getByRole("textbox", { name: "Preset name" });
    await user.type(name, "Keep this draft");
    const providerPicker = screen.getByRole("button", { name: "Add provider" });
    await user.click(providerPicker);
    const dialog = await screen.findByRole("dialog", { name: "Add provider" });
    expect(dialog).toBeVisible();
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Add provider" })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("dialog", { name: "New preset" })).toBeVisible();
    expect(name).toHaveValue("Keep this draft");
    expect(screen.getByRole("button", { name: "OpenAI Provider" })).toBeVisible();
    expect(providerPicker).toHaveFocus();
    expect(requestMutationMock).not.toHaveBeenCalled();
  });

  it.each([false, true])(
    "selects the newly added provider and preserves the preset draft (custom: %s)",
    async (custom) => {
      const user = userEvent.setup();
      const payload = settingsPayload();
      const provider = {
        id: custom ? "company" : "moonshot",
        name: custom ? "Company" : "Moonshot",
        configured: false,
      };
      payload.providers = custom ? [] : [provider];
      requestMutationMock.mockResolvedValueOnce({
        ...payload,
        providers: [{ ...provider, configured: true, api_key_hint: "configured" }],
        ...(custom ? { created_provider: provider.id } : {}),
      });
      renderSettingsView({ initialSection: "models", initialSettings: payload });
      await user.click(screen.getByRole("button", { name: "New preset" }));
      const name = screen.getByRole("textbox", { name: "Preset name" });
      await user.type(name, "My first preset");
      const providerPicker = screen.getByRole("button", { name: "Add provider" });
      expect(providerPicker).toBeEnabled();
      await user.click(providerPicker);
      await user.click(
        custom
          ? screen.getByRole("button", { name: "Custom" })
          : screen.getByRole("option", { name: "Moonshot" }),
      );
      if (custom) {
        await user.type(screen.getByPlaceholderText("My model provider"), "Company");
        await user.type(
          screen.getByPlaceholderText("https://api.example.com/v1"),
          "https://gateway.example/v1",
        );
      }
      await user.type(screen.getByPlaceholderText("Enter API key"), "test-key");
      await user.click(within(providerDialog()).getByRole("button", { name: "Add provider" }));
      await waitFor(() => expect(screen.getByRole("dialog", { name: "New preset" })).toBeVisible());
      expect(name).toHaveValue("My first preset");
      expect(providerPicker).toBeEnabled();
      expect(screen.getByRole("button", { name: `${provider.name} Provider` })).toBeVisible();
      expect(name).toHaveValue("My first preset");
      expect(requestMutationMock).toHaveBeenCalledTimes(1);
      expect(requestMutationMock.mock.calls[0][0]).toBe(
        custom ? "settings.provider.create" : "settings.provider.update",
      );
    },
  );
});
