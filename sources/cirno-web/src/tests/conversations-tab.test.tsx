import { conversation, renderCatalog as mount } from "./helpers/conversation-catalog";
import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";


describe("Conversations tab", () => {
  it("shows independent Projects and ordinary conversations without Cirno or utility navigation", async () => {
    const user = userEvent.setup();
    const catalog = mount();
    expect(screen.queryByText("Cirno")).not.toBeInTheDocument();
    expect(screen.queryByText("Automations")).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Research" }),
    ).toHaveTextContent("Review paper");
    await user.click(screen.getByRole("button", { name: "Review paper" }));
    expect(catalog.open).toHaveBeenCalledWith("websocket:worker");
    await user.click(
      screen.getByRole("button", { name: "New conversation in Research" }),
    );
    expect(catalog.create).toHaveBeenCalledWith(catalog.projects[0]);
    await user.click(screen.getByRole("button", { name: "Conversation actions for Review paper" }));
    const projects = screen.getByRole("menuitem", { name: "Projects" });
    projects.focus();
    await user.keyboard("{ArrowRight}");
    await user.click(await screen.findByRole("menuitemradio", { name: "Unfiled conversations" }));
    expect(catalog.assign).toHaveBeenCalledWith("websocket:worker", null);
  });

  it("searches titles and keeps failed project creation visible and editable", async () => {
    const user = userEvent.setup();
    mount({
      saveProject: vi.fn(async () => {
        throw new Error("Project storage unavailable");
      }),
    });
    await user.type(
      screen.getByRole("searchbox", {
        name: "Search conversations and projects",
      }),
      "Review",
    );
    expect(screen.getByRole("button", { name: "Review paper" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Investigate data/ }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New project" }));
    await user.type(
      screen.getByRole("textbox", { name: "Project name" }),
      "New research",
    );
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Project storage unavailable",
    );
    expect(screen.getByRole("textbox", { name: "Project name" })).toHaveValue(
      "New research",
    );
  });

  it("requires project deletion confirmation and explains preserved work", async () => {
    const user = userEvent.setup();
    const catalog = mount();
    await user.click(screen.getByRole("button", { name: "Project actions for Research" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(catalog.deleteProject).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(
      "Its conversations, history and files will be kept",
    );
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(catalog.deleteProject).toHaveBeenCalledWith("research");
  });

  it("reuses conversation actions and keeps a failed rename editable", async () => {
    const user = userEvent.setup();
    const catalog = mount({ rename: vi.fn().mockRejectedValueOnce(new Error("Disk full")).mockResolvedValue(undefined) });
    const menu = () => screen.getByRole("button", { name: "Conversation actions for Review paper" });
    await user.click(menu());
    await user.click(screen.getByRole("menuitem", { name: "Pin" }));
    expect(catalog.togglePin).toHaveBeenCalledWith("websocket:worker");
    await user.click(menu());
    await user.click(screen.getByRole("menuitem", { name: "Archive" }));
    expect(catalog.toggleArchive).toHaveBeenCalledWith("websocket:worker");
    await user.click(menu());
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
    const editor = screen.getByRole("textbox", { name: "Conversation name" });
    await user.clear(editor);
    await user.type(editor, "Updated research");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Disk full");
    expect(editor).toHaveValue("Updated research");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(catalog.rename).toHaveBeenLastCalledWith("websocket:worker", "Updated research");
    expect(screen.queryByRole("textbox", { name: "Conversation name" })).not.toBeInTheDocument();
    await user.click(menu());
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await vi.waitFor(() => expect(catalog.deleteConversation).toHaveBeenCalledWith("websocket:worker", "Review paper"));
  });

  it("shows preference save failures and offers retry without discarding the catalog", async () => {
    const user = userEvent.setup();
    const catalog = mount({ error: "Preferences are read-only", preferencesError: "Preferences are read-only", retryPreferences: vi.fn() });
    expect(screen.getByRole("alert")).toHaveTextContent("Preferences are read-only");
    expect(screen.getByRole("button", { name: "Review paper" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(catalog.retryPreferences).toHaveBeenCalledTimes(1);
  });

  it("shows canonical run and recovery state instead of stale session timestamps", () => {
    mount({ sessions: [
      { ...conversation("websocket:worker", ""), preview: "Inspect resource usage" },
      conversation("websocket:failed", "API interrupted"),
      { ...conversation("websocket:stale", "Finished work"), runStartedAt: 123 },
    ], activity: { "websocket:worker": "running", "websocket:failed": "recovery" } });
    expect(within(screen.getByRole("button", { name: "Inspect resource usage" })).getByRole("img", { name: "Agent running" })).toBeVisible();
    expect(within(screen.getByRole("button", { name: "API interrupted" })).getByRole("img", { name: "This conversation needs your attention" })).toBeVisible();
    expect(within(screen.getByRole("button", { name: "Finished work" })).queryByRole("img")).not.toBeInTheDocument();
  });

  it("selects across Projects and archives the selected conversations through one shared action", async () => {
    const user = userEvent.setup();
    const catalog = mount();
    await user.click(screen.getByRole("button", { name: "Conversation actions for Review paper" }));
    await user.click(screen.getByRole("menuitem", { name: "Select" }));
    await user.click(screen.getByRole("button", { name: "Investigate data" }));
    expect(catalog.open).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Review paper" })).toHaveAttribute("aria-pressed", "true");
    const bar = screen.getByTestId("delete-selection-bar");
    expect(bar).toHaveTextContent("2 selected");
    await user.click(within(bar).getByRole("button", { name: "Archive" }));
    expect(catalog.archiveMany).not.toHaveBeenCalled();
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Archive" }));
    expect(catalog.archiveMany).toHaveBeenCalledWith(["websocket:worker", "websocket:other"], true);
    expect(screen.queryByTestId("delete-selection-bar")).not.toBeInTheDocument();
  });

  it("keeps the batch after a cancelled delete confirmation and allows cancelling selection on mobile", async () => {
    const user = userEvent.setup();
    const catalog = mount();
    await user.click(screen.getByRole("button", { name: "Conversation actions for Review paper" }));
    await user.click(screen.getByRole("menuitem", { name: "Select" }));
    await user.click(screen.getByRole("button", { name: "Investigate data" }));
    const bar = screen.getByTestId("delete-selection-bar");
    await user.click(within(bar).getByRole("button", { name: "Delete" }));
    expect(catalog.deleteMany).toHaveBeenCalledWith([
      { key: "websocket:worker", label: "Review paper" },
      { key: "websocket:other", label: "Investigate data" },
    ], expect.any(Function));
    const decide = vi.mocked(catalog.deleteMany).mock.calls[0][1]!;
    expect(within(bar).getByRole("button", { name: "Delete" })).toBeDisabled();
    act(() => decide(false));
    expect(bar).toHaveTextContent("2 selected");
    await user.click(within(bar).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByTestId("delete-selection-bar")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review paper" })).not.toHaveAttribute("aria-pressed");
  });

  it("uses persisted sorting through the catalog owner", async () => {
    const user = userEvent.setup();
    const catalog = mount();
    await user.click(screen.getByRole("button", { name: "Sort conversations" }));
    expect(screen.getByRole("menuitemradio", { name: "Recently updated" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: "Title A–Z" }));
    expect(catalog.setSort).toHaveBeenCalledWith("title_asc");
  });
  it("selects a Shift range across the displayed Project boundary and hides row actions", async () => {
    const user = userEvent.setup();
    mount({ sessions: [
      conversation("websocket:first", "First", "research"),
      conversation("websocket:second", "Second", "research"),
      conversation("websocket:third", "Third"),
      conversation("websocket:fourth", "Fourth"),
    ] });
    await user.click(screen.getByRole("button", { name: "Conversation actions for Second" }));
    await user.click(screen.getByRole("menuitem", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Fourth" }), { shiftKey: true });
    expect(screen.getByTestId("delete-selection-bar")).toHaveTextContent("3 selected");
    expect(screen.getByRole("button", { name: "First" })).toHaveAttribute("aria-pressed", "false");
    for (const title of ["Second", "Third", "Fourth"]) {
      expect(screen.getByRole("button", { name: title })).toHaveAttribute("aria-pressed", "true");
    }
    expect(screen.queryByRole("button", { name: /Conversation actions for/ })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("delete-selection-bar")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conversation actions for Second" })).toBeVisible();
  });

  it("opens the actual conversation action menu on right-click without opening the conversation", async () => {
    const user = userEvent.setup();
    const catalog = mount();
    fireEvent.contextMenu(screen.getByRole("button", { name: "Review paper" }));
    await user.click(await screen.findByRole("menuitem", { name: "Pin" }));
    expect(catalog.togglePin).toHaveBeenCalledWith("websocket:worker");
    expect(catalog.open).not.toHaveBeenCalled();
  });

  it("keeps loading explicit without rendering fake conversations", () => {
    mount({ loading: true, sessions: [], projects: [] });
    expect(screen.getByRole("status")).toBeVisible();
    expect(screen.getByRole("region", { name: "Conversations" })).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("button", { name: /Conversation actions for/ })).not.toBeInTheDocument();
  });

});
