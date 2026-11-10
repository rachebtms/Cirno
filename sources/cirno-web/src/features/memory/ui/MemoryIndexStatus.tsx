import type { MemoryService } from "../model/service";
import { useMemoryStatus } from "../model/useMemoryStatus";
import { useMemoryMaintenance } from "../model/useMemoryMaintenance";
import { MemoryStats } from "./MemoryStats";

export function MemoryIndexStatus({ service }: { service: MemoryService }) {
  const stats = useMemoryStatus(service);
  const maintenance = useMemoryMaintenance(service, stats.refresh);
  return <MemoryStats data={stats.data} error={stats.error} maintenance={maintenance}
    refreshing={stats.loading} onRefresh={() => { void stats.refresh(); }} />;
}
