import { afterEach, expect, it, vi } from "vitest";
import { copyTextToClipboard } from "@/lib/clipboard";

afterEach(() => { document.body.replaceChildren(); vi.restoreAllMocks(); });

it.each(["success", "failure", "exception"])("restores editor focus and selection after legacy copy %s", async outcome => {
  const input = document.createElement("textarea");
  input.value = "keep this draft";
  document.body.appendChild(input);
  input.focus();
  input.setSelectionRange(2, 7, "backward");
  const exec = vi.fn(() => {
    expect(document.activeElement).not.toBe(input);
    if (outcome === "exception") throw new Error("copy unavailable");
    return outcome === "success";
  });
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue({ writeText: vi.fn().mockRejectedValue(new Error("insecure context")) } as unknown as Clipboard);
  const original = Object.getOwnPropertyDescriptor(document, "execCommand");
  Object.defineProperty(document, "execCommand", { configurable: true, value: exec });
  try {
    expect(await copyTextToClipboard("copied")).toBe(outcome === "success");
    expect(document.activeElement).toBe(input);
    expect([input.selectionStart, input.selectionEnd, input.selectionDirection]).toEqual([2, 7, "backward"]);
    expect(document.querySelectorAll("textarea")).toHaveLength(1);
  } finally {
    if (original) Object.defineProperty(document, "execCommand", original);
    else delete (document as unknown as { execCommand?: unknown }).execCommand;
  }
});

it("preserves a deliberate focus change during the copy event", async () => {
  const source = document.createElement("input"), target = document.createElement("button");
  document.body.append(source, target);
  source.focus();
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue({ writeText: vi.fn().mockRejectedValue(new Error("fallback")) } as unknown as Clipboard);
  const original = Object.getOwnPropertyDescriptor(document, "execCommand");
  Object.defineProperty(document, "execCommand", { configurable: true, value: () => { target.focus(); return true; } });
  try {
    expect(await copyTextToClipboard("copied")).toBe(true);
    expect(document.activeElement).toBe(target);
  } finally {
    if (original) Object.defineProperty(document, "execCommand", original);
    else delete (document as unknown as { execCommand?: unknown }).execCommand;
  }
});
