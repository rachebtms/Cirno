import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
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
  it("saves proxy switches for xAI and OpenAI Codex OAuth providers before sign-in", async () => {
    const base = settingsPayload();
    const providers: SettingsPayload["providers"] = [
      {
        id: "xai_grok",
        name: "xAI Grok",
        configured: false,
        auth_type: "oauth",
        api_key_required: false,
        api_key_hint: null,
        api_base: null,
        default_api_base: "https://cli-chat-proxy.grok.com/v1",
        model_catalog: "builtin",
        oauth_account: null,
        oauth_expires_at: null,
        oauth_login_supported: true,
        use_proxy: true,
        advanced_fields: ["extra_body", "use_proxy"],
        extra_body: null,
      },
      {
        id: "openai_codex",
        name: "OpenAI Codex",
        configured: false,
        auth_type: "oauth",
        api_key_required: false,
        api_key_hint: null,
        api_base: null,
        default_api_base: "https://chatgpt.com/backend-api",
        model_catalog: "builtin",
        oauth_account: null,
        oauth_expires_at: null,
        oauth_login_supported: true,
        use_proxy: false,
        advanced_fields: ["extra_body", "use_proxy"],
        extra_body: null,
      },
    ];
    let payload: SettingsPayload = { ...base, providers };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(payload);
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({ apps: [], installed_count: 0 });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      if (url === "/v0/settings/cirno-features") return jsonResponse({ features: [] });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockImplementation(
      async (
        _action: string,
        values: { provider?: string; use_proxy?: boolean; extraBody?: string },
      ) => {
        payload = {
          ...payload,
          providers: payload.providers.map((provider) =>
            provider.id === values.provider
              ? {
                  ...provider,
                  use_proxy: values.use_proxy,
                  extra_body: values.extraBody ? JSON.parse(values.extraBody) : null,
                }
              : provider,
          ),
        };
        return payload;
      },
    );

    renderProviderManager({ initialSection: "models", initialSettings: payload });

    await chooseProviderToConfigure("xAI Grok");
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    const xaiProxy = screen.getByRole("switch", { name: "Use proxy" });
    expect(xaiProxy).toBeChecked();
    expect(screen.queryByPlaceholderText("http://127.0.0.1:7890")).not.toBeInTheDocument();
    fireEvent.click(xaiProxy);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
    expect(screen.getByText("Save advanced changes before signing in.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        {
          provider: "xai_grok",
          extraBody: "",
          use_proxy: false,
        },
        20_000,
      ),
    );
    await waitFor(() =>
      expect(within(providerDialog()).getByRole("button", { name: "Sign in" })).toBeEnabled(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Back to providers" }));
    fireEvent.click(screen.getByRole("button", { name: "Back to providers" }));
    await chooseProviderToConfigure("OpenAI Codex");
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    const codexProxy = screen.getByRole("switch", { name: "Use proxy" });
    expect(codexProxy).not.toBeChecked();
    fireEvent.click(codexProxy);
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        {
          provider: "openai_codex",
          extraBody: "",
          use_proxy: true,
        },
        20_000,
      ),
    );
  });
});
