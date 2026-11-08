import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  it.each([
    { save: false, activation: "pointer" }, { save: true, activation: "pointer" },
    { save: false, activation: "direct" }, { save: true, activation: "direct" },
  ])(
    "configures the current provider without losing the preset draft (save: $save, activation: $activation)",
    async ({ save, activation }) => {
      const user = userEvent.setup();
      const payload = settingsPayload();
      payload.providers = [
        {
          id: "openai",
          name: "OpenAI",
          configured: true,
          api_key_hint: "configured",
          api_base: "https://api.openai.com/v1",
        },
      ];
      requestMutationMock.mockResolvedValueOnce({
        ...payload,
        providers: [{ ...payload.providers[0], api_base: "https://gateway.example/v1" }],
      });
      renderSettingsView({ initialSection: "models", initialSettings: payload });
      await user.click(screen.getByRole("button", { name: "New preset" }));
      const name = screen.getByRole("textbox", { name: "Preset name" });
      await user.type(name, "Keep this draft");
      const model = screen.getByRole("combobox", { name: "Model" });
      await user.click(model);
      fireEvent.change(model, { target: { value: "gpt-4o-mini" } });
      await user.keyboard("{Enter}");
      const picker = screen.getByRole("button", { name: "Configure" });
      if (activation === "direct") fireEvent.click(picker);
      else await user.click(picker);
      fireEvent.change(screen.getByLabelText("API URL"), {
        target: { value: "https://gateway.example/v1" },
      });
      await user.click(
        within(providerDialog()).getByRole("button", { name: save ? "Save provider" : "Cancel" }),
      );
      await waitFor(() =>
        expect(screen.queryByRole("dialog", { name: "OpenAI" })).not.toBeInTheDocument(),
      );
      expect(screen.getByRole("dialog", { name: "New preset" })).toBeVisible();
      expect(name).toHaveValue("Keep this draft");
      expect(model).toHaveValue("gpt-4o-mini");
      expect(screen.getByRole("button", { name: "OpenAI Provider" })).toBeVisible();
      await waitFor(() => expect(picker).toHaveFocus());
      expect(requestMutationMock).toHaveBeenCalledTimes(save ? 1 : 0);
      await user.click(picker);
      expect(screen.getByLabelText("API URL")).toHaveValue(
        save ? "https://gateway.example/v1" : "https://api.openai.com/v1",
      );
    },
  );

  it("preserves the preset draft when signing out of its current provider", async () => {
    const user = userEvent.setup();
    const payload = settingsPayload();
    const provider = {
      id: "openai_codex",
      name: "OpenAI Codex",
      configured: true,
      auth_type: "oauth" as const,
      api_key_required: false,
      oauth_login_supported: true,
    };
    payload.providers = [provider];
    requestMutationMock.mockResolvedValueOnce({
      ...payload,
      providers: [{ ...provider, configured: false }],
    });
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    await user.click(screen.getByRole("button", { name: "New preset" }));
    await user.type(screen.getByRole("textbox", { name: "Preset name" }), "OAuth draft");
    const picker = screen.getByRole("button", { name: "Configure" });
    await user.click(picker);
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() =>
      expect(within(providerDialog()).getByRole("button", { name: "Sign in" })).toBeEnabled(),
    );
    await user.click(within(providerDialog()).getByRole("button", { name: "Close" }));
    expect(screen.getByRole("dialog", { name: "New preset" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Preset name" })).toHaveValue("OAuth draft");
    expect(screen.getByRole("button", { name: "OpenAI Codex Provider" })).toBeVisible();
    await waitFor(() => expect(picker).toHaveFocus());
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.provider.oauth_logout",
      { provider: "openai_codex" },
      20_000,
    );
  });
});
