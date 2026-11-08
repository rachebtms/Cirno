import { useCallback, useEffect, useRef, useState } from "react";
import { useRequest } from "@/ui/resources/useRequest";
import type { EvidencePage, EvidenceReference, MemoryDocument, MemoryRecord } from "@/lib/contracts/memory";
import { nextEvidenceCursor } from "./evidence-cursor";
import type { MemoryService } from "./service";

export function useMemoryInspector(service: MemoryService, memory: MemoryRecord) {
  const record = useRequest<MemoryDocument>(service);
  const versions = useRequest<{ revisions: MemoryRecord[] }>(service);
  const source = useRequest<EvidencePage>(service);
  const [view, setView] = useState("record");
  const [revision, setRevision] = useState(memory.revision);
  const sourceCursor = useRef<EvidenceReference>({ id: memory.id, revision: memory.revision });
  const { load: read, clear: clearRecord } = record,
    { clear: clearSource } = source;
  const openRevision = useCallback(
    (revision: number) => {
      clearRecord();
      clearSource();
      setView("record");
      setRevision(revision);
      sourceCursor.current = { id: memory.id, revision };
      return read(() => service.read(memory.id, revision));
    },
    [read, clearRecord, clearSource, service, memory.id],
  );
  useEffect(() => {
    void openRevision(memory.revision);
  }, [openRevision, memory.revision]);
  const readSource = (reference = sourceCursor.current) => {
    sourceCursor.current = reference;
    return source.load(() => service.source(reference));
  };
  const selectView = (next: string) => {
    setView(next);
    if (next === "versions" && versions.status === "idle")
      void versions.load(() => service.history(memory.id));
    if (next === "source" && source.status === "idle") void readSource();
  };
  return {
    record,
    versions,
    source,
    view,
    selectView,
    revision,
    openRevision,
    readSource,
    reload: () => read(() => service.read(memory.id, revision)),
    loadVersions: () => versions.load(() => service.history(memory.id)),
    more: () => {
      const next = source.value && nextEvidenceCursor(source.value);
      if (next) void readSource(next);
    },
  };
}
