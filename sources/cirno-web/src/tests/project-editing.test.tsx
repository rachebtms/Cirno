import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { catalogFixture } from "./helpers/conversation-catalog";
import { ConversationCatalogContext, type ConversationCatalog } from "@/features/conversations/catalog/context";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";

const view = (catalog: ConversationCatalog, active = true) => <ConversationCatalogContext.Provider value={catalog}><ConversationsPage active={active} /></ConversationCatalogContext.Provider>;

it("serializes repeated create submissions and ignores an old acknowledgement after instance replacement", async () => {
  let finish!: () => void;
  const save = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  const first = catalogFixture({ saveProject: save }), second = catalogFixture();
  const page = render(view(first)), user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "New project" }));
  const name = screen.getByRole("textbox", { name: /^Project name/ });
  await user.type(name, "First instance");
  act(() => { fireEvent.submit(name.closest("form")!); fireEvent.submit(name.closest("form")!); });
  expect(save).toHaveBeenCalledExactlyOnceWith({ name: "First instance", working_directory: "" });
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  page.rerender(view(second));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "New project" }));
  const next = screen.getByRole("textbox", { name: /^Project name/ });
  await user.type(next, "Second instance draft");
  await act(async () => finish());
  expect(next).toHaveValue("Second instance draft");
  expect(screen.getByRole("dialog", { name: "New project" })).toBeInTheDocument();
  expect(second.saveProject).not.toHaveBeenCalled();
});

it("keeps the opening draft through catalog refresh and submits stable project identity", async () => {
  const catalog = catalogFixture(), user = userEvent.setup();
  catalog.projects[0].working_directory = "/old";
  const page = render(view(catalog));
  await user.click(screen.getByRole("button", { name: "Project actions for Research" }));
  await user.click(screen.getByRole("menuitem", { name: "Rename" }));
  const name = screen.getByRole("textbox", { name: /^Project name/ });
  await user.clear(name); await user.type(name, "Local draft");
  const directory = screen.getByRole("textbox", { name: "Working directory (optional)" });
  await user.clear(directory); await user.type(directory, "/new");
  page.rerender(view({ ...catalog, projects: [{ ...catalog.projects[0], name: "Another device", working_directory: "/remote" }] }));
  expect(name).toHaveValue("Local draft"); expect(directory).toHaveValue("/new");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(catalog.saveProject).toHaveBeenCalledExactlyOnceWith({ id: "research", name: "Local draft", working_directory: "/new" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it.each(["project", "conversation"])("hides an inactive pane's %s editor without losing its draft", async kind => {
  const catalog = catalogFixture(), user = userEvent.setup(), page = render(view(catalog));
  if (kind === "project") await user.click(screen.getByRole("button", { name: "New project" }));
  else {
    await user.click(screen.getByRole("button", { name: "Conversation actions for Review paper" }));
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
  }
  const input = screen.getByRole("textbox", { name: kind === "project" ? /^Project name/ : /^Conversation name/ });
  await user.clear(input); await user.type(input, "Unsubmitted draft");
  page.rerender(view(catalog, false));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  page.rerender(view(catalog, true));
  expect(await screen.findByRole("textbox", { name: kind === "project" ? /^Project name/ : /^Conversation name/ })).toHaveValue("Unsubmitted draft");
  expect(catalog.saveProject).not.toHaveBeenCalled();
  expect(catalog.rename).not.toHaveBeenCalled();
});
