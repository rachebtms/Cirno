import { fetchWorkspaces } from "@/lib/api";
import type { WorkspacesPayload } from "@/lib/contracts/workspaces";
import { useCallback, useEffect, useRef, useState } from "react";

/** Keep the last usable directory catalog while the latest refresh settles. */
export function useWorkspaceDirectoryCatalog(
  getToken: () => string,
  onLoad: (payload: WorkspacesPayload) => void,
) {
  const generation = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );

  const refresh = useCallback(async () => {
    const request = ++generation.current;
    setPending(true);
    try {
      const payload = await fetchWorkspaces(getToken());
      if (request !== generation.current) return;
      onLoad(payload);
      setError(null);
    } catch (reason) {
      if (request === generation.current) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (request === generation.current) setPending(false);
    }
  }, [getToken, onLoad]);

  return { refresh, error, pending };
}
