import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  requestMutationMock,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("persists a disabled proxy switch on an API-key provider without changing credentials", async () => {
    const base = settingsPayload();
    let payload: SettingsPayload = {
      ...base,
      providers: [
        {
          id: "openrouter",
          name: "OpenRouter",
          configured: true,
          api_key_hint: "sk-••••test",
          api_base: "https://openrouter.ai/api/v1",
          use_proxy: true,
          advanced_fields: ["use_proxy"],
        },
      ],
    };
    requestMutationMock.mockImplementation(async (_action, values) => {
      payload = {
        ...payload,
        providers: payload.providers.map((provider) => ({
          ...provider,
          use_proxy: values.use_proxy,
        })),
      };
      return payload;
    });
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    fireEvent.click(screen.getByRole("button", { name: "OpenRouter" }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    const useProxy = screen.getByRole("switch", { name: "Use proxy" });
    expect(useProxy).toBeChecked();
    fireEvent.click(useProxy);
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        {
          provider: "openrouter",
          apiBase: "https://openrouter.ai/api/v1",
          apiKey: undefined,
          use_proxy: false,
        },
        20_000,
      ),
    );
    fireEvent.click(await screen.findByRole("button", { name: "OpenRouter" }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByRole("switch", { name: "Use proxy" })).not.toBeChecked();
  });

  it("keeps ordinary OpenAI edits available on hosts without API declarations", async () => {
    const payload = settingsPayload();
    payload.providers = [
      {
        id: "openai",
        name: "OpenAI",
        configured: true,
        api_key_hint: "sk-...",
        api_base: "https://api.openai.com/v1",
        advanced_fields: ["extra_body"],
        extra_body: { tools: [{ type: "web_search" }] },
      },
    ];
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    fireEvent.click(screen.getByRole("button", { name: "OpenAI" }));
    expect(screen.queryByRole("button", { name: /Default API/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "OpenAI web search" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("API URL"), {
      target: { value: "https://gateway.test/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.provider.update",
        expect.objectContaining({
          provider: "openai",
          apiBase: "https://gateway.test/v1",
        }),
        20_000,
      ),
    );
    const update = requestMutationMock.mock.calls.at(-1)?.[1];
    expect(JSON.parse(update.extraBody)).toEqual({ tools: [{ type: "web_search" }] });
  });
});
