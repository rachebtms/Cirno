import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WorkspaceFiles } from "@/components/WorkspaceFiles";
import type { CirnoClient } from "@/lib/cirno-client";

vi.mock("@/components/FilePreviewPanelView", () => ({
  FilePreviewPanelView: () => <div>File preview</div>,
}));

function setup(conflict = false) {
  let content = "Original text";
  const requestMutation = vi.fn(
    async (action: string, data: Record<string, string>) => {
      if (action.endsWith("list"))
        return {
          path: "/project",
          project_path: "/project",
          parent: null,
          entries: [
            { path: "/project/notes.md", name: "notes.md", kind: "file" },
          ],
          truncated: false,
        };
      if (action.endsWith("save")) {
        if (conflict)
          throw new Error(
            "The file changed. Reload it before saving your edits.",
          );
        content = data.content;
      }
      return {
        kind: "text",
        path: "/project/notes.md",
        display_path: "notes.md",
        project_path: "/project",
        content,
        language: "markdown",
        truncated: false,
        editable: true,
        revision: "revision-1",
      };
    },
  );
  render(
    <WorkspaceFiles
      client={{ requestMutation } as unknown as CirnoClient}
      sessionKey="websocket:test"
    />,
  );
  return requestMutation;
}

async function editFile() {
  fireEvent.click(await screen.findByRole("button", { name: "notes.md" }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  fireEvent.change(screen.getByRole("textbox", { name: "File contents" }), {
    target: { value: "Edited text" },
  });
}

it("saves file edits to their originating conversation with the loaded revision", async () => {
  const request = setup();
  await editFile();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("workspace.files.save", {
      session_key: "websocket:test",
      path: "/project/notes.md",
      content: "Edited text",
      revision: "revision-1",
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled(),
  );
});

it("keeps unsaved edits visible when a concurrent update prevents saving", async () => {
  setup(true);
  await editFile();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The file changed",
  );
  expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue(
    "Edited text",
  );
});

it("lets users cancel closing and discards the draft only after confirmation", async () => {
  setup();
  await editFile();
  fireEvent.click(screen.getByRole("button", { name: "Back to files" }));
  const warning = await screen.findByRole("alertdialog");
  fireEvent.click(within(warning).getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue(
    "Edited text",
  );
  fireEvent.click(screen.getByRole("button", { name: "Back to files" }));
  fireEvent.click(
    within(await screen.findByRole("alertdialog")).getByRole("button", {
      name: "Discard changes",
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "notes.md" })).toBeVisible(),
  );
  fireEvent.click(screen.getByRole("button", { name: "notes.md" }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue(
    "Original text",
  );
});
