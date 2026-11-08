import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRequest } from "@/ui/resources/useRequest";
import type { SkillsSearchPayload, SkillsTrendingPayload, SkillsTrendsPayload } from "@/lib/contracts/skills";
import type { SkillService } from "./service";
interface SearchSnapshot {
  query: string;
  payload: SkillsSearchPayload;
}
export function useMarketplaceSearch(service: SkillService) {
  const [draft, setDraft] = useState({ service, query: "" });
  const query = draft.service === service ? draft.query : "",
    normalized = query.trim();
  const owner = useMemo(() => ({ service, query: normalized }), [service, normalized]);
  const search = useRequest<SearchSnapshot>(owner);
  const popular = useRequest<SkillsTrendingPayload>(service);
  const [previous, setPrevious] = useState<{ service: SkillService; snapshot: SearchSnapshot } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const { load: loadPopular } = popular,
    { load } = search;
  const searchNow = useCallback(() => {
    window.clearTimeout(timer.current);
    return load(async () => ({ query: normalized, payload: await service.search(normalized) }));
  }, [load, service, normalized]);
  useEffect(() => {
    void loadPopular(service.popular);
  }, [service, loadPopular]);
  useEffect(() => {
    if (normalized.length < 2) return;
    timer.current = window.setTimeout(() => {
      void searchNow();
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [normalized, searchNow]);
  useEffect(() => {
    if (search.value) setPrevious({ service, snapshot: search.value });
  }, [search.value, service]);
  const snapshot = search.value ?? (previous?.service === service ? previous.snapshot : null);
  return {
    query,
    change: (query: string) => setDraft({ service, query }),
    searching: normalized.length >= 2,
    snapshot,
    popular,
    loading: normalized.length >= 2 && (search.status === "idle" || search.loading),
    error: search.error,
    retrySearch: searchNow,
    retryPopular: () => loadPopular(service.popular),
  };
}
export function useMarketplaceTrends(service: SkillService, ids: string[]) {
  const key = [...new Set(ids)].sort().join("\n");
  const owner = useMemo(() => ({ service, ids: key ? key.split("\n") : [] }), [service, key]);
  const resource = useRequest<SkillsTrendsPayload>(owner),
    { load } = resource;
  const refresh = useCallback(() => load(() => service.trends(owner.ids)), [load, owner, service]);
  useEffect(() => {
    if (owner.ids.length) void refresh();
  }, [owner, refresh]);
  return { ...resource, refresh };
}
