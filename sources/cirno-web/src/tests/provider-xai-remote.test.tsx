import { fireEvent, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager, chooseProviderToConfigure } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("recognizes remote access before starting xAI Grok sign-in", async () => {
    const happyWindow = window as typeof window & {
      happyDOM: { setURL: (url: string) => void };
    };
    const originalUrl = window.location.href;
    happyWindow.happyDOM.setURL("http://203.0.113.10:18887/#/settings?section=models");

    try {
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
      const authorization = {
        status: "authorization_required",
        provider: "xai_grok",
        flow_id: "flow-remote",
        authorization_url: "https://auth.x.ai/oauth2/authorize?state=remote",
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
        if (url === "/v0/settings/cirno-features") return jsonResponse({ features: [] });
        return jsonResponse({});
      });
      vi.stubGlobal("fetch", fetchMock);
      requestMutationMock.mockResolvedValueOnce(authorization);
      const popup = {
        opener: window,
        location: { href: "about:blank" },
        close: vi.fn(),
      };
      const openMock = vi.fn(() => popup);
      vi.stubGlobal("open", openMock);

      renderProviderManager({ initialSection: "models", initialSettings: payload });

      await chooseProviderToConfigure("xAI Grok");
      expect(
        screen.getByText(
          "Select Sign in to open xAI on your computer, then paste the authorization code shown after login.",
        ),
      ).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      const dialog = (
        await screen.findByText(
          "Select Sign in to open xAI on your computer. After signing in, paste the authorization code shown by xAI below.",
        )
      ).closest('[role="dialog"]') as HTMLElement;

      expect(openMock).not.toHaveBeenCalled();
      expect(
        within(dialog).getByText(
          "Select Sign in to open xAI on your computer. After signing in, paste the authorization code shown by xAI below.",
        ),
      ).toBeInTheDocument();
      expect(
        within(dialog).getByRole("textbox", { name: "Authorization code" }),
      ).toBeInTheDocument();

      fireEvent.click(within(dialog).getByRole("button", { name: "Sign in" }));
      expect(openMock).toHaveBeenCalledWith(
        authorization.authorization_url,
        "_blank",
        "noopener,noreferrer",
      );
      expect(popup.opener).toBeNull();
    } finally {
      happyWindow.happyDOM.setURL(originalUrl);
    }
  });
});
