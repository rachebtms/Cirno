import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { openModelPicker } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it.each(["manual", "poll", "direct"])(
    "reauthenticates from the catalog and preserves the preset draft (%s)",
    async (mode) => {
      const payload = settingsPayload();
      payload.providers = [
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          configured: true,
          auth_type: "oauth",
          model_catalog: "hybrid",
          oauth_login_supported: true,
        },
      ];
      let recovered = false;
      const signedIn = () => {
        recovered = true;
        return { ...payload, providers: payload.providers.map((row) => ({ ...row })) };
      };
      requestMutationMock.mockImplementation(async (action, args) => {
        if (action === "settings.provider.oauth_login") {
          return mode === "direct"
            ? signedIn()
            : {
                status: "authorization_required",
                provider: "openai_codex",
                flow_id: "flow-test",
                authorization_url: "https://example.com/authorize",
                expires_in: 600,
                completion_input: "callback_url",
              };
        }
        if (action === "settings.provider.oauth_complete") {
          return mode === "manual" && !args.authorization_response
            ? { status: "pending", provider: "openai_codex", flow_id: "flow-test" }
            : signedIn();
        }
        throw new Error(`Unexpected mutation: ${action}`);
      });
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          if (String(input).includes("/provider-models?"))
            return jsonResponse({
              provider: "openai_codex",
              label: "OpenAI Codex",
              status: "available",
              catalog_kind: "hybrid",
              source: recovered ? "remote" : "fallback",
              error_kind: recovered ? null : "auth_required",
              models: [{ id: recovered ? "openai-codex/new-model" : "openai-codex/offline-model" }],
              model_count: 1,
            });
          return jsonResponse(payload);
        }),
      );
      renderSettingsView({ initialSection: "models" });
      fireEvent.click(await screen.findByRole("button", { name: "New preset" }));
      fireEvent.change(screen.getByRole("textbox", { name: /^Preset name/ }), {
        target: { value: "My unsaved preset" },
      });
      await openModelPicker();
      fireEvent.click(await screen.findByRole("button", { name: "Sign in again" }));
      if (mode === "manual") {
        fireEvent.change(await screen.findByRole("textbox", { name: "Callback URL" }), {
          target: { value: "http://localhost:1455/auth/callback?code=fixture&state=test" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Finish sign-in" }));
      }
      await waitFor(() => expect(recovered).toBe(true), { timeout: 3000 });
      expect(screen.getByRole("textbox", { name: /^Preset name/ })).toHaveValue(
        "My unsaved preset",
      );
      await openModelPicker();
      expect(await screen.findByRole("option", { name: /openai-codex\/new-model/ })).toBeVisible();
      expect(
        screen.queryByText("Authorization expired. Please sign in again."),
      ).not.toBeInTheDocument();
      expect(
        requestMutationMock.mock.calls.every(([action]) =>
          action.startsWith("settings.provider.oauth_"),
        ),
      ).toBe(true);
    },
  );
});
