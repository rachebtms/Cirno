import { useRef, type KeyboardEvent } from "react";

/** Escape first cancels IME composition; it must not dismiss the enclosing editor. */
export function useComposingEscape() {
  const composing = useRef(false);
  return {
    onCompositionStartCapture: () => { composing.current = true; },
    onCompositionEndCapture: () => { composing.current = false; },
    onKeyDownCapture: (event: KeyboardEvent<HTMLElement>) => {
      if (event.key === "Escape" && (composing.current || event.nativeEvent.isComposing)) event.stopPropagation();
    },
  };
}
