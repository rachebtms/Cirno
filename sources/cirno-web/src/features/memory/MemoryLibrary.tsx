import { Button } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { WebUIMutationTransport } from "@/lib/api";
import type { MemoryRecord } from "@/lib/contracts/memory";
import { createMemoryService, type MemoryService } from "./model/service";
import { useMemorySearch } from "./model/useMemorySearch";
import { useMemoryStatus } from "./model/useMemoryStatus";
import { useMemoryMaintenance } from "./model/useMemoryMaintenance";
import { MemoryFilters } from "./ui/MemoryFilters";
import { MemoryStats } from "./ui/MemoryStats";
import { MemoryResults } from "./ui/MemoryResults";
import { MemoryInspector } from "./ui/MemoryInspector";
import "./memory.css";

export function MemoryLibrary({ client }: { client: WebUIMutationTransport }) {
  const { t } = useTranslation();
  const service = useMemo(() => createMemoryService(client), [client]);
  const search = useMemorySearch(service),
    stats = useMemoryStatus(service);
  const maintenance = useMemoryMaintenance(service, stats.refresh);
  const [selection, setSelection] = useState<{ service: MemoryService; memory: MemoryRecord } | null>(null);
  return (
    <section className="memory-library">
      <header className="memory-library-heading">
        <h2>{t("features.memorySources")}</h2>
        <Button
          variant="ghost"
          size="sm"
          isIconOnly
          aria-label={t("features.refresh")}
          isDisabled={search.loading || stats.loading}
          onPress={() => {
            void search.refresh();
            void stats.refresh();
          }}
        >
          <RefreshCw size={17} />
        </Button>
      </header>
      <MemoryFilters service={service} search={search} />
      <MemoryResults search={search} onInspect={(memory) => setSelection({ service, memory })} />
      <MemoryStats data={stats.data} error={stats.error} maintenance={maintenance} />
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
