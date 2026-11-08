import { useCallback, useEffect } from "react";
import type { MemoryStatus } from "@/lib/contracts/memory";
import { useRequest } from "@/ui/resources/useRequest";
import type { MemoryService } from "./service";

export function useMemoryStatus(service: MemoryService) {
  const state = useRequest<MemoryStatus>(service);
  const { load } = state;
  const refresh = useCallback(() => load(() => service.status()), [service, load]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return { data: state.value, error: state.error, loading: state.loading, refresh };
}
