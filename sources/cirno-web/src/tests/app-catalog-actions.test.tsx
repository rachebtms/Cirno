import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  deleteChatSpy,
  getSessionAutomationsSpy,
  setSidebarStateSpy,
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
import { describe, expect, it } from "vitest";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import App from "@/App";

describe("App catalog-actions", () => {
  installAppTestLifecycle();

  it("switches to the next session when deleting the active chat", async () => {
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

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^First chat$/ }),
      ).toBeInTheDocument(),
    );

    fireEvent.pointerDown(
      screen.getByLabelText("Conversation actions for First chat"),
      {
        button: 0,
      },
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));

    await waitFor(() =>
      expect(screen.getByText("Delete this conversation?")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(deleteChatSpy).toHaveBeenCalledWith("websocket:chat-a"),
    );
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^Second chat$/ }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByText("Delete this conversation?"),
    ).not.toBeInTheDocument();
    expect(document.body.style.pointerEvents).not.toBe("none");
  }, 15_000);

  it("archives selected conversations in one preference update while keeping the catalog active", async () => {
    appTest.sessions = ["a", "b", "c"].map((id) => ({
      key: `websocket:chat-${id}`,
      channel: "websocket",
      chatId: `chat-${id}`,
      createdAt: "2026-04-16T10:00:00Z",
      updatedAt: "2026-04-16T10:00:00Z",
      title: `Topic ${id}`,
      preview: `Message ${id}`,
    }));
    mockFetchRoutes({
      "/v0/webui/sidebar-state": {
        pinned_keys: ["websocket:chat-a", "websocket:chat-b"],
      },
    });
    window.history.replaceState(null, "", "/#/chat/websocket%3Achat-a");
    render(<App />);
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => statusHandlers.forEach((handler) => handler("open")));
    const sidebar = await openAppCatalog();
    await within(sidebar).findByRole("button", { name: "Topic a" });
    await waitFor(() =>
      expect(within(sidebar).queryByText("Loading…")).not.toBeInTheDocument(),
    );
    fireEvent.pointerDown(
      within(sidebar).getByLabelText("Conversation actions for Topic a"),
      { button: 0 },
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Select" }));
    fireEvent.click(within(sidebar).getByRole("button", { name: "Topic b" }));
    fireEvent.click(within(sidebar).getByRole("button", { name: "Archive" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Archive 2 conversations?",
    });
    expect(setSidebarStateSpy).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(setSidebarStateSpy).toHaveBeenCalledTimes(1));
    expect(setSidebarStateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        archived_keys: ["websocket:chat-a", "websocket:chat-b"],
        pinned_keys: [],
      }),
    );
    expect(screen.getByRole("tab", { name: "Conversations" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      within(sidebar).getByRole("button", { name: "Topic c" }),
    ).toBeInTheDocument();
    expect(
      within(sidebar).queryByRole("button", { name: "Topic a" }),
    ).not.toBeInTheDocument();
    expect(
      within(sidebar).queryByRole("button", { name: "Topic b" }),
    ).not.toBeInTheDocument();
    expect(deleteChatSpy).not.toHaveBeenCalled();
  });

  it("deletes multiple selected topics through one confirmation", async () => {
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
      {
        key: "websocket:chat-c",
        channel: "websocket",
        chatId: "chat-c",
        createdAt: "2026-04-16T12:00:00Z",
        updatedAt: "2026-04-16T12:00:00Z",
        preview: "Third chat",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    fireEvent.pointerDown(
      within(sidebar).getByLabelText("Conversation actions for First chat"),
      { button: 0 },
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Select" }));
    fireEvent.click(
      within(sidebar).getByRole("button", { name: "Second chat" }),
    );
    expect(within(sidebar).getByText("2 selected")).toBeInTheDocument();

    const automationReads: Array<(jobs: SessionAutomationJob[]) => void> = [];
    getSessionAutomationsSpy.mockImplementation(
      () => new Promise((resolve) => automationReads.push(resolve)),
    );
    fireEvent.click(within(sidebar).getByRole("button", { name: "Delete" }));
    fireEvent.click(document.body);
    expect(screen.getByTestId("delete-selection-bar")).toHaveTextContent(
      "2 selected",
    );
    expect(deleteChatSpy).not.toHaveBeenCalled();
    await act(async () => automationReads.forEach((resolve) => resolve([])));
    expect(
      await screen.findByText("Delete 2 conversations?"),
    ).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
    expect(screen.getByTestId("delete-selection-bar")).toHaveTextContent(
      "2 selected",
    );
    expect(deleteChatSpy).not.toHaveBeenCalled();

    getSessionAutomationsSpy.mockResolvedValue([]);
    fireEvent.click(within(sidebar).getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByText("Delete 2 conversations?"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      screen.queryByTestId("delete-selection-bar"),
    ).not.toBeInTheDocument();

    await waitFor(() => expect(deleteChatSpy).toHaveBeenCalledTimes(2));
    expect(deleteChatSpy.mock.calls.map(([key]) => key)).toEqual([
      "websocket:chat-a",
      "websocket:chat-b",
    ]);
    expect(getSessionAutomationsSpy).toHaveBeenCalledWith("websocket:chat-a");
    expect(getSessionAutomationsSpy).toHaveBeenCalledWith("websocket:chat-b");
    expect(
      within(sidebar).getByRole("button", { name: "Third chat" }),
    ).toBeInTheDocument();
  }, 15_000);

});
