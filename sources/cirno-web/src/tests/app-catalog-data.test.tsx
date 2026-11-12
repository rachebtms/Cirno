import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  createChatSpy,
  setSidebarStateSpy,
  statusHandlers,
  sessionUpdateHandlers,
  jsonResponse,
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
import userEvent from "@testing-library/user-event";
import { useSessions } from "@/hooks/useSessions";
import { activateReloadCache, writeReloadCache } from "@/lib/reload-cache";
import type { ChatSummary } from "@/lib/contracts/conversations";
import App from "@/App";

describe("App catalog-data", () => {
  installAppTestLifecycle();

  it("retries a failed sidebar read before enabling edits without losing saved state", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Second chat",
      },
    ];
    const initialState = {
      schema_version: 2,
      pinned_keys: ["websocket:chat-b"],
      archived_keys: ["websocket:chat-a"],
      title_overrides: { "websocket:chat-b": "Roadmap" },
      tags_by_key: {},
      collapsed_groups: {},
      view: {
        density: "comfortable",
        show_archived: false,
        sort: "updated_desc",
      },
      updated_at: null,
    };
    let sidebarReads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string | URL | Request) => {
        const href = String(url);
        if (href === "/v0/webui/sidebar-state") {
          if (++sidebarReads === 1) throw new Error("Service restarting");
          return { ok: true, json: async () => initialState };
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => {
      statusHandlers.forEach((handler) => handler("open"));
    });
    const sidebar = await openAppCatalog();
    expect(await within(sidebar).findByRole("alert")).toBeInTheDocument();
    expect(setSidebarStateSpy).not.toHaveBeenCalled();
    await waitFor(
      () =>
        expect(
          within(sidebar).getByRole("button", { name: "Roadmap" }),
        ).toBeInTheDocument(),
      { timeout: 5_000 },
    );
    expect(
      within(sidebar).getByRole("button", { name: /^Roadmap$/ }),
    ).toBeInTheDocument();
    expect(
      within(sidebar).queryByRole("button", { name: /^First chat$/ }),
    ).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(within(sidebar).getByRole("button", { name: "Sort conversations" }));
    await user.click(screen.getByRole("menuitem", { name: "Show archived" }));
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: "First chat" }),
      ).toBeInTheDocument(),
    );
    expect(
      within(sidebar).getByRole("button", { name: /^First chat$/ }),
    ).toBeInTheDocument();
    expect(setSidebarStateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        pinned_keys: initialState.pinned_keys,
        archived_keys: initialState.archived_keys,
        title_overrides: initialState.title_overrides,
        view: expect.objectContaining({ show_archived: true }),
      }),
    );

    expect(
      within(sidebar).queryByRole("button", { name: "View" }),
    ).not.toBeInTheDocument();
  }, 10_000);

  it.each([false, true])(
    "preserves preferences and retained tabs after both reads fail with partial cache: %s",
    async (cached) => {
      const actual = await vi.importActual<
        typeof import("@/hooks/useSessions")
      >("@/hooks/useSessions");
      vi.mocked(useSessions).mockImplementation(actual.useSessions);
      const sessions: ChatSummary[] = ["a", "b"].map((id) => ({
        key: `websocket:chat-${id}`,
        channel: "websocket",
        chatId: `chat-${id}`,
        createdAt: null,
        updatedAt: null,
        preview: "",
      }));
      if (cached) {
        activateReloadCache("ws://test");
        writeReloadCache("sessions", sessions.slice(0, 1));
      }
      const saved = {
        schema_version: 2,
        pinned_keys: ["websocket:chat-b", "websocket:deleted"],
        archived_keys: ["websocket:deleted"],
        session_order: [
          "websocket:chat-a",
          "websocket:chat-b",
          "websocket:deleted",
        ],
        title_overrides: {
          "websocket:chat-a": "Saved A",
          "websocket:chat-b": "Saved B",
          "websocket:deleted": "Old topic",
        },
        project_name_overrides: {},
        tags_by_key: {
          "websocket:chat-b": ["important"],
          "websocket:deleted": ["old"],
        },
        collapsed_groups: {},
        view: {
          density: "comfortable",
          show_archived: false,
          sort: "updated_desc",
        },
        updated_at: null,
      };
      const retainedTabs = ["a", "b", "deleted"].map(id => ({
        id: `chat:websocket:chat-${id}`, type: "route", route: {
          view: "chat", activeKey: `websocket:chat-${id}`, settingsSection: "overview",
        },
      }));
      const tabsKey = "cirno-webui.workspace-tabs.v1";
      localStorage.setItem(tabsKey, JSON.stringify(retainedTabs));
      let sidebarReads = 0;
      let sessionsFail = true;
      let serverSessions = sessions;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          if (String(input) === "/v0/sessions") {
            return sessionsFail
              ? Response.json({}, { status: 503 })
              : jsonResponse({ sessions: serverSessions });
          }
          if (String(input) === "/v0/webui/sidebar-state") {
            return ++sidebarReads === 1
              ? Response.json({}, { status: 503 })
              : jsonResponse(saved);
          }
          return Response.json({}, { status: 404 });
        }),
      );

      const markersKey = "cirno-webui.sidebar.session-updates.v1";
      localStorage.setItem(markersKey, JSON.stringify(["chat-b", "deleted"]));
      render(<App />);
      await waitFor(() => expect(connectSpy).toHaveBeenCalled());
      act(() => statusHandlers.forEach((handler) => handler("open")));
      const sidebar = await openAppCatalog();
      expect(await within(sidebar).findByRole("alert")).toBeInTheDocument();
      await waitFor(() => expect(sidebarReads).toBe(2), { timeout: 5_000 });
      await act(async () => {});
      expect(setSidebarStateSpy).not.toHaveBeenCalled();
      expect(JSON.parse(localStorage.getItem(markersKey)!)).toEqual([
        "chat-b",
        "deleted",
      ]);

      expect(JSON.parse(localStorage.getItem(tabsKey)!)).toEqual(expect.arrayContaining(retainedTabs.map(tab => expect.objectContaining(tab))));

      // A successful full list can authorize removal; the failed read and cache cannot.
      sessionsFail = false;
      act(() => sessionUpdateHandlers.forEach((handler) => handler("chat-a")));
      await within(sidebar).findByRole("button", { name: "Saved A" });
      expect(
        await within(sidebar).findByRole("button", { name: "Saved B" }),
      ).toBeInTheDocument();
      await waitFor(() =>
        expect(setSidebarStateSpy).toHaveBeenLastCalledWith({
          ...saved,
          view: expect.objectContaining(saved.view),
          pinned_keys: ["websocket:chat-b"],
          archived_keys: [],
          session_order: ["websocket:chat-a", "websocket:chat-b"],
          title_overrides: {
            "websocket:chat-a": "Saved A",
            "websocket:chat-b": "Saved B",
          },
          tags_by_key: { "websocket:chat-b": ["important"] },

        }),
      );

      await waitFor(() => expect(JSON.parse(localStorage.getItem(markersKey)!)).toEqual(["chat-b"]));
      await waitFor(() => expect(JSON.parse(localStorage.getItem(tabsKey)!).some(
        (tab: { route?: { activeKey: string } }) => tab.route?.activeKey === "websocket:chat-deleted",
      )).toBe(false));
      serverSessions = [];
      act(() => sessionUpdateHandlers.forEach((handler) => handler("chat-a")));
      await waitFor(() =>
        expect(setSidebarStateSpy).toHaveBeenLastCalledWith({
          ...saved,
          view: expect.objectContaining(saved.view),
          pinned_keys: [],
          archived_keys: [],
          session_order: [],
          title_overrides: {},
          tags_by_key: {},
        }),
      );
      await waitFor(() => expect(JSON.parse(localStorage.getItem(markersKey)!)).toEqual([]));
    },
    10_000,
  );

  it("filters sessions in the centered search dialog", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-alpha",
        channel: "websocket",
        chatId: "chat-alpha",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        title: "Q2 roadmap",
        preview: "Project planning notes",
      },
      {
        key: "websocket:chat-beta",
        channel: "websocket",
        chatId: "chat-beta",
        createdAt: "2026-04-15T10:00:00Z",
        updatedAt: "2026-04-15T10:00:00Z",
        preview: "Travel ideas",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    expect(within(sidebar).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(
      within(sidebar).getByRole("button", {
        name: "Travel ideas",
        hidden: true,
      }),
    ).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const dialog = await screen.findByRole("dialog", { name: "Search" });
    expect(within(dialog).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(within(dialog).getByText("Travel ideas")).toBeInTheDocument();
    expect(within(dialog).queryByText("websocket")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("#1")).not.toBeInTheDocument();

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Search" }), {
      target: { value: "planning" },
    });

    expect(within(dialog).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(within(dialog).queryByText("Travel ideas")).not.toBeInTheDocument();
    expect(
      within(sidebar).getByRole("button", {
        name: "Travel ideas",
        hidden: true,
      }),
    ).toBeInTheDocument();

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Search" }), {
      target: { value: "road q2" },
    });

    expect(within(dialog).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(within(dialog).queryByText("Travel ideas")).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: /Q2 roadmap/ }));

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Search" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("opens search from the keyboard shortcut", async () => {
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

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: "k", metaKey: true });

    const dialog = await screen.findByRole("dialog", { name: "Search" });
    expect(
      within(dialog).queryByText("Global actions"),
    ).not.toBeInTheDocument();
    expect(within(dialog).getByText("Existing chat")).toBeInTheDocument();

    const textbox = within(dialog).getByRole("textbox", { name: "Search" });
    fireEvent.change(textbox, { target: { value: "missing" } });
    expect(within(dialog).queryByText("Existing chat")).not.toBeInTheDocument();

    fireEvent.change(textbox, { target: { value: "existing" } });
    expect(within(dialog).getByText("Existing chat")).toBeInTheDocument();

    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Search" }),
      ).not.toBeInTheDocument(),
    );
    expect(createChatSpy).not.toHaveBeenCalled();
  });

  it("closes search when starting a new chat from the keyboard shortcut", async () => {
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

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(
      await screen.findByRole("dialog", { name: "Search" }),
    ).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "O", shiftKey: true, metaKey: true });

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Search" }),
      ).not.toBeInTheDocument(),
    );
    expect(window.location.hash).toBe("#/new");
  });

  it("pages the catalog while search still covers conversations outside the displayed page", async () => {
    appTest.sessions = Array.from({ length: 170 }, (_, index) => {
      const chatId = `chat-${index}`;
      return {
        key: `websocket:${chatId}`,
        channel: "websocket" as const,
        chatId,
        createdAt: new Date(Date.UTC(2026, 3, 16, 12, 0 - index)).toISOString(),
        updatedAt: new Date(Date.UTC(2026, 3, 16, 12, 0 - index)).toISOString(),
        title: index === 169 ? "Hidden target" : `Bulk chat ${index}`,
        preview: "",
      };
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: "Bulk chat 0" }),
      ).toBeInTheDocument(),
    );
    expect(
      within(sidebar).queryByText("Hidden target"),
    ).not.toBeInTheDocument();
    expect(
      within(sidebar).getByRole("button", { name: "Show more" }),
    ).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const dialog = await screen.findByRole("dialog", { name: "Search" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Search" }), {
      target: { value: "hidden" },
    });
    expect(within(dialog).getByText("Hidden target")).toBeInTheDocument();
  });

  it("opens the conversation library from the Settings launcher", async () => {
    mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });
    window.history.replaceState(null, "", "/#/settings");
    render(<App />);
    await screen.findByRole("navigation", { name: "Settings sections" });
    expect(await openAppCatalog()).toBeVisible();
    expect(screen.getByRole("tab", { name: "Conversations" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(window.location.hash).toBe("#/settings");
    fireEvent.click(screen.getByRole("tab", { name: "Settings" }));
    expect(
      await screen.findByRole("navigation", { name: "Settings sections" }),
    ).toBeVisible();
  });
});
