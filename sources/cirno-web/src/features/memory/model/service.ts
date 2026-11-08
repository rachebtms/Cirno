import type { WebUIMutationTransport } from "@/lib/api";
import type {
  EvidenceReference,
  EvidencePage,
  MemoryDocument,
  MemoryQuery,
  MemoryRecord,
  MemorySearchResult,
  MemoryStatus,
} from "@/lib/contracts/memory";
export const EMPTY_MEMORY_QUERY: MemoryQuery = {
  query: "",
  tags: "",
  mode: "bm25",
  layer: "all",
  scope: "all",
  since: "",
  until: "",
  timeField: "observed_at",
  includeHistory: false,
};
export function createMemoryService(client: WebUIMutationTransport) {
  const call = <T>(action: string, values?: Record<string, unknown>) =>
    client.requestMutation<T>("instance.action", { action, ...(values ? { values } : {}) });
  return {
    list: (query: MemoryQuery, offset = 0) =>
      call<MemorySearchResult>("memory.list", {
        query: query.query,
        mode: query.mode,
        layer: query.layer,
        scope: query.scope,
        tags: [
          ...new Set(
            query.tags
              .split(/[,，]/)
              .map((tag) => tag.trim())
              .filter(Boolean),
          ),
        ],
        since: query.since || undefined,
        until: query.until || undefined,
        time_field: query.timeField,
        include_history: query.includeHistory,
        limit: 10,
        offset,
      }),
    status: () => call<MemoryStatus>("memory.status"),
    tags: () => call<{ tags: { name: string; count: number }[] }>("memory.tags", { limit: 30 }),
    read: (id: string, revision: number) => call<MemoryDocument>("memory.read", { id, revision }),
    history: (id: string) => call<{ revisions: MemoryRecord[] }>("memory.history", { id }),
    source: (cursor: EvidenceReference) => call<EvidencePage>("memory.source", { ...cursor }),
    reindex: () => call<{ scanned: number; has_more: boolean }>("memory.reindex"),
    retry: () => call<{ retried: number }>("memory.retry"),
  };
}
export type MemoryService = ReturnType<typeof createMemoryService>;
