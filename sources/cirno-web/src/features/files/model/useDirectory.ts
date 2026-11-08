import { useEffect, useMemo, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { fileRequest } from "../api";

export type FileEntry = { name: string; path: string; kind: "file" | "directory" };
export type Directory = { path: string; project_path: string; parent: string | null; entries: FileEntry[]; truncated: boolean };

/** Listing lifetime belongs to the directory, independently of document tabs. */
export function useDirectory(client: CirnoClient, sessionKey: string | null, scope?: WorkspaceScopePayload | null) {
  const [path, setPath] = useState(scope?.project_path ?? "");
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [query, setQuery] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const request = useMemo(() => fileRequest(client, sessionKey, scope), [client, sessionKey, scope]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void request<Directory>("list", { path, query, show_hidden: showHidden })
        .then(value => { if (!cancelled) { setDirectory(value); setError(""); } })
        .catch(reason => { if (!cancelled) setError(String(reason instanceof Error ? reason.message : reason)); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, query ? 200 : 0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [path, query, showHidden, generation, request]);
  const navigate = (next: string) => { setPath(next); setQuery(""); };
  const refresh = () => setGeneration(value => value + 1);
  const create = async (kind: FileEntry["kind"], name: string) => {
    if (!directory) throw new Error("Open a directory before creating a file");
    const entry = await request<FileEntry>("create", { path: `${directory.path}/${name}`, kind });
    refresh();
    return entry;
  };
  return { directory, path, query, setQuery, showHidden, setShowHidden, loading, error, navigate, refresh, create };
}
export type DirectoryModel = ReturnType<typeof useDirectory>;
