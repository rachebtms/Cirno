import { useCallback, useEffect, useMemo, useRef } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { ProjectSummary } from "@/lib/contracts/conversations";
import { useRequest } from "@/ui/resources/useRequest";
import { useMutation } from "@/ui/resources/useMutation";
import { projectService, type ProjectDraft } from "./service";

export function useProjects(client: CirnoClient, refreshSessions: () => Promise<void>) {
  const service = useMemo(() => projectService(client), [client]);
  const records = useRequest<ProjectSummary[]>(service);
  const assignment = useMutation(service);
  const pending = useRef<{ service: typeof service; key: string; id: string | null } | null>(null);
  const { load, isCurrent } = records;
  const refresh = useCallback(() => load(service.list), [load, service]);
  useEffect(() => client.onStatus(status => { if (status === "open") void refresh(); }), [client, refresh]);
  useEffect(() => client.onSessionUpdate((_chatId, scope) => {
    if (scope === "projects" && isCurrent()) {
      void refresh();
    }
  }), [client, refresh, isCurrent]);

  // Writes reject to the editor; their failed drafts remain open for retry.
  const save = async (draft: ProjectDraft) => {
    if (!isCurrent()) return;
    await service.save(draft);
    if (isCurrent()) await refresh();
  };
  const remove = async (id: string) => {
    if (!isCurrent()) return;
    await service.remove(id);
    if (!isCurrent()) return;
    await Promise.all([refresh(), refreshSessions()]);
  };
  const assign = (key: string, id: string | null) => assignment.run(async () => {
    pending.current = { service, key, id };
    await service.assign(key, id);
    if (isCurrent()) await refreshSessions();
  }, () => { pending.current = null; });
  const retry = () => {
    if (records.error) void refresh();
    else if (pending.current?.service === service) void assign(pending.current.key, pending.current.id);
  };
  return {
    projects: records.value ?? [],
    loading: records.loading,
    error: records.error ?? assignment.error,
    assigning: assignment.busy,
    refresh, retry, save, remove, assign,
  };
}
