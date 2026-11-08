import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager, chooseProviderToConfigure } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it.each([false, true])(
    "signs in to the xAI Grok provider (from preset: %s)",
    async (fromPreset) => {
      const base = settingsPayload();
      const xaiProvider = {
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
      } satisfies SettingsPayload["providers"][number];
      const payload: SettingsPayload = { ...base, providers: [xaiProvider] };
      const signedIn: SettingsPayload = {
        ...payload,
        providers: [{ ...xaiProvider, configured: true, oauth_account: "user@example.com" }],
      };
      const authorization = {
        status: "authorization_required",
        provider: "xai_grok",
        flow_id: "flow-123",
        authorization_url: "https://auth.x.ai/oauth2/authorize?state=test",
        expires_in: 600,
      };
      const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/v0/settings") return jsonResponse(payload);
        if (url === "/v0/settings/cli-apps") {
          return jsonResponse({ apps: [], installed_count: 0 });
        }
        if (url === "/v0/settings/mcp-presets") {
          return jsonResponse({ presets: [], installed_count: 0 });
        }
        if (url.startsWith("/v0/settings/provider-models"))
          return jsonResponse({
            provider: "xai_grok",
            status: "available",
            catalog_kind: "hybrid",
            models: [],
            model_count: 0,
          });
        if (url === "/v0/settings/cirno-features") return jsonResponse({ features: [] });
        return jsonResponse({});
      });
      vi.stubGlobal("fetch", fetchMock);
      requestMutationMock.mockResolvedValueOnce(authorization).mockResolvedValueOnce(signedIn);
      const popup = {
        opener: window,
        location: { href: "about:blank" },
        close: vi.fn(),
      };
      vi.stubGlobal(
        "open",
        vi.fn(() => popup),
      );

      (fromPreset ? renderSettingsView : renderProviderManager)({
        initialSection: "models",
        initialSettings: payload,
      });

      if (fromPreset) {
        const user = userEvent.setup();
        await user.click(screen.getByRole("button", { name: "New preset" }));
        await user.type(screen.getByRole("textbox", { name: "Preset name" }), "OAuth preset");
        await user.click(screen.getByRole("button", { name: "Add provider" }));
        await user.click(screen.getByRole("option", { name: "xAI Grok" }));
      } else {
        await chooseProviderToConfigure("xAI Grok");
      }

      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenCalledWith(
          "settings.provider.oauth_login",
          { provider: "xai_grok" },
          20_000,
        ),
      );
      expect(popup.opener).toBeNull();
      expect(popup.location.href).toBe(authorization.authorization_url);

      expect(
        screen.getByText(
          "Complete sign-in in your browser. If cirno does not connect automatically, paste the authorization code below.",
        ),
      ).toBeInTheDocument();
      const callbackInput = await screen.findByRole("textbox", {
        name: "Authorization code",
      });
      fireEvent.change(callbackInput, {
        target: { value: "secret" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Finish sign-in" }));

      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenCalledWith(
          "settings.provider.oauth_complete",
          {
            provider: "xai_grok",
            flow_id: "flow-123",
            authorization_response: "secret",
          },
          20_000,
        ),
      );
      if (fromPreset) {
        await waitFor(() =>
          expect(screen.queryByRole("dialog", { name: "xAI Grok" })).not.toBeInTheDocument(),
        );
        await waitFor(() =>
          expect(screen.getByRole("button", { name: "Add provider" })).toHaveFocus(),
        );
        expect(screen.getByRole("textbox", { name: "Preset name" })).toHaveValue("OAuth preset");
      } else {
        expect(await screen.findByText("Signed in")).toBeInTheDocument();
      }
    },
  );
});
