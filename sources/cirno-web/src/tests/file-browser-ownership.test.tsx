import { act, cleanup, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FileDocumentView } from "@/features/files/FileDocumentView";
import { FileDocumentsProvider } from "@/features/files/documents";
import { useDirectory } from "@/features/files/model/useDirectory";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { setAppLanguage } from "@/i18n";

vi.mock("@/components/FilePreviewPanelView", () => ({ FilePreviewPanelView: () => <div>Preview</div> }));
const file = { kind: "text", path: "/project/notes.txt", display_path: "notes.txt", project_path: "/project",
  size: 4, content: "First instance", editable: true, revision: "v1", truncated: false, language: "text" };
function source(content: string) {
  const request = vi.fn().mockResolvedValue({ ...file, content });
  return { client: { requestMutation: request } as unknown as CirnoClient, request };
}
function scope(root: string) { return { project_path: root, access_mode: "restricted" } as WorkspaceScopePayload; }
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(async () => { await setAppLanguage("en"); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("keeps shared editor documents separate for different clients", async () => {
  const first = source("First instance"), second = source("Second instance");
  render(<FileDocumentsProvider>
    <div data-testid="first"><FileDocumentView client={first.client} path={file.path} sessionKey="websocket:owner" /></div>
    <div data-testid="second"><FileDocumentView client={second.client} path={file.path} sessionKey="websocket:owner" /></div>
  </FileDocumentsProvider>);
  await screen.findAllByRole("textbox", { name: "File contents" });
  expect(within(screen.getByTestId("first")).getByRole("textbox", { name: "File contents" })).toHaveValue("First instance");
  expect(within(screen.getByTestId("second")).getByRole("textbox", { name: "File contents" })).toHaveValue("Second instance");
  expect(first.request).toHaveBeenCalledOnce();
  expect(second.request).toHaveBeenCalledOnce();
});

it("does not replace the new client's editor with an old save completion", async () => {
  const first = source("First instance"), second = source("Second instance"), save = pending<unknown>();
  const view = (client: CirnoClient) => <FileDocumentsProvider><FileDocumentView client={client} path={file.path} sessionKey="websocket:owner" /></FileDocumentsProvider>;
  const ui = render(view(first.client));
  fireEvent.change(await screen.findByRole("textbox", { name: "File contents" }), { target: { value: "Old saved draft" } });
  first.request.mockImplementationOnce(() => save.promise);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(first.request).toHaveBeenCalledTimes(2));
  ui.rerender(view(second.client));
  await act(async () => { save.resolve({ ...file, content: "Old saved draft", revision: "v2" }); });
  await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toBeEnabled());
  expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("Second instance");
  expect(second.request).toHaveBeenCalledOnce();
});

it.each(["client", "scope"])("resets a directory's path and filters when its %s owner changes", async change => {
  const first = source("unused"), second = change === "client" ? source("unused") : first;
  const read = async (_action: string, values: { path: string }) => ({ path: values.path, parent: null, project_path: values.path, entries: [], truncated: false });
  first.request.mockImplementation(read);
  second.request.mockImplementation(read);
  const view = renderHook(props => useDirectory(props.client, "websocket:owner", props.scope), {
    initialProps: { client: first.client, scope: scope("/first") },
  });
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  act(() => { view.result.current.navigate("/first/nested"); view.result.current.setQuery("private notes"); view.result.current.setShowHidden(true); });
  view.rerender({ client: second.client, scope: scope("/second") });
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  expect(view.result.current.path).toBe("/second");
  expect(view.result.current.query).toBe("");
  expect(view.result.current.showHidden).toBe(false);
  expect(second.request).toHaveBeenLastCalledWith("workspace.files.list", expect.objectContaining({ path: "/second", query: "", show_hidden: false }));
});

it("retires a previous file's discard confirmation when opening another document", async () => {
  const { client, request } = source("First file");
  const back = vi.fn();
  const ui = render(<FileDocumentView client={client} path={file.path} sessionKey="websocket:owner" onBack={back} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "File contents" }), { target: { value: "Draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Back to files" }));
  await screen.findByRole("alertdialog");
  request.mockResolvedValue({ ...file, path: "/project/other.txt", content: "Second file" });
  ui.rerender(<FileDocumentView client={client} path="/project/other.txt" sessionKey="websocket:owner" onBack={back} />);
  await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("Second file"));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(back).not.toHaveBeenCalled();
});

it("keeps directory filters and avoids another read for an equivalent scope snapshot", async () => {
  const { client, request } = source("unused");
  request.mockImplementation(async (_action: string, values: { path: string }) => ({ path: values.path, parent: null,
    project_path: "/first", entries: [], truncated: false }));
  const ui = renderHook(props => useDirectory(client, "websocket:owner", props.scope), { initialProps: { scope: scope("/first") } });
  await waitFor(() => expect(ui.result.current.loading).toBe(false));
  act(() => { ui.result.current.navigate("/first/nested"); ui.result.current.setQuery("notes"); ui.result.current.setShowHidden(true); });
  await waitFor(() => expect(ui.result.current.loading).toBe(false));
  const count = request.mock.calls.length;
  ui.rerender({ scope: { ...scope("/first") } });
  await act(async () => {});
  expect(ui.result.current.path).toBe("/first/nested");
  expect(ui.result.current.query).toBe("notes");
  expect(ui.result.current.showHidden).toBe(true);
  expect(request).toHaveBeenCalledTimes(count);
});

it("ignores retained filter setters after the directory's workspace is replaced", async () => {
  const { client, request } = source("unused");
  request.mockImplementation(async (_action: string, values: { path: string }) => ({
    path: values.path, parent: null, project_path: values.path, entries: [], truncated: false,
  }));
  const view = renderHook(props => useDirectory(client, "websocket:owner", props.scope), {
    initialProps: { scope: scope("/first") },
  });
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  const { setQuery, setShowHidden } = view.result.current;
  view.rerender({ scope: scope("/second") });
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  act(() => { setQuery("first workspace filter"); setShowHidden(true); });
  expect(view.result.current.query).toBe("");
  expect(view.result.current.showHidden).toBe(false);
  expect(view.result.current.path).toBe("/second");
});
