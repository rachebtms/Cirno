import { useRef } from "react";

/** Let the overlay restore keyboard focus without refocusing pointer dismissals. */
export function useOverlayFocusReturn() {
  const restore = useRef(false);
  return {
    pointer: () => { restore.current = false; },
    keyboard: () => { restore.current = true; },
    onCloseAutoFocus: (event: Event) => {
      if (!restore.current) event.preventDefault();
    },
  };
}
