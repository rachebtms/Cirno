import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  it("completes remote OpenAI Codex sign-in with the full callback URL", async () => {
    const happyWindow = window as typeof window & {
      happyDOM: { setURL: (url: string) => void };
    };
    const originalUrl = window.location.href;
    happyWindow.happyDOM.setURL("http://203.0.113.10:18887/#/settings?section=models");

    try {
      const base = settingsPayload();
      const codexProvider = {
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
      } satisfies SettingsPayload["providers"][number];
      const payload: SettingsPayload = { ...base, providers: [codexProvider] };
      const signedIn: SettingsPayload = {
        ...payload,
        providers: [{ ...codexProvider, configured: true, oauth_account: "acct-codex" }],
      };
      const authorization = {
        status: "authorization_required",
        provider: "openai_codex",
        flow_id: "flow-codex",
        authorization_url: "https://auth.openai.com/oauth/authorize?state=test",
        expires_in: 600,
        completion_input: "callback_url",
      };
      const callbackUrl = "http://localhost:1455/auth/callback?code=secret&state=test";
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
        async (action: string, mutationPayload: Record<string, unknown>) => {
          if (action === "settings.provider.oauth_login") return authorization;
          if (mutationPayload.authorization_response === callbackUrl) return signedIn;
          return {
            status: "pending",
            provider: "openai_codex",
            flow_id: "flow-codex",
          };
        },
      );
      const popup = {
        opener: window,
        location: { href: "about:blank" },
        close: vi.fn(),
      };
      const openMock = vi.fn(() => popup);
      vi.stubGlobal("open", openMock);

      renderProviderManager({ initialSection: "models", initialSettings: payload });

      await chooseProviderToConfigure("OpenAI Codex");
      expect(
        screen.getByText(
          "Sign in through this browser, then paste the full localhost callback URL back into cirno.",
        ),
      ).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      const dialog = (
        await screen.findByText(
          "Open ChatGPT in this browser and finish signing in. On the localhost page, copy the full URL from the address bar—even if the page cannot load—paste it below, then select “Finish sign-in”.",
        )
      ).closest('[role="dialog"]') as HTMLElement;

      expect(openMock).not.toHaveBeenCalled();
      expect(
        within(dialog).getByText(
          "Open ChatGPT in this browser and finish signing in. On the localhost page, copy the full URL from the address bar—even if the page cannot load—paste it below, then select “Finish sign-in”.",
        ),
      ).toBeInTheDocument();
      expect(within(dialog).getByText("Paste the callback URL to continue.")).toBeInTheDocument();
      const callbackInput = within(dialog).getByRole("textbox", {
        name: "Callback URL",
      });
      expect(callbackInput).toHaveAttribute("placeholder", "Paste the full callback URL here");

      fireEvent.click(within(dialog).getByRole("button", { name: "Open ChatGPT" }));
      expect(openMock).toHaveBeenCalledWith(
        authorization.authorization_url,
        "_blank",
        "noopener,noreferrer",
      );
      expect(popup.opener).toBeNull();

      fireEvent.change(callbackInput, { target: { value: callbackUrl } });
      fireEvent.click(within(dialog).getByRole("button", { name: "Finish sign-in" }));

      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenCalledWith(
          "settings.provider.oauth_complete",
          {
            provider: "openai_codex",
            flow_id: "flow-codex",
            authorization_response: callbackUrl,
          },
          20_000,
        ),
      );
      expect(await screen.findByText("Signed in")).toBeInTheDocument();
    } finally {
      happyWindow.happyDOM.setURL(originalUrl);
    }
  });
});
