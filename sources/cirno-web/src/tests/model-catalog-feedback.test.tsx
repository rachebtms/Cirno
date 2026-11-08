import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ModelCatalogField } from "@/features/settings/models/ui/ModelCatalogField";
import type { ProviderModelsPayload } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { installSettingsViewTestHooks, jsonResponse } from "@/tests/settings-test-utils";

type Provider = SettingsPayload["providers"][number];
const provider = (): Provider => ({
  id: "openai_codex",
  name: "OpenAI Codex",
  configured: true,
  auth_type: "oauth",
  model_catalog: "hybrid",
  oauth_login_supported: true,
});
const catalog = (
  source: ProviderModelsPayload["source"] = "remote",
  error_kind?: ProviderModelsPayload["error_kind"],
): ProviderModelsPayload => ({
  provider: "openai_codex",
  label: "OpenAI Codex",
  status: "available",
  catalog_kind: "hybrid",
  source,
  error_kind,
  models: [{ id: "offline-model", label: "Offline model", context_window: 100000 }],
  model_count: 1,
  message: error_kind ? "upstream response details" : null,
});
function Field({
  row,
  onChange = () => {},
  login,
}: {
  row: Provider;
  onChange?: (id: string) => void;
  login?: (id: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <ModelCatalogField
      token="catalog-feedback"
      provider={row}
      value={value}
      onSignIn={login}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}
const open = () =>
  userEvent.setup().click(screen.getByRole("button", { name: "Show suggestions Model" }));

describe("native model catalog feedback", () => {
  installSettingsViewTestHooks();
  it.each(["stale", "fallback"] as const)(
    "hides %s models after expired authorization and offers a working sign-in action",
    async (source) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => jsonResponse(catalog(source, "auth_required"))),
      );
      const change = vi.fn(),
        login = vi.fn();
      render(<Field row={provider()} onChange={change} login={login} />);
      await open();
      expect(await screen.findByRole("alert")).toHaveTextContent("Authorization expired");
      expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
      expect(screen.queryByRole("option")).not.toBeInTheDocument();
      expect(screen.queryByText("upstream response details")).not.toBeInTheDocument();
      await userEvent.setup().click(screen.getByRole("button", { name: "Sign in again" }));
      expect(login).toHaveBeenCalledWith("openai_codex");
      expect(change).not.toHaveBeenCalled();
    },
  );

  it.each(["stale", "fallback"] as const)(
    "keeps the %s list selectable with an explicit notice and retriable error details",
    async (source) => {
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(catalog(source, "unavailable")))
        .mockResolvedValueOnce(jsonResponse(catalog()));
      vi.stubGlobal("fetch", fetch);
      const change = vi.fn();
      render(<Field row={provider()} onChange={change} />);
      await open();
      expect(await screen.findByRole("alert")).toHaveTextContent(
        source === "stale" ? "Cached list" : "Built-in list",
      );
      expect(screen.getByRole("option", { name: /Offline model/ })).toBeVisible();
      await userEvent.setup().click(screen.getByRole("button", { name: "Error details" }));
      expect(await screen.findByText("upstream response details")).toBeVisible();
      await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
      await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
      expect(String(fetch.mock.calls[1][0])).toContain("refresh=1");
      await userEvent.setup().click(screen.getByRole("option", { name: /Offline model/ }));
      expect(change).toHaveBeenLastCalledWith("offline-model");
    },
  );

  it("shows rejected request details and recovers without losing a custom model draft", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("Network connection interrupted"))
      .mockResolvedValueOnce(jsonResponse(catalog()));
    vi.stubGlobal("fetch", fetch);
    render(<Field row={provider()} />);
    await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh failed");
    await userEvent.setup().click(screen.getByRole("button", { name: "Error details" }));
    expect(await screen.findByText("Network connection interrupted")).toBeVisible();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("option", { name: /Offline model/ });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "custom-model" } });
    expect(screen.getByRole("combobox")).toHaveValue("custom-model");
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(screen.getByRole("combobox")).toHaveValue("custom-model");
  });

  it("retains a good catalog during a failed refresh and exposes the new failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(catalog()))
        .mockResolvedValueOnce(
          jsonResponse({
            ...catalog(),
            status: "error",
            models: [],
            error_kind: "unavailable",
            message: "Provider timed out",
          }),
        ),
    );
    render(<Field row={provider()} />);
    await open();
    await screen.findByRole("option", { name: /Offline model/ });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
    await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh failed");
    expect(screen.getByRole("option", { name: /Offline model/ })).toBeVisible();
    await userEvent.setup().click(screen.getByRole("button", { name: "Error details" }));
    expect(await screen.findByText("Provider timed out")).toBeVisible();
  });

  it("clears rejected authorization when another provider or a fresh login replaces the provider revision", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(catalog("fallback", "auth_required")))
      .mockResolvedValueOnce(jsonResponse(catalog()))
      .mockResolvedValueOnce(jsonResponse(catalog()));
    vi.stubGlobal("fetch", fetch);
    const view = render(<Field row={provider()} />);
    await open();
    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Sign in again" })).not.toBeInTheDocument();
    view.rerender(<Field row={{ ...provider(), id: "other" }} />);
    await open();
    await screen.findByRole("option", { name: /Offline model/ });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    view.rerender(<Field row={provider()} />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("combobox")).toBeVisible();
  });

  it("ignores an old authorization response that arrives after a new login", async () => {
    let finish!: (response: Response) => void;
    const fetch = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValueOnce(jsonResponse(catalog()));
    vi.stubGlobal("fetch", fetch);
    const view = render(<Field row={provider()} />);
    await open();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    view.rerender(<Field row={provider()} />);
    await screen.findByRole("option", { name: /Offline model/ });
    await act(async () => finish(jsonResponse(catalog("stale", "auth_required"))));
    expect(screen.getByRole("option", { name: /Offline model/ })).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("loads a large catalog only after a search term and keeps manual-only providers editable", async () => {
    const fetch = vi.fn(async () => jsonResponse(catalog()));
    vi.stubGlobal("fetch", fetch);
    const row = { ...provider(), id: "openrouter", auth_type: "api_key" as const };
    const view = render(<Field row={row} />);
    await open();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "of" } });
    await screen.findByRole("option", { name: /Offline model/ });
    view.rerender(<Field row={{ ...row, id: "manual", model_catalog: "unsupported" }} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "custom-id" } });
    expect(screen.getByRole("combobox")).toHaveValue("custom-id");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
