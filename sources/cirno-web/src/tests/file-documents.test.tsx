import { FileDocumentView } from "@/features/files/FileDocumentView";
import {
  FileDocument,
  FileDocuments,
  FileDocumentsProvider,
} from "@/features/files/documents";
import { fileRequest } from "@/features/files/api";
import { preloadMarkdownText } from "@/components/MarkdownText";
import type { CirnoClient } from "@/lib/cirno-client";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeAll, expect, it, vi } from "vitest";

beforeAll(async () => preloadMarkdownText());
const file = {
  kind: "text",
  path: "/workspace/notes.md",
  display_path: "notes.md",
  project_path: "/workspace",
  size: 20,
  content: "# Original heading",
  language: "markdown",
  truncated: false,
  editable: true,
  revision: "v1",
};

it("shares unsaved Markdown across editor and preview without making extra requests", async () => {
  const requestMutation = vi.fn(async () => file);
  const client = { requestMutation } as unknown as CirnoClient;
  const views = (editor: boolean) => (
    <FileDocumentsProvider>
      {editor && (
        <div key="editor" data-testid="editor">
          <FileDocumentView
            client={client}
            path={file.path}
            sessionKey="websocket:test"
          />
        </div>
      )}
      <div key="preview" data-testid="preview">
        <FileDocumentView
          client={client}
          path={file.path}
          sessionKey="websocket:test"
          preview
        />
      </div>
    </FileDocumentsProvider>
  );
  const result = render(views(true));
  const textbox = await screen.findByRole("textbox", { name: "File contents" });
  expect(
    await screen.findByRole("heading", { name: "Original heading" }),
  ).toBeVisible();
  fireEvent.change(textbox, { target: { value: "# Unsaved heading" } });
  expect(
    await screen.findByRole("heading", { name: "Unsaved heading" }),
  ).toBeVisible();
  expect(requestMutation).toHaveBeenCalledTimes(1);
  result.rerender(views(false));
  expect(
    await screen.findByRole("heading", { name: "Original heading" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Unsaved heading" }),
  ).not.toBeInTheDocument();
});

it("retains the draft and reports a failed save to every live view", async () => {
  const requestMutation = vi.fn(async (action: string) => {
    if (action.endsWith("save"))
      throw new Error("The file changed; reload before saving");
    return file;
  });
  const client = { requestMutation } as unknown as CirnoClient;
  render(
    <FileDocumentsProvider>
      <div data-testid="editor">
        <FileDocumentView
          client={client}
          path={file.path}
          sessionKey="websocket:test"
        />
      </div>
      <div data-testid="preview">
        <FileDocumentView
          client={client}
          path={file.path}
          sessionKey="websocket:test"
          preview
        />
      </div>
    </FileDocumentsProvider>,
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: "File contents" }),
    { target: { value: "# Keep my draft" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(
    await within(screen.getByTestId("editor")).findByRole("alert"),
  ).toHaveTextContent("The file changed");
  expect(
    within(screen.getByTestId("preview")).getByRole("alert"),
  ).toHaveTextContent("The file changed");
  expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue(
    "# Keep my draft",
  );
  expect(
    await screen.findByRole("heading", { name: "Keep my draft" }),
  ).toBeVisible();
});

it("keeps an accepted save owned when its last tab closes and reopens", async () => {
  let finish!: (value: typeof file) => void;
  const requestMutation = vi.fn(async (action: string) =>
    action.endsWith("save")
      ? new Promise<typeof file>((resolve) => {
          finish = resolve;
        })
      : file,
  );
  const client = { requestMutation } as unknown as CirnoClient;
  const documents = new FileDocuments();
  const create = () =>
    new FileDocument(file.path, fileRequest(client, "websocket:test"));
  const original = documents.document("key", create);
  const release = documents.retain("key", original, true);
  await original.settled();
  original.edit("Saved after reopening");
  const saving = original.save();
  await waitFor(() => expect(requestMutation).toHaveBeenCalledTimes(2));
  release();
  const reopened = documents.document("key", create);
  expect(reopened).toBe(original);
  const close = documents.retain("key", reopened, true);
  await act(async () => {
    finish({ ...file, content: "Saved after reopening", revision: "v2" });
    await saving;
  });
  expect(reopened.snapshot().draft).toBe("Saved after reopening");
  expect(reopened.snapshot().file?.revision).toBe("v2");
  expect(requestMutation).toHaveBeenCalledTimes(2);
  close();
});

it("refuses to dispose an editor when its in-flight save fails", async () => {
  let fail!: (reason: Error) => void;
  const requestMutation = vi.fn(async (action: string) => action.endsWith("save")
    ? new Promise<typeof file>((_, reject) => { fail = reject; }) : file);
  let close!: () => Promise<void>;
  render(<FileDocumentView client={{ requestMutation } as unknown as CirnoClient} path={file.path} sessionKey="websocket:test"
    onRegisterClose={callback => { close = callback; }} />);
  const editor = await screen.findByRole("textbox", { name: "File contents" });
  fireEvent.change(editor, { target: { value: "# Keep the failed save" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(requestMutation).toHaveBeenCalledTimes(2));
  const disposed = close().catch(error => error);
  await act(async () => fail(new Error("Save connection lost")));
  expect(await disposed).toEqual(new Error("Save connection lost"));
  expect(editor).toHaveValue("# Keep the failed save");
  expect(screen.getByRole("alert")).toHaveTextContent("Save connection lost");
});
