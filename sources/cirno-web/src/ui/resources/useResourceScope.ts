import { useEffect, useLayoutEffect, useMemo, useRef } from "react";

export interface ResourceScope {
  readonly isCurrent: () => boolean;
}

/** One activation of an owner; returning to that owner creates a new scope. */
export function useResourceScope(owner: unknown): ResourceScope {
  const current = useRef<ResourceScope | null>(null);
  const scope = useMemo<ResourceScope>(() => {
    const activation: ResourceScope = { isCurrent: () => current.current === activation };
    return activation;
  }, [owner]);
  useLayoutEffect(() => {
    current.current = scope;
  }, [scope]);
  // Suspense disconnects layout effects while hiding a still-mounted view.
  // Its accepted writes remain owned until replacement or actual unmount.
  useEffect(() => () => {
    if (current.current === scope) current.current = null;
  }, [scope]);
  return scope;
}
