import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useMessageEditing } from "@/features/messages/model/useMessageEditing";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { UIMessage } from "@/lib/contracts/messages";

const message: UIMessage = {
  id: "human",
  role: "user",
  content: "Original",
  createdAt: 1,
  turnId: "turn",
};
const tool: UIMessage = {
  id: "effect",
  role: "tool",
  kind: "trace",
  content: "shell command",
  createdAt: 2,
};
function Harness({
  chat,
  reset,
}: {
  chat: string;
  reset: (id?: string) => void;
}) {
  const state = useMessageEditing({
    sessionKey: chat,
    displayMessages: [message, tool],
    turnActive: false,
    resetHistory: reset,
  });
  return (
    <>
      <button onClick={() => state.beginMessageEdit(message)}>
        Edit original
      </button>
      {state.messageEditor?.content}
    </>
  );
}
function client(request: ReturnType<typeof vi.fn>) {
  return { requestMutation: request } as unknown as CirnoClient;
}
function view(chat: string, api: CirnoClient, reset: (id?: string) => void) {
  return (
    <ClientProvider client={api} token="fixture">
      <Harness chat={chat} reset={reset} />
    </ClientProvider>
  );
}
function edit() {
  fireEvent.click(screen.getByRole("button", { name: "Edit original" }));
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Revised\nrequest" },
  });
  fireEvent.submit(screen.getByRole("form"));
}

it("serializes edit submissions and resets only the acknowledged turn", async () => {
  let resolve!: (result: { turn_id: string }) => void;
  const request = vi.fn(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    ),
    reset = vi.fn();
  render(view("first", client(request), reset));
  edit();
  fireEvent.submit(screen.getByRole("form"));
  expect(request).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledWith("instance.action", {
    action: "conversations.edit",
    values: {
      session_key: "first",
      turn_id: "turn",
      content: "Revised\nrequest",
    },
  });
  expect(screen.getByRole("textbox")).toBeDisabled();
  await act(async () => resolve({ turn_id: "new-turn" }));
  expect(reset).toHaveBeenCalledWith("new-turn");
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
});

it.each(["chat", "client", "unmount"] as const)(
  "ignores an old edit acknowledgement after %s ownership changes",
  async (change) => {
    let resolve!: (result: { turn_id: string }) => void;
    const request = vi.fn(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      ),
      reset = vi.fn(),
      first = client(request);
    const { rerender, unmount } = render(view("first", first, reset));
    edit();
    if (change === "unmount") unmount();
    else {
      rerender(
        view(
          change === "chat" ? "second" : "first",
          change === "client" ? client(vi.fn()) : first,
          reset,
        ),
      );
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Edit original" }));
      fireEvent.change(screen.getByRole("textbox"), {
        target: { value: "Replacement draft" },
      });
    }
    await act(async () => resolve({ turn_id: "old-turn" }));
    expect(reset).not.toHaveBeenCalled();
    if (change !== "unmount")
      expect(screen.getByRole("textbox")).toHaveValue("Replacement draft");
  },
);

it("retains a rejected draft and its file-effect warning for retry", async () => {
  const request = vi
      .fn()
      .mockRejectedValueOnce(new Error("Conversation changed"))
      .mockResolvedValueOnce({ turn_id: "new-turn" }),
    reset = vi.fn();
  render(view("first", client(request), reset));
  edit();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Conversation changed",
  );
  expect(screen.getByRole("textbox")).toHaveValue("Revised\nrequest");
  expect(screen.getByRole("note")).toHaveTextContent(
    "does not undo earlier commands or file edits",
  );
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(reset).toHaveBeenCalledWith("new-turn"));
});
