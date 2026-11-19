import { useCallback, useState, type Dispatch, type SetStateAction } from "react";
import type { ResourceScope } from "./useResourceScope";

/** Resets on scope replacement and ignores setters retained by a retired view. */
export function useScopedState<T>(
  scope: ResourceScope,
  initialize: () => T,
): [T, Dispatch<SetStateAction<T>>] {
  const [snapshot, setSnapshot] = useState(() => ({ scope, value: initialize() }));
  let current = snapshot;
  if (snapshot.scope !== scope) {
    current = { scope, value: initialize() };
    setSnapshot(current);
  }
  const setValue = useCallback<Dispatch<SetStateAction<T>>>((update) => {
    if (!scope.isCurrent()) return;
    setSnapshot((previous) => {
      if (previous.scope !== scope || !scope.isCurrent()) return previous;
      const value = typeof update === "function"
        ? (update as (previous: T) => T)(previous.value)
        : update;
      return Object.is(value, previous.value) ? previous : { scope, value };
    });
  }, [scope]);
  return [current.value, setValue];
}
