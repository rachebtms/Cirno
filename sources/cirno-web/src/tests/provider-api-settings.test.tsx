import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import {
  requestMutationMock,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager, providerDialog } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("declares custom connection APIs on creation and preserves them when editing", async () => {
    const user = userEvent.setup();
    let payload = settingsPayload();
    payload.provider_api_configuration_supported = true;
    const api = {
      supported_apis: ["anthropic_messages" as const],
      preferred_api: "anthropic_messages" as const,
    };
    requestMutationMock.mockImplementation(async (action, args) => {
      if (action === "settings.provider.create") {
        payload = {
          ...payload,
          providers: [
            ...payload.providers,
            {
              id: "tenant",
              name: "Tenant",
              is_custom: true,
              configured: true,
              api_base: args.apiBase,
              api: args.api,
              provider_api_configurable: true,
              request_apis: args.api.supported_apis,
            },
          ],
        };
      }
      if (action === "settings.provider.update") {
        payload = {
          ...payload,
          providers: payload.providers.map((row) =>
            row.id === "tenant"
              ? { ...row, api: args.api, request_apis: args.api.supported_apis }
              : row,
          ),
        };
      }
      return payload;
    });
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    await user.click(screen.getByRole("button", { name: "Add provider" }));
    await user.click(screen.getByRole("button", { name: "Custom" }));
    await user.type(screen.getByPlaceholderText("My model provider"), "Tenant");
    await user.type(
      screen.getByPlaceholderText("https://api.example.com/v1"),
      "https://tenant.test",
    );
    expect(screen.queryByRole("group", { name: "Supported APIs" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("checkbox", { name: "Chat Completions" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "Anthropic Messages" }));
    await user.click(screen.getByRole("checkbox", { name: "Chat Completions" }));
    expect(screen.getByRole("button", { name: /Default API/ })).toHaveTextContent(
      "Anthropic Messages",
    );
    expect(screen.getByRole("checkbox", { name: "Anthropic Messages" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    await user.click(within(providerDialog()).getByRole("button", { name: "Add provider" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.provider.create",
      expect.objectContaining({ api }),
      20_000,
    );
    await user.click(screen.getByRole("button", { name: "Tenant" }));
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("button", { name: /Default API/ })).toHaveTextContent(
      "Anthropic Messages",
    );
    await user.click(screen.getByRole("checkbox", { name: "Responses" }));
    await user.click(screen.getByRole("button", { name: /Default API/ }));
    await user.click(screen.getByRole("option", { name: "Responses" }));
    await user.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        expect.objectContaining({
          provider: "tenant",
          api: { supported_apis: ["responses", "anthropic_messages"], preferred_api: "responses" },
        }),
        20_000,
      ),
    );
    await user.click(screen.getByRole("button", { name: "Tenant" }));
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("button", { name: /Default API/ })).toHaveTextContent("Responses");
  });

  it("hides connection API declarations on hosts without the capability", async () => {
    renderProviderManager({ initialSection: "models", initialSettings: settingsPayload() });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.queryByRole("button", { name: /Default API/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Supported APIs" })).not.toBeInTheDocument();
  });

  it("saves and reopens OpenAI defaults, including automatic routing", async () => {
    const user = userEvent.setup();
    let payload = settingsPayload();
    payload.providers = [
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        api_key_hint: "sk-...",
        provider_api_configurable: true,
        request_apis: ["chat_completions", "responses"],
        api: { supported_apis: ["responses"], preferred_api: "responses" },
      },
    ];
    requestMutationMock.mockImplementation(async (_action, args) => {
      payload = { ...payload, providers: [{ ...payload.providers[0], api: args.api }] };
      return payload;
    });
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    await user.click(screen.getByRole("button", { name: "OpenAI" }));
    expect(screen.queryByRole("button", { name: /Default API/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("button", { name: /Default API/ })).toHaveTextContent("Responses");
    await user.click(screen.getByRole("button", { name: /Default API/ }));
    await user.click(screen.getByRole("option", { name: "Chat Completions" }));
    await user.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.provider.update",
      expect.objectContaining({
        provider: "openai",
        api: { supported_apis: ["chat_completions"], preferred_api: "chat_completions" },
      }),
      20_000,
    );
    await user.click(screen.getByRole("button", { name: "OpenAI" }));
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("button", { name: /Default API/ })).toHaveTextContent(
      "Chat Completions",
    );
    await user.click(screen.getByRole("button", { name: /Default API/ }));
    await user.click(screen.getByRole("option", { name: "Auto" }));
    await user.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.provider.update",
      expect.objectContaining({
        provider: "openai",
        api: null,
      }),
      20_000,
    );
    await user.click(screen.getByRole("button", { name: "OpenAI" }));
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("button", { name: /Default API/ })).toHaveTextContent("Auto");
  });
});
