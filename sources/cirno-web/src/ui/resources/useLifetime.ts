import { useCallback, useEffect, useRef } from "react";

const INACTIVE = Symbol("inactive resource owner");

/** A callback belongs to this mounted owner, including before effect cleanup. */
export function useLifetime(owner: unknown) {
  const current = useRef(owner);
  current.current = owner;
  useEffect(() => {
    current.current = owner;
    return () => {
      if (current.current === owner) current.current = INACTIVE;
    };
  }, [owner]);
  return useCallback(() => current.current === owner, [owner]);
}
