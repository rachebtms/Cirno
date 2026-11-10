import { useCallback, useEffect, useState } from "react";
import type { MemoryQuery, MemorySearchResult } from "@/lib/contracts/memory";
import { useRequest } from "@/ui/resources/useRequest";
import { EMPTY_MEMORY_QUERY, type MemoryService } from "./service";

interface SearchSnapshot {
  query: MemoryQuery;
  result: MemorySearchResult;
}
export const MEMORY_GRAPH_LIMIT = 300;
export function useMemorySearch(service: MemoryService, graph = false) {
  const resource = useRequest<SearchSnapshot>(service);
  const { load } = resource;
  const [draftState, setDraft] = useState({ service, value: { ...EMPTY_MEMORY_QUERY } });
  const draft = draftState.service === service ? draftState.value : EMPTY_MEMORY_QUERY;
  const search = useCallback(
    (query: MemoryQuery) => load(async () => ({ query: { ...query }, result: await (graph ? service.graph(query) : service.list(query)) })),
    [service, graph, load],
  );
  useEffect(() => {
    setDraft({ service, value: { ...EMPTY_MEMORY_QUERY } });
    void search(EMPTY_MEMORY_QUERY);
  }, [service, search]);
  const change = (patch: Partial<MemoryQuery>) => setDraft({ service, value: { ...draft, ...patch } });
  const apply = (patch: Partial<MemoryQuery>) => {
    const query = { ...draft, ...patch };
    setDraft({ service, value: query });
    void search(query);
  };
  const more = async () => {
    const previous = resource.value;
    if (!previous?.result.has_more || resource.loading || (graph && previous.result.memories.length >= MEMORY_GRAPH_LIMIT)) return;
    await load(async () => {
      const page = await (graph
        ? service.graph(previous.query, previous.result.next_offset, previous.result.memories.map(row => row.id))
        : service.list(previous.query, previous.result.next_offset));
      const records = new Map(previous.result.memories.map((record) => [record.id, record]));
      for (const record of page.memories) records.set(record.id, record);
      const memories = [...records.values()];
      return { query: previous.query, result: { ...page, memories,
        has_more: page.has_more && (!graph || memories.length < MEMORY_GRAPH_LIMIT) } };
    });
  };
  return {
    draft,
    change,
    apply,
    submit: () => search(draft),
    more,
    refresh: () => search(resource.value?.query ?? draft),
    snapshot: resource.value,
    loading: resource.loading,
    error: resource.error,
    status: resource.status,
  };
}
