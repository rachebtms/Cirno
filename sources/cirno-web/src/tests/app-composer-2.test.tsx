import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  createChatSpy,
  toggleThemeSpy,
  requestMutationSpy,
  sendSystemCommandSpy,
  statusHandlers,
  HERO_GREETING_PATTERN,
  mockFetchRoutes,
  baseSettingsPayload,
} from "./helpers/app-harness";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "@/App";

describe("App composer", () => {
  installAppTestLifecycle();

  it.each(["before disconnect", "after disconnect"])(
    "finishes a requested restart when another tab clears its marker %s",
    async (clearWhen) => {
      appTest.defaultChatId = "restart-fixture";
      window.history.replaceState(null, "", "/#/settings?section=runtime");
      mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });
      render(<App />);
      fireEvent.click(await screen.findByRole("button", { name: "Restart" }));
      expect(sendSystemCommandSpy).toHaveBeenCalledWith(
        "restart-fixture",
        "/restart",
      );
      expect(
        screen.getByRole("button", { name: "Restarting..." }),
      ).toHaveAttribute("aria-disabled", "true");
      act(() => {
        if (clearWhen === "before disconnect")
          localStorage.removeItem("cirno-webui.restartStartedAt");
        for (const handler of statusHandlers) handler("reconnecting");
        localStorage.removeItem("cirno-webui.restartStartedAt");
        for (const handler of statusHandlers) handler("open");
      });
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Restart" })).toBeEnabled(),
      );
      expect(createChatSpy).not.toHaveBeenCalled();
    },
  );

  it("refreshes settings after the browser reconnects from a restart", async () => {
    let restartCompleted = false;
    let refreshedSettingsRequests = 0;
    let releaseRefreshedSettings!: () => void;
    const refreshedSettingsReady = new Promise<void>((resolve) => {
      releaseRefreshedSettings = resolve;
    });
    const pendingSettings = {
      ...baseSettingsPayload(),
      requires_restart: true,
      restart_required_sections: ["runtime"],
    };
    const refreshedSettings = {
      ...baseSettingsPayload(),
      requires_restart: false,
      restart_required_sections: [],
    };
    localStorage.setItem(
      "cirno-webui.restartStartedAt",
      String(Date.now() - 2_000),
    );
    window.history.replaceState(null, "", "/#/settings?section=runtime");
    mockFetchRoutes({
      "/v0/settings": () => {
        if (!restartCompleted) return pendingSettings;
        refreshedSettingsRequests += 1;
        if (refreshedSettingsRequests === 1)
          throw new Error("gateway is still starting");
        return refreshedSettingsReady.then(() => refreshedSettings);
      },
    });

    render(<App />);

    await waitFor(
      () => {
        expect(
          screen.getAllByText("Saved. Restart to apply changes.").length,
        ).toBeGreaterThan(0);
      },
      { timeout: 10_000 },
    );

    restartCompleted = true;
    act(() => {
      for (const handler of statusHandlers) handler("reconnecting");
      for (const handler of statusHandlers) handler("open");
    });

    await waitFor(() => expect(refreshedSettingsRequests).toBeGreaterThan(1));
    await act(async () => {
      releaseRefreshedSettings();
      await refreshedSettingsReady;
    });
    fireEvent.click(screen.getByRole("button", { name: "Back to chat" }));
    await waitFor(() => expect(window.location.hash).toBe("#/new"));
    expect(
      await screen.findByText(HERO_GREETING_PATTERN, {}, { timeout: 10_000 }),
    ).toBeInTheDocument();
  }, 30_000);

  it("keeps the backend timezone without writing settings on mount", async () => {
    const initialSettings = baseSettingsPayload();
    mockFetchRoutes({
      "/v0/settings": initialSettings,
    });
    window.history.replaceState(null, "", "/#/settings?section=runtime");

    render(<App />);

    expect(await screen.findByText("UTC")).toBeInTheDocument();
    expect(
      requestMutationSpy.mock.calls.some(
        ([action]) => action === "settings.agent.update",
      ),
    ).toBe(false);
    expect(
      screen.queryByRole("heading", { name: "Region and timezone" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Used for schedules and time-aware replies."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Search timezone"),
    ).not.toBeInTheDocument();
    const systemSection = screen
      .getByRole("heading", { name: "System" })
      .closest("section");
    expect(systemSection).not.toBeNull();
    const system = within(systemSection as HTMLElement);
    expect(system.getByText("Timezone")).toBeInTheDocument();
    expect(
      within(screen.getByRole("complementary")).getByRole("button", {
        name: "Restart",
      }),
    ).toBeInTheDocument();
    expect(
      system.queryByText("Restart cirno to apply runtime changes."),
    ).not.toBeInTheDocument();
  });

  it("opens a blank start page without creating an empty chat", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Existing chat",
      },
    ];

    const matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("1024px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    vi.stubGlobal("matchMedia", matchMedia);

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());

    fireEvent.click(
      await screen.findByRole("button", { name: "Toggle theme from header" }),
    );
    expect(toggleThemeSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole("button", { name: "Open New conversation" }),
    );
    expect(createChatSpy).not.toHaveBeenCalled();
    expect(screen.getByText(HERO_GREETING_PATTERN)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start a new topic" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Toggle theme from header" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Open Settings" }),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("tab", { name: "Existing chat" }),
    ).not.toBeInTheDocument();
  });
});
