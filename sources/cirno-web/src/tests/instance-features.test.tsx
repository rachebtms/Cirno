import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationCatalogPreview } from "@/dev/fixtures/ConversationCatalogPreview";
import { projectConversationCatalog } from "@/features/conversations/catalog/projection";
import { NodesSettings } from "@/features/settings/nodes/NodesSettings";
import { setAppLanguage } from "@/i18n";
import type { CirnoClient } from "@/lib/cirno-client";

const projects = [ { id: "project-one", name: "One", working_directory: "/same" }, { id: "project-two", name: "Two", working_directory: "/same" } ];
afterEach(async () => { cleanup(); await setAppLanguage("en"); });
it("keeps Projects with the same directory distinct and preserves an empty Project", () => {
  const result = projectConversationCatalog({ sessions: [{ key: "websocket:one", chatId: "one", channel: "websocket", projectId: "project-one", preview: "", createdAt: null, updatedAt: null }], projects, showArchived: false }, "");
  expect(result.groups.map(group => [group.project.id, group.members.length])).toEqual([["project-one", 1], ["project-two", 0]]);
});
it("renders Project actions with icons and excludes Cirno from the conversation catalog", () => {
  render(<ConversationCatalogPreview sessions={[{ key: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", chatId: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", channel: "websocket", title: "Cirno", preview: "", createdAt: null, updatedAt: null }]} projects={projects} />);
  expect(screen.queryByText("Cirno")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "One" })).toBeVisible();
  expect(screen.getByRole("button", { name: "New project" }).querySelector("svg")).not.toBeNull();
  expect(document.body.textContent).not.toMatch(/[\u4e00-\u9fff]/);
});
it("translates catalog controls when Chinese is selected", async () => {
  await act(() => setAppLanguage("zh-CN"));
  render(<ConversationCatalogPreview sessions={[]} />);
  expect(screen.getByRole("button", { name: "新建项目" })).toBeVisible();
  expect(screen.queryByText("New project")).not.toBeInTheDocument();
});
it("selects existing SSH credentials instead of duplicating authentication fields", async () => {
  await act(() => setAppLanguage("en"));
  const requestMutation = vi.fn().mockImplementation((_name, payload) => Promise.resolve(payload.action === "credentials.list" ? { records: [] } : { nodes: [], jobs: [] }));
  render(
    <NodesSettings client={{ requestMutation } as unknown as CirnoClient} />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Add Node" }));
  expect(screen.getByRole("button", { name: /SSH credential/ })).toBeVisible();
  expect(screen.queryByRole("textbox", { name: /^SSH username/ })).not.toBeInTheDocument();
  expect(screen.getByText("Create an SSH credential in Credentials first.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(document.body.textContent).not.toMatch(/[\u4e00-\u9fff]/);
});

it("keeps pinned ordinary conversations first in the current projection", () => {
  const sessions = [ { key: "websocket:new", chatId: "new", channel: "websocket", preview: "", createdAt: null, updatedAt: "2026-10-31T12:00:00Z" }, { key: "websocket:pinned", chatId: "pinned", channel: "websocket", preview: "", createdAt: null, updatedAt: "2026-10-30T12:00:00Z" } ];
  const result = projectConversationCatalog({ sessions, projects: [], showArchived: false, preferences: { pinned_keys: ["websocket:pinned"], archived_keys: [], title_overrides: {} } }, "");
  expect(result.unfiled.map(session => session.key)).toEqual(["websocket:pinned", "websocket:new"]);
});
