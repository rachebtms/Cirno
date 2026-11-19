import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRequest } from "@/ui/resources/useRequest";
import { useLifetime } from "@/ui/resources/useLifetime";
import type { SkillsSearchPayload, SkillsTrendingPayload, SkillsTrendsPayload } from "@/lib/contracts/skills";
import type { SkillService } from "./service";
interface SearchSnapshot {
  query: string;
  payload: SkillsSearchPayload;
}
export function useMarketplaceSearch(service: SkillService) {
  const isCurrent = useLifetime(service);
  const [draft, setDraft] = useState({ lifetime: isCurrent, query: "" });
  const query = draft.lifetime === isCurrent ? draft.query : "",
    normalized = query.trim();
  const owner = useMemo(() => ({ service, query: normalized }), [service, normalized]);
  const search = useRequest<SearchSnapshot>(owner);
  const popular = useRequest<SkillsTrendingPayload>(service);
  const [previous, setPrevious] = useState<{ lifetime: typeof isCurrent; snapshot: SearchSnapshot } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const { load: loadPopular } = popular,
    { load, isCurrent: isSearchCurrent } = search;
  const searchNow = useCallback(() => {
    if (!isSearchCurrent()) return;
    window.clearTimeout(timer.current);
    return load(async () => ({ query: normalized, payload: await service.search(normalized) }));
  }, [isSearchCurrent, load, service, normalized]);
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
    if (search.value) setPrevious({ lifetime: isCurrent, snapshot: search.value });
  }, [search.value, isCurrent]);
  const snapshot = search.value ?? (previous?.lifetime === isCurrent ? previous.snapshot : null);
  return {
    query,
    change: (query: string) => {
      if (isCurrent()) setDraft({ lifetime: isCurrent, query });
    },
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
