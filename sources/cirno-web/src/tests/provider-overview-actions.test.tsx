import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager, providerDialog } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("manages providers unused by presets and returns focus through the manager", async () => {
    const user = userEvent.setup();
    const payload = settingsPayload();
    payload.providers = [
      { id: "openai", name: "OpenAI", configured: true },
      { id: "deepseek", name: "DeepSeek", configured: true, api_base: "https://api.deepseek.com" },
    ];
    renderSettingsView({ initialSection: "models", initialSettings: payload });
    expect(screen.queryByRole("button", { name: "DeepSeek" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add provider" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Manage providers" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "DeepSeek" }));
    fireEvent.change(screen.getByLabelText("API URL"), {
      target: { value: "https://unsaved.example/v1" },
    });
    await user.click(screen.getByRole("button", { name: "Back to providers" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "DeepSeek" })).toHaveFocus());
    await user.keyboard("{Enter}");
    expect(screen.getByLabelText("API URL")).toHaveValue("https://api.deepseek.com");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("region", { name: "Providers" })).toBeVisible();
    await waitFor(() => expect(screen.getByRole("button", { name: "DeepSeek" })).toHaveFocus());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requestMutationMock).not.toHaveBeenCalled();
  });

  it("adds a built-in provider only after saving and returns focus to its management row", async () => {
    const user = userEvent.setup();
    const payload = settingsPayload();
    payload.providers = [{ id: "moonshot", name: "Moonshot", configured: false }];
    requestMutationMock.mockResolvedValueOnce({
      ...payload,
      providers: [{ ...payload.providers[0], configured: true, api_key_hint: "configured" }],
    });
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    const trigger = screen.getByRole("button", { name: "Add provider" });
    await user.click(trigger);
    await user.click(screen.getByRole("option", { name: "Moonshot" }));
    await user.type(screen.getByPlaceholderText("Enter API key"), "test-key");
    await user.click(within(providerDialog()).getByRole("button", { name: "Add provider" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
    expect(screen.getByRole("button", { name: "Moonshot" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Moonshot" })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "Add provider" }));
    expect(screen.queryByRole("option", { name: "Moonshot" })).not.toBeInTheDocument();
  });

  it("keeps provider labels and keyboard configuration accessible with decorative logos", async () => {
    const user = userEvent.setup();
    const payload: SettingsPayload = {
      ...settingsPayload(),
      providers: [
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          configured: true,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          model_catalog: "builtin",
          oauth_account: "test-account",
          oauth_login_supported: true,
        },
      ],
    };
    renderProviderManager({ initialSection: "models", initialSettings: payload });

    const provider = await screen.findByRole("button", { name: "OpenAI Codex" });
    expect(within(provider).getByText("OpenAI Codex")).toBeInTheDocument();
    expect(within(provider).queryByRole("img")).not.toBeInTheDocument();
    provider.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "OpenAI Codex" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
    expect(screen.getByRole("button", { name: "OpenAI Codex" })).toHaveFocus();
    expect(requestMutationMock).not.toHaveBeenCalled();
  });
});
