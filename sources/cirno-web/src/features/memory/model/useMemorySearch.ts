import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { MemoryQuery, MemorySearchResult } from "@/lib/contracts/memory";
import { useRequest } from "@/ui/resources/useRequest";
import { EMPTY_MEMORY_QUERY, type MemoryService } from "./service";
import { DEFAULT_MEMORY_GRAPH_LIMIT } from "@/features/preferences/contracts";

interface SearchSnapshot {
  query: MemoryQuery;
  result: MemorySearchResult;
}
function constrain(result: MemorySearchResult, maxNodes?: number): MemorySearchResult {
  return maxNodes === undefined ? result : { ...result, has_more: result.has_more && result.memories.length < maxNodes };
}
export function useMemorySearch(service: MemoryService, graph = false, graphLimit = DEFAULT_MEMORY_GRAPH_LIMIT) {
  const { t } = useTranslation();
  const resource = useRequest<SearchSnapshot>(service);
  const { load } = resource;
  const pagination = useRef<{ service: MemoryService; all: boolean } | null>(null);
  const [paging, setPaging] = useState<typeof pagination.current>(null);
  const limit = useRef(graphLimit);
  const previousLimit = useRef(graphLimit);
  limit.current = graphLimit;
  const appliedQuery = useRef(EMPTY_MEMORY_QUERY);
  const [draftState, setDraft] = useState({ service, value: { ...EMPTY_MEMORY_QUERY } });
  const draft = draftState.service === service ? draftState.value : EMPTY_MEMORY_QUERY;
  const search = useCallback(
    (query: MemoryQuery) => {
      pagination.current = null;
      setPaging(null);
      appliedQuery.current = query;
      return load(async () => {
        const maxNodes = graph ? limit.current : undefined;
        const result = await (graph ? service.graph(query, 0, [], maxNodes) : service.list(query));
        return { query: { ...query }, result: constrain(result, maxNodes) };
      });
    },
    [service, graph, load],
  );
  useEffect(() => {
    setDraft({ service, value: { ...EMPTY_MEMORY_QUERY } });
    void search(EMPTY_MEMORY_QUERY);
    return () => {
      if (pagination.current?.service === service) pagination.current = null;
    };
  }, [service, search]);
  useEffect(() => {
    if (previousLimit.current === graphLimit) return;
    previousLimit.current = graphLimit;
    if (graph) void search(appliedQuery.current);
  }, [graphLimit, graph, search]);
  const change = (patch: Partial<MemoryQuery>) => setDraft({ service, value: { ...draft, ...patch } });
  const apply = (patch: Partial<MemoryQuery>) => {
    const query = { ...draft, ...patch };
    setDraft({ service, value: query });
    void search(query);
  };
  const canContinue = (snapshot: SearchSnapshot) => snapshot.result.has_more
    && (!graph || snapshot.result.memories.length < limit.current);
  const append = async (previous: SearchSnapshot): Promise<SearchSnapshot> => {
    const page = await (graph
      ? service.graph(previous.query, previous.result.next_offset, previous.result.memories.map(row => row.id), limit.current)
      : service.list(previous.query, previous.result.next_offset));
    if (page.has_more && !(page.next_offset > previous.result.next_offset)) {
      throw new Error(t("memoryLibrary.paginationError"));
    }
    const records = new Map(previous.result.memories.map((record) => [record.id, record]));
    for (const record of page.memories) records.set(record.id, record);
    const memories = [...records.values()];
    return { query: previous.query, result: constrain({ ...page, memories }, graph ? limit.current : undefined) };
  };
  const paginate = async (all: boolean) => {
    let snapshot = resource.value;
    if (!snapshot || !canContinue(snapshot) || resource.loading || pagination.current || !resource.isCurrent()) return;
    const operation = { service, all };
    pagination.current = operation;
    setPaging(operation);
    try {
      do {
        const previous = snapshot;
        const next = await load(() => append(previous));
        if (!next || pagination.current !== operation || !resource.isCurrent()) return;
        snapshot = next;
      } while (all && canContinue(snapshot));
    } finally {
      if (pagination.current === operation) {
        pagination.current = null;
        if (resource.isCurrent()) setPaging(null);
      }
    }
  };
  return {
    draft,
    change,
    apply,
    submit: () => search(draft),
    more: () => paginate(false),
    loadAll: () => paginate(true),
    loadingAll: paging?.service === service && paging.all,
    refresh: () => search(resource.value?.query ?? draft),
    snapshot: resource.value,
    loading: resource.loading,
    error: resource.error,
    status: resource.status,
  };
}
