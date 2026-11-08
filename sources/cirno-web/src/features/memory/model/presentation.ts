import type { MemoryRecord } from "@/lib/contracts/memory";

export function memoryTitle(
  memory: MemoryRecord,
  t: (key: string, values?: Record<string, unknown>) => string,
): string {
  return memory.layer === "source"
    ? `${t("memoryLibrary.archivedEvidenceTitle")} · ${new Date(memory.updated_at).toLocaleString()} · ${memory.id.slice(-6)}`
    : memory.title === "Task checkpoint"
      ? t("memoryLibrary.taskCheckpoint")
      : memory.title;
}
