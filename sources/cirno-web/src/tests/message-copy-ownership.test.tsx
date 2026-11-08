import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MessageActions } from "@/features/messages";
import * as clipboard from "@/lib/clipboard";

it("shows a failed clipboard operation and allows retry", async () => {
  const copy = vi
    .spyOn(clipboard, "copyTextToClipboard")
    .mockResolvedValueOnce(false)
    .mockResolvedValueOnce(true);
  try {
    render(
      <MessageActions
        message={{
          id: "copy",
          role: "assistant",
          content: "Exact result",
          createdAt: 1,
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not copy to the clipboard.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeEnabled();
    expect(copy).toHaveBeenNthCalledWith(2, "Exact result");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  } finally {
    copy.mockRestore();
  }
});

it("does not mark replacement text as copied when an older clipboard request completes", async () => {
  let resolve!: (value: boolean) => void;
  const copy = vi
    .spyOn(clipboard, "copyTextToClipboard")
    .mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    )
    .mockResolvedValue(true);
  try {
    const message = {
      id: "copy",
      role: "assistant" as const,
      content: "Earlier text",
      createdAt: 1,
    };
    const { rerender } = render(<MessageActions message={message} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(screen.getByRole("button", { name: "Copy" })).toBeDisabled();
    rerender(<MessageActions message={{ ...message, content: "New text" }} />);
    await act(async () => resolve(true));
    expect(
      screen.queryByRole("button", { name: "Copied" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(copy).toHaveBeenLastCalledWith("New text"));
  } finally {
    copy.mockRestore();
  }
});
