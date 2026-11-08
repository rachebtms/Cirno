import { useCallback, useEffect, useRef, useState } from "react";
import { useLifetime } from "./useLifetime";

type RequestStatus = "idle" | "loading" | "success" | "error";
interface RequestState<T> {
  owner: unknown;
  value: T | null;
  status: RequestStatus;
  error: string | null;
}
/** Latest read wins; replacing an owner immediately hides its previous data. */
export function useRequest<T>(owner: unknown) {
  const sequence = useRef(0);
  const isCurrent = useLifetime(owner);
  const [state, setState] = useState<RequestState<T>>({
    owner,
    value: null,
    status: "idle",
    error: null,
  });
  useEffect(() => {
    return () => {
      sequence.current += 1;
    };
  }, [owner]);
  const load = useCallback(
    async (request: () => Promise<T>) => {
      if (!isCurrent()) return;
      const id = ++sequence.current;
      setState((previous) => ({
        owner,
        value: previous.owner === owner ? previous.value : null,
        status: "loading",
        error: null,
      }));
      try {
        const value = await request();
        if (id === sequence.current && isCurrent()) {
          setState({ owner, value, status: "success", error: null });
          return value;
        }
      } catch (reason) {
        if (id === sequence.current && isCurrent())
          setState((previous) => ({
            ...previous,
            status: "error",
            error: reason instanceof Error ? reason.message : String(reason),
          }));
      }
    },
    [owner, isCurrent],
  );
  const clear = useCallback(() => {
    if (!isCurrent()) return;
    sequence.current += 1;
    setState({ owner, value: null, status: "idle", error: null });
  }, [owner, isCurrent]);
  const assign = useCallback(
    (value: T) => {
      if (!isCurrent()) return;
      sequence.current += 1;
      setState({ owner, value, status: "success", error: null });
    },
    [owner, isCurrent],
  );
  const current =
    state.owner === owner ? state : { owner, value: null, status: "idle" as const, error: null };
  return { ...current, loading: current.status === "loading", load, clear, assign, isCurrent };
}
