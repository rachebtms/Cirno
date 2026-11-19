import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { WorkspaceFiles } from "@/features/files/WorkspaceFiles";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { setAppLanguage } from "@/i18n";

function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function scope(root: string) { return { project_path: root, access_mode: "restricted" } as WorkspaceScopePayload; }
function client(create: ReturnType<typeof pending<unknown>>) {
  const request = vi.fn((action: string, values: { path: string }) => action.endsWith("create") ? create.promise : Promise.resolve({
    path: values.path, parent: null, project_path: values.path, entries: [], truncated: false,
  }));
  return { client: { requestMutation: request } as unknown as CirnoClient, request };
}
async function openCreation() {
  const button = await screen.findByRole("button", { name: "New file" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  fireEvent.change(await screen.findByRole("textbox", { name: "Name" }), { target: { value: "draft.txt" } });
  return screen.getByRole("button", { name: "Create" }).closest("form")!;
}
beforeEach(async () => { await setAppLanguage("en"); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("admits one create request when the form submits twice before busy renders", async () => {
  const created = pending<unknown>(), api = client(created);
  const open = vi.fn();
  render(<WorkspaceFiles client={api.client} sessionKey="websocket:owner" workspaceScope={scope("/first")} onOpenFile={open} />);
  const form = await openCreation();
  act(() => { fireEvent.submit(form); fireEvent.submit(form); });
  const count = api.request.mock.calls.filter(([action]) => action.endsWith("create")).length;
  await act(async () => { created.resolve({ name: "draft.txt", path: "/first/draft.txt", kind: "file" }); });
  expect(count).toBe(1);
  expect(open).toHaveBeenCalledOnce();
});

it.each(["client", "scope"])("does not open an old creation result after its %s changes", async change => {
  const created = pending<unknown>(), first = client(created), second = change === "client" ? client(created) : first;
  const open = vi.fn();
  const ui = render(<WorkspaceFiles client={first.client} sessionKey="websocket:owner" workspaceScope={scope("/first")} onOpenFile={open} />);
  const form = await openCreation();
  fireEvent.submit(form);
  await waitFor(() => expect(first.request).toHaveBeenCalledWith("workspace.files.create", expect.objectContaining({ path: "/first/draft.txt" })));
  ui.rerender(<WorkspaceFiles client={second.client} sessionKey="websocket:owner" workspaceScope={scope("/second")} onOpenFile={open} />);
  await waitFor(() => expect(second.request).toHaveBeenCalledWith("workspace.files.list", expect.objectContaining({ path: "/second" })));
  await act(async () => { created.resolve({ name: "draft.txt", path: "/first/draft.txt", kind: "file" }); });
  expect(open).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps a failed creation's name and lets a later attempt succeed", async () => {
  const created = pending<unknown>(), api = client(created), open = vi.fn();
  render(<WorkspaceFiles client={api.client} sessionKey="websocket:owner" workspaceScope={scope("/first")} onOpenFile={open} />);
  const form = await openCreation();
  api.request.mockRejectedValueOnce(new Error("Fixture creation failed"));
  fireEvent.submit(form);
  expect(await screen.findByRole("alert")).toHaveTextContent("Fixture creation failed");
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("draft.txt");
  expect(screen.getByRole("button", { name: "Create" })).toBeEnabled();
  expect(open).not.toHaveBeenCalled();
  api.request.mockResolvedValueOnce({ name: "draft.txt", path: "/first/draft.txt", kind: "file" });
  fireEvent.submit(form);
  await waitFor(() => expect(open).toHaveBeenCalledWith("/first/draft.txt"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
