import { useLayoutEffect, useState, type RefObject } from "react";
import { isKeyboardEditableElement } from "./input-geometry";
import { readSoftKeyboardInsetBottom } from "./geometry";

type ScrollLatest = (smooth: boolean, options: { force: boolean; }) => void;

export function useComposerViewport(
  composerDockRef: RefObject<HTMLDivElement | null>,
  hasMessages: boolean,
  scrollToBottom: ScrollLatest,
): number {
  const [keyboardInsetBottom, setKeyboardInsetBottom] = useState(0);
  useLayoutEffect(() => {
    const updateKeyboardInset = () => {
      const composerDock = composerDockRef.current;
      const next = readSoftKeyboardInsetBottom(composerDock);
      const active = document.activeElement;
      const composerFocused =
        hasMessages
        && isKeyboardEditableElement(active)
        && Boolean(composerDock?.contains(active));
      setKeyboardInsetBottom((current) =>
        Math.abs(current - next) < 1 ? current : next,
      );
      if (composerFocused) {
        // Focusing the composer establishes a new reference frame at the
        // latest message. This is one immediate positioning command; viewport
        // events may issue a fresh command, but no command survives into a
        // later render as a train of retry frames.
        scrollToBottom(false, { force: true });
      }
    };
    updateKeyboardInset();
    const viewport = window.visualViewport;
    viewport?.addEventListener("resize", updateKeyboardInset);
    viewport?.addEventListener("scroll", updateKeyboardInset);
    window.addEventListener("resize", updateKeyboardInset);
    document.addEventListener("focusin", updateKeyboardInset);
    document.addEventListener("focusout", updateKeyboardInset);
    return () => {
      viewport?.removeEventListener("resize", updateKeyboardInset);
      viewport?.removeEventListener("scroll", updateKeyboardInset);
      window.removeEventListener("resize", updateKeyboardInset);
      document.removeEventListener("focusin", updateKeyboardInset);
      document.removeEventListener("focusout", updateKeyboardInset);
    };
  }, [composerDockRef, hasMessages, scrollToBottom]);

  return keyboardInsetBottom;
}
