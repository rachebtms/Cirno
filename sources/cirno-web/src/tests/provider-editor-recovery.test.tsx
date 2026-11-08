import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import {
  requestMutationMock,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import {
  renderProviderManager,
  providerDialog,
  chooseProviderToConfigure,
} from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it.each([false, true])(
    "retains the add-provider draft after a failed save (custom: %s)",
    async (custom) => {
      const user = userEvent.setup();
      const payload = settingsPayload();
      payload.providers = [{ id: "moonshot", name: "Moonshot", configured: false }];
      requestMutationMock.mockRejectedValueOnce(new Error("Provider could not be saved"));
      renderProviderManager({ initialSection: "models", initialSettings: payload });
      await user.click(screen.getByRole("button", { name: "Add provider" }));
      await user.click(
        custom
          ? screen.getByRole("button", { name: "Custom" })
          : screen.getByRole("option", { name: "Moonshot" }),
      );
      const dialog = screen.getByRole("dialog");
      if (custom) {
        await user.type(screen.getByPlaceholderText("My model provider"), "Company gateway");
        await user.type(
          screen.getByPlaceholderText("https://api.example.com/v1"),
          "https://gateway.example/v1",
        );
      }
      await user.type(screen.getByPlaceholderText("Enter API key"), "test-key");
      await user.click(within(providerDialog()).getByRole("button", { name: "Add provider" }));
      await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
      await waitFor(() =>
        expect(within(dialog).getByRole("button", { name: "Add provider" })).toBeEnabled(),
      );
      expect(screen.getByRole("dialog")).toBe(dialog);
      expect(within(dialog).getByPlaceholderText("Enter API key")).toHaveValue("test-key");
      await user.click(within(dialog).getByRole("button", { name: "Back to providers" }));
      expect(screen.getByRole("dialog", { name: "Add provider" })).toBe(dialog);
      await user.click(
        custom
          ? screen.getByRole("button", { name: "Custom" })
          : screen.getByRole("option", { name: "Moonshot" }),
      );
      expect(screen.getByPlaceholderText("Enter API key")).toHaveValue("");
      await user.click(screen.getByRole("button", { name: "Cancel" }));
      await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
      expect(screen.queryByRole("button", { name: "Moonshot" })).not.toBeInTheDocument();
    },
  );

  it("shows a credential read failure in the OAuth provider editor", async () => {
    const payload = settingsPayload();
    payload.providers = [
      {
        id: "openai_codex",
        name: "OpenAI Codex",
        configured: false,
        auth_type: "oauth",
        api_key_required: false,
        oauth_login_supported: true,
        oauth_error: "Could not read OAuth credentials: permission denied",
      },
    ];
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    await chooseProviderToConfigure("OpenAI Codex");
    expect(await screen.findByRole("alert")).toHaveTextContent("permission denied");
    expect(within(providerDialog()).getByRole("button", { name: "Sign in" })).toBeEnabled();
  });
});
