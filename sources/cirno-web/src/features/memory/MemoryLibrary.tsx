import { Button } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { WebUIMutationTransport } from "@/lib/api";
import type { MemoryRecord } from "@/lib/contracts/memory";
import { createMemoryService, type MemoryService } from "./model/service";
import { useMemorySearch } from "./model/useMemorySearch";
import { DEFAULT_MEMORY_GRAPH_LIMIT } from "@/features/preferences/contracts";
import { usePreferences } from "@/hooks/usePreferences";
import { MemoryFilters } from "./ui/MemoryFilters";
import { MemoryIndexStatus } from "./ui/MemoryIndexStatus";
import { MemoryCloud } from "./ui/MemoryCloud";
import { MemoryResults } from "./ui/MemoryResults";
import { MemoryInspector } from "./ui/MemoryInspector";
import { MemoryGraphLimit } from "./ui/MemoryGraphLimit";
import "./memory.css";

const EMPTY_RECORDS: MemoryRecord[] = [];
export function MemoryLibrary({ client, graph = false, active = true }: { client: WebUIMutationTransport; graph?: boolean; active?: boolean }) {
  const { t } = useTranslation();
  const service = useMemo(() => createMemoryService(client), [client]);
  const graphLimit = usePreferences().memoryGraphLimit ?? DEFAULT_MEMORY_GRAPH_LIMIT;
  const search = useMemorySearch(service, graph, graphLimit);
  const result = search.snapshot?.result;
  const records = result?.memories ?? EMPTY_RECORDS;
  const [selection, setSelection] = useState<{ service: MemoryService; memory: MemoryRecord } | null>(null);
  return (
    <section className="memory-library">
      <header className="memory-library-heading">
        {graph ? <div><h1>{t("workspace.memory")}</h1><p className="memory-hint">{t("memoryGraph.description")}</p></div> : <h2>{t("features.memorySources")}</h2>}
        <div className="memory-library-actions">
        {graph && <MemoryGraphLimit value={graphLimit} />}
        <Button
          variant="ghost"
          size="sm"
          isIconOnly
          aria-label={t("features.refresh")}
          isDisabled={search.loading}
          onPress={() => {
            void search.refresh();
          }}
        >
          <RefreshCw size={17} />
        </Button>
        </div>
      </header>
      <MemoryFilters service={service} search={search} compact={graph} />
      <div className={graph ? "memory-explorer" : undefined}>
        {graph && <MemoryCloud records={records} links={result?.links} active={active} loading={!result && !search.error}
          onInspect={memory => setSelection({ service, memory })} onTag={tags => search.apply({ tags })} />}
        <div className="memory-explorer-results"><MemoryResults search={search} onInspect={(memory) => setSelection({ service, memory })} />
          {graph && records.length >= graphLimit && <p className="memory-hint">{t("memoryGraph.limit", { count: graphLimit })}</p>}
          {graph && result?.links_truncated && <p className="memory-hint">{t("memoryGraph.linksLimit")}</p>}
        </div>
      </div>
      {!graph && <MemoryIndexStatus service={service} />}
      {selection?.service === service && (
        <MemoryInspector
          key={`${selection.memory.id}:${selection.memory.revision}`}
          service={service}
          memory={selection.memory}
          onClose={() => setSelection(null)}
        />
      )}
    </section>
  );
}
