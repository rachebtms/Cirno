import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { UIMessage } from "@/lib/contracts/messages";

interface DeferredActivityDetails {
  messages: UIMessage[];
  scope: string | null;
  expanded: boolean;
  load?: (refs: string[]) => void | Promise<void>;
}

/** Immutable trace references are fetched once per scope; failures need an explicit retry. */
export function useDeferredActivityDetails({ messages, scope, expanded, load }: DeferredActivityDetails) {
  const encodedRefs = JSON.stringify(Array.from(new Set(messages.flatMap((message) =>
    message.traceDetail?.ref ? [message.traceDetail.ref] : [],
  ))));
  const refs = useMemo(() => JSON.parse(encodedRefs) as string[], [encodedRefs]);
  const key = JSON.stringify([scope, refs]);
  const currentKey = useRef(key);
  currentKey.current = key;
  const attempted = useRef<string | null>(null);
  const pending = useRef(new Set<string>());
  const mounted = useRef(true);
  const [failedKey, setFailedKey] = useState<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const retry = useCallback(async () => {
    if (!load || !refs.length || pending.current.has(key)) return;
    attempted.current = key;
    pending.current.add(key);
    setFailedKey(null);
    try {
      await load(refs);
    } catch {
      if (mounted.current && currentKey.current === key) setFailedKey(key);
    } finally {
      pending.current.delete(key);
    }
  }, [key, load, refs]);

  useEffect(() => {
    if (expanded && attempted.current !== key) void retry();
  }, [expanded, key, retry]);

  return { failed: failedKey === key, retry };
}
