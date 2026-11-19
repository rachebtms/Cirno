import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ConversationCatalogContext, type ConversationCatalog } from "@/features/conversations/catalog/context";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";
import { catalogFixture } from "./helpers/conversation-catalog";

function view(catalog: ConversationCatalog) {
  return <ConversationCatalogContext.Provider value={catalog}><ConversationsPage /></ConversationCatalogContext.Provider>;
}

async function selectWorker(user: ReturnType<typeof userEvent.setup>) {
  fireEvent.contextMenu(screen.getByRole("button", { name: "Review paper" }));
  await user.click(await screen.findByRole("menuitem", { name: "Select" }));
  return screen.getByTestId("delete-selection-bar");
}

it("drops an old connection's batch archive confirmation even when session IDs match", async () => {
  const user = userEvent.setup();
  const first = catalogFixture(), next = catalogFixture();
  const mounted = render(view(first));
  const toolbar = await selectWorker(user);
  await user.click(within(toolbar).getByRole("button", { name: "Archive" }));
  expect(screen.getByRole("alertdialog")).toBeVisible();
  mounted.rerender(view(next));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.queryByTestId("delete-selection-bar")).not.toBeInTheDocument();
  expect(first.archiveMany).not.toHaveBeenCalled();
  expect(next.archiveMany).not.toHaveBeenCalled();
});

it.each([false, true])("ignores a former connection's delete decision after a new selection (return owner: %s)", async (returnOwner) => {
  const user = userEvent.setup();
  const first = catalogFixture();
  const mounted = render(view(first));
  const toolbar = await selectWorker(user);
  await user.click(within(toolbar).getByRole("button", { name: "Delete" }));
  const decide = vi.mocked(first.deleteMany).mock.calls[0][1]!;
  const next = catalogFixture();
  mounted.rerender(view(next));
  if (returnOwner) mounted.rerender(view(first));
  expect(screen.queryByTestId("delete-selection-bar")).not.toBeInTheDocument();
  await selectWorker(user);
  act(() => decide(true));
  expect(screen.getByTestId("delete-selection-bar")).toHaveTextContent("1 selected");
  expect(screen.getByRole("button", { name: "Review paper" })).toHaveAttribute("aria-pressed", "true");
});

it("preserves a current connection's selection across a catalog refresh", async () => {
  const user = userEvent.setup();
  const catalog = catalogFixture();
  const mounted = render(view(catalog));
  await selectWorker(user);
  mounted.rerender(view({ ...catalog, sessions: [...catalog.sessions] }));
  expect(screen.getByTestId("delete-selection-bar")).toHaveTextContent("1 selected");
  expect(screen.getByRole("button", { name: "Review paper" })).toHaveAttribute("aria-pressed", "true");
});
