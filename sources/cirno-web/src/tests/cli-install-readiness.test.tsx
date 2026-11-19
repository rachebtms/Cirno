import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { appsReady } from "@/features/settings/apps/model/catalog";
import type { CliAppInfo } from "@/lib/contracts/apps";
import {
  installSettingsViewTestHooks, jsonResponse, renderSettingsView,
  requestMutationMock, settingsPayload,
} from "@/tests/settings-test-utils";

const app: CliAppInfo = {
  name: "research", display_name: "Research CLI", category: "research", description: "Research tools",
  requires: "", source: "local", entry_point: "research-cli", install_supported: true,
  installed: true, available: false, status: "missing", skill_installed: true,
};

describe("CLI installation readiness", () => {
  installSettingsViewTestHooks();

  it("keeps installed but unavailable commands out of the ready filter", () => {
    expect(appsReady({ id: "cli:research", kind: "cli", app })).toBe(false);
    expect(appsReady({ id: "cli:research", kind: "cli", app: { ...app, available: true } })).toBe(true);
  });

  it("shows verification failure as an error rather than a ready panel", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/settings/cli-apps") return jsonResponse({
        apps: [{ ...app, installed: false, status: "not_installed" }], installed_count: 0,
      });
      if (url === "/v0/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      return jsonResponse({});
    }));
    requestMutationMock.mockResolvedValue({
      apps: [app], installed_count: 1,
      last_action: { ok: false, message: "research-cli is still missing; installation record retained", installed: true },
    });
    renderSettingsView();
    const card = await screen.findByRole("article", { name: "Research CLI" });
    fireEvent.click(within(card).getByRole("button", { name: /Install/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("research-cli is still missing");
    expect(screen.queryByText("@research · research-cli")).not.toBeInTheDocument();
  });

  it("reports a retained installation after failed removal as an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/settings/cli-apps") return jsonResponse({ apps: [{ ...app, available: true }], installed_count: 1 });
      if (url === "/v0/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      return jsonResponse({});
    }));
    requestMutationMock.mockResolvedValue({
      apps: [{ ...app, available: true }], installed_count: 1,
      last_action: { ok: false, message: "Executable remains; installation retained", removed: false },
    });
    renderSettingsView();
    const card = await screen.findByRole("article", { name: "Research CLI" });
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "More actions: Research CLI" }));
    await user.click(await screen.findByRole("menuitem", { name: "Uninstall app" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Executable remains; installation retained");
    expect(screen.getByRole("article", { name: "Research CLI" })).toBeInTheDocument();
  });

  it("disables other CLI management controls until the current action settles", async () => {
    let finish!: (payload: unknown) => void;
    requestMutationMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const second = { ...app, name: "second", display_name: "Second CLI", installed: false };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/settings/cli-apps") return jsonResponse({ apps: [{ ...app, installed: false }, second], installed_count: 0 });
      if (url === "/v0/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      return jsonResponse({});
    }));
    renderSettingsView();
    const firstCard = await screen.findByRole("article", { name: "Research CLI" });
    const secondCard = screen.getByRole("article", { name: "Second CLI" });
    fireEvent.click(within(firstCard).getByRole("button", { name: /Install/ }));
    const otherInstall = within(secondCard).getByRole("button", { name: /Install/ });
    expect(otherInstall).toBeDisabled();
    fireEvent.click(otherInstall);
    expect(requestMutationMock).toHaveBeenCalledTimes(1);
    await act(async () => { finish({ apps: [{ ...app, available: true }, second], installed_count: 1 }); });
    expect(otherInstall).toBeEnabled();
  });
});
