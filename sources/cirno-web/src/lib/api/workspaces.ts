/** Workspaces operations for the versioned Cirno API. */

import type {
  WorkspaceDirectoriesPayload,
  WorkspacesPayload,
} from "@/lib/contracts/workspaces";
import { API_READ_TIMEOUT_MS, request } from "./transport";

export async function fetchWorkspaces(
  token: string,
  base: string = "",
): Promise<WorkspacesPayload> {
  return request<WorkspacesPayload>(
    `${base}/v0/workspaces`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchWorkspaceDirectories(
  token: string,
  path: string,
  query: string,
  showHidden: boolean,
  allowPartial = false,
): Promise<WorkspaceDirectoriesPayload> {
  const params = new URLSearchParams({
    path,
    q: query,
    hidden: showHidden ? "1" : "0",
    partial: allowPartial ? "1" : "0",
  });
  return request<WorkspaceDirectoriesPayload>(
    `/v0/workspaces/directories?${params}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}
