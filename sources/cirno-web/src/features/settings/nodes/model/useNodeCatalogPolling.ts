import { useEffect } from "react";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { useThreadVisibility } from "@/hooks/useThreadVisibility";

/** Read the local catalog while visible. Only the backend monitor contacts SSH. */
export function useNodeCatalogPolling(refresh: (quiet?: boolean) => Promise<void>) {
  const pageVisible = usePageVisibility(), tabVisible = useThreadVisibility();
  useEffect(() => {
    if (!pageVisible || !tabVisible) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      await refresh(true);
      if (!stopped) timer = setTimeout(() => { void poll(); }, 5000);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [pageVisible, tabVisible, refresh]);
}
