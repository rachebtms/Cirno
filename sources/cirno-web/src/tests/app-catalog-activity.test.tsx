import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  attachSpy,
  runStatusHandlers,
  runState,
  sessionUpdateHandlers,
} from "./helpers/app-harness";
import {
  act,
  fireEvent,
  render,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "@/App";

describe("App catalog-activity", () => {
  installAppTestLifecycle();

  it("shows running and completed session indicators in the sidebar", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Working chat",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Quiet chat",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^Working chat$/ }),
      ).toBeInTheDocument(),
    );

    act(() => {
      for (const handler of runStatusHandlers)
        handler("chat-a", runState(12_345));
    });
    expect(
      within(sidebar).getByRole("img", { name: "Agent running" }),
    ).toBeInTheDocument();

    act(() => {
      for (const handler of runStatusHandlers)
        handler("chat-a", runState(null));
    });
    expect(
      within(sidebar).queryByRole("img", { name: "Agent running" }),
    ).not.toBeInTheDocument();
    expect(
      within(sidebar).getByRole("img", { name: "New activity" }),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(
        within(sidebar).getByRole("button", { name: /^Working chat$/ }),
      );
    });
    expect(
      within(sidebar).queryByRole("img", { name: "New activity" }),
    ).not.toBeInTheDocument();
  });

  it("does not show an updated dot later when the active session finishes", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Active work",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Other chat",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^Active work$/ }),
      ).toBeInTheDocument(),
    );

    await act(async () => {
      fireEvent.click(
        within(sidebar).getByRole("button", { name: /^Active work$/ }),
      );
    });
    await waitFor(() => expect(document.title).toContain("Active work"));

    act(() => {
      for (const handler of runStatusHandlers)
        handler("chat-a", runState(12_345));
    });

    act(() => {
      for (const handler of runStatusHandlers)
        handler("chat-a", runState(null));
    });
    expect(
      within(sidebar).queryByRole("img", { name: "Agent running" }),
    ).not.toBeInTheDocument();
    expect(
      within(sidebar).queryByRole("img", { name: "New activity" }),
    ).not.toBeInTheDocument();

    const currentCatalog = await openAppCatalog();
    expect(
      within(currentCatalog).queryByRole("img", { name: "New activity" }),
    ).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(
        within(currentCatalog).getByRole("button", { name: /^Other chat$/ }),
      );
    });
    const afterSwitch = await openAppCatalog();
    expect(
      within(afterSwitch).queryByRole("img", { name: "New activity" }),
    ).not.toBeInTheDocument();
  });

  it("marks inactive sessions when a thread update arrives", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Open chat",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Scheduled update target",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await act(async () => {
      fireEvent.click(
        within(sidebar).getByRole("button", { name: /^Open chat$/ }),
      );
    });

    act(() => {
      for (const handler of sessionUpdateHandlers) handler("chat-b", "thread");
    });

    const updatedCatalog = await openAppCatalog();
    expect(
      within(updatedCatalog).getByRole("img", { name: "New activity" }),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(
        within(updatedCatalog).getByRole("button", {
          name: /^Scheduled update target$/,
        }),
      );
    });

    const viewedCatalog = await openAppCatalog();
    expect(
      within(viewedCatalog).queryByRole("img", { name: "New activity" }),
    ).not.toBeInTheDocument();
  });

  it("restores sidebar runs from lifecycle replay without reviving them from stale session rows", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Running after reload",
        runStartedAt: 12_345,
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Completed after reload",
      },
    ];
    localStorage.setItem(
      "cirno-webui.sidebar.session-updates.v1",
      JSON.stringify(["chat-b"]),
    );

    const { rerender } = render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() => expect(attachSpy).toHaveBeenCalledWith("chat-a"));
    expect(
      within(sidebar).queryByRole("img", { name: "Agent running" }),
    ).not.toBeInTheDocument();
    act(() => {
      for (const handler of runStatusHandlers)
        handler("chat-a", runState(12_345));
    });
    expect(
      within(sidebar).getByRole("img", { name: "Agent running" }),
    ).toBeInTheDocument();
    expect(
      within(sidebar).getByRole("img", { name: "New activity" }),
    ).toBeInTheDocument();
    act(() => {
      for (const handler of runStatusHandlers)
        handler("chat-a", runState(null));
    });
    appTest.sessions = appTest.sessions.map((session) => ({ ...session }));
    rerender(<App />);
    expect(
      within(sidebar).queryByRole("img", { name: "Agent running" }),
    ).not.toBeInTheDocument();
  });
});
