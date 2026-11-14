import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { UIMessage } from "@/lib/contracts/messages";

interface DeferredActivityDetails {
  messages: UIMessage[];
  scope: string | null;
  expanded: boolean;
  load?: (refs: string[]) => void | Promise<void>;
}

interface DetailScope {
  scope: string | null;
  attempted: Set<string>;
  pending: Set<string>;
}

interface FailedDetails {
  owner: DetailScope;
  refs: Set<string>;
}

/** Immutable trace references are fetched once per scope; failures need an explicit retry. */
export function useDeferredActivityDetails({ messages, scope, expanded, load }: DeferredActivityDetails) {
  const encodedRefs = JSON.stringify(Array.from(new Set(messages.flatMap((message) =>
    message.traceDetail?.ref ? [message.traceDetail.ref] : [],
  ))));
  const refs = useMemo(() => JSON.parse(encodedRefs) as string[], [encodedRefs]);
  const scopeRef = useRef<DetailScope>({ scope, attempted: new Set(), pending: new Set() });
  if (scopeRef.current.scope !== scope) {
    scopeRef.current = { scope, attempted: new Set(), pending: new Set() };
  }
  const owner = scopeRef.current;
  const mounted = useRef(true);
  const [failure, setFailure] = useState<FailedDetails | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const request = useCallback(async (selected: string[]) => {
    const wanted = selected.filter(ref => !owner.pending.has(ref));
    if (!load || !wanted.length || scopeRef.current !== owner) return;
    for (const ref of wanted) {
      owner.attempted.add(ref);
      owner.pending.add(ref);
    }
    const requested = new Set(wanted);
    setFailure(current => {
      if (current?.owner !== owner) return current;
      const remaining = new Set([...current.refs].filter(ref => !requested.has(ref)));
      return remaining.size ? { owner, refs: remaining } : null;
    });
    try {
      await load(wanted);
    } catch {
      if (mounted.current && scopeRef.current === owner) {
        setFailure(current => ({ owner, refs: new Set([
          ...(current?.owner === owner ? current.refs : []), ...wanted,
        ]) }));
      }
    } finally {
      for (const ref of wanted) owner.pending.delete(ref);
    }
  }, [load, owner]);

  const retry = useCallback(() => request(refs), [refs, request]);

  useEffect(() => {
    if (expanded) void request(refs.filter(ref => !owner.attempted.has(ref)));
  }, [expanded, owner, refs, request]);

  return { failed: failure?.owner === owner && refs.some(ref => failure.refs.has(ref)), retry };
}
