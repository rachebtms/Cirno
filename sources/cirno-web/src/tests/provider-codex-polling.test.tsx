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
  it("polls local OpenAI Codex sign-in until the loopback callback completes", async () => {
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
      flow_id: "flow-codex-local",
      authorization_url: "https://auth.openai.com/oauth/authorize?state=local",
      expires_in: 600,
      completion_input: "callback_url",
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
    requestMutationMock.mockResolvedValueOnce(authorization).mockResolvedValueOnce(signedIn);
    const openMock = vi.fn();
    vi.stubGlobal("open", openMock);

    renderProviderManager({ initialSection: "models", initialSettings: payload });

    await chooseProviderToConfigure("OpenAI Codex");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const dialog = (
      await screen.findByText(
        "Finish signing in using your browser. If cirno does not connect automatically, copy the full URL from the localhost page’s address bar—even if the page cannot load—paste it below, then select “Finish sign-in”.",
      )
    ).closest('[role="dialog"]') as HTMLElement;

    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.provider.oauth_login",
      { provider: "openai_codex" },
      20_000,
    );
    expect(openMock).not.toHaveBeenCalled();
    expect(
      within(dialog).getByText(
        "Finish signing in using your browser. If cirno does not connect automatically, copy the full URL from the localhost page’s address bar—even if the page cannot load—paste it below, then select “Finish sign-in”.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Waiting for sign-in to finish…")).toBeInTheDocument();

    expect(await screen.findByText("Signed in", {}, { timeout: 2500 })).toBeInTheDocument();
  });
});
