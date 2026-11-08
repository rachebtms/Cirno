import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  setSidebarStateSpy,
  sendMessageSpy,
  statusHandlers,
  mockFetchRoutes,
} from "./helpers/app-harness";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SidebarStatePayload } from "@/lib/contracts/conversation-preferences";
import App from "@/App";
import { mockBrowserFocus } from "./browser-focus";

describe("App catalog-names", () => {
  installAppTestLifecycle();

  it("renames from the mobile catalog and reloads the saved title", async () => {
    appTest.restoreBrowserFocus = mockBrowserFocus();
    const user = userEvent.setup();
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: null,
        updatedAt: null,
        title: "Existing chat",
        preview: "",
      },
    ];
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: !query.includes("1024px"),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    const persisted: { state?: SidebarStatePayload } = {};
    mockFetchRoutes({ "/v0/webui/sidebar-state": () => persisted.state ?? {} });
    setSidebarStateSpy.mockImplementation(
      async (state: SidebarStatePayload) => {
        persisted.state = state;
        return state;
      },
    );
    const firstRender = render(<App />);
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => statusHandlers.forEach((handler) => handler("open")));
    const route = window.location.hash;
    const sheet = await openAppCatalog();
    const startRename = async () => {
      await user.click(
        within(sheet).getByRole("button", {
          name: "Conversation actions for Existing chat",
        }),
      );
      await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
      return screen.findByRole("textbox", { name: "Conversation name" });
    };
    const firstInput = await startRename();
    expect(screen.getByRole("dialog", { name: "Rename" })).toBeVisible();
    fireEvent.compositionStart(firstInput);
    fireEvent.keyDown(firstInput, { key: "Escape" });
    expect(firstInput).toBeInTheDocument();
    expect(sheet).toBeInTheDocument();
    fireEvent.compositionEnd(firstInput);
    fireEvent.keyDown(firstInput, { key: "Escape" });
    expect(
      within(sheet).queryByRole("textbox", { name: "Conversation name" }),
    ).not.toBeInTheDocument();
    expect(sheet).toBeInTheDocument();

    const input = await startRename();
    await user.clear(input);
    await user.type(input, "Renamed topic");
    setSidebarStateSpy.mockRejectedValueOnce(new Error("Disk full"));
    await user.keyboard("{Enter}");
    expect(
      await within(input.closest("form")!).findByRole("alert"),
    ).toHaveTextContent("Disk full");
    expect(input).toHaveValue("Renamed topic");
    expect(
      persisted.state?.title_overrides["websocket:chat-a"],
    ).toBeUndefined();
    await user.keyboard("{Enter}");
    expect(
      await within(sheet).findByRole("button", { name: "Renamed topic" }),
    ).toBeInTheDocument();
    expect(persisted.state?.title_overrides["websocket:chat-a"]).toBe(
      "Renamed topic",
    );
    expect(window.location.hash).toBe(route);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    firstRender.unmount();
    render(<App />);
    const restored = await openAppCatalog();
    expect(
      await within(restored).findByRole("button", { name: "Renamed topic" }),
    ).toBeInTheDocument();
  });

  it.each([false, true])(
    "uses renamed titles in mentions across reloads with retained tabs=%s",
    async (split) => {
      appTest.restoreBrowserFocus = mockBrowserFocus();
      const user = userEvent.setup();
      const target: ChatSummary = {
        key: "websocket:target",
        channel: "websocket",
        chatId: "target",
        createdAt: null,
        updatedAt: null,
        title: "Generated title",
        preview: "Original question",
        handle: { id: "handle_0123456789abcdef0123456789abcdef", name: "gane" },
      };
      appTest.sessions = [
        {
          ...target,
          key: "websocket:source",
          chatId: "source",
          title: "Source",
          handle: undefined,
        },
        {
          ...target,
          key: "websocket:second",
          chatId: "second",
          title: "Second",
          handle: undefined,
        },
        target,
      ];
      window.history.replaceState(
        null,
        "",
        split ? "/#/chat/websocket%3Asource" : "/#/new",
      );
      let persisted: Partial<SidebarStatePayload> = {};
      if (split) localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify(
        ["source", "second"].map((key, group) => ({ id: `chat:websocket:${key}`, type: "route", group,
          route: { view: "chat", activeKey: `websocket:${key}`, settingsSection: "overview" } })),
      ));
      mockFetchRoutes({ "/v0/webui/sidebar-state": () => persisted });
      setSidebarStateSpy.mockImplementation(
        async (state: SidebarStatePayload) => {
          persisted = state;
          return state;
        },
      );
      const firstRender = render(<App />);
      await act(async () => {
        await import("@/components/thread/ThreadShell");
      });
      await waitFor(() => expect(connectSpy).toHaveBeenCalled());
      act(() => statusHandlers.forEach((handler) => handler("open")));
      const sidebar = await openAppCatalog();
      await user.click(
        await within(sidebar).findByRole("button", {
          name: "Conversation actions for Generated title",
        }),
      );
      await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
      const name = screen.getByRole("textbox", { name: "Conversation name" });
      await user.clear(name);
      await user.type(name, "会话编辑{Enter}");
      await within(sidebar).findByText("会话编辑");
      expect(persisted.title_overrides?.[target.key]).toBe("会话编辑");

      fireEvent.click(
        screen.getByRole("tab", {
          name: split ? "Source" : "New conversation",
        }),
      );
      const input = await within(screen.getByRole("tabpanel", { name: split ? "Source" : "New conversation" })).findByRole("textbox");
      fireEvent.change(input, { target: { value: "@", selectionStart: 1 } });
      expect(screen.getByRole("option", { name: /@gane/ })).toHaveTextContent(
        "会话编辑",
      );
      fireEvent.change(input, {
        target: { value: "@会话", selectionStart: 3 },
      });
      expect(screen.getByRole("option", { name: /@gane/ })).toHaveTextContent(
        "会话编辑",
      );
      fireEvent.keyDown(input, { key: "Tab" });
      fireEvent.keyDown(input, { key: "Escape" });
      expect(input).toHaveValue("@gane ");
      expect(
        screen.getByTestId("composer-session-mention-gane"),
      ).toHaveAttribute("title", "Session: 会话编辑");
      fireEvent.keyDown(input, { key: "Enter" });
      await waitFor(() => expect(sendMessageSpy).toHaveBeenCalled());
      expect(sendMessageSpy.mock.calls.at(-1)?.[3]?.sessionMentions).toEqual([
        {
          id: target.handle?.id,
          name: "gane",
          session_key: target.key,
          title: "会话编辑",
        },
      ]);

      firstRender.unmount();
      render(<App />);
      await act(async () =>
        statusHandlers.forEach((handler) => handler("open")),
      );
      if (!split) await user.click(screen.getByRole("button", { name: "Open New conversation" }));
      const restoredInput = split
        ? within(await screen.findByRole("tabpanel", { name: "Source" })).getByRole("textbox")
        : await screen.findByRole("textbox", { name: "Message input" });
      fireEvent.focus(restoredInput);
      fireEvent.change(restoredInput, {
        target: { value: "@gane", selectionStart: 5 },
      });
      expect(
        await screen.findByRole("option", { name: /@gane/ }),
      ).toHaveTextContent("会话编辑");
    },
  );

  it("searches the full preview of a session without a custom title", async () => {
    appTest.restoreBrowserFocus = mockBrowserFocus();
    const preview = `Review notes ${"alpha ".repeat(10)}orangeunique`;
    appTest.sessions = [
      {
        key: "websocket:target",
        channel: "websocket",
        chatId: "target",
        createdAt: null,
        updatedAt: null,
        title: "",
        preview,
        handle: { id: "handle_0123456789abcdef0123456789abcdef", name: "gane" },
      },
    ];
    window.history.replaceState(null, "", "/#/new");
    render(<App />);
    await act(async () => {
      await import("@/components/thread/ThreadShell");
    });
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => statusHandlers.forEach((handler) => handler("open")));
    const input = screen.getByRole("textbox", { name: /^Message / });
    fireEvent.change(input, {
      target: { value: "@orangeunique", selectionStart: 13 },
    });
    expect(screen.getByRole("option", { name: /@gane/ })).toHaveTextContent(
      "orangeunique",
    );
  });

  it("sorts chats by displayed title when A-Z is persisted", async () => {
    appTest.sessions = [
      {
        key: "websocket:zulu",
        channel: "websocket",
        chatId: "zulu",
        createdAt: "2026-04-16T12:00:00Z",
        updatedAt: "2026-04-16T12:00:00Z",
        title: "Zulu work",
        preview: "later",
      },
      {
        key: "websocket:new",
        channel: "websocket",
        chatId: "new",
        createdAt: "2026-04-15T12:00:00Z",
        updatedAt: "2026-04-15T12:00:00Z",
        preview: "hi cirno",
      },
      {
        key: "websocket:alpha",
        channel: "websocket",
        chatId: "alpha",
        createdAt: "2026-04-14T12:00:00Z",
        updatedAt: "2026-04-14T12:00:00Z",
        title: "Alpha plan",
        preview: "earlier",
      },
    ];
    const initialState = {
      schema_version: 1,
      pinned_keys: [],
      archived_keys: [],
      title_overrides: {},
      tags_by_key: {},
      collapsed_groups: {},
      view: {
        density: "comfortable",
        show_archived: false,
        sort: "title_asc",
      },
      updated_at: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string | URL | Request) => {
        const href = String(url);
        if (href === "/v0/webui/sidebar-state") {
          return { ok: true, json: async () => initialState };
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() =>
      expect(within(sidebar).getByText("Conversations")).toBeInTheDocument(),
    );
    const group = within(sidebar)
      .getByRole("heading", { name: "Unfiled conversations" })
      .closest("section");
    const labels = Array.from(group!.querySelectorAll("[data-chat-row]")).map(
      (row) => row.querySelector("button")?.getAttribute("aria-label"),
    );

    expect(labels).toEqual(["Alpha plan", "New conversation", "Zulu work"]);
  });
});
