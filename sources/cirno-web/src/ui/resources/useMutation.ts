import { useCallback, useRef } from "react";
import { useResourceScope, type ResourceScope } from "./useResourceScope";
import { useScopedState } from "./useScopedState";

/** Serializes writes for one owner; stale acknowledgements cannot mutate a replacement view. */
export function useMutation(owner: unknown) {
  const scope = useResourceScope(owner);
  const { isCurrent } = scope;
  const flight = useRef<{ scope: ResourceScope } | null>(null);
  const [state, setState] = useScopedState(scope, () => ({ busy: false, error: null as string | null }));
  const run = useCallback(
    async <T>(operation: () => Promise<T>, onSuccess: (value: T) => void) => {
      if (!isCurrent() || flight.current?.scope === scope) return;
      const request = { scope };
      flight.current = request;
      setState({ busy: true, error: null });
      try {
        const value = await operation();
        if (flight.current !== request || !isCurrent()) return;
        onSuccess(value);
        if (flight.current !== request || !isCurrent()) return;
        setState({ busy: false, error: null });
        return value;
      } catch (reason) {
        if (flight.current === request && isCurrent())
          setState({
            busy: false,
            error: reason instanceof Error ? reason.message : String(reason),
          });
      } finally {
        if (flight.current === request) flight.current = null;
      }
    },
    [scope, isCurrent, setState],
  );
  const clear = useCallback(() => {
    if (isCurrent() && flight.current?.scope !== scope)
      setState({ busy: false, error: null });
  }, [scope, isCurrent, setState]);
  return { owner, ...state, run, clear };
}
