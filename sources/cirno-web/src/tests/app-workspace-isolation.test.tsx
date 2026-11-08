import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import { installAppTestLifecycle, appTest, mockFetchRoutes, requestMutationSpy,
  sessionUpdateHandlers, statusHandlers, createChatSpy, connectSpy } from "./helpers/app-harness";
import { openAppConversation } from "./helpers/app-navigation";
import App from "@/App";

installAppTestLifecycle();
const scope = (name: string) => ({ project_path: `/workspaces/${name}`, project_name: name,
  access_mode: "restricted" as const, restrict_to_workspace: true });

async function startDraft() {
  appTest.sessions = [{ key: "websocket:worker", chatId: "worker", channel: "websocket",
    title: "Research worker", preview: "", createdAt: null, updatedAt: null, workspaceScope: scope("worker") }];
  mockFetchRoutes({ "/v0/workspaces": {
    schema_version: 1, default_access_mode: "default", default_scope: scope("default"),
    recent_projects: [{ path: "/workspaces/draft", name: "draft" }],
    controls: { can_change_project: true, can_resolve_project: true },
  } });
  requestMutationSpy.mockImplementation(async (action: unknown) => action === "workspace.resolve_project"
    ? { path: "/workspaces/draft", name: "draft" } : { projects: [] });
  render(<App />);
  await waitFor(() => expect(connectSpy).toHaveBeenCalled());
  act(() => statusHandlers.forEach(handler => handler("open")));
  fireEvent.click(await screen.findByRole("button", { name: "Switch directory" }));
  fireEvent.click(await screen.findByRole("button", { name: "/workspaces/draft" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Switch directory" })).toHaveTextContent("draft");
  fireEvent.change(screen.getByRole("textbox", { name: "Message input" }), { target: { value: "Keep this draft scope" } });
}

it("keeps an unsent workspace when a background worker changes its own directory", async () => {
  await startDraft();
  await act(async () => sessionUpdateHandlers.forEach(handler => handler("worker", "metadata", scope("background"))));
  expect(screen.getByRole("button", { name: "Switch directory" })).toHaveTextContent("draft");
  await openAppConversation("Research worker");
  expect(screen.getByRole("button", { name: "Switch directory" })).toHaveTextContent("background");
  fireEvent.click(screen.getByRole("tab", { name: "New conversation" }));
  expect(screen.getByRole("button", { name: "Switch directory" })).toHaveTextContent("draft");
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(createChatSpy).toHaveBeenCalledWith(scope("draft")));
});

it("restores the unsent workspace after visiting another conversation", async () => {
  await startDraft();
  await openAppConversation("Research worker");
  expect(await screen.findByRole("button", { name: "Switch directory" })).toHaveTextContent("worker");
  fireEvent.click(screen.getByRole("tab", { name: "New conversation" }));
  expect(screen.getByRole("button", { name: "Switch directory" })).toHaveTextContent("draft");
  expect(screen.getByRole("textbox", { name: "Message input" })).toHaveValue("Keep this draft scope");
});
