import { useCallback, useMemo, useSyncExternalStore } from "react";
import type { PromptAnchor } from "@/components/thread/promptNavigation";
import { EMPTY_DIRECTORY, PromptDirectorySource } from "./source";

export interface PromptDirectoryView {
  scope?: object;
  total: number;
  ready: boolean;
  loading: boolean;
  error: string | null;
  loaded: PromptAnchor[];
  get: (position: number) => PromptAnchor | undefined;
  ensure: (start: number, end: number) => void;
  retry: () => void;
}

export function useDirectoryListing(source: PromptDirectorySource | null | undefined, query = ""): PromptDirectoryView {
  const subscribe = useCallback((listener: () => void) => source?.subscribe(listener) ?? (() => {}), [source]);
  const read = useCallback(() => source?.getSnapshot() ?? EMPTY_DIRECTORY, [source]);
  const snapshot = useSyncExternalStore(subscribe, read, read);
  const pages = useMemo(() => [...snapshot.pages.values()].filter((entry) => !query || entry.query === query), [snapshot, query]);
  const rows = useMemo(() => {
    const positions = new Map<number, PromptAnchor>();
    for (const { page } of pages) page.prompts.forEach((prompt, offset) => positions.set(query ? page.offset + offset : prompt.index, {
      ...prompt, label: prompt.preview.replace(/\s+/g, " ").slice(0, 80) || `Prompt ${prompt.index + 1}`,
    }));
    return positions;
  }, [pages, query]);
  const ensure = useCallback((start: number, end: number) => source?.ensure(query, start, end), [source, query]);
  const retry = useCallback(() => source?.retry(query), [source, query]);
  return useMemo(() => ({ scope: source ?? undefined, total: snapshot.totals.get(query) ?? 0,
    ready: snapshot.totals.has(query), loading: snapshot.loading.has(query),
    error: snapshot.failures.get(query)?.message ?? null,
    loaded: [...rows.entries()].sort(([a], [b]) => a - b).map(([, row]) => row),
    get: (index: number) => rows.get(index), ensure, retry,
  }), [source, snapshot, query, rows, ensure, retry]);
}
