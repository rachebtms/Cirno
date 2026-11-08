import { useEffect, useRef, useState } from "react";

interface InstalledSettingItemsOptions<Payload, Item> {
  requestCount: number;
  getToken: () => string;
  eventName: string;
  fetchPayload: (token: string) => Promise<Payload>;
  isPayload: (value: unknown) => value is Payload;
  selectItems: (payload: Payload) => Item[];
}

export function useInstalledSettingItems<Payload, Item>({
  requestCount,
  getToken,
  eventName,
  fetchPayload,
  isPayload,
  selectItems,
}: InstalledSettingItemsOptions<Payload, Item>) {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const failedRef = useRef(false);
  const revisionRef = useRef(0);
  const loadedRef = useRef(false);
  const pendingRef = useRef<{ promise: Promise<Payload>; revision: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let refreshQueued = false;
    let refreshAfterFlight = false;
    let refreshing = false;
    const refresh = async (): Promise<void> => {
      if (refreshing) return;
      refreshing = true;
      const pending = pendingRef.current ?? { promise: fetchPayload(getToken()), revision: revisionRef.current };
      pendingRef.current = pending;
      try {
        const payload = await pending.promise;
        if (!cancelled && pending.revision === revisionRef.current) {
          loadedRef.current = true;
          setItems(selectItems(payload));
          setError("");
          failedRef.current = false;
        }
      } catch (reason) {
        if (!cancelled && pending.revision === revisionRef.current) {
          failedRef.current = true;
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      } finally {
        if (pendingRef.current === pending) pendingRef.current = null;
        refreshing = false;
        if (refreshAfterFlight && !cancelled) {
          refreshAfterFlight = false;
          void refresh();
        }
      }
    };
    const queueRefresh = () => {
      if (!requestCount || document.visibilityState === "hidden" || refreshQueued) return;
      refreshQueued = true;
      queueMicrotask(() => {
        refreshQueued = false;
        if (!cancelled) void refresh();
      });
    };
    if (requestCount && (!loadedRef.current || failedRef.current)) void refresh();

    const refreshOnChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isPayload(payload)) {
        revisionRef.current += 1;
        failedRef.current = false;
        setError("");
        loadedRef.current = true;
        setItems(selectItems(payload));
        return;
      }
      if (refreshing) {
        refreshAfterFlight = true;
        return;
      }
      queueRefresh();
    };

    window.addEventListener(eventName, refreshOnChanged);
    return () => {
      cancelled = true;
      window.removeEventListener(eventName, refreshOnChanged);
    };
  }, [requestCount, eventName, fetchPayload, getToken, isPayload, selectItems]);

  return { items, error };
}
