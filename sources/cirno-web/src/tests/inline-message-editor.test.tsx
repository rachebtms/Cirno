import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InlineMessageEditor } from "@/components/thread/InlineMessageEditor";
import { MessageBubble } from "@/components/MessageBubble";

function editor(overrides: Partial<React.ComponentProps<typeof InlineMessageEditor>> = {}) {
  const props = { value: "Original request", busy: false, error: "", hasToolEffects: false,
    onChange: vi.fn(), onCancel: vi.fn(), onSubmit: vi.fn(), ...overrides };
  return { props, view: render(<InlineMessageEditor {...props} />) };
}

describe("inline message editing", () => {
  it("focuses the original text, leaves Enter for multiline input, and submits with Ctrl+Enter", () => {
    const { props } = editor();
    const input = screen.getByRole("textbox", { name: "Edited message" });
    expect(input).toHaveFocus();
    expect(input).toHaveValue("Original request");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(props.onSubmit).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "Line one\nLine two" } });
    expect(props.onChange).toHaveBeenCalledWith("Line one\nLine two");
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });
    expect(props.onSubmit).toHaveBeenCalledOnce();
  });

  it("does not submit or cancel while the input method is composing", () => {
    const { props } = editor();
    const input = screen.getByRole("textbox");
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true, isComposing: true });
    fireEvent.keyDown(input, { key: "Escape", keyCode: 229 });
    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(props.onCancel).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(props.onCancel).toHaveBeenCalledOnce();
  });

  it("blocks duplicate submissions while saving and disallows blank messages", () => {
    const { props, view } = editor({ busy: true });
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("form"));
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", metaKey: true });
    expect(props.onSubmit).not.toHaveBeenCalled();
    view.rerender(<InlineMessageEditor {...props} busy={false} value={" \n "} />);
    expect(screen.getByRole("button", { name: "Save and send" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("form"));
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("keeps failures and side effect warnings beside the retained draft", () => {
    editor({ error: "Conversation is active", hasToolEffects: true });
    expect(screen.getByRole("alert")).toHaveTextContent("Conversation is active");
    expect(screen.getByRole("note")).toHaveTextContent("does not undo earlier commands or file edits");
    expect(screen.getByRole("textbox")).toHaveAccessibleDescription(/Existing attachments are retained.*does not undo/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("replaces the text bubble while keeping existing attachments", () => {
    render(<MessageBubble message={{ id: "u", role: "user", content: "Original request", createdAt: 1,
      images: [{ name: "Attached evidence", url: "https://example.com/evidence.png" }] }}
      editor={<InlineMessageEditor value="Edited request" busy={false} error="" hasToolEffects={false}
        onChange={() => {}} onCancel={() => {}} onSubmit={() => {}} />} />);
    expect(screen.getByRole("textbox")).toHaveValue("Edited request");
    expect(screen.queryByText("Original request")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Attached evidence" })).toBeInTheDocument();
    expect(document.querySelector("[data-user-text-bubble]")).toBeNull();
  });
});
