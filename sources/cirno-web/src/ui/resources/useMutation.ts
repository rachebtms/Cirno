import { useCallback, useEffect, useRef, useState } from "react";
import { useLifetime } from "./useLifetime";

/** Serializes writes for one owner; stale acknowledgements cannot mutate a replacement view. */
export function useMutation(owner: unknown) {
  const isCurrent = useLifetime(owner);
  const flight = useRef<{ owner: unknown } | null>(null);
  const [state, setState] = useState({ owner, busy: false, error: null as string | null });
  useEffect(
    () => () => {
      if (flight.current?.owner === owner) flight.current = null;
    },
    [owner],
  );
  const run = useCallback(
    async <T>(operation: () => Promise<T>, onSuccess: (value: T) => void) => {
      if (!isCurrent() || flight.current?.owner === owner) return;
      const request = { owner };
      flight.current = request;
      setState({ owner, busy: true, error: null });
      try {
        const value = await operation();
        if (flight.current !== request || !isCurrent()) return;
        onSuccess(value);
        setState({ owner, busy: false, error: null });
        return value;
      } catch (reason) {
        if (flight.current === request && isCurrent())
          setState({
            owner,
            busy: false,
            error: reason instanceof Error ? reason.message : String(reason),
          });
      } finally {
        if (flight.current === request) flight.current = null;
      }
    },
    [owner, isCurrent],
  );
  const clear = useCallback(() => {
    if (isCurrent() && flight.current?.owner !== owner)
      setState({ owner, busy: false, error: null });
  }, [owner, isCurrent]);
  return { ...(state.owner === owner ? state : { owner, busy: false, error: null }), run, clear };
}
