import { act, cleanup, renderHook } from "@testing-library/react";
import type { ClipboardEvent, DragEvent } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useClipboardAndDrop } from "@/hooks/useClipboardAndDrop";

afterEach(cleanup);

function paste(files: File[], text = "") {
  return {
    clipboardData: { items: files.map(file => ({ kind: "file", getAsFile: () => file })), getData: (type: string) => type === "text/plain" ? text : "<b>ignored</b>" },
    preventDefault: vi.fn(),
  } as unknown as ClipboardEvent;
}

it("attaches clipboard files without discarding accompanying text", () => {
  const add = vi.fn();
  const hook = renderHook(() => useClipboardAndDrop(add));
  const file = new File(["x"], "image.png", { type: "image/png" });
  const event = paste([file], "/tmp/notes.png");
  let handled = false;
  act(() => { handled = hook.result.current.onPaste(event); });
  expect(event.preventDefault).not.toHaveBeenCalled();
  expect(add).toHaveBeenCalledWith([file]);
  expect(handled).toBe(true);
});

it("consumes a file-only clipboard event", () => {
  const add = vi.fn();
  const hook = renderHook(() => useClipboardAndDrop(add));
  const file = new File(["x"], "image.png", { type: "image/png" });
  const event = paste([file]);
  act(() => { hook.result.current.onPaste(event); });
  expect(event.preventDefault).toHaveBeenCalledOnce();
  expect(add).toHaveBeenCalledWith([file]);
});

it("leaves text and HTML without files to the textarea", () => {
  const add = vi.fn();
  const hook = renderHook(() => useClipboardAndDrop(add));
  const event = paste([], "plain text");
  act(() => { hook.result.current.onPaste(event); });
  expect(event.preventDefault).not.toHaveBeenCalled();
  expect(add).not.toHaveBeenCalled();
});

it("prevents dropped unsupported files from navigating away", () => {
  const add = vi.fn();
  const hook = renderHook(() => useClipboardAndDrop(add));
  const event = { dataTransfer: { files: [new File(["x"], "unknown.bin", { type: "application/octet-stream" })] }, preventDefault: vi.fn() } as unknown as DragEvent;
  act(() => { hook.result.current.onDrop(event); });
  expect(event.preventDefault).toHaveBeenCalledOnce();
  expect(add).not.toHaveBeenCalled();
  expect(hook.result.current.isDragging).toBe(false);
});

it("still attaches supported dropped files", () => {
  const add = vi.fn();
  const hook = renderHook(() => useClipboardAndDrop(add));
  const file = new File(["x"], "notes.txt", { type: "text/plain" });
  const event = { dataTransfer: { files: [file] }, preventDefault: vi.fn() } as unknown as DragEvent;
  act(() => { hook.result.current.onDrop(event); });
  expect(event.preventDefault).toHaveBeenCalledOnce();
  expect(add).toHaveBeenCalledWith([file]);
});

it("does not consume an ordinary text or URL drop", () => {
  const add = vi.fn();
  const hook = renderHook(() => useClipboardAndDrop(add));
  const event = { dataTransfer: { files: [] }, preventDefault: vi.fn() } as unknown as DragEvent;
  act(() => { hook.result.current.onDrop(event); });
  expect(event.preventDefault).not.toHaveBeenCalled();
  expect(add).not.toHaveBeenCalled();
});
