import { useEffect, useLayoutEffect, type MutableRefObject, type RefObject } from "react";
import { ThreadViewportInput } from "./input";
import type { ThreadViewportInputOptions } from "./input-contracts";

export function useViewportInput(
  controller: MutableRefObject<ThreadViewportInput | null>,
  scroller: RefObject<HTMLElement | null>,
  options: ThreadViewportInputOptions,
): void {
  useLayoutEffect(() => {
    controller.current ??= new ThreadViewportInput(options);
    controller.current.update(options);
    controller.current.connect(scroller.current);
  });
  useEffect(() => () => controller.current?.disconnect(), [controller]);
}
