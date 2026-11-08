import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  installSettingsViewTestHooks,
  jsonResponse,
  renderSettingsView,
  requestMutationMock,
  settingsPayload,
} from "./settings-test-utils";

describe("independent provider balance settings", () => {
  installSettingsViewTestHooks();
  it("saves a separate endpoint and credential, queries only on refresh, and can disable it", async () => {
    const user = userEvent.setup();
    const payload = settingsPayload();
    payload.providers = [{ id: "deepseek", name: "DeepSeek", configured: true }];
    const configured = {
      ...payload,
      providers: [
        {
          ...payload.providers[0],
          balance: {
            endpoint: "https://billing.example/account",
            format: "json" as const,
            amount_path: "/data/balance",
            currency: "CNY",
            api_key: "••••••••",
          },
        },
      ],
    };
    requestMutationMock.mockResolvedValueOnce(configured).mockResolvedValueOnce(payload);
    renderSettingsView({ initialSettings: payload, initialSection: "providers" });
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("provider-balance")),
    ).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Account balance: DeepSeek" }));
    const dialog = screen.getByRole("dialog", { name: "Account balance" });
    fireEvent.click(within(dialog).getByRole("switch", { name: "Enable balance queries" }));
    expect(within(dialog).getByRole("textbox", { name: "Balance API URL" })).toHaveValue(
      "https://api.deepseek.com/user/balance",
    );
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Balance API URL" }), {
      target: { value: configured.providers[0].balance.endpoint },
    });
    await user.click(within(dialog).getByRole("button", { name: /Response format/ }));
    await user.click(screen.getByRole("option", { name: "Custom JSON" }));
    fireEvent.change(
      within(dialog).getByRole("textbox", { name: "Balance field (JSON pointer)" }),
      { target: { value: "/data/balance" } },
    );
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Currency / unit" }), {
      target: { value: "CNY" },
    });
    fireEvent.change(within(dialog).getByLabelText("Balance API key (optional)"), {
      target: { value: "billing-secret" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.provider.update",
      expect.objectContaining({
        provider: "deepseek",
        balance: { ...configured.providers[0].balance, api_key: "billing-secret" },
      }),
      20000,
    );
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        provider_id: "deepseek",
        status: "ok",
        balances: [{ amount: "21.50", currency: "CNY" }],
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh balance: DeepSeek" }));
    expect(await screen.findByText("21.50 CNY")).toBeInTheDocument();
    expect(fetch).toHaveBeenLastCalledWith(
      "/v0/settings/provider-balance?provider_id=deepseek",
      expect.objectContaining({ headers: { Authorization: "Bearer tok" } }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Account balance: DeepSeek" }));
    fireEvent.click(screen.getByRole("switch", { name: "Enable balance queries" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Refresh balance: DeepSeek" }),
      ).not.toBeInTheDocument(),
    );
    expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.provider.update",
      { provider: "deepseek", balance: null },
      20000,
    );
  });
});
