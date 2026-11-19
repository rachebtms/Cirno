import { useEffect, useMemo, type SetStateAction } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { fileRequest } from "../api";
import { useResourceScope } from "@/ui/resources/useResourceScope";
import { useScopedState } from "@/ui/resources/useScopedState";

export type FileEntry = { name: string; path: string; kind: "file" | "directory" };
export type Directory = { path: string; project_path: string; parent: string | null; entries: FileEntry[]; truncated: boolean };

/** Listing lifetime belongs to the directory, independently of document tabs. */
export function useDirectory(client: CirnoClient, sessionKey: string | null, scope?: WorkspaceScopePayload | null) {
  const project = scope?.project_path, access = scope?.access_mode;
  const request = useMemo(() => fileRequest(client, sessionKey,
    project !== undefined && access !== undefined ? { project_path: project, access_mode: access } : null,
  ), [client, sessionKey, project, access]);
  const resource = useResourceScope(request);
  const [view, setView] = useScopedState(resource, () => ({
    path: project ?? "", directory: null as Directory | null,
    query: "", showHidden: false, generation: 0, loading: true, error: "",
  }));
  const { path, directory, query, showHidden, generation, loading, error } = view;
  useEffect(() => {
    let cancelled = false;
    setView(current => current.loading ? current : { ...current, loading: true });
    const timer = window.setTimeout(() => {
      void request<Directory>("list", { path, query, show_hidden: showHidden })
        .then(value => {
          if (!cancelled) setView(current => ({ ...current, directory: value, error: "" }));
        })
        .catch(reason => {
          if (!cancelled) setView(current => ({
            ...current, error: reason instanceof Error ? reason.message : String(reason),
          }));
        })
        .finally(() => {
          if (!cancelled) setView(current => ({ ...current, loading: false }));
        });
    }, query ? 200 : 0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [path, query, showHidden, generation, request, setView]);
  const setQuery = (value: SetStateAction<string>) => setView(current => ({
    ...current, query: typeof value === "function" ? value(current.query) : value,
  }));
  const setShowHidden = (value: SetStateAction<boolean>) => setView(current => ({
    ...current, showHidden: typeof value === "function" ? value(current.showHidden) : value,
  }));
  const navigate = (next: string) => setView(current => ({ ...current, path: next, query: "" }));
  const refresh = () => setView(current => ({ ...current, generation: current.generation + 1 }));
  const create = async (kind: FileEntry["kind"], name: string) => {
    if (!resource.isCurrent() || !directory) throw new Error("Open a directory before creating a file");
    const entry = await request<FileEntry>("create", { path: `${directory.path}/${name}`, kind });
    refresh();
    return entry;
  };
  return { owner: request, directory, path, query, setQuery, showHidden, setShowHidden, loading, error, navigate, refresh, create };
}
export type DirectoryModel = ReturnType<typeof useDirectory>;
