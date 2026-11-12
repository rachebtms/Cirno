import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { requestMutationMock, jsonResponse, settingsPayload, renderSettingsView, installSettingsViewTestHooks } from "@/tests/settings-test-utils";

describe("Settings navigation lifecycle", () => {
  installSettingsViewTestHooks();

  it("exposes the memory context and scanning budgets in the actual library page", async () => {
    renderSettingsView({ initialSection: "memory", initialSettings: { ...settingsPayload(), runtime_config: {
      "agents.defaults.memory.context_tokens": 2000, "agents.defaults.memory.index_scan_batch": 100,
    } } });
    expect(screen.getByRole("spinbutton", { name: "Shared memory budget (tokens)" })).toHaveValue(2000);
    const batch = screen.getByRole("spinbutton", { name: "Index scan batch" });
    fireEvent.change(batch, { target: { value: "250" } });
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith("settings.runtime_config.update", {
      values: { "agents.defaults.memory.index_scan_batch": 250 },
    }, 20_000));
  });

  it("asks before leaving with pending changes and lets the user restart later", () => {
    const leave = vi.fn();
    const view = renderSettingsView({ initialSection: "runtime", initialSettings: {
      ...settingsPayload(), requires_restart: true, restart_required_sections: ["runtime"],
    }, onBackToChat: leave });
    act(() => view.requestExit(leave));
    const dialog = screen.getByRole("dialog", { name: "Restart before leaving?" });
    expect(leave).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Your changes are saved. Restart to apply them.")).toBeVisible();
    expect(within(dialog).getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Restart later", "Restart",
    ]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Restart later" }));
    expect(leave).toHaveBeenCalledTimes(1);
    expect(requestMutationMock).not.toHaveBeenCalled();
  });

  it("restarts from the exit prompt", () => {
    const restart = vi.fn();
    const view = renderSettingsView({ initialSection: "runtime", initialSettings: {
      ...settingsPayload(), requires_restart: true,
    }, onRestart: restart });
    act(() => view.requestExit(() => {}));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Restart" }));
    expect(restart).toHaveBeenCalledTimes(1);
  });

  it("leaves directly when no restart is pending", () => {
    const leave = vi.fn();
    const view = renderSettingsView({ initialSection: "runtime", initialSettings: settingsPayload(), onBackToChat: leave });
    act(() => view.requestExit(leave));
    expect(leave).toHaveBeenCalledTimes(1);
  });

  it("keeps one restart action and pending notice in the sidebar across settings pages", async () => {
    renderSettingsView({
      initialSection: "runtime",
      initialSettings: {
        ...settingsPayload(),
        requires_restart: true,
        restart_required_sections: ["runtime", "image"],
      },
    });
    const sidebar = screen.getByRole("complementary");
    const restart = within(sidebar).getByRole("button", { name: "Restart" });
    for (const section of ["Web search", "Models", "Permissions", "Server"]) {
      fireEvent.click(within(sidebar).getByRole("button", { name: section }));
      await waitFor(() => {
        expect(screen.getAllByRole("button", { name: "Restart" })).toEqual([restart]);
        expect(screen.getAllByText("Saved. Restart to apply changes.")).toHaveLength(1);
        expect(within(sidebar).getByText("Saved. Restart to apply changes.")).toBeVisible();
      });
    }
  });

  it.each([
    ["skills", "Loading skills…"],
    ["apps", "Loading apps…"],
    ["channels", "Loading channels…"],
    ["automations", "Loading automations..."],
  ] as const)("keeps the %s loading surface mounted when the settings snapshot arrives", async (initialSection, label) => {
    let resolveSettings!: (value: Response) => void;
    const pendingSettings = new Promise<Response>((resolve) => { resolveSettings = resolve; });
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input) === "/v0/settings"
      ? pendingSettings : new Promise<Response>(() => {})));
    renderSettingsView({ initialSection, initialSettings: null, skillsLoading: true, showSidebar: false });
    const skeleton = screen.getByRole("status", { name: label });
    expect(skeleton).toHaveAttribute("aria-busy", "true");
    await act(async () => { resolveSettings(jsonResponse(settingsPayload())); });
    expect(screen.getByRole("status", { name: label })).toBe(skeleton);
  });



  it.each(["apps", "skills", "automations", "channels"] as const)(
    "keeps the standalone %s semantic heading inside its own tab",
    (initialSection) => {
      renderSettingsView({ initialSection, initialSettings: settingsPayload(), showSidebar: false });
      const page = screen.getByTestId("settings-section-transition");
      const heading = within(page).getByRole("heading", { level: 1 });
      expect(heading).toBeVisible();
    },
  );
});
