import { useCallback, useRef } from "react";
import { useResourceScope } from "./useResourceScope";
import { useScopedState } from "./useScopedState";

type RequestStatus = "idle" | "loading" | "success" | "error";
interface RequestState<T> {
  value: T | null;
  status: RequestStatus;
  error: string | null;
}
/** Latest read wins; replacing an owner immediately hides its previous data. */
export function useRequest<T>(owner: unknown) {
  const sequence = useRef(0);
  const scope = useResourceScope(owner);
  const { isCurrent } = scope;
  const [state, setState] = useScopedState<RequestState<T>>(scope, () => ({
    value: null,
    status: "idle",
    error: null,
  }));
  const load = useCallback(
    async (request: () => Promise<T>) => {
      if (!isCurrent()) return;
      const id = ++sequence.current;
      setState((previous) => ({
        value: previous.value,
        status: "loading",
        error: null,
      }));
      try {
        const value = await request();
        if (id === sequence.current && isCurrent()) {
          setState({ value, status: "success", error: null });
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
    [isCurrent, setState],
  );
  const clear = useCallback(() => {
    if (!isCurrent()) return;
    sequence.current += 1;
    setState({ value: null, status: "idle", error: null });
  }, [isCurrent, setState]);
  const assign = useCallback(
    (value: T) => {
      if (!isCurrent()) return;
      sequence.current += 1;
      setState({ value, status: "success", error: null });
    },
    [isCurrent, setState],
  );
  return { owner, ...state, loading: state.status === "loading", load, clear, assign, isCurrent };
}
