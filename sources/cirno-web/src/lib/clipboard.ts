export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path for browsers/WebViews where the
    // Clipboard API exists but rejects outside a secure context.
  }

  return copyTextWithTextarea(text);
}

function copyTextWithTextarea(text: string): boolean {
  if (typeof document.execCommand !== "function") {
    return false;
  }

  const focused = document.activeElement;
  const input = focused instanceof HTMLInputElement || focused instanceof HTMLTextAreaElement
    ? focused : null;
  const selection = input && input.selectionStart !== null && input.selectionEnd !== null
    ? { start: input.selectionStart, end: input.selectionEnd, direction: input.selectionDirection ?? "none" }
    : null;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";

  document.body.appendChild(textarea);

  try {
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    const restoreFocus = document.activeElement === textarea;
    document.body.removeChild(textarea);
    if (restoreFocus && focused instanceof HTMLElement && focused.isConnected) {
      focused.focus({ preventScroll: true });
      if (input && selection) input.setSelectionRange(selection.start, selection.end, selection.direction);
    }
  }
}
