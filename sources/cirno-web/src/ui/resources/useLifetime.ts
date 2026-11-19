import { useResourceScope } from "./useResourceScope";

/** A callback belongs to this committed owner, including before passive cleanup. */
export function useLifetime(owner: unknown) {
  return useResourceScope(owner).isCurrent;
}
