import { appTest, connectSpy, deleteChatSpy, installAppTestLifecycle, statusHandlers } from "./helpers/app-harness";
import { openAppCatalog, openAppConversation } from "./helpers/app-navigation";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "@/App";

function setupTabs() {
  appTest.sessions = ["Alpha", "Beta", "Unrelated"].map(title => ({
    key: `websocket:${title.toLowerCase()}`, chatId: title.toLowerCase(), channel: "websocket", title,
    preview: "", createdAt: null, updatedAt: null,
  }));
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify(appTest.sessions.slice(0, 2).map(session => ({
    id: `chat:${session.key}`, type: "route", group: 0,
    route: { view: "chat", activeKey: session.key, settingsSection: "overview" },
  }))));
  window.history.replaceState(null, "", "/#/chat/websocket%3Abeta");
}

function editor(title: string) {
  return within(screen.getByRole("tabpanel", { name: title })).getByRole("textbox");
}

describe("App conversation tab lifetime", () => {
  installAppTestLifecycle();

  it("keeps both conversation drafts and their mounted editors through catalog and tab switching", async () => {
    setupTabs();
    render(<App />);
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => statusHandlers.forEach(handler => handler("open")));
    const beta = await within(await screen.findByRole("tabpanel", { name: "Beta" })).findByRole("textbox");
    fireEvent.change(beta, { target: { value: "Beta's unsent research" } });
    await openAppConversation("Alpha");
    const alpha = editor("Alpha");
    fireEvent.change(alpha, { target: { value: "Alpha's independent draft" } });
    await openAppCatalog();
    await openAppConversation("Beta");
    expect(editor("Beta")).toBe(beta);
    expect(beta).toHaveValue("Beta's unsent research");
    await openAppConversation("Alpha");
    expect(editor("Alpha")).toBe(alpha);
    expect(alpha).toHaveValue("Alpha's independent draft");
  });

  it("deletes a conversation from the catalog without stealing selection or discarding another tab's draft", async () => {
    setupTabs();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => statusHandlers.forEach(handler => handler("open")));
    await openAppConversation("Alpha");
    const alpha = editor("Alpha");
    fireEvent.change(alpha, { target: { value: "Keep this draft after Beta is deleted" } });
    await openAppConversation("Beta");
    const catalog = await openAppCatalog();
    await user.click(within(catalog).getByRole("button", { name: "Conversation actions for Beta" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const confirmation = await screen.findByRole("alertdialog", { name: "Delete this conversation?" });
    await user.click(within(confirmation).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteChatSpy).toHaveBeenCalledWith("websocket:beta"));
    await waitFor(() => expect(screen.queryByRole("tab", { name: "Beta" })).not.toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Conversations" })).toHaveAttribute("aria-selected", "true");
    await openAppConversation("Alpha");
    expect(editor("Alpha")).toBe(alpha);
    expect(alpha).toHaveValue("Keep this draft after Beta is deleted");
    expect(screen.queryByRole("tab", { name: "Unrelated" })).not.toBeInTheDocument();
  });
});
